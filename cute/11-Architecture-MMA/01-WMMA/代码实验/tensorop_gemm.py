# Copyright (c) 2025 - 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.

# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.

# 3. Neither the name of the copyright holder nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# 中文注释版出处：
# https://github.com/NVIDIA/cutlass/blob/098de2a652cf8f00fd70b2df54051c7eccbb855a/examples/python/CuTeDSL/cute/ampere/kernel/dense_gemm/tensorop_gemm.py
# 逐行翻译注释和文档字符串，不删除或合并内容；计算代码保持英文原版结构。

import argparse
import math
from functools import lru_cache
from typing import Tuple, Type

import cuda.bindings.driver as cuda

import cutlass
import cutlass.cute as cute
from cutlass import testing
import cutlass.utils as utils
from cutlass.utils.tensor_helpers import create_cute_tensor_for_fp8
from cutlass.utils.tensor_helpers import is_fp8_dtype

"""
使用 CUTE DSL 的 NVIDIA Ampere 架构的密集 GEMM (C = A * B) 示例。
- 矩阵 A 为 MxKxL，L 为批量维度，A 可以是行优先（“K”）或列优先（“M”）
- 矩阵 B 为 NxKxL，L 为批次维度，B 可以是行优先（“N”）或列优先（“K”）
- 矩阵 C 为 MxNxL，L 为批量维度，C 可以是行优先（“N”）或列优先（“M”）

该GEMM内核支持以下功能：
    - 利用 Ampere 的张量核心进行矩阵乘法累加 (MMA) 运算
    - 线程块光栅化以提高数据重用
    - 支持多级流水线重叠计算和内存访问
    - 为epilogue实现共享内存缓冲，以增加合并的全局内存访问

这个GEMM的工作原理如下：
1. 使用异步副本将 A 和 B 矩阵从全局内存 (GMEM) 加载到共享内存 (SMEM)。
2. 执行矩阵乘加（MMA）运算。
3. 将结果从寄存器(RMEM)存储到共享内存(SMEM)，然后存储到全局内存(GMEM)。

使用的Ampere张量核心指令操作如下：
- 从SMEM读取矩阵A
- 从SMEM读取矩阵B
- 执行MMA运算并将结果存储到累加器（寄存器）中

要运行此示例：

.. code-block:: bash

    python examples/cute/ampere/kernel/dense_gemm/tensorop_gemm.py                                  \
      --mnkl 8192,8192,8192,1 --atom_layout_mnk 2,2,1                        \
      --ab_dtype Float16                                                     \
      --c_dtype Float16 --acc_dtype Float32                                  \
      --a_major m --b_major n --c_major n

上面的示例命令计算为 M=8192、N=8192、K=8192，
batch_count=1。Atom layout的形状是 2x2x1，输入 mma
累加器，输出数据类型设置为fp16、fp32和fp16，
依次对应。

要使用 NCU 分析器收集性能：

.. code-block:: bash

    ncu python examples/cute/ampere/kernel/dense_gemm/tensorop_gemm.py                              \
      --mnkl 8192,8192,8192,1 --atom_layout_mnk 2,2,1                        \
      --ab_dtype Float16                                                     \
      --c_dtype Float16 --acc_dtype Float32                                  \
      --a_major m --b_major n --c_major n                                    \
      --skip_ref_check --iterations 2

约束：
* 支持的输入数据类型：fp16/bf16/fp8
* 支持的输出数据类型：fp16
* 支持的累加器数据类型：f32/f16
* fp16/bf16 的默认图块形状为 128x128x32，fp8 的默认图块形状为 128x128x64
* Atom 布局的 MNK 形状被设置为使得tile形状可以被 MMA 划分
  指令形状
* A/B/C 张量的连续维度必须至少 16 字节对齐，
  即，元素数量是8的倍数
"""


