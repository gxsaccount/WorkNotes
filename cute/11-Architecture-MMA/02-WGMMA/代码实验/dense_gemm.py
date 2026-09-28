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
# https://github.com/NVIDIA/cutlass/blob/098de2a652cf8f00fd70b2df54051c7eccbb855a/examples/python/CuTeDSL/cute/hopper/kernel/dense_gemm/dense_gemm.py
# 逐行翻译注释和文档字符串，不删除或合并内容；计算代码保持英文原版结构。

import argparse
from typing import Tuple, Type
import math
import cuda.bindings.driver as cuda

import cutlass
import cutlass.cute as cute
import cutlass.cute.testing as testing
import cutlass.utils as utils
import cutlass.pipeline as pipeline
from cutlass.pipeline import pipeline_init_arrive, pipeline_init_wait
from cutlass.cute.runtime import from_dlpack
import cutlass.utils.hopper_helpers as sm90_utils

"""
NVIDIA Hopper 架构的高性能批量密集 GEMM (C = A * B) 示例
使用 CuTe DSL。
- 矩阵 A 为 MxKxL，L 为批量维度，A 可以是行优先（“K”）或列优先（“M”）
- 矩阵 B 为 NxKxL，L 为批次维度，B 可以是行优先（“N”）或列优先（“K”）
- 矩阵 C 为 MxNxL，L 为批量维度，C 可以是行优先（“N”）或列优先（“M”）

该GEMM内核支持以下功能：
    - 利用张量内存访问 (TMA) 进行高效的内存操作
    - 利用 Hopper 的 WGMMA 进行矩阵乘法累加 (MMA) 运算
    - 通过集群实现 TMA 多播，以减少 L2 内存流量
    - 支持多级流水线重叠计算和内存访问

这个GEMM的工作原理如下：
1. 使用 TMA 操作将 A 和 B 矩阵从全局内存 (GMEM) 加载到共享内存 (SMEM)。
2. 使用WGMMA 指令执行矩阵乘法累加(MMA) 运算。
3. 将结果从寄存器（RMEM）存储到共享内存（SMEM），然后通过 TMA 操作存储到全局内存（GMEM）。

Hopper WGMMA 指令的工作方式如下：
- 从SMEM读取矩阵A
- 从SMEM读取矩阵B
- 执行MMA运算并将结果存储到累加器（寄存器）中

要运行此示例：

.. code-block:: bash

    python examples/hopper/dense_gemm.py                                   \
      --mnkl 8192,8192,8192,1 --tile_shape_mn 128,256                      \
      --cluster_shape_mn 1,1 --a_dtype Float16 --b_dtype Float16           \
      --c_dtype Float16 --acc_dtype Float32                                \
      --a_major k --b_major k --c_major n

上面的示例命令计算批处理的gemm，其中M=8192，N=8192，K=8192，
batch_count=1。 Hopper WGMMA tile形状为 128x256x64，簇形状
是(1,1)。输入、mma累加器和输出数据类型设置为fp16、fp32
和 fp16 分别。

要使用 NCU 分析器收集性能：

.. code-block:: bash

    ncu python examples/hopper/dense_gemm.py                               \
      --mnkl 8192,8192,8192,1 --tile_shape_mn 128,256                      \
      --cluster_shape_mn 1,1 --a_dtype Float16 --b_dtype Float16           \
      --c_dtype Float16 --acc_dtype Float32                                \
      --a_major k --b_major k --c_major n

约束：
* 支持的输入数据类型：fp16、fp8（e4m3fn、e5m2）、int8、uint8
* 对于 fp16 类型，A 和 B 必须具有相同的数据类型
* 对于 fp8 类型，A 和 B 可以有不同的类型（e4m3fn 或 e5m2）
* 对于 8 位整数类型，A 和 B 可以有不同的类型（int8 或 uint8）
* 8 位类型（e4m3fn、e5m2、int8、uint8）仅支持 k major布局
* CTA tile形状 M 必须为 64/128
* CTA tile形状 N 必须为 64/128/256
* 簇形状 M/N 必须为正且为 2 的幂，簇总大小 <= 4
* A/B/C 张量的连续维度必须至少 16 字节对齐，
  即，Float16、Float8的元素数量分别是8的倍数、16的倍数。
"""


