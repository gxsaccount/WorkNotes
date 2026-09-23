/***************************************************************************************************
 * Copyright (c) 2023 - 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice, this
 * list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 * this list of conditions and the following disclaimer in the documentation
 * and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
 * FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 * CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
 * OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 **************************************************************************************************/
#include <cstdlib>
#include <cstdio>
#include <cassert>

#include <thrust/host_vector.h>
#include <thrust/device_vector.h>

#include <cute/tensor.hpp>

#include "cutlass/util/print_error.hpp"
#include "cutlass/util/GPU_Clock.hpp"
#include "reference_check.hpp"
#include "cutlass/util/helper_cuda.hpp"

template <class ProblemShape, class CtaTiler,
          class TA, class AStride, class ASmemLayout, class TiledCopyA,
          class TB, class BStride, class BSmemLayout, class TiledCopyB,
          class TC, class CStride, class CSmemLayout, class TiledMma,
          class Alpha, class Beta>
__global__ static
__launch_bounds__(decltype(size(TiledMma{}))::value)
void
gemm_device(ProblemShape shape_MNK, CtaTiler cta_tiler,
            TA const* A, AStride dA, ASmemLayout sA_layout, TiledCopyA copy_a,
            TB const* B, BStride dB, BSmemLayout sB_layout, TiledCopyB copy_b,
            TC      * C, CStride dC, CSmemLayout          , TiledMma mma,
            Alpha alpha, Beta beta)
{
  using namespace cute;

  // 前置条件
  CUTE_STATIC_ASSERT_V(rank(shape_MNK) == Int<3>{});                   // (M, N, K)
  CUTE_STATIC_ASSERT_V(rank(cta_tiler) == Int<3>{});                   // (BLK_M, BLK_N, BLK_K)

  CUTE_STATIC_ASSERT_V(size(copy_a) == size(mma));                     // 线程总数
  CUTE_STATIC_ASSERT_V(size(copy_b) == size(mma));                     // 线程总数

  static_assert(is_static<ASmemLayout>::value);
  static_assert(is_static<BSmemLayout>::value);
  static_assert(is_static<CSmemLayout>::value);

  CUTE_STATIC_ASSERT_V(size<0>(ASmemLayout{}) == size<0>(cta_tiler));  // BLK_M
  CUTE_STATIC_ASSERT_V(size<0>(CSmemLayout{}) == size<0>(cta_tiler));  // BLK_M
  CUTE_STATIC_ASSERT_V(size<0>(BSmemLayout{}) == size<1>(cta_tiler));  // BLK_N
  CUTE_STATIC_ASSERT_V(size<1>(CSmemLayout{}) == size<1>(cta_tiler));  // BLK_N
  CUTE_STATIC_ASSERT_V(size<1>(ASmemLayout{}) == size<2>(cta_tiler));  // BLK_K
  CUTE_STATIC_ASSERT_V(size<1>(BSmemLayout{}) == size<2>(cta_tiler));  // BLK_K

  CUTE_STATIC_ASSERT_V(congruent(select<0,2>(shape_MNK), dA));         // dA 的 Stride 必须与 MK Shape 兼容
  CUTE_STATIC_ASSERT_V(congruent(select<1,2>(shape_MNK), dB));         // dB 的 Stride 必须与 NK Shape 兼容
  CUTE_STATIC_ASSERT_V(congruent(select<0,1>(shape_MNK), dC));         // dC 的 Stride 必须与 MN Shape 兼容

  //
  // 完整 Tensor 与分块 Tensor
  //

  // 构造完整矩阵 Tensor
  Tensor mA = make_tensor(make_gmem_ptr(A), select<0,2>(shape_MNK), dA); // (M,K)
  Tensor mB = make_tensor(make_gmem_ptr(B), select<1,2>(shape_MNK), dB); // (N,K)
  Tensor mC = make_tensor(make_gmem_ptr(C), select<0,1>(shape_MNK), dC); // (M,N)

  // 取得当前 thread block 对应的矩阵块
  auto cta_coord = make_coord(blockIdx.x, blockIdx.y, _);              // (m,n,k)
  Tensor gA = local_tile(mA, cta_tiler, cta_coord, Step<_1, X,_1>{});  // (BLK_M,BLK_K,k)
  Tensor gB = local_tile(mB, cta_tiler, cta_coord, Step< X,_1,_1>{});  // (BLK_N,BLK_K,k)
  Tensor gC = local_tile(mC, cta_tiler, cta_coord, Step<_1,_1, X>{});  // (BLK_M,BLK_N)

  // 共享内存缓冲区。
  // cosize_v<Layout> 会在编译期计算覆盖 Layout 所有物理 offset 所需的数组容量，
  // 因此即使 Layout 含有 padding 或空洞也不会越界；容量单位是元素而不是字节。
  __shared__ TA smemA[cosize_v<ASmemLayout>];
  __shared__ TB smemB[cosize_v<BSmemLayout>];
  Tensor sA = make_tensor(make_smem_ptr(smemA), sA_layout);            // (BLK_M,BLK_K)
  Tensor sB = make_tensor(make_smem_ptr(smemB), sB_layout);            // (BLK_N,BLK_K)

  //
  // 将 A、B tile 的搬运任务划分到各线程
  //

  // 教程：使用 TiledCopy 进行分区。
  // copy_a/copy_b 由 Host 端构造并传入，内部包含：
  //   1. Copy Atom：一次 copy 使用什么指令、处理多少个 value；
  //   2. Thread Layout：线程怎样分布在 copy tile 上；
  //   3. Value Layout：每线程的一条 Copy Atom 负责哪些 value。
  //
  // gemm_device 是泛型 kernel，本身没有固定使用 128-bit copy。
  // gemm_nt 与 gemm_tn 会传入不同类型的 copyA/copyB，编译器据此生成两个
  // 不同的 gemm_device 模板实例：
  //
  //   NT 路径：
  //     copy_a/copy_b = 128-bit UniversalCopy
  //     Thread Layout = 32x8，Value Layout = 4x1
  //     A 的 M mode、B 的 N mode 都是 stride=1；同一线程取得的 4 个 value
  //     在 global memory 中连续，因此可以组合成一次 128-bit load。
  //     gA/gB tile = 128x8，因此每线程结果为：
  //       tAgA/tBgB = (CPY=4, CPY_M/N=1, CPY_K=1, k)
  //       tAsA/tBsB = (CPY=4, CPY_M/N=1, CPY_K=1)
  //
  //   TN 路径：
  //     copy_a/copy_b = 标量 UniversalCopy<T>
  //     Thread Layout = 32x8 K-major，Value Layout = 1x1
  //     A/B 的 K mode 虽然连续，但当前 Thread Layout 已把连续 K 坐标分给
  //     不同线程；同一线程在 M/N 方向重复取得的 4 个 value 相隔 ldA/ldB，
  //     不能直接套用 NT 的 4x1 uint128_t vector load。
  //     gA/gB tile = 128x8，Thread Layout 会在 M/N 方向重复 4 次：
  //       tAgA/tBgB = (CPY=1, CPY_M/N=4, CPY_K=1, k)
  //       tAsA/tBsB = (CPY=1, CPY_M/N=4, CPY_K=1)
  //     TN 并非永远不能使用 128-bit copy；若重新设计为同一线程沿 K 取得
  //     连续 value，并同时调整线程布局、目标布局和对齐约束，也可以向量化。
  //
  // Host 端变量名是 copyA/copyB，传入 kernel 后对应形参 copy_a/copy_b。

  // 从完整 TiledCopy 中取出 threadIdx.x 对应的每线程 copy 对象。
  ThrCopy thr_copy_a = copy_a.get_slice(threadIdx.x);
  // partition_S：按 Copy Atom 的 Source TV Layout 划分源 Tensor，
  // 得到当前线程应从 global A 的哪些位置读取；这里只创建 nonowning view。
  Tensor tAgA = thr_copy_a.partition_S(gA);                            // (CPY,CPY_M,CPY_K,k)
  // partition_D：按 Copy Atom 的 Destination TV Layout 划分目标 Tensor，
  // 得到当前线程应向 shared A 的哪些位置写入；这里只创建 nonowning view。
  // 普通 UniversalCopy 的 S/D 映射通常相同，但硬件 Copy Atom 可能不同。
  Tensor tAsA = thr_copy_a.partition_D(sA);                            // (CPY,CPY_M,CPY_K)
  // 分配与目标分区 Shape/Layout 相同的 owning register Tensor。
  // 后续先执行 global → register，再执行 register → shared。
  // 普通的 direct global → shared copy（非 cp.async）在机器指令层通常也会拆成
  // LDG：global → 临时寄存器，再由 STS：临时寄存器 → shared。
  // 显式 tArA 的区别是延长寄存器数据的生命周期：先预取下一 tile，中间执行
  // 与 tArA 无数据依赖的当前 GEMM，下一轮才将 tArA 写入 shared。
  // 如果寄存器压力过大，编译器可能把部分值 spill 到 local memory，导致额外
  // device-memory load/store，并削弱这种 register staging 的收益。
  Tensor tArA = make_fragment_like(tAsA);                              // (CPY,CPY_M,CPY_K)

  ThrCopy thr_copy_b = copy_b.get_slice(threadIdx.x);
  // B 使用相同流程：partition_S 决定从哪里读，partition_D 决定向哪里写。
  Tensor tBgB = thr_copy_b.partition_S(gB);                            // (CPY,CPY_N,CPY_K,k)
  Tensor tBsB = thr_copy_b.partition_D(sB);                            // (CPY,CPY_N,CPY_K)
  // 分配 B 的 owning register staging Tensor。
  Tensor tBrB = make_fragment_like(tBsB);                              // (CPY,CPY_N,CPY_K)

  CUTE_STATIC_ASSERT_V(size<1>(tAgA) == size<1>(tAsA));                // CPY_M
  CUTE_STATIC_ASSERT_V(size<1>(tAgA) == size<1>(tArA));                // CPY_M
  CUTE_STATIC_ASSERT_V(size<2>(tAgA) == size<2>(tAsA));                // CPY_K
  CUTE_STATIC_ASSERT_V(size<2>(tAgA) == size<2>(tArA));                // CPY_K
  CUTE_STATIC_ASSERT_V(size<1>(tBgB) == size<1>(tBsB));                // CPY_N
  CUTE_STATIC_ASSERT_V(size<1>(tBgB) == size<1>(tBrB));                // CPY_N
  CUTE_STATIC_ASSERT_V(size<2>(tBgB) == size<2>(tBsB));                // CPY_K
  CUTE_STATIC_ASSERT_V(size<2>(tBgB) == size<2>(tBrB));                // CPY_K

  // 预取 k_tile=0：gmem → rmem
  copy(copy_a, tAgA(_,_,_,0), tArA);
  copy(copy_b, tBgB(_,_,_,0), tBrB);
  //
  // 定义 A/B 的计算分区与 C accumulator
  //

  // 教程：使用 TiledMMA 进行计算分区。
  // mma 由 Host 端构造并传入，内部包含：
  //   1. MMA Atom：使用什么乘加指令，以及单个 Atom 的 A/B/C TV Layout；
  //   2. Atom Thread Layout：多少个 Atom 怎样铺到 M/N/K 和线程上；
  //   3. 可选的 MNK tile/permutation：最终逻辑 tile 的大小和坐标顺序。
  //
  // 当前 sgemm_2 的 NT/TN 路径都传入：
  //   MMA Atom = UniversalFMA<TC,TA,TB>，Shape_MNK=1x1x1，每个 Atom 使用 1 个线程；
  //   Atom Thread Layout = 16x16x1，共 256 个线程；
  //   自然 TiledMMA tile = 16x16x1。
  //
  // 当前 CTA tile 为 128x128x8，因此 16x16x1 的线程/Atom 模式会在 value
  // 方向重复，得到每线程的具体分区：
  //   tCsA = (MMA=1, MMA_M=128/16=8, MMA_K=8/1=8)
  //   tCsB = (MMA=1, MMA_N=128/16=8, MMA_K=8/1=8)
  //   tCgC = (MMA=1, MMA_M=128/16=8, MMA_N=128/16=8)
  //
  // 与 copy_a 类似，gemm_device 是泛型 kernel；如果 Host 改传 Tensor Core
  // TiledMMA，MMA mode 大小、每线程 fragment 和 lane 映射会随类型一起改变。

  // 从完整 TiledMMA 中取出 threadIdx.x 对应的每线程计算对象。
  ThrMMA thr_mma = mma.get_slice(threadIdx.x);
  // partition_A：按 MMA 的 A TV Layout，从 shared A 得到当前线程所需的 A view。
  Tensor tCsA = thr_mma.partition_A(sA);                               // (MMA,MMA_M,MMA_K)
  // partition_B：按 MMA 的 B TV Layout，从 shared B 得到当前线程所需的 B view。
  Tensor tCsB = thr_mma.partition_B(sB);                               // (MMA,MMA_N,MMA_K)
  // partition_C：按 MMA 的 C TV Layout，从 global C 得到当前线程负责的 C view。
  // 上述 partition 都只创建 nonowning view，不会搬运数据或执行乘加。
  Tensor tCgC = thr_mma.partition_C(gC);                               // (MMA,MMA_M,MMA_N)

  // 创建符合 MMA accumulator 类型与 Layout 要求的 owning register Tensor。
  // 当前 UniversalFMA 配置下实际 Shape 为 (1,8,8)，共 64 个 accumulator。
  Tensor tCrC = thr_mma.make_fragment_C(tCgC);                         // (MMA,MMA_M,MMA_N)

  CUTE_STATIC_ASSERT_V(  shape(tCrC) ==   shape(tCgC));                // (MMA,MMA_M,MMA_N)
  CUTE_STATIC_ASSERT_V(size<1>(tCgC) == size<1>(tCsA));                // MMA_M
  CUTE_STATIC_ASSERT_V(size<2>(tCgC) == size<1>(tCsB));                // MMA_N
  CUTE_STATIC_ASSERT_V(size<2>(tCsA) == size<2>(tCsB));                // MMA_K

  // 清零 accumulator
  clear(tCrC);

#if 0
  if(thread0()) {
    print("  mA : "); print(  mA); print("\n");
    print("  gA : "); print(  gA); print("\n");
    print("  sA : "); print(  sA); print("\n");
    print("tAgA : "); print(tAgA); print("\n");
    print("tAsA : "); print(tAsA); print("\n");
    print("tArA : "); print(tArA); print("\n");
  }
#endif

#if 0
  if(thread0()) {
    print("  mB : "); print(  mB); print("\n");
    print("  gB : "); print(  gB); print("\n");
    print("  sB : "); print(  sB); print("\n");
    print("tBgB : "); print(tBgB); print("\n");
    print("tBsB : "); print(tBsB); print("\n");
    print("tBrB : "); print(tBrB); print("\n");
  }
#endif

#if 0
  if(thread0()) {
    print("  mC : "); print(  mC); print("\n");
    print("  gC : "); print(  gC); print("\n");
    print("tCsA : "); print(tCsA); print("\n");
    print("tCsB : "); print(tCsB); print("\n");
    print("tCgC : "); print(tCgC); print("\n");
    print("tCrC : "); print(tCrC); print("\n");
  }
#endif

#if 1

  // 教程：将计算与读取重叠的内层流水循环
  //           数据从 global memory 经 register 和 shared memory 分级暂存
  //   数据先从 global 读到 register，再通过 TiledCopy 分区写入 shared
  //   gemm(.) 通过 TiledMMA 分区直接使用 shared memory

  auto K_TILE_MAX = size<3>(tAgA); // = 64

  for (int k_tile = 0; k_tile < K_TILE_MAX; ++k_tile)
  {
    // 使用按 tA/tB 分区的 Tensor 将 rmem 搬到 smem
    __syncthreads();         // 等待所有线程使用完当前 smem 数据
    copy(tArA, tAsA);
    copy(tBrB, tBsB);
    __syncthreads();         // 等待所有线程完成新一轮 smem 写入

    // 本版本没有 cp_async_fence/wait：
    //   copy_a 执行普通 gmem → rmem load；
    //   上面的 copy 执行普通 rmem → smem store。
    // 两步都没有创建 cp.async transaction group，因此无需 commit/wait。
    // __syncthreads() 仍然必须保留，用于协调 CTA 内所有线程对 smem 的读写。
    //
    // 简单理解普通 load 的“预取”：
    //   发出 LDG 后，数据可能仍在内存系统中传输；
    //   只有后续指令与 tArA/tBrB 没有数据依赖，才有机会继续执行；
    //   当前 GEMM 只读取 sA/sB 并更新 tCrC，不读取 tArA/tBrB，所以满足条件；
    //   下一轮真正读取 tArA/tBrB 时，若数据还没到，scoreboard 才会让线程等待。
    // 这只是为延迟重叠创造机会，不是 cp.async，也不保证一定完全隐藏延迟。

    // 使用按 tA/tB 分区的 Tensor 预取下一 k_tile：gmem → rmem
    int k_tile_next = (k_tile + 1 < K_TILE_MAX) ? k_tile + 1 : k_tile;
    copy(copy_a, tAgA(_,_,_,k_tile_next), tArA);
    copy(copy_b, tBgB(_,_,_,k_tile_next), tBrB);
    // 教程：上面的 copy(copy_a, tAgA(_,_,_,k_tile_next), tArA) 等价于
    //   CUTE_UNROLL
    //   for (int k = 0; k < size<1>(tCsA); ++k) {
    //     CUTE_UNROLL
    //     for (int m = 0; m < size<0>(tCrC); ++m) {
    //       copy_a.call(tAgA(_,m,k), tArA(_,m,k);
    //     }
    //   }

    // 在按 MMA 分区的 smem 上执行 GEMM
    // tCsA: (1,8,8) // MMA,M,K
    // tCsB: (1,8,8) // MMA,N,K
    // tCrC: (1,8,8) // MMA,M,N
    gemm(mma, tCsA, tCsB, tCrC);
    // 教程：上面的 gemm(tCsA, tCsB, tCrC) 等价于
    //   CUTE_UNROLL
    //   for (int k = 0; k < size<1>(tCsA); ++k) {
    //     CUTE_UNROLL
    //     for (int m = 0; m < size<0>(tCrC); ++m) {
    //       CUTE_UNROLL
    //       for (int n = 0; n < size<1>(tCrC); ++n) {
    //         mma.call(tCsA(_,m,k), tCsB(_,n,k), tCrC(_,m,n);
    //       }
    //     }
    //   }
  }

#endif

  //
  // Epilogue：将 accumulator 写回 C
  //

  axpby(alpha, tCrC, beta, tCgC);
}

