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
# 仅翻译注释、文档字符串和用户提示；代码逻辑与公开 API 保持不变。

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
Ampere Warp MMA 批量 GEMM 示例。

数据流：
    GMEM --异步拷贝--> SMEM --ldmatrix--> RMEM --Warp MMA--> RMEM

功能：
- 支持 FP16、BF16 和 FP8 输入；
- 支持 FP16 输出以及 FP16/FP32 累加；
- 使用多 stage 流水重叠数据搬运与计算；
- 使用共享内存完成合并写回。

约束：
- FP16/BF16 默认 CTA tile 为 128×128×32；
- FP8 默认 CTA tile 为 128×128×64；
- A/B/C 的连续维度至少满足 16 字节对齐。
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
            "ab_dtype 必须是 Float16、BFloat16、Float8E4M3FN 或 Float8E5M2"
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

        # C 为 M-major 时改算 C^T = B^T * A^T，并交换 Atom layout 的 M/N 角色。
        if is_m_major_c:
            assert self.bM % (atom_lay_N * mmaM) == 0, (
                "bM 必须能被 MMA 指令 shape 整除"
            )
            assert self.bN % (atom_lay_M * mmaN) == 0, (
                "bN 必须能被 MMA 指令 shape 整除"
            )
        else:
            assert self.bM % (atom_lay_M * mmaM) == 0, (
                "bM 必须能被 MMA 指令 shape 整除"
            )
            assert self.bN % (atom_lay_N * mmaN) == 0, (
                "bN 必须能被 MMA 指令 shape 整除"
            )
        assert atom_lay_K == 1, "本示例不支持 atom layout 的 K 维大于 1"
        assert self.bK % mmaK == 0, "bK 必须能被 MMA 指令 shape 整除"
        assert self.num_stages >= 3, "num_stages 必须大于或等于 3"

    @cute.jit
    def __call__(
        self,
        mA: cute.Tensor,
        mB: cute.Tensor,
        mC: cute.Tensor,
        stream: cuda.CUstream,
        epilogue_op: cutlass.Constexpr = lambda x: x,
    ):
        # grid 使用 tile shape (bM, bN, 1) 划分问题的 M、N、L 维；
        # K 维由每个 block 内部的多 stage 流水处理。

        # Ampere MMA Atom 的累加器布局沿行方向排列 M 维。
        # 当 C 为列主序（M-major）时，累加器布局与 C 的连续维不自然对齐，
        # 写回会产生不合并的寄存器/SMEM 流量。
        # 因此改为计算 C^T = B^T * A^T，而不是直接计算 C = A * B：
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

        # 按给定 tile 大小和 stage 数构造 Layout，其中 stage 沿 K 维排列。
        # Layout 由 64×8 或 8×32 的 Layout Atom 平铺而成，并设置 swizzle，
        # 使 SMEM→RMEM 的拷贝避免共享内存 bank 冲突。

        # 假设输入满足 16 字节对齐。
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

        # 为 C 构造类似的 Layout，但不包含多 stage 维和上述 Layout Atom。
        sC_layout = self._make_smem_layout_C(
            mC.element_type,
            self.c_major_mode,
            ab_copy_bits,
            (self.cta_tiler[0], self.cta_tiler[1]),
        )

        # ///////////////////////////////////////////////////////////////////////////////
        # 分块拷贝：
        # tA/tB/tC 的主序与 gA/gB/gC 一致，以便合并访问全局内存，
        # 提高 GMEM 与 SMEM 之间的数据传输效率。
        # ///////////////////////////////////////////////////////////////////////////////

        # 构造 GMEM→SMEM 异步拷贝使用的拷贝原子（CopyAtom）。
        atom_async_copy = cute.make_copy_atom(
            cute.nvgpu.cpasync.CopyG2SOp(cache_mode=cute.nvgpu.LoadCacheMode.GLOBAL),
            mA.element_type,
            num_bits_per_copy=ab_copy_bits,
        )

        # 从拷贝原子构造分块拷贝（TiledCopy），线程布局沿张量主维排列。
        tiled_copy_A = self._make_gmem_tiled_copy_AB(
            atom_async_copy, mA.element_type, self.a_major_mode, ab_copy_bits
        )
        tiled_copy_B = self._make_gmem_tiled_copy_AB(
            atom_async_copy, mB.element_type, self.b_major_mode, ab_copy_bits
        )

        # 为尾声构造同步拷贝原子和线程布局。
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
            # 当 Atom layout 的 N mode 为 1 时，为获得最大粒度的
            # SMEM→RMEM 合并拷贝，将 TiledMMA 的 N mode 扩展为 16。
            atom_layout_mnk[1] * self.mma_inst_shape[1] * 2,
            atom_layout_mnk[2] * self.mma_inst_shape[2],
        )

        # 按指定 Atom layout 构造 TiledMMA。
        # 对于 2×2×1 的 Atom layout，MMA Atom 共复制四份：
        # M 方向两份，N 方向两份。
        tC = cute.make_layout(atom_layout_mnk)
        tiled_mma = cute.make_tiled_mma(
            op,
            tC,
            permutation_mnk=permutation_mnk,
        )

        # grid_dim: ((m + BLK_M - 1) // BLK_M, (n + BLK_N - 1) // BLK_N, l)
        grid_dim = cute.ceil_div(mC.shape, (self.bM, self.bN, 1))

        # 添加线程块光栅化以提高数据复用。
        raster_factor = 1
        grid_dim_n = cute.size(grid_dim[1])
        # 选择合适阈值，避免产生过多空操作 CTA。
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
            # 取得当前线程块对应的 tile。
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

            # 如果 Tensor 的 K mode 不能被 K tile 整除，默认最后一个 tile
            # 会成为不规则 tile。这里反向移动起始指针，让第一个 tile 不规则，
            # 从而先处理边界，避免在主循环中反复检查。

            # residual_k 是负数，表示指针需要沿 K 维反向移动的距离。
            residual_k = cute.size(mA, mode=[1]) - cutlass.Int32(self.bK) * cute.size(
                gA, mode=[2]
            )

            # 将 gA/gB 的指针沿 `-K` 方向移动。
            gA = cute.domain_offset((0, residual_k, 0), gA)
            gB = cute.domain_offset((0, residual_k, 0), gB)
            # 输入满足 16 字节对齐。
            gA = cute.make_tensor(gA.iterator.align(16), gA.layout)
            gB = cute.make_tensor(gB.iterator.align(16), gB.layout)

            # 构造与全局 Tensor 同 shape 的恒等坐标 Tensor，仅用于谓词判断。
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
            # 创建共享内存缓冲区，并取得当前线程对应的 fragment。
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
            # A/B 使用的共享内存随后会由 C 的 epilogue 覆盖复用，
            # 从而减少每个 block 申请的共享内存容量。
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

            # 使用恒等坐标 Tensor 重复执行分区。
            tAcA = thr_copy_A.partition_S(cA)
            tBcB = thr_copy_B.partition_S(cB)

            # ///////////////////////////////////////////////////////////////////////////////
            # 谓词：当 problem shape 不是 tile shape 的整数倍时，
            # 标记仍需执行拷贝的有效索引。
            # ///////////////////////////////////////////////////////////////////////////////

            # A(M/K)、B(N/K) 和 epilogue 中的 C(M/N) 都采用类似外积的
            # 谓词方式：一个维度的有效性保存到谓词 Tensor，另一个维度
            # 在执行拷贝时通过 if/else 判断。
            # A/B 的 M/N 边界保存在谓词 Tensor 中，K 边界由 if/else 处理。

            # 为 M、N 分配谓词张量。谓词按拷贝原子粒度检查，
            # 因此 Atom 内的每个元素不需要各自保存布尔值。
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
            # 设置 M/N 边界谓词。
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
            # 预取序言阶段
            # ///////////////////////////////////////////////////////////////////////////////
            # 清零 SMEM tile，使被谓词屏蔽的加载位置保持为零。
            tAsA.fill(0)
            tBsB.fill(0)
            cute.arch.sync_threads()
            # 异步加载第一个 K tile，并通过 K 维 if/else 处理余数。
            # 恒等坐标 Tensor 已按 residual_k 平移，因此无效坐标小于 -1。
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

            # 为其余 K tile 发起异步加载。
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
            # 对分块 MMA 的计算线程做分区，并分配累加器
            # ///////////////////////////////////////////////////////////////////////////////
            thr_mma = tiled_mma.get_slice(tidx)
            tCsA = thr_mma.partition_A(sA)
            tCsB = thr_mma.partition_B(sB)
            tCsC = thr_mma.partition_C(sC)
            tCgC = thr_mma.partition_C(gC)
            tCrA = tiled_mma.make_fragment_A(tCsA[None, None, None, 0])
            tCrB = tiled_mma.make_fragment_B(tCsB[None, None, None, 0])
            tCrC = tiled_mma.make_fragment_C(tCgC)
            # 清零累加器。
            tCrC.fill(0.0)

            # ///////////////////////////////////////////////////////////////////////////////
            # 为 A/B 的拷贝原子重新分块。
            # ///////////////////////////////////////////////////////////////////////////////

            # 构造 SMEM→RMEM 的拷贝原子。
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

            # 构造与 TiledMMA 所需 thread-value layout 匹配的 TiledCopy。
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
                # 等待第一个预取 tile 完成加载。
                cute.arch.cp_async_wait_group(num_smem_stages - 2)
                cute.arch.sync_threads()
                # 从第一个 K tile 预取首个 K block 的 RMEM 片段
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
            # 默认 SMEM 流水线深度为 3，因此分配的共享内存缓冲区总量
            # 是 CTA tiler 所描述单级大小的三倍。进入主循环前先预取两级。
            # 只考虑 GMEM→SMEM 搬运时，主循环结构如下：
            # (1) 将 K tile 从 GMEM 拷贝到 SMEM；
            # (2) 对 K tile 执行 GEMM 计算；
            # (3) 等待下一次拷贝完成。
            # `cute.arch.cp_async_wait_group(num_smem_stages - 2)` 命令
            # 等待未完成的异步拷贝组数量不超过 1，使 SMEM 的生产与消费重叠。
            # 不能简单预取 N 级后只等待 N-1 个未完成拷贝，因为必须先完整
            # 消费某一级缓冲区，才能把它重新交给下一次拷贝。
            # 2. 寄存器流水线（SMEM→RMEM）：
            # 流水线在消费第 i 级时生产第 i+1 级，并继续准备第 i+2 级。
            # 相邻级使用不同寄存器，减少寄存器数据依赖。
            # 3. SMEM 流水线与寄存器流水线共同组成主循环。
            # ///////////////////////////////////////////////////////////////////////////////
            for k_tile in range(k_tile_count):
                for k_block in cutlass.range(num_k_block, unroll_full=True):
                    if k_block == num_k_block - 1:
                        tCsA_p = tCsA_copy_view[None, None, None, smem_pipe_read]
                        tCsB_p = tCsB_copy_view[None, None, None, smem_pipe_read]
                        cute.arch.cp_async_wait_group(num_smem_stages - 2)
                        cute.arch.sync_threads()

                    # 将 A、B 从 SMEM 加载到下一个 K block 的寄存器。
                    k_block_next = (k_block + 1) % num_k_block  # 编译期静态值
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

                    # 取得下一组 A/B，并更新 SMEM 流水线的读写位置。
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

                    # 对当前 K block 执行线程级寄存器 GEMM。
                    cute.gemm(
                        tiled_mma,
                        tCrC,
                        tCrA[None, None, k_block],
                        tCrB[None, None, k_block],
                        tCrC,
                    )

            # 进入 epilogue 前完成同步。
            cute.arch.cp_async_wait_group(0)
            cute.arch.sync_threads()

            # ///////////////////////////////////////////////////////////////////////////////
            # 融合 epilogue。
            # ///////////////////////////////////////////////////////////////////////////////
            tCrD = cute.make_fragment_like(tCrC, self.c_dtype)
            tCrD[None] = epilogue_op(tCrC.load()).to(self.c_dtype)

            # 将 D 结果拷贝回共享内存。
            cute.autovec_copy(tCrD, tCsC)

            # 为 C 创建坐标 Tensor。
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
            # 等待共享内存写入全部完成，再使用新 Layout 开始拷贝。
            cute.arch.sync_threads()
            cute.autovec_copy(tCsC_epilogue, tCrC_epilogue)

            # 为 M 维创建谓词 Tensor。
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

            # 使用更充分的向量化拷贝到全局内存。
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
        # 最大限制为 128 字节（FP16：64 个元素，FP8：128 个元素）
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

        # 受 MMA 线程布局影响，需要移除 C 的 swizzle，避免单个线程持有的
        # 共享内存 fragment 自身仍带有 swizzle。
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
        # 拷贝使用的线程布局。
        thread_layout = cute.make_layout(
            (self.num_threads // shape_dim_1, shape_dim_1), stride=(shape_dim_1, 1)
        )
        if major_mode != utils.LayoutEnum.ROW_MAJOR:
            shape_dim_0 = cute.size(self.bM) // copy_elems
            thread_layout = cute.make_layout(
                (shape_dim_0, self.num_threads // shape_dim_0), stride=(1, shape_dim_0)
            )
        # 拷贝使用的值布局。
        value_layout = (
            cute.make_layout((1, copy_elems))
            if major_mode == utils.LayoutEnum.ROW_MAJOR
            else cute.make_layout((copy_elems, 1))
        )
        return cute.make_tiled_copy_tv(atom_copy, thread_layout, value_layout)

    def _make_gmem_tiled_copy_C(self, atom_copy, dtype, major_mode, copy_bits):
        copy_elems = copy_bits // dtype.width
        shape_dim_1 = cute.size(self.bN) // copy_elems
        # 拷贝使用的线程布局。
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
    """按 PyTorch 批量矩阵乘法约定封装 GEMM kernel。

    函数内部把 a、b、c 从 PyTorch 的批次优先顺序转换为 CuTe 使用的
    (m,k,l)、(n,k,l)、(m,n,l) 顺序，然后调用实际 GEMM。"""
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
    """准备 GEMM 的输入和输出 Tensor。

    根据 MNKL、数据类型和 major 模式创建 GPU Tensor；FP8 使用 uint8
    作为底层存储，并额外保留 FP32 数据供量化和参考计算使用。"""
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

    # 对于 FP8 类型，使用 uint8 作为底层存储，以规避 DLPack 限制。
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
    """编译并缓存 BMM kernel。

    返回固定的 JIT Executor；缓存大小为 1，用于复用相同配置的编译结果。"""
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
    """运行 Ampere Tensor Core GEMM，并按需执行参考结果校验和性能测试。

    返回值为每次迭代的执行时间，单位为微秒；关闭 benchmark 时返回 0。"""
    import torch
    from cutlass.torch import dtype as torch_dtype

    if not torch.cuda.is_available():
        raise RuntimeError("运行本示例需要 NVIDIA GPU！")

    # 从 PyTorch 获取当前 CUDA 流
    torch_stream = torch.cuda.current_stream()
    # 获取 CUstream 形式的原始流指针
    current_stream = cuda.CUstream(torch_stream.cuda_stream)

    # 使用 PyTorch 运行并验证 BMM。
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

    print("使用以下配置运行 Ampere Tensor Core GEMM 测试：")
    print(f"问题规模 MNKL：{mnkl}")
    print(f"容差：{tolerance}")
    print(f"预热迭代次数：{warmup_iterations}")
    print(f"迭代次数：{iterations}")
    print(f"跳过参考结果检查：{'是' if skip_ref_check else '否'}")
    print(f"使用冷 L2：{'是' if use_cold_l2 else '否'}")

    if not skip_ref_check:
        # 使用范围较小的随机数，获得稳定的参考检查结果。
        compiled_fn(a_, b_, c_, current_stream)

        # 手动量化以便比较。
        # FP8 路径使用 FP32 源 Tensor 做参考计算，因为 a/b/c 可能以
        # uint8 作为底层存储。
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
    print(f"[DSL 信息] 执行时间：{exec_time} 微秒/次迭代")
    return exec_time


def _parse_comma_separated_ints(s: str) -> Tuple[int, ...]:
    try:
        return tuple(int(x.strip()) for x in s.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(
            "格式无效，应为逗号分隔的整数。"
        )


def prepare_parser():
    parser = argparse.ArgumentParser(description="Ampere Dense GEMM 示例。")

    parser.add_argument(
        "--mnkl",
        type=_parse_comma_separated_ints,
        default=(256, 256, 512, 1),
        help="MNKL 维度，以逗号分隔",
    )
    parser.add_argument(
        "--atom_layout_mnk",
        type=_parse_comma_separated_ints,
        default=(2, 2, 1),
        help="Atom layout，以逗号分隔",
    )
    parser.add_argument("--ab_dtype", type=cutlass.dtype, default=cutlass.Float16)
    parser.add_argument("--c_dtype", type=cutlass.dtype, default=cutlass.Float16)
    parser.add_argument("--acc_dtype", type=cutlass.dtype, default=cutlass.Float32)
    parser.add_argument("--a_major", choices=["k", "m"], type=str, default="m")
    parser.add_argument("--b_major", choices=["k", "n"], type=str, default="n")
    parser.add_argument("--c_major", choices=["n", "m"], type=str, default="n")
    parser.add_argument(
        "--tolerance", type=float, default=1e-03, help="结果验证容差"
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default="default",
        choices=["default", "none"],
        help="使用 default（cutlass.testing.benchmark）测试 kernel，或用 none 关闭测试",
    )
    parser.add_argument(
        "--warmup_iterations", type=int, default=2, help="预热迭代次数"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="运行 kernel 的迭代次数",
    )
    parser.add_argument(
        "--skip_ref_check", action="store_true", help="跳过参考结果检查"
    )
    parser.add_argument(
        "--use_cold_l2",
        action="store_true",
        default=False,
        help="使用循环缓冲 Tensor 集合维持冷 L2 cache",
    )

    return parser


if __name__ == "__main__":
    parser = prepare_parser()

    args = parser.parse_args()

    if len(args.mnkl) != 4:
        parser.error("--mnkl 必须恰好包含 4 个值")

    if len(args.atom_layout_mnk) != 3:
        parser.error("--atom_layout_mnk 必须恰好包含 3 个值")

    print("[DSL 信息] 使用以下配置编译 Ampere Dense GEMM：")
    print(
        f"[DSL 信息] A 数据类型：{args.ab_dtype}，B 数据类型：{args.ab_dtype}，"
        f"C 数据类型：{args.c_dtype}，累加器数据类型：{args.acc_dtype}"
    )
    print(
        f"[DSL 信息] 矩阵主序 - A：{args.a_major}，B：{args.b_major}，C：{args.c_major}"
    )
    print(f"[DSL 信息] Atom layout（M、N、K）：{args.atom_layout_mnk}")

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
    print("运行通过")