# /////////////////////////////////////////////////////////////////////////////
#  解析参数的助手
# /////////////////////////////////////////////////////////////////////////////
def parse_comma_separated_ints(s: str):
    try:
        return tuple([int(x.strip()) for x in s.split(",")])
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Invalid format. Expected comma-separated integers."
        )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Example of MxNxKxL GEMM on Hopper.")

    parser.add_argument(
        "--mnkl",
        type=parse_comma_separated_ints,
        default=(4096, 4096, 4096, 1),
        help="mnkl dimensions (comma-separated)",
    )
    parser.add_argument(
        "--tile_shape_mn",
        type=parse_comma_separated_ints,
        choices=[(128, 128), (128, 256), (128, 64), (64, 64)],
        default=(128, 128),
        help="Cta tile shape (comma-separated)",
    )
    parser.add_argument(
        "--cluster_shape_mn",
        type=parse_comma_separated_ints,
        choices=[(1, 1), (2, 1), (1, 2), (2, 2)],
        default=(1, 1),
        help="Cluster shape (comma-separated)",
    )
    parser.add_argument(
        "--a_dtype",
        type=cutlass.dtype,
        default=cutlass.Float16,
    )
    parser.add_argument(
        "--b_dtype",
        type=cutlass.dtype,
        default=cutlass.Float16,
    )
    parser.add_argument(
        "--c_dtype",
        type=cutlass.dtype,
        default=cutlass.Float16,
    )
    parser.add_argument(
        "--acc_dtype",
        type=cutlass.dtype,
        default=cutlass.Float32,
    )
    parser.add_argument("--a_major", choices=["k", "m"], type=str, default="k")
    parser.add_argument("--b_major", choices=["k", "n"], type=str, default="k")
    parser.add_argument("--c_major", choices=["n", "m"], type=str, default="n")
    parser.add_argument(
        "--tolerance", type=float, default=1e-01, help="Tolerance for validation"
    )
    parser.add_argument(
        "--warmup_iterations", type=int, default=0, help="Warmup iterations"
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
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

    args = parser.parse_args()

    if len(args.mnkl) != 4:
        parser.error("--mnkl must contain exactly 4 values")
    if len(args.tile_shape_mn) != 2:
        parser.error("--tile_shape_mn must contain exactly 2 values")
    if len(args.cluster_shape_mn) != 2:
        parser.error("--cluster_shape_mn must contain exactly 2 values")

    return args


# /////////////////////////////////////////////////////////////////////////////
#  主机设置和设备内核启动
# /////////////////////////////////////////////////////////////////////////////


class HopperWgmmaGemmKernel:
    """
    此类实现批量矩阵乘法 (C = A x B)，支持各种数据类型
    以及 Hopper GPU 特有的架构特性。

    :param acc_dtype: 计算期间累加的数据类型
    :type acc_dtype: type[cutlass.Numeric]
    :param tile_shape_mn: CTA tile的形状（M、N）
    :type tile_shape_mn: Tuple[int, int]
    :param cluster_shape_mn: 用于并行处理的集群维度 (M,N)
    :type cluster_shape_mn: Tuple[int, int]

    :note: 支持的 A/B 数据类型：
        - Float16
          A 和 B 必须具有相同的数据类型
        - Float8E4M3FN/Float8E5M2
          A 和 B 可以有不同的类型 (Float8E4M3FN/Float8E5M2)
          仅支持kmajor布局
        - Int8/Uint8
          A 和 B 可以有不同的类型 (Int8/Uint8)
          仅支持kmajor布局

    :note: 支持的累积类型：
        - Float32/Float16（适用于所有浮点输入）
        - Int32（适用于 Int8/Uint8 输入）

    :note: Constraints:
        - CTA tile M 必须为 64/128
        - CTA tile N 必须为 64/128/256
        - CTA tile K 必须为 64
        - 簇形状 M/N 必须为正且为 2 的幂，簇总大小 <= 4

    例子：
        >>> gemm = HopperWgmmaGemmKernel(
        ...     acc_dtype=cutlass.Float32,
        ...     tile_shape_mn=(128, 256),
        ...     cluster_shape_mn=(1, 1)
        ... )
        >>> gemm(a_tensor, b_tensor, c_tensor, stream)
    """

    def __init__(
        self,
        acc_dtype: type[cutlass.Numeric],
        tile_shape_mn: tuple[int, int],
        cluster_shape_mn: tuple[int, int],
    ):
        """
        初始化 Hopper 密集 GEMM 内核的配置。

        此配置包括操作数的数据类型、图块形状、簇配置、
        和线程布局。

        :param acc_dtype: 计算期间累加的数据类型
        :type acc_dtype: type[cutlass.Numeric]
        :param tile_shape_mn: CTA tile的形状（M、N）
        :type tile_shape_mn: Tuple[int, int]
        :param cluster_shape_mn: 用于并行处理的集群维度 (M,N)
        :type cluster_shape_mn: Tuple[int, int]
        """

        self.acc_dtype = acc_dtype

        self.cluster_shape_mn = cluster_shape_mn
        self.mma_inst_shape_mn = None
        # K 维度在 _setup_attributes 中延迟
        self.tile_shape_mnk = (*tile_shape_mn, 1)
        # 对于大tile尺寸，最好使用两个经纱组，因为仅使用一个经纱
        # 组可能会导致寄存器溢出
        self.atom_layout_mnk = (
            (2, 1, 1)
            if self.tile_shape_mnk[0] > 64 and self.tile_shape_mnk[1] > 128
            else (1, 1, 1)
        )
        self.num_mcast_ctas_a = None
        self.num_mcast_ctas_b = None
        self.is_a_mcast = False
        self.is_b_mcast = False
        self.tiled_mma = None

        self.occupancy = 1
        self.mma_warp_groups = math.prod(self.atom_layout_mnk)
        self.num_threads_per_warp_group = 128
        self.threads_per_cta = self.mma_warp_groups * self.num_threads_per_warp_group
        self.smem_capacity = utils.get_smem_capacity_in_bytes("sm_90")

        self.ab_stage = None
        self.epi_stage = None

        self.a_smem_layout_staged = None
        self.b_smem_layout_staged = None
        self.epi_smem_layout_staged = None
        self.epi_tile = None

        self.shared_storage = None
        self.buffer_align_bytes = 1024

    def _setup_attributes(self):
        """设置依赖于 GEMM 输入的配置

        该方法根据输入张量属性配置各种属性
        （数据类型、主维）和内核设置：
        - 配置分块 MMA
        - 计算 MMA、cluster 和 tile shape
        - 计算集群布局
        - 计算 A/B 的多播 CTA
        - 计算epilogue小标题
        - 在共享内存中设置 A/B/C 阶段计数
        - 计算A/B/C共享内存布局
        """

        # 检查 cta tile形状
        if self.tile_shape_mnk[0] not in [64, 128]:
            raise ValueError("CTA tile shape M must be 64/128")
        if self.tile_shape_mnk[1] not in [64, 128, 256]:
            raise ValueError("CTA tile shape N must be 64/128/256")

        self.tiled_mma = sm90_utils.make_trivial_tiled_mma(
            self.a_dtype,
            self.b_dtype,
            self.a_layout.sm90_mma_major_mode(),
            self.b_layout.sm90_mma_major_mode(),
            self.acc_dtype,
            self.atom_layout_mnk,
            tiler_mn=(64, self.tile_shape_mnk[1]),
        )
        mma_inst_shape_k = cute.size(self.tiled_mma.shape_mnk, mode=[2])
        mma_inst_tile_k = 4
        self.tile_shape_mnk = (
            self.tile_shape_mnk[0],
            self.tile_shape_mnk[1],
            mma_inst_shape_k * mma_inst_tile_k,
        )

        self.cta_layout_mnk = cute.make_layout((*self.cluster_shape_mn, 1))
        self.num_mcast_ctas_a = self.cluster_shape_mn[1]
        self.num_mcast_ctas_b = self.cluster_shape_mn[0]
        self.is_a_mcast = self.num_mcast_ctas_a > 1
        self.is_b_mcast = self.num_mcast_ctas_b > 1

        is_cooperative = self.atom_layout_mnk == (2, 1, 1)
        self.epi_tile = sm90_utils.compute_tile_shape_or_override(
            self.tile_shape_mnk, self.c_dtype, is_cooperative=is_cooperative
        )

        # 计算 smem 布局之前的计算阶段
        self.ab_stage, self.epi_stage = self._compute_stages(
            self.tile_shape_mnk,
            self.a_dtype,
            self.b_dtype,
            self.smem_capacity,
            self.occupancy,
        )

        (
            self.a_smem_layout_staged,
            self.b_smem_layout_staged,
            self.epi_smem_layout_staged,
        ) = self._make_smem_layouts(
            self.tile_shape_mnk,
            self.epi_tile,
            self.a_dtype,
            self.a_layout,
            self.b_dtype,
            self.b_layout,
            self.ab_stage,
            self.c_dtype,
            self.c_layout,
            self.epi_stage,
        )

    @cute.jit
    def __call__(
        self,
        a: cute.Tensor,
        b: cute.Tensor,
        c: cute.Tensor,
        stream: cuda.CUstream,
    ):
        """执行GEMM操作步骤：
        - 设置静态属性
        - 设置 TMA 加载/存储原子和张量
        - 计算网格大小
        - 为内核定义共享存储
        - 同步启动内核

        :param a: 输入张量 A
        :type a: cute.Tensor
        :param b: 输入张量 B
        :type b: cute.Tensor
        :param c: 输出张量C
        :type c: cute.Tensor
        :param stream: CUDA 异步执行流
        :type stream: cuda.CUstream
        """

        # 在 smem/grid/tma 计算之前设置静态属性
        self.a_dtype = a.element_type
        self.b_dtype = b.element_type
        self.c_dtype = c.element_type
        self.a_layout = utils.LayoutEnum.from_tensor(a)
        self.b_layout = utils.LayoutEnum.from_tensor(b)
        self.c_layout = utils.LayoutEnum.from_tensor(c)

        if cutlass.const_expr(
            self.a_dtype.width == 16 and self.a_dtype != self.b_dtype
        ):
            raise TypeError(f"Type mismatch: {self.a_dtype} != {self.b_dtype}")
        if cutlass.const_expr(self.a_dtype.width != self.b_dtype.width):
            raise TypeError(
                f"Type width mismatch: {self.a_dtype.width} != {self.b_dtype.width}"
            )
        if cutlass.const_expr(self.a_dtype.width != 16 and self.a_dtype.width != 8):
            raise TypeError("a_dtype should be float16 or float8")

        self._setup_attributes()

        tma_atom_a, tma_tensor_a = self._make_tma_atoms_and_tensors(
            a,
            self.a_smem_layout_staged,
            (self.tile_shape_mnk[0], self.tile_shape_mnk[2]),
            self.cluster_shape_mn[1],
        )

        tma_atom_b, tma_tensor_b = self._make_tma_atoms_and_tensors(
            b,
            self.b_smem_layout_staged,
            (self.tile_shape_mnk[1], self.tile_shape_mnk[2]),
            self.cluster_shape_mn[0],
        )

        tma_atom_c, tma_tensor_c = self._make_tma_store_atoms_and_tensors(
            c,
            self.epi_smem_layout_staged,
            self.epi_tile,
        )

        grid = self._compute_grid(c, self.tile_shape_mnk, self.cluster_shape_mn)

        @cute.struct
        class SharedStorage:
            mainloop_pipeline_array_ptr: cute.struct.MemRange[
                cutlass.Int64, self.ab_stage * 2
            ]
            sA: cute.struct.Align[
                cute.struct.MemRange[
                    self.a_dtype, cute.cosize(self.a_smem_layout_staged)
                ],
                self.buffer_align_bytes,
            ]
            sB: cute.struct.Align[
                cute.struct.MemRange[
                    self.b_dtype, cute.cosize(self.b_smem_layout_staged)
                ],
                self.buffer_align_bytes,
            ]

        self.shared_storage = SharedStorage

        # 同步启动内核
        self.kernel(
            tma_atom_a,
            tma_tensor_a,
            tma_atom_b,
            tma_tensor_b,
            tma_atom_c,
            tma_tensor_c,
            self.tiled_mma,
            self.cta_layout_mnk,
            self.a_smem_layout_staged,
            self.b_smem_layout_staged,
            self.epi_smem_layout_staged,
        ).launch(
            grid=grid,
            block=[self.threads_per_cta, 1, 1],
            cluster=(*self.cluster_shape_mn, 1),
            stream=stream,
        )
        return

    #  GPU设备内核
    @cute.kernel
    def kernel(
        self,
        tma_atom_a: cute.CopyAtom,
        mA_mkl: cute.Tensor,
        tma_atom_b: cute.CopyAtom,
        mB_nkl: cute.Tensor,
        tma_atom_c: cute.CopyAtom,
        mC_mnl: cute.Tensor,
        tiled_mma: cute.TiledMma,
        cta_layout_mnk: cute.Layout,
        a_smem_layout_staged: cute.ComposedLayout,
        b_smem_layout_staged: cute.ComposedLayout,
        epi_smem_layout_staged: cute.ComposedLayout,
    ):
        """
        GPU 设备内核执行批量 GEMM 计算。

        :param tma_atom_a: TMA A 张量的拷贝原子
        :type tma_atom_a: cute.CopyAtom
        :param mA_mkl: 输入张量 A
        :type mA_mkl: cute.Tensor
        :param tma_atom_b: B 张量的 TMA 拷贝原子
        :type tma_atom_b: cute.CopyAtom
        :param mB_nkl: 输入张量 B
        :type mB_nkl: cute.Tensor
        :param tma_atom_c: C 张量的 TMA 拷贝原子
        :type tma_atom_c: cute.CopyAtom
        :param mC_mnl: 输出张量C
        :type mC_mnl: cute.Tensor
        :param tiled_mma: 分块 MMA 对象
        :type tiled_mma: cute.TiledMma
        :param cta_layout_mnk: CTA布局
        :type cta_layout_mnk: cute.Layout
        :param a_smem_layout_staged: A 的共享内存布局
        :type a_smem_layout_staged: cute.ComposedLayout
        :param b_smem_layout_staged: B 的共享内存布局
        :type b_smem_layout_staged: cute.ComposedLayout
        :param epi_smem_layout_staged: epilogue的共享内存布局
        :type epi_smem_layout_staged: cute.ComposedLayout
        """

        warp_idx = cute.arch.warp_idx()
        warp_idx = cute.arch.make_warp_uniform(warp_idx)

        # /////////////////////////////////////////////////////////////////////////////
        #  预取 Tma 描述
        # /////////////////////////////////////////////////////////////////////////////
        if warp_idx == 0:
            cute.nvgpu.cpasync.prefetch_descriptor(tma_atom_a)
            cute.nvgpu.cpasync.prefetch_descriptor(tma_atom_b)

        # ///////////////////////////////////////////////////////////////////////////////
        #  获取 cta/warp/线程 idx
        # ///////////////////////////////////////////////////////////////////////////////
        bidx, bidy, bidz = cute.arch.block_idx()
        tidx, _, _ = cute.arch.thread_idx()

        cidx, cidy, _ = cute.arch.cluster_idx()
        cdimx, cdimy, _ = cute.arch.cluster_dim()
        cluster_id = cidx + cdimx * cidy

        # CTA Swizzle促进L2数据重用
        group_size_m = 8
        s_shape = (
            (group_size_m, cdimx // group_size_m),
            cdimy,
        )
        s_stride = ((1, cdimy * group_size_m), group_size_m)
        s_layout = cute.make_layout(s_shape, stride=s_stride)
        num_reg_cids = cute.size(s_shape)
        cid_m, cid_n = s_layout.get_flat_coord(cluster_id % num_reg_cids)

        # 处理尾部部分
        if cluster_id >= num_reg_cids:
            tail_size_m = cdimx % group_size_m
            tail_layout = cute.make_layout(
                (tail_size_m, cdimy), stride=(1, tail_size_m)
            )
            tail_cid = cluster_id - num_reg_cids
            tail_cid_m, tail_cid_n = tail_layout.get_flat_coord(tail_cid)
            cid_m = cute.size(s_shape, mode=[0]) + tail_cid_m
            cid_n = tail_cid_n

        # 从集群id中获取pid
        bidx_in_cluster = cute.arch.block_in_cluster_idx()
        pid_m = cid_m * self.cluster_shape_mn[0] + bidx_in_cluster[0]
        pid_n = cid_n * self.cluster_shape_mn[1] + bidx_in_cluster[1]

        tile_coord_mnkl = (pid_m, pid_n, None, bidz)
        cta_rank_in_cluster = cute.arch.make_warp_uniform(
            cute.arch.block_idx_in_cluster()
        )
        cluster_coord_mnk = cta_layout_mnk.get_flat_coord(cta_rank_in_cluster)

        # ///////////////////////////////////////////////////////////////////////////////
        # 获取 multicast mask
        # ///////////////////////////////////////////////////////////////////////////////
        a_mcast_mask = cute.make_layout_image_mask(
            cta_layout_mnk, cluster_coord_mnk, mode=1
        )
        b_mcast_mask = cute.make_layout_image_mask(
            cta_layout_mnk, cluster_coord_mnk, mode=0
        )

        a_mcast_mask = a_mcast_mask if self.is_a_mcast else 0
        b_mcast_mask = b_mcast_mask if self.is_b_mcast else 0
        a_smem_layout = cute.slice_(a_smem_layout_staged, (None, None, 0))
        b_smem_layout = cute.slice_(b_smem_layout_staged, (None, None, 0))
        tma_copy_bytes = cute.size_in_bytes(
            self.a_dtype, a_smem_layout
        ) + cute.size_in_bytes(self.b_dtype, b_smem_layout)

        # /////////////////////////////////////////////////////////////////////////////
        #  分配和初始化 AB 满/空 + ACC 满 mbar（流水线）
        # /////////////////////////////////////////////////////////////////////////////
        smem = cutlass.utils.SmemAllocator()
        storage = smem.allocate(self.shared_storage)

        # mbar 数组
        mainloop_pipeline_array_ptr = storage.mainloop_pipeline_array_ptr.data_ptr()

        # 参与该流水线的线程/warp
        mainloop_pipeline_producer_group = pipeline.CooperativeGroup(
            pipeline.Agent.Thread
        )
        # 每个 warp 将根据 mcast 大小的数量贡献到达计数
        mcast_size = self.num_mcast_ctas_a + self.num_mcast_ctas_b - 1
        num_warps = self.threads_per_cta // 32
        consumer_arrive_cnt = mcast_size * num_warps
        mainloop_pipeline_consumer_group = pipeline.CooperativeGroup(
            pipeline.Agent.Thread, consumer_arrive_cnt
        )

        cta_layout_vmnk = cute.make_layout((1, *cta_layout_mnk.shape))
        mainloop_pipeline = pipeline.PipelineTmaAsync.create(
            barrier_storage=mainloop_pipeline_array_ptr,
            num_stages=self.ab_stage,
            producer_group=mainloop_pipeline_producer_group,
            consumer_group=mainloop_pipeline_consumer_group,
            tx_count=tma_copy_bytes,
            cta_layout_vmnk=cta_layout_vmnk,
            defer_sync=True,
        )

        #  屏障初始化后集群到达
        pipeline_init_arrive(cluster_shape_mn=self.cluster_shape_mn, is_relaxed=True)

        # ///////////////////////////////////////////////////////////////////////////////
        #  生成 smem 张量 A/B
        # ///////////////////////////////////////////////////////////////////////////////
        sA = storage.sA.get_tensor(
            a_smem_layout_staged.outer, swizzle=a_smem_layout_staged.inner
        )
        sB = storage.sB.get_tensor(
            b_smem_layout_staged.outer, swizzle=b_smem_layout_staged.inner
        )
        sC_ptr = cute.recast_ptr(
            sA.iterator, epi_smem_layout_staged.inner, dtype=self.c_dtype
        )
        sC = cute.make_tensor(sC_ptr, epi_smem_layout_staged.outer)

        # ///////////////////////////////////////////////////////////////////////////////
        #  Local_tile 分区全局张量
        # ///////////////////////////////////////////////////////////////////////////////
        # (bM, bK, RestK)
        gA_mkl = cute.local_tile(
            mA_mkl, self.tile_shape_mnk, tile_coord_mnkl, proj=(1, None, 1)
        )
        # (bN, bK, RestK)
        gB_nkl = cute.local_tile(
            mB_nkl, self.tile_shape_mnk, tile_coord_mnkl, proj=(None, 1, 1)
        )
        # (bM, bN)
        gC_mnl = cute.local_tile(
            mC_mnl, self.tile_shape_mnk, tile_coord_mnkl, proj=(1, 1, None)
        )

        # //////////////////////////////////////////////////////////////////////////////
        #  TiledMMA_A/B/C 的全局张量分区
        # //////////////////////////////////////////////////////////////////////////////
        warp_group_idx = cute.arch.make_warp_uniform(
            tidx // self.num_threads_per_warp_group
        )
        warp_group_thread_layout = cute.make_layout(
            self.mma_warp_groups, stride=self.num_threads_per_warp_group
        )
        thr_mma = tiled_mma.get_slice(warp_group_thread_layout(warp_group_idx))

        tCgC = thr_mma.partition_C(gC_mnl)

        # //////////////////////////////////////////////////////////////////////////////
        #  TMA 加载 A/B 的分区共享张量
        # //////////////////////////////////////////////////////////////////////////////
        #  TMA 加载A partition_S/D
        a_cta_layout = cute.make_layout(cute.slice_(cta_layout_mnk, (0, None, 0)).shape)
        a_cta_crd = cluster_coord_mnk[1]
        sA_for_tma_partition = cute.group_modes(sA, 0, 2)
        gA_for_tma_partition = cute.group_modes(gA_mkl, 0, 2)
        tAsA, tAgA_mkl = cute.nvgpu.cpasync.tma_partition(
            tma_atom_a,
            a_cta_crd,
            a_cta_layout,
            sA_for_tma_partition,
            gA_for_tma_partition,
        )

        # TMA 加载B partition_S/D
        b_cta_layout = cute.make_layout(cute.slice_(cta_layout_mnk, (None, 0, 0)).shape)
        b_cta_crd = cluster_coord_mnk[0]
        sB_for_tma_partition = cute.group_modes(sB, 0, 2)
        gB_for_tma_partition = cute.group_modes(gB_nkl, 0, 2)
        tBsB, tBgB_nkl = cute.nvgpu.cpasync.tma_partition(
            tma_atom_b,
            b_cta_crd,
            b_cta_layout,
            sB_for_tma_partition,
            gB_for_tma_partition,
        )

        # //////////////////////////////////////////////////////////////////////////////
        #  制作fragment
        # //////////////////////////////////////////////////////////////////////////////
        tCsA = thr_mma.partition_A(sA)
        tCsB = thr_mma.partition_B(sB)
        tCrA = tiled_mma.make_fragment_A(tCsA)
        tCrB = tiled_mma.make_fragment_B(tCsB)

        acc_shape = tCgC.shape
        accumulators = cute.make_rmem_tensor(acc_shape, self.acc_dtype)

        # ///////////////////////////////////////////////////////////////////////////////
        #  集群等待
        # ///////////////////////////////////////////////////////////////////////////////
        # 集群等待屏障初始化
        pipeline_init_wait(cluster_shape_mn=self.cluster_shape_mn)
        # /////////////////////////////////////////////////////////////////////////////
        #  预取
        # /////////////////////////////////////////////////////////////////////////////
        k_tile_cnt = cute.size(gA_mkl, mode=[2])
        prefetch_k_tile_cnt = cutlass.max(cutlass.min(self.ab_stage, k_tile_cnt), 0)

        mainloop_producer_state = pipeline.make_pipeline_state(
            pipeline.PipelineUserType.Producer, self.ab_stage
        )
        if warp_idx == 0:
            # /////////////////////////////////////////////////////////////////////////////
            # 预取 TMA 加载
            # /////////////////////////////////////////////////////////////////////////////
            for prefetch_idx in cutlass.range(prefetch_k_tile_cnt, unroll=1):
                # /////////////////////////////////////////////////////////////////////////////
                #  等待 A/B 缓冲区为空后再加载
                #  还设置 A/B 缓冲区的事务屏障
                # /////////////////////////////////////////////////////////////////////////////
                mainloop_pipeline.producer_acquire(mainloop_producer_state)
                # /////////////////////////////////////////////////////////////////////////////
                #  切片到当前 k_tile 的全局/共享 memref
                # /////////////////////////////////////////////////////////////////////////////
                tAgA_k = tAgA_mkl[(None, mainloop_producer_state.count)]
                tAsA_pipe = tAsA[(None, mainloop_producer_state.index)]

                tBgB_k = tBgB_nkl[(None, mainloop_producer_state.count)]
                tBsB_pipe = tBsB[(None, mainloop_producer_state.index)]

                # /////////////////////////////////////////////////////////////////////////////
                #  TMA 加载A/B
                # /////////////////////////////////////////////////////////////////////////////
                cute.copy(
                    tma_atom_a,
                    tAgA_k,
                    tAsA_pipe,
                    tma_bar_ptr=mainloop_pipeline.producer_get_barrier(
                        mainloop_producer_state
                    ),
                    mcast_mask=a_mcast_mask,
                )
                cute.copy(
                    tma_atom_b,
                    tBgB_k,
                    tBsB_pipe,
                    tma_bar_ptr=mainloop_pipeline.producer_get_barrier(
                        mainloop_producer_state
                    ),
                    mcast_mask=b_mcast_mask,
                )
                # Mainloop 流水线的生产者提交是 NOP
                mainloop_pipeline.producer_commit(mainloop_producer_state)
                mainloop_producer_state.advance()

        # /////////////////////////////////////////////////////////////////////////////
        #  序言 MMA
        # /////////////////////////////////////////////////////////////////////////////
        k_pipe_mmas = 1

        mainloop_consumer_read_state = pipeline.make_pipeline_state(
            pipeline.PipelineUserType.Consumer, self.ab_stage
        )
        mainloop_consumer_release_state = pipeline.make_pipeline_state(
            pipeline.PipelineUserType.Consumer, self.ab_stage
        )

        peek_ab_full_status = cutlass.Boolean(1)
        if mainloop_consumer_read_state.count < k_tile_cnt:
            peek_ab_full_status = mainloop_pipeline.consumer_try_wait(
                mainloop_consumer_read_state
            )

        tiled_mma.set(cute.nvgpu.warpgroup.Field.ACCUMULATE, False)
        num_k_blocks = cute.size(tCrA, mode=[2])
        for k_tile in cutlass.range_constexpr(k_pipe_mmas):
            # 等待 A/B 缓冲区准备就绪
            mainloop_pipeline.consumer_wait(
                mainloop_consumer_read_state, peek_ab_full_status
            )

            cute.nvgpu.warpgroup.fence()
            for k_block_idx in cutlass.range(num_k_blocks, unroll_full=True):
                k_block_coord = (
                    None,
                    None,
                    k_block_idx,
                    mainloop_consumer_read_state.index,
                )
                tCrA_1phase = tCrA[k_block_coord]
                tCrB_1phase = tCrB[k_block_coord]

                cute.gemm(
                    tiled_mma,
                    accumulators,
                    tCrA_1phase,
                    tCrB_1phase,
                    accumulators,
                )
                tiled_mma.set(cute.nvgpu.warpgroup.Field.ACCUMULATE, True)

            cute.nvgpu.warpgroup.commit_group()
            mainloop_consumer_read_state.advance()
            peek_ab_full_status = cutlass.Boolean(1)
            if mainloop_consumer_read_state.count < k_tile_cnt:
                peek_ab_full_status = mainloop_pipeline.consumer_try_wait(
                    mainloop_consumer_read_state
                )

        # /////////////////////////////////////////////////////////////////////////////
        #  主循环
        # /////////////////////////////////////////////////////////////////////////////
        for k_tile in cutlass.range(k_pipe_mmas, k_tile_cnt, 1, unroll=1):
            # /////////////////////////////////////////////////////////////////////////////
            #  等待 TMA 拷贝完成
            # /////////////////////////////////////////////////////////////////////////////
            mainloop_pipeline.consumer_wait(
                mainloop_consumer_read_state, peek_ab_full_status
            )
            # /////////////////////////////////////////////////////////////////////////////
            #  WGMMA
            # /////////////////////////////////////////////////////////////////////////////
            cute.nvgpu.warpgroup.fence()
            for k_block_idx in cutlass.range(num_k_blocks, unroll_full=True):
                k_block_coord = (
                    None,
                    None,
                    k_block_idx,
                    mainloop_consumer_read_state.index,
                )
                tCrA_1phase = tCrA[k_block_coord]
                tCrB_1phase = tCrB[k_block_coord]

                cute.gemm(
                    tiled_mma,
                    accumulators,
                    tCrA_1phase,
                    tCrB_1phase,
                    accumulators,
                )

            cute.nvgpu.warpgroup.commit_group()
            # 等待先前 k_pipe_mmas wgmma 的 wgmma 障碍完成
            cute.nvgpu.warpgroup.wait_group(k_pipe_mmas)

            mainloop_pipeline.consumer_release(mainloop_consumer_release_state)

            mainloop_consumer_read_state.advance()
            mainloop_consumer_release_state.advance()

            peek_ab_full_status = cutlass.Boolean(1)
            if mainloop_consumer_read_state.count < k_tile_cnt:
                peek_ab_full_status = mainloop_pipeline.consumer_try_wait(
                    mainloop_consumer_read_state
                )
            # /////////////////////////////////////////////////////////////////////////////
            #  TMA加载
            # /////////////////////////////////////////////////////////////////////////////
            if warp_idx == 0 and mainloop_producer_state.count < k_tile_cnt:
                # /////////////////////////////////////////////////////////////////////////////
                #  等待 A/B 缓冲区为空后再加载
                #  还设置 A/B 缓冲区的事务屏障
                # /////////////////////////////////////////////////////////////////////////////
                mainloop_pipeline.producer_acquire(mainloop_producer_state)

                # /////////////////////////////////////////////////////////////////////////////
                #  切片到当前 k_tile 的全局/共享 memref
                # /////////////////////////////////////////////////////////////////////////////
                tAgA_k = tAgA_mkl[(None, mainloop_producer_state.count)]
                tAsA_pipe = tAsA[(None, mainloop_producer_state.index)]

                tBgB_k = tBgB_nkl[(None, mainloop_producer_state.count)]
                tBsB_pipe = tBsB[(None, mainloop_producer_state.index)]

                # /////////////////////////////////////////////////////////////////////////////
                #  TMA 加载A/B
                # /////////////////////////////////////////////////////////////////////////////
                cute.copy(
                    tma_atom_a,
                    tAgA_k,
                    tAsA_pipe,
                    tma_bar_ptr=mainloop_pipeline.producer_get_barrier(
                        mainloop_producer_state
                    ),
                    mcast_mask=a_mcast_mask,
                )
                cute.copy(
                    tma_atom_b,
                    tBgB_k,
                    tBsB_pipe,
                    tma_bar_ptr=mainloop_pipeline.producer_get_barrier(
                        mainloop_producer_state
                    ),
                    mcast_mask=b_mcast_mask,
                )
                # Mainloop 流水线的生产者提交是 NOP
                mainloop_pipeline.producer_commit(mainloop_producer_state)
                mainloop_producer_state.advance()

        # /////////////////////////////////////////////////////////////////////////////
        #  EPILOG
        # /////////////////////////////////////////////////////////////////////////////
        cute.nvgpu.warpgroup.wait_group(0)

        if cute.size(self.cluster_shape_mn) > 1:
            # 等待集群中所有线程完成，避免提前释放 smem
            cute.arch.cluster_arrive()
            cute.arch.cluster_wait()
        else:
            # 对于具有单个线程块的集群，它可能具有多个warpgroup。
            # 等待线程块中的所有warpgroup完成，因为张量 A 的 smem
            # 主循环在epilogue中被重用。
            cute.arch.sync_threads()

        copy_atom_r2s = sm90_utils.sm90_get_smem_store_op(
            self.c_layout,
            elem_ty_d=self.c_dtype,
            elem_ty_acc=self.acc_dtype,
        )

        copy_atom_C = cute.make_copy_atom(
            cute.nvgpu.warp.StMatrix8x8x16bOp(
                self.c_layout.is_m_major_c(),
                4,
            ),
            self.c_dtype,
        )

        tiled_copy_C_Atom = cute.make_tiled_copy_C_atom(copy_atom_C, tiled_mma)

        tiled_copy_r2s = cute.make_tiled_copy_S(
            copy_atom_r2s,
            tiled_copy_C_Atom,
        )

        # (R2S, R2S_M, R2S_N, PIPE_D)
        thr_copy_r2s = tiled_copy_r2s.get_slice(tidx)
        tRS_sD = thr_copy_r2s.partition_D(sC)
        # (R2S, R2S_M, R2S_N)
        tRS_rAcc = tiled_copy_r2s.retile(accumulators)

        # 分配D寄存器。
        rD_shape = cute.shape(thr_copy_r2s.partition_S(sC))
        tRS_rD_layout = cute.make_layout(rD_shape[:3])
        tRS_rD = cute.make_rmem_tensor_like(tRS_rD_layout, self.acc_dtype)
        size_tRS_rD = cute.size(tRS_rD)

        sepi_for_tma_partition = cute.group_modes(sC, 0, 2)
        tCgC_for_tma_partition = cute.zipped_divide(gC_mnl, self.epi_tile)

        bSG_sD, bSG_gD = cute.nvgpu.cpasync.tma_partition(
            tma_atom_c,
            0,
            cute.make_layout(1),
            sepi_for_tma_partition,
            tCgC_for_tma_partition,
        )

        epi_tile_num = cute.size(tCgC_for_tma_partition, mode=[1])
        epi_tile_shape = tCgC_for_tma_partition.shape[1]
        epi_tile_layout = cute.make_layout(
            epi_tile_shape, stride=(epi_tile_shape[1], 1)
        )

        # 初始化 tma 存储 c_pipeline
        c_producer_group = pipeline.CooperativeGroup(
            pipeline.Agent.Thread, self.threads_per_cta
        )
        c_pipeline = pipeline.PipelineTmaStore.create(
            num_stages=self.epi_stage,
            producer_group=c_producer_group,
        )

        for epi_idx in cutlass.range_constexpr(epi_tile_num):
            # 从累加器拷贝到 D 寄存器
            for epi_v in cutlass.range_constexpr(size_tRS_rD):
                tRS_rD[epi_v] = tRS_rAcc[epi_idx * size_tRS_rD + epi_v]

            # 类型转换
            tRS_rD_out = cute.make_rmem_tensor_like(tRS_rD_layout, self.c_dtype)
            acc_vec = tRS_rD.load()
            tRS_rD_out.store(acc_vec.to(self.c_dtype))

            # 从 D 寄存器拷贝到共享内存
            epi_buffer = epi_idx % cute.size(tRS_sD, mode=[3])
            cute.copy(
                tiled_copy_r2s, tRS_rD_out, tRS_sD[(None, None, None, epi_buffer)]
            )

            cute.arch.fence_proxy(
                "async.shared",
                space="cta",
            )
            # 同步障碍
            pipeline.sync(barrier_id=1)

            gmem_coord = epi_tile_layout.get_hier_coord(epi_idx)
            # 从共享内存拷贝到全局内存
            if warp_idx == 0:
                cute.copy(
                    tma_atom_c,
                    bSG_sD[(None, epi_buffer)],
                    bSG_gD[(None, gmem_coord)],
                )
                c_pipeline.producer_commit()
                c_pipeline.producer_acquire()

            pipeline.sync(barrier_id=1)

        if warp_idx == 0:
            c_pipeline.producer_tail()

        return

    @staticmethod
    def _compute_stages(
        tile_shape_mnk: tuple[int, int, int],
        a_dtype: type[cutlass.Numeric],
        b_dtype: type[cutlass.Numeric],
        smem_capacity: int,
        occupancy: int,
    ) -> tuple[int, int]:
        """根据启发式计算 A/B/C 操作数的阶段数。

        :param tile_shape_mnk: CTA tile的形状（M、N、K）。
        :type tile_shape_mnk: tuple[int, int, int]
        :param a_dtype: 操作数A的数据类型。
        :type a_dtype: type[cutlass.Numeric]
        :param b_dtype: 操作数B的数据类型
        :type b_dtype: type[cutlass.Numeric]
        :param smem_capacity: 可用共享内存总容量（以字节为单位）。
        :type smem_capacity: int
        :param occupancy: 每个 SM 的 CTA 目标数量（占用）。
        :type occupancy: int

        :return: 包含计算的阶段数的元组：
                 （A/B 操作数阶段、epilogue阶段）
        :rtype: tuple[int, int]
        """

        epi_stage = 4
        # epilogue 的 SMEM 将复用 A/B 的 SMEM。
        epi_bytes = 0

        a_shape = cute.slice_(tile_shape_mnk, (None, 0, None))
        b_shape = cute.slice_(tile_shape_mnk, (0, None, None))
        ab_bytes_per_stage = (
            cute.size(a_shape) * a_dtype.width // 8
            + cute.size(b_shape) * b_dtype.width // 8
        )
        mbar_helpers_bytes = 1024

        ab_stage = (
            smem_capacity // occupancy - mbar_helpers_bytes - epi_bytes
        ) // ab_bytes_per_stage
        return ab_stage, epi_stage

    @staticmethod
    def _make_smem_layouts(
        tile_shape_mnk: tuple[int, int, int],
        epi_tile: tuple[int, int],
        a_dtype: type[cutlass.Numeric],
        a_layout: utils.LayoutEnum,
        b_dtype: type[cutlass.Numeric],
        b_layout: utils.LayoutEnum,
        ab_stage: int,
        c_dtype: type[cutlass.Numeric],
        c_layout: utils.LayoutEnum,
        epi_stage: int,
    ) -> tuple[cute.ComposedLayout, cute.ComposedLayout, cute.ComposedLayout]:
        """为 A、B 和 C 张量创建共享内存布局。

        :param tile_shape_mnk: CTA tile形状（M、N、K）
        :type tile_shape_mnk: Tuple[int, int, int]
        :param epi_tile: epiloguetile形状
        :type epi_tile: Tuple[int, int]
        :param a_dtype: 矩阵 A 的数据类型
        :type a_dtype: type[cutlass.Numeric]
        :param a_layout: 矩阵 A 的布局枚举
        :type a_layout: utils.LayoutEnum
        :param b_dtype: 矩阵 B 的数据类型
        :type b_dtype: type[cutlass.Numeric]
        :param b_layout: 矩阵 B 的布局枚举
        :type b_layout: utils.LayoutEnum
        :param ab_stage: A/B 张量的级数
        :type ab_stage: int
        :param c_dtype: 输出矩阵 C 的数据类型
        :type c_dtype: type[cutlass.Numeric]
        :param c_layout: 输出矩阵 C 的布局枚举
        :type c_layout: utils.LayoutEnum
        :param epi_stage: epilogue阶段数
        :type epi_stage: int

        :return: A、B 和 C 的共享内存布局元组
        :rtype: Tuple[cute.ComposedLayout, cute.ComposedLayout, cute.ComposedLayout]
        """
        a_smem_layout_staged = sm90_utils.make_smem_layout_a(
            a_layout,
            tile_shape_mnk,
            a_dtype,
            ab_stage,
        )

        b_smem_layout_staged = sm90_utils.make_smem_layout_b(
            b_layout,
            tile_shape_mnk,
            b_dtype,
            ab_stage,
        )

        epi_smem_layout_staged = sm90_utils.make_smem_layout_epi(
            c_dtype,
            c_layout,
            epi_tile,
            epi_stage,
        )

        return a_smem_layout_staged, b_smem_layout_staged, epi_smem_layout_staged

    @staticmethod
    def _compute_grid(
        c: cute.Tensor,
        tile_shape_mnk: tuple[int, int, int],
        cluster_shape_mn: tuple[int, int],
    ) -> tuple[int, int, int]:
        """计算输出张量 C 的网格形状。

        :param c: 输出张量C
        :type c: cute.Tensor
        :param tile_shape_mnk: CTA tile的形状（M、N、K）。
        :type tile_shape_mnk: tuple[int, int, int]
        :param cluster_shape_mn: M、N 维度中每个簇的形状。
        :type cluster_shape_mn: tuple[int, int]

        :return: 用于内核启动的网格形状。
        :rtype: tuple[int, int, int]
        """

        c_shape = (tile_shape_mnk[0], tile_shape_mnk[1])
        gc = cute.zipped_divide(c, tiler=c_shape)
        cluster_shape_mnl = (*cluster_shape_mn, 1)
        clusters = cute.ceil_div(cute.get(gc.layout, mode=[1]).shape, cluster_shape_mnl)
        grid = tuple(x * y for x, y in zip(clusters, cluster_shape_mnl))
        return grid

    @staticmethod
    def _make_tma_store_atoms_and_tensors(
        tensor_c: cute.Tensor,
        epi_smem_layout_staged: cute.ComposedLayout,
        epi_tile: tuple[int, int],
    ) -> tuple[cute.CopyAtom, cute.Tensor]:
        """创建 TMA 原子和张量用于 C 张量存储。

        :param tensor_c: 输出张量C
        :type tensor_c: cute.Tensor
        :param epi_smem_layout_staged: epilogue的共享内存布局
        :type epi_smem_layout_staged: cute.ComposedLayout
        :param epi_tile: epiloguetile形状
        :type epi_tile: Tuple[int, int]

        :return: TMA C 的原子和张量
        :rtype: 元组[cute.CopyAtom, cute.Tensor]
        """
        epi_smem_layout = cute.slice_(epi_smem_layout_staged, (None, None, 0))
        tma_atom_c, tma_tensor_c = cute.nvgpu.cpasync.make_tiled_tma_atom(
            cute.nvgpu.cpasync.CopyBulkTensorTileS2GOp(),
            tensor_c,
            epi_smem_layout,
            epi_tile,
        )

        return tma_atom_c, tma_tensor_c

    @staticmethod
    def _make_tma_atoms_and_tensors(
        tensor: cute.Tensor,
        smem_layout_staged: cute.ComposedLayout,
        smem_tile: tuple[int, int],
        mcast_dim: int,
    ) -> tuple[cute.CopyAtom, cute.Tensor]:
        """创建 TMA 原子和张量作为输入张量。

        :param tensor: 输入张量（A 或 B）
        :type tensor: cute.Tensor
        :param smem_layout_staged: 张量的共享内存布局
        :type smem_layout_staged: cute.ComposedLayout
        :param smem_tile: 共享内存tile形状
        :type smem_tile: Tuple[int, int]
        :param mcast_dim: 组播维度
        :type mcast_dim: int

        :return: TMA 原子和张量
        :rtype: 元组[cute.CopyAtom, cute.Tensor]
        """
        op = (
            cute.nvgpu.cpasync.CopyBulkTensorTileG2SOp()
            if mcast_dim == 1
            else cute.nvgpu.cpasync.CopyBulkTensorTileG2SMulticastOp()
        )

        smem_layout = cute.slice_(smem_layout_staged, (None, None, 0))
        tma_atom, tma_tensor = cute.nvgpu.cpasync.make_tiled_tma_atom(
            op,
            tensor,
            smem_layout,
            smem_tile,
            num_multicast=mcast_dim,
        )
        return tma_atom, tma_tensor

    @staticmethod
    def is_valid_dtypes(
        a_dtype: Type[cutlass.Numeric],
        b_dtype: Type[cutlass.Numeric],
        acc_dtype: Type[cutlass.Numeric],
        c_dtype: Type[cutlass.Numeric],
        a_major: str,
        b_major: str,
    ) -> bool:
        """
        检查 dtype 是否有效

        :param a_dtype: 张量A的数据类型
        :type a_dtype: Type[cutlass.Numeric]
        :param b_dtype: 张量 B 的数据类型
        :type b_dtype: Type[cutlass.Numeric]
        :param acc_dtype: 累加器的数据类型
        :type acc_dtype: Type[cutlass.Numeric]
        :param c_dtype: 输出张量的数据类型
        :type c_dtype: Type[cutlass.Numeric]
        :param a_major: 张量 A 的主模
        :type a_major: str
        :param b_major: 张量 B 的主模
        :type b_major: str

        :return: 如果数据类型有效则为 True，否则为 False
        :rtype: bool
        """
        is_valid = True

        valid_ab_dtypes = {
            cutlass.Float16,
            cutlass.Float8E4M3FN,
            cutlass.Float8E5M2,
            cutlass.Uint8,
            cutlass.Int8,
        }
        if a_dtype not in valid_ab_dtypes:
            is_valid = False
        if b_dtype not in valid_ab_dtypes:
            is_valid = False

        # 确保 Float16 的 a_dtype == b_dtype
        if a_dtype.width == 16 and a_dtype != b_dtype:
            is_valid = False
        if a_dtype.width != b_dtype.width:
            is_valid = False
        if not a_dtype.is_same_kind(b_dtype):
            is_valid = False

        # 对于 8 位类型，此实现仅支持 k major布局
        if (a_dtype.width == 8 and a_major != "k") or (
            b_dtype.width == 8 and b_major != "k"
        ):
            is_valid = False

        # 定义累加器类型和 AB 类型之间的兼容性映射
        acc_ab_compatibility = {
            cutlass.Float32: {
                cutlass.Float16,
                cutlass.Float8E4M3FN,
                cutlass.Float8E5M2,
            },
            cutlass.Float16: {
                cutlass.Float16,
                cutlass.Float8E4M3FN,
                cutlass.Float8E5M2,
            },
            cutlass.Int32: {cutlass.Uint8, cutlass.Int8},
        }
        # 检查累加器类型和 A 型之间的兼容性
        if a_dtype not in acc_ab_compatibility[acc_dtype]:
            is_valid = False

        # 定义累加器类型和 C 类型之间的兼容性映射
        acc_c_compatibility = {
            cutlass.Float32: {
                cutlass.Float32,
                cutlass.Float16,
                cutlass.Float8E4M3FN,
                cutlass.Float8E5M2,
            },
            cutlass.Float16: {
                cutlass.Float32,
                cutlass.Float16,
                cutlass.Float8E4M3FN,
                cutlass.Float8E5M2,
            },
            cutlass.Int32: {
                cutlass.Float32,
                cutlass.Float16,
                cutlass.Int32,
                cutlass.Int8,
                cutlass.Uint8,
            },
        }
        # 检查累加器类型和 C 类型之间的兼容性
        if c_dtype not in acc_c_compatibility[acc_dtype]:
            is_valid = False

        return is_valid

    @staticmethod
    def is_valid_tensor_alignment(
        m: int,
        n: int,
        k: int,
        l: int,
        ab_dtype: Type[cutlass.Numeric],
        c_dtype: Type[cutlass.Numeric],
        a_major: str,
        b_major: str,
        c_major: str,
    ) -> bool:
        """
        检查张量对齐是否有效

        :param m: A 张量中的行数
        :type m: int
        :param n: B 张量中的列数
        :type n: int
        :param k: A 张量中的列数
        :type k: int
        :param l: C 张量中的列数
        :type l: int
        :param ab_dtype: A和B操作数的数据类型
        :type ab_dtype: Type[cutlass.Numeric]
        :param c_dtype: 输出张量的数据类型
        :type c_dtype: Type[cutlass.Numeric]
        :param a_major: A 张量的长轴
        :type a_major: str
        :param b_major: B 张量的长轴
        :type b_major: str
        :param c_major: C 张量的长轴
        :type c_major: str

        :return: 如果问题形状有效则为 True，否则为 False
        :rtype: bool
        """
        is_valid = True

        def check_contigous_16B_alignment(dtype, is_mode0_major, tensor_shape):
            major_mode_idx = 0 if is_mode0_major else 1
            num_major_elements = tensor_shape[major_mode_idx]
            num_contiguous_elements = 16 * 8 // dtype.width
            return num_major_elements % num_contiguous_elements == 0

        if (
            not check_contigous_16B_alignment(ab_dtype, a_major == "m", (m, k, l))
            or not check_contigous_16B_alignment(ab_dtype, b_major == "n", (n, k, l))
            or not check_contigous_16B_alignment(c_dtype, c_major == "m", (m, n, l))
        ):
            is_valid = False
        return is_valid


def run(
    mnkl: Tuple[int, int, int, int],
    a_dtype: Type[cutlass.Numeric],
    b_dtype: Type[cutlass.Numeric],
    c_dtype: Type[cutlass.Numeric],
    acc_dtype: Type[cutlass.Numeric],
    a_major: str,
    b_major: str,
    c_major: str,
    tile_shape_mn: Tuple[int, int],
    cluster_shape_mn: Tuple[int, int],
    tolerance: float,
    warmup_iterations: int,
    iterations: int,
    skip_ref_check: bool,
    use_cold_l2: bool = False,
    **kwargs,
):
    """
    准备 A/B/C 张量，启动 GPU 内核，并进行参考检查。

    :param mnkl: 问题规模（M、N、K、L）
    :type mnkl: Tuple[int, int, int, int]
    :param a_dtype: 输入张量 A 的数据类型
    :type a_dtype: Type[cutlass.Numeric]
    :param b_dtype: 输入张量 B 的数据类型
    :type b_dtype: Type[cutlass.Numeric]
    :param c_dtype: 输出张量 C 的数据类型
    :type c_dtype: Type[cutlass.Numeric]
    :param acc_dtype: 矩阵乘法期间累加的数据类型
    :type acc_dtype: Type[cutlass.Numeric]
    :param a_major/b_major/c_major: 张量A/B/C的内存布局
    :type a_major/b_major/c_major: str
    :param tile_shape_mn: CTA tile形状（M、N）
    :type tile_shape_mn: Tuple[int, int]
    :param cluster_shape_mn: 簇形状（M、N）
    :type cluster_shape_mn: Tuple[int, int]
    :param tolerance: 参考验证比较的公差值
    :type tolerance: float
    :param warmup_iterations: 基准测试前的预热迭代次数，默认为 0
    :type warmup_iterations: int, optional
    :param iterations: 要运行的基准测试迭代次数，默认为 1
    :type iterations: int, optional
    :param skip_ref_check: 是否跳过参考结果验证，默认为False
    :type skip_ref_check: bool, optional
    :param use_cold_l2: 是否使用循环缓冲策略保证L2冷缓存，默认为False
    :type use_cold_l2: bool, optional
    :return: GEMM 内核的执行时间（以微秒为单位）
    :rtype: float
    """

    import torch
    import cutlass.torch as cutlass_torch

    print("Running Hopper Dense GEMM with:")
    print(f"mnkl: {mnkl}")
    print(
        f"A dtype: {a_dtype}, B dtype: {b_dtype}, C dtype: {c_dtype}, Acc dtype: {acc_dtype}"
    )
    print(f"Matrix majors - A: {a_major}, B: {b_major}, C: {c_major}")
    print(f"Tile Shape: {tile_shape_mn}, Cluster Shape: {cluster_shape_mn}")
    print(f"Tolerance: {tolerance}")
    print(f"Warmup iterations: {warmup_iterations}")
    print(f"Iterations: {iterations}")
    print(f"Skip reference checking: {skip_ref_check}")
    print(f"Use cold L2: {use_cold_l2}")

    # 解包参数
    m, n, k, l = mnkl

    if not HopperWgmmaGemmKernel.is_valid_dtypes(
        a_dtype, b_dtype, acc_dtype, c_dtype, a_major, b_major
    ):
        raise TypeError(
            f"unsupported combination of types and majors: A {a_dtype}, B {b_dtype}, Acc {acc_dtype}, C {c_dtype}, {a_major=}, {b_major=}"
        )
    if not HopperWgmmaGemmKernel.is_valid_tensor_alignment(
        m, n, k, l, a_dtype, c_dtype, a_major, b_major, c_major
    ):
        raise TypeError(
            "the contiguous dimension of A/B/C tensors is not 16 bytes aligned"
        )

    if not torch.cuda.is_available():
        raise RuntimeError("GPU is required to run this example!")

    torch.manual_seed(1111)

    # 创建并排列张量 A/B/C
    def create_and_permute_tensor(
        l, mode0, mode1, is_mode0_major, dtype, is_dynamic_layout=True
    ):
        # is_mode0_major: (l, mode1, mode0) -> (mode0, mode1, l)
        # else : (l, mode0, mode1) -> (mode0, mode1, l)
        shape = (l, mode1, mode0) if is_mode0_major else (l, mode0, mode1)
        permute_order = (2, 1, 0) if is_mode0_major else (1, 2, 0)
        is_unsigned = dtype in {cutlass.Uint8}
        # 由于torch不支持fp8类型，暂时使用uint8
        torch_dtype = (
            cutlass_torch.dtype(dtype)
            if dtype not in {cutlass.Float8E5M2, cutlass.Float8E4M3FN}
            else torch.uint8
        )

        # 创建 dtype PyTorch张量（CPU）
        torch_tensor_cpu = cutlass.torch.create_and_permute_torch_tensor(
            shape,
            torch_dtype,
            permute_order=permute_order,
            init_type=cutlass.torch.TensorInitType.RANDOM,
            init_config=cutlass.torch.RandomInitConfig(
                min_val=0 if is_unsigned else -2, max_val=4 if is_unsigned else 2
            ),
        )
        # 创建 dtype PyTorch张量（GPU）
        torch_tensor = torch_tensor_cpu.cuda()

        # 创建 f32 torch 张量（cpu）
        f32_torch_tensor = torch_tensor_cpu.to(dtype=torch.float32)

        # 创建 dtype CuTe张量（GPU）
        cute_tensor = from_dlpack(torch_tensor, assumed_align=16)
        cute_tensor.element_type = dtype
        if is_dynamic_layout:
            cute_tensor = cute_tensor.mark_layout_dynamic(
                leading_dim=(0 if is_mode0_major else 1)
            )
        cute_tensor = cutlass.torch.convert_cute_tensor(
            f32_torch_tensor,
            cute_tensor,
            dtype,
            is_dynamic_layout=is_dynamic_layout,
        )

        return f32_torch_tensor, cute_tensor, torch_tensor

    a, mA, a_torch = create_and_permute_tensor(l, m, k, a_major == "m", a_dtype)
    b, mB, b_torch = create_and_permute_tensor(l, n, k, b_major == "n", b_dtype)
    c, mC, c_torch = create_and_permute_tensor(l, m, n, c_major == "m", c_dtype)

    gemm = HopperWgmmaGemmKernel(acc_dtype, tile_shape_mn, cluster_shape_mn)

    torch_stream = torch.cuda.current_stream()
    stream = cuda.CUstream(torch_stream.cuda_stream)
    # 编译gemm内核
    compiled_gemm = cute.compile(gemm, mA, mB, mC, stream)

    if not skip_ref_check:
        # execution
        compiled_gemm(mA, mB, mC, stream)

        torch.cuda.synchronize()

        # 参考检查
        ref = (torch.einsum("mkl,nkl->mnl", a, b)).cpu()

        if c_dtype in (cutlass.Float8E4M3FN, cutlass.Float8E5M2):
            # m major: (l, n, m) -> (m, n, l)
            # n major: (l, m, n) -> (m, n, l)
            permute_order = (1, 2, 0) if c_major == "n" else (2, 1, 0)
            shape = (l, m, n) if c_major == "n" else (l, n, m)
            f8_torch_tensor = cutlass_torch.create_and_permute_torch_tensor(
                shape,
                torch.uint8,
                permute_order=permute_order,
                init_type=cutlass_torch.TensorInitType.SKIP,
            ).cuda()
            # 创建 dtype CuTe张量（GPU）
            ref_c_tensor = from_dlpack(
                f8_torch_tensor, assumed_align=16
            ).mark_layout_dynamic(leading_dim=(1 if c_major == "n" else 0))
            ref_c_tensor.element_type = c_dtype
            ref_c_tensor = cutlass_torch.convert_cute_tensor(
                ref,
                ref_c_tensor,
                c_dtype,
                is_dynamic_layout=True,
            )
            ref_c = f8_torch_tensor.cpu()
        else:
            ref_c = ref.to(cutlass_torch.dtype(c_dtype))

        torch.testing.assert_close(c_torch.cpu(), ref_c, atol=tolerance, rtol=1e-03)

    def generate_tensors():
        _, mA_workspace, _ = create_and_permute_tensor(l, m, k, a_major == "m", a_dtype)
        _, mB_workspace, _ = create_and_permute_tensor(l, n, k, b_major == "n", b_dtype)
        _, mC_workspace, _ = create_and_permute_tensor(l, m, n, c_major == "m", c_dtype)
        return testing.JitArguments(mA_workspace, mB_workspace, mC_workspace, stream)

    workspace_count = 1
    if use_cold_l2:
        one_workspace_bytes = (
            a_torch.numel() * a_torch.element_size()
            + b_torch.numel() * b_torch.element_size()
            + c_torch.numel() * c_torch.element_size()
        )
        workspace_count = testing.get_workspace_count(
            one_workspace_bytes, warmup_iterations, iterations
        )

    exec_time = testing.benchmark(
        compiled_gemm,
        workspace_generator=generate_tensors,
        workspace_count=workspace_count,
        stream=stream,
        warmup_iterations=warmup_iterations,
        iterations=iterations,
    )

    return exec_time  # 返回执行时间（以微秒为单位）


if __name__ == "__main__":
    args = parse_arguments()
    run(
        args.mnkl,
        args.a_dtype,
        args.b_dtype,
        args.c_dtype,
        args.acc_dtype,
        args.a_major,
        args.b_major,
        args.c_major,
        args.tile_shape_mn,
        args.cluster_shape_mn,
        args.tolerance,
        args.warmup_iterations,
        args.iterations,
        args.skip_ref_check,
        args.use_cold_l2,
    )
    print("PASS")