// 设置 NT GEMM 参数
template <class TA, class TB, class TC,
          class Alpha, class Beta>
void
gemm_nt(int m, int n, int k,
        Alpha alpha,
        TA const* A, int ldA,
        TB const* B, int ldB,
        Beta beta,
        TC      * C, int ldC,
        cudaStream_t stream = 0)
{
  using namespace cute;

  // 定义动态 Shape
  auto M = int(m);
  auto N = int(n);
  auto K = int(k);
  auto prob_shape = make_shape(M, N, K);                     // (M, N, K)

  // 定义 NT 的混合静态/动态 Stride
  // 哪个 mode 的 stride 为 1，哪个 mode 就在物理内存中连续。
  auto dA = make_stride(Int<1>{}, ldA);                      // (dM,dK)：M mode stride=1，M 连续（M-major）
  auto dB = make_stride(Int<1>{}, ldB);                      // (dN,dK)：N mode stride=1，N 连续（N-major）
  auto dC = make_stride(Int<1>{}, ldC);                      // (dM,dN)：M mode stride=1，M 连续（M-major）

  // 定义静态 CTA tile 大小
  auto bM = Int<128>{};
  auto bN = Int<128>{};
  auto bK = Int<  8>{};
  auto cta_tiler = make_shape(bM, bN, bK);                   // (BLK_M, BLK_N, BLK_K)

  // 定义静态 shared-memory Layout
  auto sA = make_layout(make_shape(bM, bK));                 // (m,k) -> smem 下标; M-major
  auto sB = make_layout(make_shape(bN, bK));                 // (n,k) -> smem 下标; N-major
  auto sC = make_layout(make_shape(bM, bN));                 // (m,n) -> smem 下标; M-major

  // 定义静态线程 Layout

  // 教程：使用指定 Copy_Atom 构造 TiledCopy，并定义分区模式。
  //
  // copyA/copyB 的三部分：
  //   Copy_Atom<UniversalCopy<uint128_t>, T>：
  //     将 4 个 32-bit float 组合为一次 128-bit global → register copy。
  //   Thread Layout 32x8：
  //     共 256 个线程位置，分别铺在 M/N 与 K 方向。
  //   Value Layout 4x1：
  //     每线程的一条 Copy Atom 在 M/N 方向搬 4 个 value，K 方向搬 1 个。
  //
  // 对 128x8 的 A/B tile：
  //   M/N 覆盖 = 32 threads * 4 values = 128
  //   K 覆盖   =  8 threads * 1 value  = 8
  // 因此每个线程每个 K tile 负责 4x1 个元素；这是一种设计选择，并非唯一布局。
  //
  // 为什么这里能用 128-bit：
  //   A(M,K):(1,ldA) 的 M mode 连续，4x1 的四个 A value 地址连续；
  //   B(N,K):(1,ldB) 的 N mode 连续，4x1 的四个 B value 地址连续。
  // 因而同一线程可以将四个 float 合并成一个 uint128_t load。

  TiledCopy copyA = make_tiled_copy(Copy_Atom<UniversalCopy<uint128_t>, TA>{},
                                    Layout<Shape<_32,_8>>{},  // 线程 Layout 32x8 M-major
                                    Layout<Shape< _4,_1>>{}); // 值 Layout 4x1 M-major
  TiledCopy copyB = make_tiled_copy(Copy_Atom<UniversalCopy<uint128_t>, TB>{},
                                    Layout<Shape<_32,_8>>{},  // 线程 Layout 32x8 N-major
                                    Layout<Shape< _4,_1>>{}); // 值 Layout 4x1 N-major

  // mmaC 的三部分：
  //   UniversalFMA<TC,TA,TB>：
  //     1x1x1 标量 FMA Atom，当前 float 实例最终生成普通 FFMA，不使用 Tensor Core。
  //   Atom Thread Layout 16x16x1：
  //     沿 M/N 各放置 16 个单线程 Atom，共使用 16*16=256 个线程。
  //   未显式传入第三个 MNK tiler：
  //     使用自然 16x16x1 TiledMMA tile；分区 128x128x8 CTA tile 时，
  //     多出的 M/N/K 范围成为每线程的 MMA_M/MMA_N/MMA_K value mode。

  TiledMMA mmaC = make_tiled_mma(UniversalFMA<TC,TA,TB>{},
                                 Layout<Shape<_16,_16,_1>>{});  // 16x16x1 UniversalFMA

#if 0
  print(copyA);
  print(copyB);
  print(mmaC);
#endif

#if 0
  print_latex(copyA);
  print_latex(copyB);
  print_latex(mmaC);
#endif

  dim3 dimBlock(size(mmaC));
  dim3 dimGrid(size(ceil_div(M, bM)),
               size(ceil_div(N, bN)));
  gemm_device<<<dimGrid, dimBlock, 0, stream>>>
      (prob_shape, cta_tiler,
       A, dA, sA, copyA,
       B, dB, sB, copyB,
       C, dC, sC, mmaC,
       alpha, beta);
}