class TensorOpGemm:
    _FP16_BF16_DTYPES = (cutlass.Float16, cutlass.BFloat16)
    _FP8_DTYPES = (cutlass.Float8E4M3FN, cutlass.Float8E5M2)
    _MMA_SHAPE_FP16_BF16 = (16, 8, 16)
    _MMA_SHAPE_FP8 = (16, 8, 32)
    _CTA_TILER_FP16_BF16 = (128, 128, 32)
    _CTA_TILER_FP8 = (128, 128, 64)

    def __init__(
        self,
        ab_dtype: Type[cutlass.Numeric],
        c_dtype: Type[cutlass.Numeric],
        acc_dtype: Type[cutlass.Numeric],
        atom_layout_mnk: Tuple[int, int, int],
        is_m_major_c: bool = False,
    ):
        self.ab_dtype = ab_dtype
        self.c_dtype = c_dtype
        self.acc_dtype = acc_dtype
        self.is_fp8 = self.ab_dtype in self._FP8_DTYPES
        assert self.ab_dtype in self._FP16_BF16_DTYPES + self._FP8_DTYPES, (
            "ab_dtype must be one of Float16, BFloat16, Float8E4M3FN, Float8E5M2"
        )
        self.cta_tiler = (
            self._CTA_TILER_FP8 if self.is_fp8 else self._CTA_TILER_FP16_BF16
        )
        self.num_stages = 4
        self.atom_layout_mnk = atom_layout_mnk
        atom_lay_M, atom_lay_N, atom_lay_K = self.atom_layout_mnk
        self.num_threads = atom_lay_M * atom_lay_N * atom_lay_K * 32

        self.bM, self.bN, self.bK = self.cta_tiler
        self.mma_inst_shape = (
            self._MMA_SHAPE_FP8 if self.is_fp8 else self._MMA_SHAPE_FP16_BF16
        )
        mmaM, mmaN, mmaK = self.mma_inst_shape

        # M major C 使用 C^T = B^T * A^T，交换Atom layout M/N 角色。
        if is_m_major_c:
            assert self.bM % (atom_lay_N * mmaM) == 0, (
                "bM must be divisible by MMA instruction"
            )
            assert self.bN % (atom_lay_M * mmaN) == 0, (
                "bN must be divisible by MMA instruction"
            )
        else:
            assert self.bM % (atom_lay_M * mmaM) == 0, (
                "bM must be divisible by MMA instruction"
            )
            assert self.bN % (atom_lay_N * mmaN) == 0, (
                "bN must be divisible by MMA instruction"
            )
        assert atom_lay_K == 1, "this example does not support atom layout K > 1"
        assert self.bK % mmaK == 0, "bK must be divisible by MMA instruction"
        assert self.num_stages >= 3, "num_stages must be greater than or equal to 3"

    @cute.jit
    def __call__(
        self,
        mA: cute.Tensor,
        mB: cute.Tensor,
        mC: cute.Tensor,
        stream: cuda.CUstream,
        epilogue_op: cutlass.Constexpr = lambda x: x,
    ):
        # 网格将问题的 M、N 和 L 维度除以
        # tile形状的相应模式（bM，bN，1）。 K 维数为
        # 通过多阶段过程在块内处理。

        # Ampere MMA 原子的累加器布局沿行写入 M
        # 方面。当 C 为列主调（M major）时，累加器执行以下操作：
        # 不自然地与 C 的连续维度对齐，因此存储
        # 结果需要非合并寄存器/SMEM 流量。为了避免
        # 我们可以计算 C^T = B^T * A^T 而不是 C = A * B：
        if cutlass.const_expr(
            utils.LayoutEnum.from_tensor(mC) == utils.LayoutEnum.COL_MAJOR
        ):
            mA, mB = mB, mA
            mC = cute.make_tensor(mC.iterator, cute.select(mC.layout, mode=[1, 0, 2]))
            atom_layout_mnk = (
                self.atom_layout_mnk[1],
                self.atom_layout_mnk[0],
                self.atom_layout_mnk[2],
            )
        else:
            atom_layout_mnk = self.atom_layout_mnk

        self.a_major_mode = utils.LayoutEnum.from_tensor(mA)
        self.b_major_mode = utils.LayoutEnum.from_tensor(mB)
        self.c_major_mode = utils.LayoutEnum.from_tensor(mC)

        # ///////////////////////////////////////////////////////////////////////////////
        # 共享内存布局：
        # ///////////////////////////////////////////////////////////////////////////////

        # 创建具有所提供图块所需尺寸的布局
        # size 和 num stage（stages 用于 K 维度）
        # 分为 64x8 或 8x32 布局原子。设置 swizzle 以便
        # 共享内存的原子 -> 寄存器拷贝未遇到
        # bank 冲突

        # 假设输入是16B对齐
        ab_copy_bits = 128
        sA_layout, sA_swizzle = self._make_smem_layout_AB(
            mA.element_type,
            self.a_major_mode,
            ab_copy_bits,
            (self.cta_tiler[0], self.cta_tiler[2], self.num_stages),
        )
        sB_layout, sB_swizzle = self._make_smem_layout_AB(
            mB.element_type,
            self.b_major_mode,
            ab_copy_bits,
            (self.cta_tiler[1], self.cta_tiler[2], self.num_stages),
        )

        # 创建类似的布局，但没有 num_stages 或布局原子
        sC_layout = self._make_smem_layout_C(
            mC.element_type,
            self.c_major_mode,
            ab_copy_bits,
            (self.cta_tiler[0], self.cta_tiler[1]),
        )

        # ///////////////////////////////////////////////////////////////////////////////
        # 平铺副本：
        # tA/tB/tC 的主数遵循 gA/gB/gC 的主数，
        # 启用对全局内存的合并访问以获得更快的数据
        # 全局内存和共享内存之间的传输。
        # ///////////////////////////////////////////////////////////////////////////////

        # 为全局到共享内存的异步拷贝创建拷贝原子
        atom_async_copy = cute.make_copy_atom(
            cute.nvgpu.cpasync.CopyG2SOp(cache_mode=cute.nvgpu.LoadCacheMode.GLOBAL),
            mA.element_type,
            num_bits_per_copy=ab_copy_bits,
        )

        # 从拷贝原子创建平铺副本的线程布局，其中
        # 线程布局简单地遵循张量的主维
        tiled_copy_A = self._make_gmem_tiled_copy_AB(
            atom_async_copy, mA.element_type, self.a_major_mode, ab_copy_bits
        )
        tiled_copy_B = self._make_gmem_tiled_copy_AB(
            atom_async_copy, mB.element_type, self.b_major_mode, ab_copy_bits
        )

        # 为epilogue创建同步拷贝原子和线程布局
        c_copy_bits = 128
        atom_sync_copy = cute.make_copy_atom(
            cute.nvgpu.CopyUniversalOp(),
            mC.element_type,
            num_bits_per_copy=c_copy_bits,
        )
        tiled_copy_C = self._make_gmem_tiled_copy_C(
            atom_sync_copy, mC.element_type, self.c_major_mode, c_copy_bits
        )

        # ///////////////////////////////////////////////////////////////////////////////
        # 分块 MMA
        # ///////////////////////////////////////////////////////////////////////////////

        if cutlass.const_expr(self.is_fp8):
            op = cute.nvgpu.warp.MmaFP8Op(
                self.ab_dtype, self.acc_dtype, self.mma_inst_shape
            )
        else:
            op = cute.nvgpu.warp.MmaF16BF16Op(
                self.ab_dtype, self.acc_dtype, self.mma_inst_shape
            )

        permutation_mnk = (
            atom_layout_mnk[0] * self.mma_inst_shape[0],
            # 如果Atom layout的 N 模式为 1，则利用最大的合并
            # 共享内存->寄存器拷贝，将tiled mma的N模式设置为16
            atom_layout_mnk[1] * self.mma_inst_shape[1] * 2,
            atom_layout_mnk[2] * self.mma_inst_shape[2],
        )

        # 创建了一个平铺 mma，根据指定的布局平铺原子。
        # 对于 2x2x1 Atom layout，mma 原子重复 4 次，两次
        # 跨越 M 并两次跨越 N
        tC = cute.make_layout(atom_layout_mnk)
        tiled_mma = cute.make_tiled_mma(
            op,
            tC,
            permutation_mnk=permutation_mnk,
        )

        # grid_dim: ((m + BLK_M - 1) // BLK_M, (n + BLK_N - 1) // BLK_N, l)
        grid_dim = cute.ceil_div(mC.shape, (self.bM, self.bN, 1))

        # 添加线程块光栅化以改善数据的重用
        raster_factor = 1
        grid_dim_n = cute.size(grid_dim[1])
        # 选择阈值，以免导致太多无操作 CTA
        if grid_dim_n > 5:
            raster_factor = 8
        elif grid_dim_n > 2:
            raster_factor = 4
        elif grid_dim_n > 1:
            raster_factor = 2
        rasterization_remap_grid_dim = (
            cute.size(grid_dim[0]) * raster_factor,
            (cute.size(grid_dim[1]) + raster_factor - 1) // raster_factor,
            cute.size(grid_dim[2]),
        )

        self.kernel(
            mA,
            mB,
            mC,
            sA_layout,
            sA_swizzle,
            sB_layout,
            sB_swizzle,
            sC_layout,
            tiled_copy_A,
            tiled_copy_B,
            tiled_copy_C,
            tiled_mma,
            raster_factor,
            epilogue_op,
        ).launch(
            grid=rasterization_remap_grid_dim,
            block=[self.num_threads, 1, 1],
            stream=stream,
        )

    @cute.kernel
    def kernel(
        self,
        mA: cute.Tensor,
        mB: cute.Tensor,
        mC: cute.Tensor,
        sA_layout: cute.Layout,
        sA_swizzle: cute.Swizzle,
        sB_layout: cute.Layout,
        sB_swizzle: cute.Swizzle,
        sC_layout: cute.ComposedLayout,
        tiled_copy_A: cute.TiledCopy,
        tiled_copy_B: cute.TiledCopy,
        tiled_copy_C: cute.TiledCopy,
        tiled_mma: cute.TiledMma,
        rasterization_factor: cutlass.Int32,
        epilogue_op: cutlass.Constexpr = lambda x: x,
    ):
        # 线程索引、块索引
        tidx, _, _ = cute.arch.thread_idx()
        bidx, bidy, bidz = cute.arch.block_idx()
        grid_dim = cute.ceil_div(mC.shape, (self.bM, self.bN, 1))
        offset_tile_x, offset_tile_y = self.raster_tile(
            bidx, bidy, rasterization_factor
        )
        # 如果 CTA 超出范围则提前退出
        if grid_dim[0] <= offset_tile_x or grid_dim[1] <= offset_tile_y:
            pass
        else:
            tiler_coord = (offset_tile_x, offset_tile_y, None)

            # ///////////////////////////////////////////////////////////////////////////////
            # 获取该线程块的适当图块。
            # gA: (BLK_M, BLK_N, k), gB: (BLK_N, BLK_K, k), gC: (BLK_M, BLK_N)
            # ///////////////////////////////////////////////////////////////////////////////
            gA = cute.local_tile(
                mA[None, None, bidz],
                tiler=self.cta_tiler,
                coord=tiler_coord,
                proj=(1, None, 1),
            )
            gB = cute.local_tile(
                mB[None, None, bidz],
                tiler=self.cta_tiler,
                coord=tiler_coord,
                proj=(None, 1, 1),
            )
            gC = cute.local_tile(
                mC[None, None, bidz],
                tiler=self.cta_tiler,
                coord=tiler_coord,
                proj=(1, 1, None),
            )

            # 默认情况下，如果张量k模式不分为tilek
            # 大小，那么 k 维中的最后一个tile是不规则的。
            # 相反，当 k 不规则时，使第一个图块不规则。
            # 这使得我们可以先处理不规则的tile，以避免
            # 在主循环中检查此条件。

            # residual_k 是负数，表示需要的金额
            # 将指针在 k 维上移动
            residual_k = cute.size(mA, mode=[1]) - cutlass.Int32(self.bK) * cute.size(
                gA, mode=[2]
            )

            # 将gA/gB的指针向`-k`方向移动
            gA = cute.domain_offset((0, residual_k, 0), gA)
            gB = cute.domain_offset((0, residual_k, 0), gB)
            # 输入是16B对齐的
            gA = cute.make_tensor(gA.iterator.align(16), gA.layout)
            gB = cute.make_tensor(gB.iterator.align(16), gB.layout)

            # 构建 sA 和 sB 的恒等布局（镜像全局张量，
            # 仅用于谓词）
            mcA = cute.make_identity_tensor(mA.layout.shape)
            mcB = cute.make_identity_tensor(mB.layout.shape)
            cA = cute.local_tile(
                mcA[None, None, bidz],
                tiler=self.cta_tiler,
                coord=tiler_coord,
                proj=(1, None, 1),
            )
            cB = cute.local_tile(
                mcB[None, None, bidz],
                tiler=self.cta_tiler,
                coord=tiler_coord,
                proj=(None, 1, 1),
            )

            cA = cute.domain_offset((0, residual_k, 0), cA)
            cB = cute.domain_offset((0, residual_k, 0), cB)

            # ///////////////////////////////////////////////////////////////////////////////
            # 创建共享内存缓冲区并获取该线程的适当fragment。
            # sA:   (BLK_M, BLK_K, PIPE)       , sB:   (BLK_N, BLK_K, PIPE)
            # tAgA: (CPY, CPY_M, CPY_K, k)     , tBgB: (CPY, CPY_N, CPY_K, k)
            # tAsA: (CPY, CPY_M, CPY_K, PIPE)  , tBsB: (CPY, CPY_N, CPY_K, PIPE)
            # ///////////////////////////////////////////////////////////////////////////////
            @cute.struct
            class SharedStorageAB:
                a: cute.struct.Align[
                    cute.struct.MemRange[mA.element_type, cute.cosize(sA_layout)],
                    16,
                ]
                b: cute.struct.Align[
                    cute.struct.MemRange[mB.element_type, cute.cosize(sB_layout)],
                    16,
                ]

            @cute.struct
            class SharedStorageC:
                c: cute.struct.Align[
                    cute.struct.MemRange[mC.element_type, cute.cosize(sC_layout)],
                    16,
                ]

            # 共享内存缓冲区
            smem = cutlass.utils.SmemAllocator()
            # 分配给 A、B 操作的共享内存将是
            # 对C上的操作进行覆盖。这是为了提高性能
            # 通过减少每个块请求的共享内存的大小
            storage = smem.allocate(
                max(SharedStorageAB.size_in_bytes(), SharedStorageC.size_in_bytes()),
                byte_alignment=16,
            )
            sA = SharedStorageAB(storage).a.get_tensor(sA_layout, swizzle=sA_swizzle)
            sB = SharedStorageAB(storage).b.get_tensor(sB_layout, swizzle=sB_swizzle)
            sC = SharedStorageC(storage).c.get_tensor(sC_layout)

            thr_copy_A = tiled_copy_A.get_slice(tidx)
            thr_copy_B = tiled_copy_B.get_slice(tidx)
            thr_copy_C = tiled_copy_C.get_slice(tidx)
            tAgA = thr_copy_A.partition_S(gA)
            tAsA = thr_copy_A.partition_D(sA)
            tBgB = thr_copy_B.partition_S(gB)
            tBsB = thr_copy_B.partition_D(sB)
            tCsC_epilogue = thr_copy_C.partition_S(sC)
            tCgC_epilogue = thr_copy_C.partition_D(gC)

            # 使用恒等 Layout重复分区
            tAcA = thr_copy_A.partition_S(cA)
            tBcB = thr_copy_B.partition_S(cB)

            # ///////////////////////////////////////////////////////////////////////////////
            # 谓词：标记 problem_shape 不是倍数时需要拷贝的索引
            # of tile_shape
            # ///////////////////////////////////////////////////////////////////////////////

            # 用于对张量 A (M/K)、B (N/K) 和（在
            # epilogue）C（M/N），我们将以类似于
            # 外层产品。沿着其中一个维度的谓词是
            # 评估并存储在谓词 Tensor中。然后，
            # 剩余维度的谓词稍后通过
            # if/else 在副本处分支。
            # 对于 A 和 B，沿 M/N 的谓词布尔值存储在
            # 谓词 Tensor和 K 是通过 if/else 分支处理的。

            # 为 M 和 N 分配谓词张量。检查谓词
            # 以拷贝原子的粒度，因此谓词张量不
            # 副本中的各个元素需要单独的布尔值
            # 原子（例如 tAgA.shape[0][0] 的元素。）
            tApA = cute.make_rmem_tensor(
                cute.make_layout(
                    (
                        tAgA.shape[0][1],
                        cute.size(tAgA, mode=[1]),
                        cute.size(tAgA, mode=[2]),
                    ),
                    stride=(cute.size(tAgA, mode=[1]), 1, 0),
                ),
                cutlass.Boolean,
            )
            tBpB = cute.make_rmem_tensor(
                cute.make_layout(
                    (
                        tBsB.shape[0][1],
                        cute.size(tBsB, mode=[1]),
                        cute.size(tBsB, mode=[2]),
                    ),
                    stride=(cute.size(tBsB, mode=[1]), 1, 0),
                ),
                cutlass.Boolean,
            )
            # 设置 M/N 界限的谓词
            for rest_v in range(tApA.shape[0]):
                for m in range(tApA.shape[1]):
                    tApA[rest_v, m, 0] = cute.elem_less(
                        tAcA[(0, rest_v), m, 0, 0][0], mA.shape[0]
                    )
            for rest_v in range(tBpB.shape[0]):
                for n in range(tBpB.shape[1]):
                    tBpB[rest_v, n, 0] = cute.elem_less(
                        tBcB[(0, rest_v), n, 0, 0][0], mB.shape[0]
                    )

            # ///////////////////////////////////////////////////////////////////////////////
            # 预取序言
            # ///////////////////////////////////////////////////////////////////////////////
            # 清除 smem 磁贴以考虑谓词卸载
            tAsA.fill(0)
            tBsB.fill(0)
            cute.arch.sync_threads()
            # 为第一个 k-tile 启动异步加载。这里我们处理k残数
            # 通过 if/else 沿着 k 维度检查。因为我们改变了恒等张量
            # 由 residue_k 并且因为恒等坐标 Tensor是坐标张量，
            # 任何有毒的单位张量元素的值小于-1
            num_smem_stages = cute.size(tAsA, mode=[3])
            k_tile_count = cute.size(tAgA, mode=[3])
            k_tile_index = cutlass.Int32(0)

            for k in range(tApA.shape[2]):
                if cute.elem_less(cutlass.Int32(-1), tAcA[0, 0, k, 0][1]):
                    cute.copy(
                        tiled_copy_A,
                        tAgA[None, None, k, k_tile_index],
                        tAsA[None, None, k, 0],
                        pred=tApA[None, None, k],
                    )
            for k in range(tBpB.shape[2]):
                if cute.elem_less(cutlass.Int32(-1), tBcB[0, 0, k, 0][1]):
                    cute.copy(
                        tiled_copy_B,
                        tBgB[None, None, k, k_tile_index],
                        tBsB[None, None, k, 0],
                        pred=tBpB[None, None, k],
                    )
            k_tile_index = k_tile_index + 1
            cute.arch.cp_async_commit_group()

            # 为其余的 k-tile 启动异步加载
            for k_tile in range(1, num_smem_stages - 1):
                if k_tile == k_tile_count:
                    tApA.fill(0)
                    tBpB.fill(0)
                cute.copy(
                    tiled_copy_A,
                    tAgA[None, None, None, k_tile_index],
                    tAsA[None, None, None, k_tile],
                    pred=tApA,
                )
                cute.copy(
                    tiled_copy_B,
                    tBgB[None, None, None, k_tile_index],
                    tBsB[None, None, None, k_tile],
                    pred=tBpB,
                )
                k_tile_index = k_tile_index + 1
                cute.arch.cp_async_commit_group()

            # ///////////////////////////////////////////////////////////////////////////////
            # Tile MMA 计算线程分区并分配累加器
            # ///////////////////////////////////////////////////////////////////////////////
            thr_mma = tiled_mma.get_slice(tidx)
            tCsA = thr_mma.partition_A(sA)
            tCsB = thr_mma.partition_B(sB)
            tCsC = thr_mma.partition_C(sC)
            tCgC = thr_mma.partition_C(gC)
            tCrA = tiled_mma.make_fragment_A(tCsA[None, None, None, 0])
            tCrB = tiled_mma.make_fragment_B(tCsB[None, None, None, 0])
            tCrC = tiled_mma.make_fragment_C(tCgC)
            # 清除累加器
            tCrC.fill(0.0)

            # ///////////////////////////////////////////////////////////////////////////////
            # 拷贝 Atom A/B 重绘
            # ///////////////////////////////////////////////////////////////////////////////

            # 创建从共享内存到寄存器的副本的副本原子
            if cutlass.const_expr(self.is_fp8):
                if cutlass.const_expr(self.a_major_mode == utils.LayoutEnum.ROW_MAJOR):
                    atom_copy_s2r_A = cute.make_copy_atom(
                        cute.nvgpu.warp.LdMatrix8x16x8bOp(False, 4),
                        mA.element_type,
                    )
                else:
                    atom_copy_s2r_A = cute.make_copy_atom(
                        cute.nvgpu.CopyUniversalOp(),
                        mA.element_type,
                        num_bits_per_copy=8,
                    )
                if cutlass.const_expr(self.b_major_mode == utils.LayoutEnum.ROW_MAJOR):
                    atom_copy_s2r_B = cute.make_copy_atom(
                        cute.nvgpu.warp.LdMatrix8x16x8bOp(False, 4),
                        mB.element_type,
                    )
                else:
                    atom_copy_s2r_B = cute.make_copy_atom(
                        cute.nvgpu.CopyUniversalOp(),
                        mB.element_type,
                        num_bits_per_copy=8,
                    )
            else:
                atom_copy_s2r_A = cute.make_copy_atom(
                    cute.nvgpu.warp.LdMatrix8x8x16bOp(
                        self.a_major_mode != utils.LayoutEnum.ROW_MAJOR, 4
                    ),
                    mA.element_type,
                )
                atom_copy_s2r_B = cute.make_copy_atom(
                    cute.nvgpu.warp.LdMatrix8x8x16bOp(
                        self.b_major_mode != utils.LayoutEnum.ROW_MAJOR, 4
                    ),
                    mB.element_type,
                )

            # 创建平铺副本，使其与线程值布局匹配
            # 平铺MMA的期望
            tiled_copy_s2r_A = cute.make_tiled_copy_A(atom_copy_s2r_A, tiled_mma)
            tiled_copy_s2r_B = cute.make_tiled_copy_B(atom_copy_s2r_B, tiled_mma)

            thr_copy_ldmatrix_A = tiled_copy_s2r_A.get_slice(tidx)
            thr_copy_ldmatrix_B = tiled_copy_s2r_B.get_slice(tidx)
            tCsA_copy_view = thr_copy_ldmatrix_A.partition_S(sA)
            tCrA_copy_view = thr_copy_ldmatrix_A.retile(tCrA)
            tCsB_copy_view = thr_copy_ldmatrix_B.partition_S(sB)
            tCrB_copy_view = thr_copy_ldmatrix_B.retile(tCrB)

            # smem 中要读取/写入的当前流水线索引
            smem_pipe_read = 0
            smem_pipe_write = num_smem_stages - 1

            tCsA_p = tCsA_copy_view[None, None, None, smem_pipe_read]
            tCsB_p = tCsB_copy_view[None, None, None, smem_pipe_read]

            # ///////////////////////////////////////////////////////////////////////////////
            # 预取寄存器流水线
            # ///////////////////////////////////////////////////////////////////////////////
            num_k_block = cute.size(tCrA, mode=[2])
            if num_k_block > 1:
                # 等到我们的第一个预取图块加载完毕
                cute.arch.cp_async_wait_group(num_smem_stages - 2)
                cute.arch.sync_threads()
                # 从第一个 k-tile 预取第一个 k-block rmem
                cute.copy(
                    tiled_copy_s2r_A,
                    tCsA_p[None, None, 0],
                    tCrA_copy_view[None, None, 0],
                )
                cute.copy(
                    tiled_copy_s2r_B,
                    tCsB_p[None, None, 0],
                    tCrB_copy_view[None, None, 0],
                )

            # ///////////////////////////////////////////////////////////////////////////////
            # 主循环
            # 1.共享内存流水线（gmem -> smem）：
            #    默认的 smem 流水线深度为 3，这意味着对于共享
            # 内存缓冲区，我们分配的大小是所描述的大小的三倍
            # CTA tile机。我们在进入主程序之前预取其中 2 个缓冲区
            # 环形。只考虑从全局内存到共享内存的传输
            # 内存中，mainloop的一般结构为：
            #   (1)将k-tile从gmem拷贝到smem；
            #   (2) 对 K tile 执行 GEMM 计算；
            #   (3)等待下一次拷贝完成。
            #    `cute.arch.cp_async_wait_group(num_smem_stages - 2)` 命令
            # 等待未完成的“拷贝”数量 <= 1。优点
            # 这种方法的优点是它允许同时生产
            # smem的（即，步骤（1））和消耗（即，步骤（2））。
            #    一个常见的误解是预取 N 个缓冲区并重写
            # 等待 N-1 个挂起副本的流水线逻辑。缺点
            # 这种方法的特点是它需要完全消耗缓冲区
            # 命令为下一个副本打开一个空缓冲区。
            # 2. 寄存器流水线（smem -> 寄存器）：
            #    类似地，寄存器流水线产生 i+1，消耗 i，并且
            # 产生 i+2... 值得注意的是，i 和 i+1 不使用相同的寄存器，
            # 消除对同一寄存器的依赖以获得更好的并行性。
            # 3. 将 smem 和寄存器流水线组合起来形成主循环。
            # ///////////////////////////////////////////////////////////////////////////////
            for k_tile in range(k_tile_count):
                for k_block in cutlass.range(num_k_block, unroll_full=True):
                    if k_block == num_k_block - 1:
                        tCsA_p = tCsA_copy_view[None, None, None, smem_pipe_read]
                        tCsB_p = tCsB_copy_view[None, None, None, smem_pipe_read]
                        cute.arch.cp_async_wait_group(num_smem_stages - 2)
                        cute.arch.sync_threads()

                    # 将 A、B 从共享内存加载到 k_block + 1 的寄存器
                    k_block_next = (k_block + 1) % num_k_block  # static
                    cute.copy(
                        tiled_copy_s2r_A,
                        tCsA_p[None, None, k_block_next],
                        tCrA_copy_view[None, None, k_block_next],
                    )
                    cute.copy(
                        tiled_copy_s2r_B,
                        tCsB_p[None, None, k_block_next],
                        tCrB_copy_view[None, None, k_block_next],
                    )

                    # 获取下一个 A 和 B 并更新 smem 流水线读/写
                    if k_block == 0:
                        if k_tile + num_smem_stages - 1 < k_tile_count:
                            cute.copy(
                                tiled_copy_A,
                                tAgA[None, None, None, k_tile_index],
                                tAsA[None, None, None, smem_pipe_write],
                                pred=tApA,
                            )
                        if k_tile + num_smem_stages - 1 < k_tile_count:
                            cute.copy(
                                tiled_copy_B,
                                tBgB[None, None, None, k_tile_index],
                                tBsB[None, None, None, smem_pipe_write],
                                pred=tBpB,
                            )
                        k_tile_index = k_tile_index + 1
                        cute.arch.cp_async_commit_group()
                        smem_pipe_write = smem_pipe_read
                        smem_pipe_read = smem_pipe_read + 1
                        if smem_pipe_read == num_smem_stages:
                            smem_pipe_read = 0

                    # k_block 的线程级寄存器 gemm
                    cute.gemm(
                        tiled_mma,
                        tCrC,
                        tCrA[None, None, k_block],
                        tCrB[None, None, k_block],
                        tCrC,
                    )

            # 在epilogue之前同步
            cute.arch.cp_async_wait_group(0)
            cute.arch.sync_threads()

            # ///////////////////////////////////////////////////////////////////////////////
            # 融合的epilogue
            # ///////////////////////////////////////////////////////////////////////////////
            tCrD = cute.make_fragment_like(tCrC, self.c_dtype)
            tCrD[None] = epilogue_op(tCrC.load()).to(self.c_dtype)

            # 将 D 的结果拷贝回共享内存
            cute.autovec_copy(tCrD, tCsC)

            # 为 C 创建坐标张量
            ceilM, ceilN, _ = cute.ceil_div(mC.shape, (self.bM, self.bN, 1))
            mcC = cute.make_identity_tensor(
                (
                    cute.size(ceilM) * self.cta_tiler[0],
                    cute.size(ceilN) * self.cta_tiler[1],
                    1,
                )
            )
            cC = cute.local_tile(
                mcC[None, None, bidz],
                tiler=self.cta_tiler,
                coord=tiler_coord,
                proj=(1, 1, None),
            )
            tCcC = thr_copy_C.partition_S(cC)

            tCrC_epilogue = cute.make_fragment_like(tCsC_epilogue)
            # 在开始拷贝之前等待对共享内存的所有写入完成
            # 使用新布局
            cute.arch.sync_threads()
            cute.autovec_copy(tCsC_epilogue, tCrC_epilogue)

            # 为 m 创建谓词 Tensor
            tCpC = cute.make_rmem_tensor(
                cute.make_layout(
                    (
                        tCgC_epilogue.shape[0][1],
                        cute.size(tCgC_epilogue, mode=[1]),
                        cute.size(tCgC_epilogue, mode=[2]),
                    ),
                    stride=(cute.size(tCgC_epilogue, mode=[1]), 1, 0),
                ),
                cutlass.Boolean,
            )
            for rest_v in range(tCpC.shape[0]):
                for m in range(tCpC.shape[1]):
                    tCpC[rest_v, m, 0] = cute.elem_less(
                        tCcC[(0, rest_v), m, 0][0], mC.shape[0]
                    )

            # 使用更好的矢量化拷贝到全局内存
            for rest_v in range(tCpC.shape[0]):
                for n in range(tCpC.shape[2]):
                    if cute.elem_less(tCcC[(0, rest_v), 0, n][1], mC.shape[1]):
                        cute.copy(
                            tiled_copy_C,
                            tCrC_epilogue[None, None, n],
                            tCgC_epilogue[None, None, n],
                            pred=tCpC[None, None, n],
                        )
        return

    def _make_smem_layout_AB(self, dtype, major_mode, copy_bits, smem_tiler):
        major_mode_size = (
            smem_tiler[1] if major_mode == utils.LayoutEnum.ROW_MAJOR else smem_tiler[0]
        )
        # 上限为 128 字节（FP16：64 个元素，FP8：128 个元素）
        max_elems = 128 * 8 // dtype.width
        major_mode_size = min(major_mode_size, max_elems)

        swizzle_bits = int(math.log2(major_mode_size * dtype.width // copy_bits))
        swizzle_bits = min(swizzle_bits, 3)
        # PDSL：base_bits 以字节为单位（copy_bits / 8），而不是以元素为单位
        base_bits = int(math.log2(copy_bits // 8))

        shift_bits = int(math.log2(copy_bits // dtype.width))
        swizzle = cute.make_swizzle(swizzle_bits, base_bits, shift_bits)

        layout_atom_outer = (
            cute.make_layout((8, major_mode_size), stride=(major_mode_size, 1))
            if major_mode == utils.LayoutEnum.ROW_MAJOR
            else cute.make_layout((major_mode_size, 8), stride=(1, major_mode_size))
        )
        layout = cute.tile_to_shape(layout_atom_outer, smem_tiler, (0, 1, 2))
        return layout, swizzle

    def _make_smem_layout_C(self, dtype, major_mode, copy_bits, smem_tiler):
        major_mode_size = (
            smem_tiler[1] if major_mode == utils.LayoutEnum.ROW_MAJOR else smem_tiler[0]
        )

        swizzle_bits = int(math.log2(major_mode_size * dtype.width // copy_bits))
        swizzle_bits = min(swizzle_bits, 3)

        layout_atom_outer = (
            cute.make_layout((8, major_mode_size), stride=(major_mode_size, 1))
            if major_mode == utils.LayoutEnum.ROW_MAJOR
            else cute.make_layout((major_mode_size, 8), stride=(1, major_mode_size))
        )
        layout_atom = cute.make_composed_layout(
            cute.make_swizzle(swizzle_bits, 3, 4),
            0,
            layout_atom_outer,
        )

        # 由于 mma 的线程布局，请删除 C 中的 swizzle
        # 防止单个线程拥有的共享内存fragment
        # 自身仍带有 swizzle
        if major_mode == utils.LayoutEnum.COL_MAJOR:
            layout_atom = cute.make_composed_layout(
                cute.make_swizzle(0, 3, 4), 0, layout_atom_outer
            )
        layout = cute.tile_to_shape(
            layout_atom,
            smem_tiler,
            (0, 1),
        )
        return layout

    def _make_gmem_tiled_copy_AB(self, atom_copy, dtype, major_mode, copy_bits):
        copy_elems = copy_bits // dtype.width
        shape_dim_1 = cute.size(self.bK) // copy_elems
        # 拷贝的线程布局
        thread_layout = cute.make_layout(
            (self.num_threads // shape_dim_1, shape_dim_1), stride=(shape_dim_1, 1)
        )
        if major_mode != utils.LayoutEnum.ROW_MAJOR:
            shape_dim_0 = cute.size(self.bM) // copy_elems
            thread_layout = cute.make_layout(
                (shape_dim_0, self.num_threads // shape_dim_0), stride=(1, shape_dim_0)
            )
        # 副本的值布局
        value_layout = (
            cute.make_layout((1, copy_elems))
            if major_mode == utils.LayoutEnum.ROW_MAJOR
            else cute.make_layout((copy_elems, 1))
        )
        return cute.make_tiled_copy_tv(atom_copy, thread_layout, value_layout)

    def _make_gmem_tiled_copy_C(self, atom_copy, dtype, major_mode, copy_bits):
        copy_elems = copy_bits // dtype.width
        shape_dim_1 = cute.size(self.bN) // copy_elems
        # 拷贝的线程布局
        thread_layout = cute.make_layout(
            (self.num_threads // shape_dim_1, shape_dim_1), stride=(shape_dim_1, 1)
        )
        if major_mode != utils.LayoutEnum.ROW_MAJOR:
            shape_dim_0 = cute.size(self.bM) // copy_elems
            thread_layout = cute.make_layout(
                (shape_dim_0, self.num_threads // shape_dim_0), stride=(1, shape_dim_0)
            )
        value_layout = (
            cute.make_layout((1, copy_elems))
            if major_mode == utils.LayoutEnum.ROW_MAJOR
            else cute.make_layout((copy_elems, 1))
        )
        return cute.make_tiled_copy_tv(atom_copy, thread_layout, value_layout)

    def raster_tile(self, i, j, f):
        new_i = i // f
        new_j = (i % f) + (j * f)
        return (new_i, new_j)


@cute.jit
def bmm(
    gemm_op: cutlass.Constexpr,
    a: cute.Tensor,  # (l, m, k)
    b: cute.Tensor,  # (l, k, n)
    c: cute.Tensor,  # (l, m, n)
    stream: cuda.CUstream,
    epilogue_op: cutlass.Constexpr = lambda x: x,
):
    """
    GEMM 内核的包装 API 遵循 PyTorch 批量矩阵乘法 (bmm) 的约定。

    在内部，张量被排列以匹配 CuTe 的约定：
      - a：（米、克、升）
      - b: (n, k, l)
      - c: (m, n, l)

    :param gemm_op: 内核操作，期望（a，b，c，流，epilogue_op）
    :type gemm_op: cutlass.Constexpr
    :param a: 输入形状为 (l, m, k) 的张量
    :type a: cute.Tensor
    :param b: 输入形状为 (l, k, n) 的张量
    :type b: cute.Tensor
    :param c: 形状为 (l, m, n) 的输出张量
    :type c: cute.Tensor
    :param stream: CUDA 异步执行流
    :type stream: cuda.CUstream
    :param epilogue_op: 适用于每个输出元素的可选元素级 lambda 函数，默认为identity
    :type epilogue_op: cutlass.Constexpr, optional
    """
    # (l,m,k) -> (m,k,l)
    a = cute.make_tensor(a.iterator, cute.select(a.layout, mode=[1, 2, 0]))
    # (l,k,n) -> (n,k,l)
    b = cute.make_tensor(b.iterator, cute.select(b.layout, mode=[2, 1, 0]))
    # (l,m,n) -> (m,n,l)
    c = cute.make_tensor(c.iterator, cute.select(c.layout, mode=[1, 2, 0]))

    gemm_op(a, b, c, stream, epilogue_op)


@lru_cache(maxsize=1)
def prepare_tensors(
    mnkl: Tuple[int, int, int, int],
    ab_dtype: Type[cutlass.Numeric],
    c_dtype: Type[cutlass.Numeric],
    a_major: str,
    b_major: str,
    c_major: str,
    init_random: bool = True,
):
    """
    为 GEMM 操作准备输入和输出张量。

    :param mnkl: 问题大小作为元组（M、N、K、L）。
    :type mnkl: Tuple[int, int, int, int]
    :param ab_dtype: 输入张量 A 和 B 的数据类型。
    :type ab_dtype: Type[cutlass.Numeric]
    :param c_dtype: 输出张量 C 的数据类型。
    :type c_dtype: Type[cutlass.Numeric]
    :param a_major: A 张量布局的主要维度（“m”或“k”）。
    :type a_major: str
    :param b_major: B 张量布局的主要维度（“n”或“k”）。
    :type b_major: str
    :param c_major: C 张量布局的主要维度（“m”或“n”）。
    :type c_major: str
    :param init_random: 是否用随机值初始化张量，默认为True。
    :type init_random: bool, optional

    :return: (a, b, c) PyTorch张量的元组。
    :rtype: 元组[torch.Tensor, torch.Tensor, torch.Tensor]
    """
    import torch
    from cutlass.torch import dtype as torch_dtype

    m, n, k, l = mnkl

    if a_major == "k":
        a = torch.empty((l, m, k), dtype=torch.float32, device="cuda")
    elif a_major == "m":
        a = torch.empty((l, k, m), dtype=torch.float32, device="cuda").permute(0, 2, 1)

    if b_major == "n":
        b = torch.empty((l, k, n), dtype=torch.float32, device="cuda")
    elif b_major == "k":
        b = torch.empty((l, n, k), dtype=torch.float32, device="cuda").permute(0, 2, 1)

    if c_major == "n":
        c = torch.empty((l, m, n), dtype=torch.float32, device="cuda")
    elif c_major == "m":
        c = torch.empty((l, n, m), dtype=torch.float32, device="cuda").permute(0, 2, 1)

    if init_random:
        a.random_(-2, 3)
        b.random_(-2, 3)
        c.random_(-2, 3)

    # 对于 fp8 类型，使用 uint8 作为存储以避免 dlpack 限制
    a_storage_dtype = torch.uint8 if is_fp8_dtype(ab_dtype) else torch_dtype(ab_dtype)
    b_storage_dtype = torch.uint8 if is_fp8_dtype(ab_dtype) else torch_dtype(ab_dtype)
    c_storage_dtype = torch.uint8 if is_fp8_dtype(c_dtype) else torch_dtype(c_dtype)

    return (
        a.to(dtype=a_storage_dtype),
        b.to(dtype=b_storage_dtype),
        c.to(dtype=c_storage_dtype),
        a.clone(),  # 用于 fp8 转换的 fp32 源
        b.clone(),  # 用于 fp8 转换的 fp32 源
        c.clone(),  # 用于 fp8 转换的 fp32 源
    )


def mark_dynamic_layout(
    a,
    b,
    c,
    leading_dim_a: int,
    leading_dim_b: int,
    leading_dim_c: int,
    ab_dtype: Type[cutlass.Numeric],
    c_dtype: Type[cutlass.Numeric],
    a_f32=None,
    b_f32=None,
    c_f32=None,
):
    a_ = create_cute_tensor_for_fp8(a, ab_dtype, leading_dim_a, source_f32_tensor=a_f32)
    b_ = create_cute_tensor_for_fp8(b, ab_dtype, leading_dim_b, source_f32_tensor=b_f32)
    c_ = create_cute_tensor_for_fp8(c, c_dtype, leading_dim_c, source_f32_tensor=c_f32)

    a_.mark_compact_shape_dynamic(
        mode=leading_dim_a,
        stride_order=(0, 1, 2) if leading_dim_a == 2 else (0, 2, 1),
        divisibility=128 // ab_dtype.width,
    )
    b_.mark_compact_shape_dynamic(
        mode=leading_dim_b,
        stride_order=(0, 1, 2) if leading_dim_b == 2 else (0, 2, 1),
        divisibility=128 // ab_dtype.width,
    )
    c_.mark_compact_shape_dynamic(
        mode=leading_dim_c,
        stride_order=(0, 1, 2) if leading_dim_c == 2 else (0, 2, 1),
        divisibility=128 // c_dtype.width,
    )
    return a_, b_, c_


@lru_cache(maxsize=1)
def compile_bmm(
    mnkl: Tuple[int, int, int, int],
    a: cute.Tensor,
    b: cute.Tensor,
    c: cute.Tensor,
    ab_dtype: Type[cutlass.Numeric],
    c_dtype: Type[cutlass.Numeric],
    acc_dtype: Type[cutlass.Numeric],
    atom_layout_mnk: Tuple[int, int, int],
    epilogue_op: cutlass.Constexpr = lambda x: x,
):
    """
    编译带有缓存的BMM内核。

    :param mnkl: 问题大小作为元组（M、N、K、L）。
    :type mnkl: Tuple[int, int, int, int]
    :param a: 输入张量 A。
    :type a: cute.Tensor
    :param b: 输入张量 B.
    :type b: cute.Tensor
    :param c: 输出张量 C.
    :type c: cute.Tensor
    :param ab_dtype: 输入张量 A 和 B 的数据类型。
    :type ab_dtype: Type[cutlass.Numeric]
    :param c_dtype: 输出张量 C 的数据类型。
    :type c_dtype: Type[cutlass.Numeric]
    :param acc_dtype: 累加器数据类型。
    :type acc_dtype: Type[cutlass.Numeric]
    :param atom_layout_mnk: Atom layout形状（M、N、K）。
    :type atom_layout_mnk: Tuple[int, int, int]
    :param epilogue_op: 应用于输出张量的可选元素 lambda 函数。
    :type epilogue_op: cutlass.Constexpr, optional

    :return: 编译后的核函数。
    """
    from cutlass.cute.runtime import make_fake_stream

    stream = make_fake_stream()

    is_m_major_c = c.leading_dim == 0
    gemm = TensorOpGemm(ab_dtype, c_dtype, acc_dtype, atom_layout_mnk, is_m_major_c)
    return cute.compile(bmm, gemm, a, b, c, stream, epilogue_op)


def run(
    mnkl: Tuple[int, int, int, int],
    ab_dtype: Type[cutlass.Numeric],
    c_dtype: Type[cutlass.Numeric],
    acc_dtype: Type[cutlass.Numeric],
    a_major: str,
    b_major: str,
    c_major: str,
    atom_layout_mnk: Tuple[int, int, int],
    tolerance: float = 1e-03,
    warmup_iterations: int = 2,
    iterations: int = 100,
    skip_ref_check: bool = False,
    use_cold_l2: bool = False,
    benchmark: bool = False,
    **kwargs,
):
    """
    通过性能基准测试执行 Ampere 张量核心 GEMM 操作。

    准备输入张量，配置并启动 GEMM 内核，
    可选择执行参考验证和基准测试执行。

    :param mnkl: 问题大小作为元组（M、N、K、L）。
    :type mnkl: Tuple[int, int, int, int]
    :param ab_dtype: 输入张量 A 和 B 的数据类型。
    :type ab_dtype: Type[cutlass.Numeric]
    :param c_dtype: 输出张量 C 的数据类型。
    :type c_dtype: Type[cutlass.Numeric]
    :param acc_dtype: 用于矩阵乘法的累加器数据类型。
    :type acc_dtype: Type[cutlass.Numeric]
    :param a_major: A 张量布局的主要维度（“m”或“k”）。
    :type a_major: str
    :param b_major: B 张量布局的主要维度（“n”或“k”）。
    :type b_major: str
    :param c_major: C 张量布局的主要维度（“m”或“n”）。
    :type c_major: str
    :param atom_layout_mnk: Atom layout形状（M、N、K）。
    :type atom_layout_mnk: Tuple[int, int, int]
    :param tolerance: 参考验证的容差，默认为 1e-03。
    :type tolerance: float, optional
    :param warmup_iterations: 基准测试之前的预热迭代次数，默认为 2。
    :type warmup_iterations: int, optional
    :param iterations: 要运行的基准测试迭代次数，默认为 100。
    :type iterations: int, optional
    :param skip_ref_check: 是否跳过参考结果验证，默认为False。
    :type skip_ref_check: bool, optional
    :param use_cold_l2: 是否使用循环缓冲策略来保证L2冷缓存，默认为False。
    :type use_cold_l2: bool, optional
    :param benchmark: 是否仅对内核进行基准测试，默认为 False。
    :type benchmark: bool, optional
    :raises RuntimeError: 如果 CUDA GPU 不可用。
    :return: GEMM 内核的执行时间。
    :rtype: float
    """
    import torch
    from cutlass.torch import dtype as torch_dtype

    if not torch.cuda.is_available():
        raise RuntimeError("GPU is required to run this example!")

    # 从 PyTorch 获取当前 CUDA 流
    torch_stream = torch.cuda.current_stream()
    # 获取 CUstream 形式的原始流指针
    current_stream = cuda.CUstream(torch_stream.cuda_stream)

    # 使用 torch 运行并验证 BMM
    a, b, c, a_f32, b_f32, c_f32 = prepare_tensors(
        mnkl, ab_dtype, c_dtype, a_major, b_major, c_major
    )

    leading_dim_a = 2 if a_major == "k" else 1
    leading_dim_b = 1 if b_major == "k" else 2
    leading_dim_c = 2 if c_major == "n" else 1

    a_, b_, c_ = mark_dynamic_layout(
        a,
        b,
        c,
        leading_dim_a,
        leading_dim_b,
        leading_dim_c,
        ab_dtype,
        c_dtype,
        a_f32,
        b_f32,
        c_f32,
    )

    compiled_fn = compile_bmm(
        mnkl,
        a_,
        b_,
        c_,
        ab_dtype,
        c_dtype,
        acc_dtype,
        atom_layout_mnk,
        epilogue_op=lambda x: x,
    )

    print("Running Ampere tensor core GEMM test with:")
    print(f"mnkl: {mnkl}")
    print(f"Tolerance: {tolerance}")
    print(f"Warmup iterations: {warmup_iterations}")
    print(f"Iterations: {iterations}")
    print(f"Skip reference checking: {skip_ref_check}")
    print(f"Use cold L2: {'True' if use_cold_l2 else 'False'}")

    if not skip_ref_check:
        # 使用小随机数获得确定性结果以进行参考检查
        compiled_fn(a_, b_, c_, current_stream)

        # 手动量化以进行比较
        # 对于fp8类型，使用f32源张量进行参考计算
        # 因为 a/b/c 可以存储为 uint8
        a_ref = a_f32 if is_fp8_dtype(ab_dtype) else a
        b_ref = b_f32 if is_fp8_dtype(ab_dtype) else b
        ref = (
            torch.bmm(a_ref.to(dtype=torch.float32), b_ref.to(dtype=torch.float32))
            .to(dtype=torch_dtype(c_dtype))
            .to(dtype=torch.float32)
        )
        torch.testing.assert_close(
            c.to(dtype=torch.float32), ref, atol=tolerance, rtol=1e-05
        )

    if not benchmark:
        return 0

    def generate_tensors():
        a, b, c, a_f32, b_f32, c_f32 = prepare_tensors(
            mnkl,
            ab_dtype,
            c_dtype,
            a_major,
            b_major,
            c_major,
            init_random=True,
        )
        a_, b_, c_ = mark_dynamic_layout(
            a,
            b,
            c,
            leading_dim_a,
            leading_dim_b,
            leading_dim_c,
            ab_dtype,
            c_dtype,
            a_f32,
            b_f32,
            c_f32,
        )
        return testing.JitArguments(a_, b_, c_, current_stream)

    workspace_count = 1
    if use_cold_l2:
        one_workspace_bytes = (
            a.numel() * a.element_size()
            + b.numel() * b.element_size()
            + c.numel() * c.element_size()
        )
        workspace_count = testing.get_workspace_count(
            one_workspace_bytes, warmup_iterations, iterations
        )

    # 返回执行时间（以微秒为单位）
    exec_time = testing.benchmark(
        compiled_fn,
        workspace_generator=generate_tensors,
        workspace_count=workspace_count,
        stream=current_stream,
        warmup_iterations=warmup_iterations,
        iterations=iterations,
    )
    print(f"[DSL INFO] Execution time: {exec_time} microseconds per iteration")
    return exec_time


def _parse_comma_separated_ints(s: str) -> Tuple[int, ...]:
    try:
        return tuple(int(x.strip()) for x in s.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Invalid format. Expected comma-separated integers."
        )


def prepare_parser():
    parser = argparse.ArgumentParser(description="Example of Dense GEMM on Ampere.")

    parser.add_argument(
        "--mnkl",
        type=_parse_comma_separated_ints,
        default=(256, 256, 512, 1),
        help="mnkl dimensions (comma-separated)",
    )
    parser.add_argument(
        "--atom_layout_mnk",
        type=_parse_comma_separated_ints,
        default=(2, 2, 1),
        help="Atom layout (comma-separated)",
    )
    parser.add_argument("--ab_dtype", type=cutlass.dtype, default=cutlass.Float16)
    parser.add_argument("--c_dtype", type=cutlass.dtype, default=cutlass.Float16)
    parser.add_argument("--acc_dtype", type=cutlass.dtype, default=cutlass.Float32)
    parser.add_argument("--a_major", choices=["k", "m"], type=str, default="m")
    parser.add_argument("--b_major", choices=["k", "n"], type=str, default="n")
    parser.add_argument("--c_major", choices=["n", "m"], type=str, default="n")
    parser.add_argument(
        "--tolerance", type=float, default=1e-03, help="Tolerance for validation"
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default="default",
        choices=["default", "none"],
        help="Benchmark the kernel with default (cutlass.testing.benchmark) or none",
    )
    parser.add_argument(
        "--warmup_iterations", type=int, default=2, help="Warmup iterations"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Number of iterations to run the kernel",
    )
    parser.add_argument(
        "--skip_ref_check", action="store_true", help="Skip reference checking"
    )
    parser.add_argument(
        "--use_cold_l2",
        action="store_true",
        default=False,
        help="Use circular buffer tensor sets to ensure L2 cold cache",
    )

    return parser


if __name__ == "__main__":
    parser = prepare_parser()

    args = parser.parse_args()

    if len(args.mnkl) != 4:
        parser.error("--mnkl must contain exactly 4 values")

    if len(args.atom_layout_mnk) != 3:
        parser.error("--atom_layout_mnk must contain exactly 3 values")

    print("[DSL INFO] Compiling Ampere Dense GEMM with:")
    print(
        f"[DSL INFO] A dtype: {args.ab_dtype}, B dtype: {args.ab_dtype}, C dtype: {args.c_dtype}, Acc dtype: {args.acc_dtype}"
    )
    print(
        f"[DSL INFO] Matrix majors - A: {args.a_major}, B: {args.b_major}, C: {args.c_major}"
    )
    print(f"[DSL INFO] Atom layout (M, N, K): {args.atom_layout_mnk}")

    run(
        args.mnkl,
        args.ab_dtype,
        args.c_dtype,
        args.acc_dtype,
        args.a_major,
        args.b_major,
        args.c_major,
        args.atom_layout_mnk,
        args.tolerance,
        args.warmup_iterations,
        args.iterations,
        args.skip_ref_check,
        args.use_cold_l2,
        args.benchmark == "default",
    )
    print("PASS")