// 设置 TN GEMM 参数
template <class TA, class TB, class TC,
          class Alpha, class Beta>
void
gemm_tn(int m, int n, int k,
        Alpha alpha,
        TA const* A, int ldA,
        TB const* B, int ldB,
        Beta beta,
        TC      * C, int ldC,
        cudaStream_t stream = 0)
{
  using namespace cute;

  // 定义动态 Shape
  auto M = int(m);
  auto N = int(n);
  auto K = int(k);
  auto prob_shape = make_shape(M, N, K);                     // (M, N, K)

  // 定义 TN 的混合静态/动态 Stride
  // 哪个 mode 的 stride 为 1，哪个 mode 就在物理内存中连续。
  auto dA = make_stride(ldA, Int<1>{});                      // (dM,dK)：K mode stride=1，K 连续（K-major）
  auto dB = make_stride(ldB, Int<1>{});                      // (dN,dK)：K mode stride=1，K 连续（K-major）
  auto dC = make_stride(Int<1>{}, ldC);                      // (dM,dN)：M mode stride=1，M 连续（M-major）

  // 定义静态 CTA tile 大小
  auto bM = Int<128>{};
  auto bN = Int<128>{};
  auto bK = Int<  8>{};
  auto cta_tiler = make_shape(bM, bN, bK);                   // (BLK_M, BLK_N, BLK_K)

  // 定义静态 shared-memory Layout
  auto sA = make_layout(make_shape (      bM,          bK),
                        make_stride(Int<1>{}, bM+Int<1>{}));        // (m,k) -> smem 下标; 带 padding 的 M-major
  auto sB = make_layout(make_shape (      bN,          bK),
                        make_stride(Int<1>{}, bN+Int<1>{}));        // (n,k) -> smem 下标; 带 padding 的 N-major
  auto sC = make_layout(make_shape(bM, bN));                        // (m,n) -> smem 下标

  // 教程：TN 路径同样使用 TiledCopy，但当前示例选择标量 UniversalCopy<T>。
  // Thread Layout 仍为 32x8，不过使用 K-major 排列来匹配 K 连续的 global 数据。
  // Value Layout 为 1x1，所以每条 Copy Atom 只搬一个元素；这是示例配置，
  // 可以替换为满足对齐、Layout 和指令约束的其他 Copy Atom/分区。
  //
  // 为什么当前配置没有直接使用 NT 的 128-bit 4x1 copy：
  //   A(M,K):(ldA,1)、B(N,K):(ldB,1) 的 M/N mode 不连续；
  //   同一线程沿 M/N 重复负责的四个元素相隔 ldA/ldB，无法组成一次连续
  //   uint128_t load。连续的 K 元素又已经被当前 32x8 K-major Thread Layout
  //   分给不同线程，因此本示例使用每线程 1x1 的标量 copy。
  // 若改成让同一线程持有连续的 1x4 K values，并重新设计 Thread Layout、
  // shared-memory destination 映射与对齐条件，TN 也可以实现向量化 copy。

  TiledCopy copyA = make_tiled_copy(Copy_Atom<UniversalCopy<TA>, TA>{},
                                    Layout<Shape<_32,_8>,Stride<_8,_1>>{}, // 线程 Layout 32x8 K-major
                                    Layout<Shape< _1,_1>>{});              // 值 Layout 1x1
  TiledCopy copyB = make_tiled_copy(Copy_Atom<UniversalCopy<TB>, TB>{},
                                    Layout<Shape<_32,_8>,Stride<_8,_1>>{}, // 线程 Layout 32x8 K-major
                                    Layout<Shape< _1,_1>>{});              // 值 Layout 1x1

  // TN 路径使用与 NT 相同的 TiledMMA：
  //   UniversalFMA 是 1x1x1 单线程标量 FMA；
  //   16x16x1 Atom Thread Layout 共使用 256 个线程；
  //   对 128x128x8 CTA tile，每线程最终得到 A(1,8,8)、B(1,8,8)、
  //   C accumulator(1,8,8)。NT/TN 的差异主要在存储与 copy，而非计算分区。

  TiledMMA mmaC = make_tiled_mma(UniversalFMA<TC,TA,TB>{},
                                 Layout<Shape<_16,_16,_1>>{});  // 16x16x1 TiledMMA

#if 0
  print(copyA);
  print(copyB);
  print(mmaC);
#endif

#if 0
  print_latex(copyA);
  print_latex(copyB);
  print_latex(mmaC);
#endif

  dim3 dimBlock(size(mmaC));
  dim3 dimGrid(size(ceil_div(M, bM)),
               size(ceil_div(N, bN)));
  gemm_device<<<dimGrid, dimBlock, 0, stream>>>
      (prob_shape, cta_tiler,
       A, dA, sA, copyA,
       B, dB, sB, copyB,
       C, dC, sC, mmaC,
       alpha, beta);
}

template <class TA, class TB, class TC,
          class Alpha, class Beta>
void
gemm(char transA, char transB, int m, int n, int k,
     Alpha alpha,
     TA const* A, int ldA,
     TB const* B, int ldB,
     Beta beta,
     TC      * C, int ldC,
     cudaStream_t stream = 0)
{
  if (transA == 'N' && transB == 'T') {
    return gemm_nt(m, n, k, alpha, A, ldA, B, ldB, beta, C, ldC, stream);
  } else
  if (transA == 'T' && transB == 'N') {
    return gemm_tn(m, n, k, alpha, A, ldA, B, ldB, beta, C, ldC, stream);
  }
  assert(false && "Not implemented");
}


int main(int argc, char** argv)
{
  int m = 5120;
  if (argc >= 2)
    sscanf(argv[1], "%d", &m);

  int n = 5120;
  if (argc >= 3)
    sscanf(argv[2], "%d", &n);

  int k = 4096;
  if (argc >= 4)
    sscanf(argv[3], "%d", &k);

  char transA = 'N';
  if (argc >= 5)
    sscanf(argv[4], "%c", &transA);

  char transB = 'T';
  if (argc >= 6)
    sscanf(argv[5], "%c", &transB);

  using TA = float;
  using TB = float;
  using TC = float;
  using TI = float;

  TI alpha = 1.0;
  TI beta  = 0.0;

  std::cout << "M = " << m << std::endl;
  std::cout << "N = " << n << std::endl;
  std::cout << "K = " << k << std::endl;
  std::cout << "C = A^" << transA << " B^" << transB << std::endl;

  cute::device_init(0);

  thrust::host_vector<TA> h_A(m*k);
  thrust::host_vector<TB> h_B(n*k);
  thrust::host_vector<TC> h_C(m*n);

  for (int j = 0; j < m*k; ++j) h_A[j] = static_cast<TA>( 2*(rand() / double(RAND_MAX)) - 1 );
  for (int j = 0; j < n*k; ++j) h_B[j] = static_cast<TB>( 2*(rand() / double(RAND_MAX)) - 1 );
  for (int j = 0; j < m*n; ++j) h_C[j] = static_cast<TC>(-1);

  thrust::device_vector<TA> d_A = h_A;
  thrust::device_vector<TB> d_B = h_B;
  thrust::device_vector<TC> d_C = h_C;

  double gflops = (2.0*m*n*k) * 1e-9;

  const int timing_iterations = 100;
  GPU_Clock timer;

  int ldA = 0, ldB = 0, ldC = m;

  if (transA == 'N') {
    ldA = m;
  } else if (transA == 'T') {
    ldA = k;
  } else {
    assert(false);
  }

  if (transB == 'N') {
    ldB = k;
  } else if (transB == 'T') {
    ldB = n;
  } else {
    assert(false);
  }

  // 先运行一次
  d_C = h_C;
  gemm(transA, transB, m, n, k,
       alpha,
       d_A.data().get(), ldA,
       d_B.data().get(), ldB,
       beta,
       d_C.data().get(), ldC);
  CUTE_CHECK_LAST();
  thrust::host_vector<TC> cute_result = d_C;

  if (!cute_tutorial::check_gemm_result(
          m, n, k, transA, transB,
          alpha, h_A, ldA, h_B, ldB,
          beta, h_C, ldC, cute_result)) {
    return -1;
  }

  // 性能计时迭代
  timer.start();
  for (int i = 0; i < timing_iterations; ++i) {
    gemm(transA, transB, m, n, k,
         alpha,
         d_A.data().get(), ldA,
         d_B.data().get(), ldB,
         beta,
         d_C.data().get(), ldC);
  }
  double cute_time = timer.seconds() / timing_iterations;
  CUTE_CHECK_LAST();
  printf("CUTE_GEMM:     [%6.1f]GFlop/s  (%6.4f)ms\n", gflops / cute_time, cute_time*1000);

  return 0;
}
