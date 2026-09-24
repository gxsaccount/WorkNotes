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

template <class ElementA,
          class ElementB,
          class SmemLayoutA,
          class SmemLayoutB>
struct SharedStorage
{
  cute::ArrayEngine<ElementA, cute::cosize_v<SmemLayoutA>> A;
  cute::ArrayEngine<ElementB, cute::cosize_v<SmemLayoutB>> B;
};

template <class ProblemShape, class CtaTiler,
          class TA, class AStride, class ASmemLayout, class TiledCopyA, class S2RAtomA,
          class TB, class BStride, class BSmemLayout, class TiledCopyB, class S2RAtomB,
          class TC, class CStride, class CSmemLayout, class TiledMma,
          class Alpha, class Beta>
__global__ static
__launch_bounds__(decltype(size(TiledMma{}))::value)
void
gemm_device(ProblemShape shape_MNK, CtaTiler cta_tiler,
            TA const* A, AStride dA, ASmemLayout sA_layout, TiledCopyA copy_a, S2RAtomA s2r_atom_a,
            TB const* B, BStride dB, BSmemLayout sB_layout, TiledCopyB copy_b, S2RAtomB s2r_atom_b,
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

  // Shared memory 缓冲区
  extern __shared__ char shared_memory[];
  using SharedStorage = SharedStorage<TA, TB, ASmemLayout, BSmemLayout>;
  SharedStorage& smem = *reinterpret_cast<SharedStorage*>(shared_memory);
  Tensor sA = make_tensor(make_smem_ptr(smem.A.begin()), sA_layout);   // (BLK_M,BLK_K,PIPE)
  Tensor sB = make_tensor(make_smem_ptr(smem.B.begin()), sB_layout);   // (BLK_N,BLK_K,PIPE)

  //
  // 将 A、B tile 的搬运任务划分到各线程
  //

  ThrCopy thr_copy_a = copy_a.get_slice(threadIdx.x);
  Tensor tAgA = thr_copy_a.partition_S(gA);                            // (CPY,CPY_M,CPY_K,k)
  Tensor tAsA = thr_copy_a.partition_D(sA);                            // (CPY,CPY_M,CPY_K,PIPE)

  ThrCopy thr_copy_b = copy_b.get_slice(threadIdx.x);
  Tensor tBgB = thr_copy_b.partition_S(gB);                            // (CPY,CPY_N,CPY_K,k)
  Tensor tBsB = thr_copy_b.partition_D(sB);                            // (CPY,CPY_N,CPY_K,PIPE)

  CUTE_STATIC_ASSERT_V(size<1>(tAgA) == size<1>(tAsA));                // CPY_M
  CUTE_STATIC_ASSERT_V(size<2>(tAgA) == size<2>(tAsA));                // CPY_K
  CUTE_STATIC_ASSERT_V(size<1>(tBgB) == size<1>(tBsB));                // CPY_N
  CUTE_STATIC_ASSERT_V(size<2>(tBgB) == size<2>(tBsB));                // CPY_K

  //
  // 预取
  //

  auto K_PIPE_MAX = size<3>(tAsA); // 3

  // 剩余 tile 总数
  int k_tile_count = size<3>(tAgA);  // 8
  // 下一次从 gmem 读取的 tile 编号
  int k_tile_next = 0;

  // 除最后一级外，为其余 pipeline stage 启动异步加载
  CUTE_UNROLL
  for (int k_pipe = 0; k_pipe < K_PIPE_MAX-1; ++k_pipe) {   // 这里只有2（K_PIPE_MAX-1）个group
    copy(copy_a, tAgA(_,_,_,k_tile_next), tAsA(_,_,_,k_pipe));
    copy(copy_b, tBgB(_,_,_,k_tile_next), tBsB(_,_,_,k_pipe));
    cp_async_fence();
    --k_tile_count;
    if (k_tile_count > 0) { ++k_tile_next; }
  }

  //
  // 定义 A/B 的计算分区与 C accumulator
  //

  ThrMMA thr_mma = mma.get_slice(threadIdx.x);
  Tensor tCgC = thr_mma.partition_C(gC);                               // (MMA,MMA_M,MMA_N)

  // 为 Tensor Core 流水线分配 A/B operand register fragment。
  // partition_fragment_A/B 先根据 MMA 的 A/B TV Layout 确定当前 lane 所需的
  // fragment Shape，再创建 owning register Tensor；此时只分配寄存器，
  // shared-memory 数据尚未加载进来。
  Tensor tCrA = thr_mma.partition_fragment_A(sA(_,_,0));               // (MMA,MMA_M,MMA_K)
  Tensor tCrB = thr_mma.partition_fragment_B(sB(_,_,0));               // (MMA,MMA_N,MMA_K)
  // 分配 Tensor Core accumulator register fragment。
  Tensor tCrC = thr_mma.make_fragment_C(tCgC);                         // (MMA,MMA_M,MMA_N)

  CUTE_STATIC_ASSERT_V((  shape(tCrC) == take<0,3>(shape(tCgC))));     // (MMA,MMA_M,MMA_N)
  CUTE_STATIC_ASSERT_V((size<1>(tCgC) == size<1>(tCrA)));              // MMA_M
  CUTE_STATIC_ASSERT_V((size<2>(tCgC) == size<1>(tCrB)));              // MMA_N

  // 清零 accumulator
  clear(tCrC);

  //
  // 为 ldmatrix 构造 shared → register 的 TiledCopy。
  //
  // ldmatrix 只负责搬运与重排，不执行矩阵乘法：
  //   shared memory --ldmatrix--> A/B operand registers
  //
  // make_tiled_copy_A/B 会读取 mma 的 A/B TV Layout，生成与 Tensor Core
  // fragment 对齐的 Copy Thread/Value Layout，确保每个 lane 从正确的 shared
  // 坐标读取，并写入该 lane 对应的 MMA register slot。
  //

  TiledCopy s2r_copy_a = make_tiled_copy_A(s2r_atom_a, mma);
  ThrCopy   s2r_thr_copy_a = s2r_copy_a.get_slice(threadIdx.x);
  // ldmatrix 的 shared source view。
  Tensor tXsA = s2r_thr_copy_a.partition_S(sA);                        // (CPY,MMA_M,MMA_K,PIPE)
  // tCrA 已经是当前线程私有的 MMA register fragment，不需要再次按线程分区。
  // retile_D 建立映射：
  //   ldmatrix 的第几个输出 value（CPY value）
  //     → 应写入 tCrA 中哪个 MMA A-fragment register slot。
  // tXrA 与 tCrA 使用同一批寄存器；这里只改变索引方式，不分配、不搬数据。
  // partition_D：
  // 整个目标里，我这个线程负责哪一块？

  // retile_D：
  // 我已有的这些寄存器，Copy Atom 的第 N 个输出该写到哪一个？
  Tensor tXrA = s2r_thr_copy_a.retile_D(tCrA);                         // (CPY,MMA_M,MMA_K)





  TiledCopy s2r_copy_b = make_tiled_copy_B(s2r_atom_b, mma);
  ThrCopy   s2r_thr_copy_b = s2r_copy_b.get_slice(threadIdx.x);
  Tensor tXsB = s2r_thr_copy_b.partition_S(sB);                        // (CPY,MMA_N,MMA_K,PIPE)
  Tensor tXrB = s2r_thr_copy_b.retile_D(tCrB);                         // (CPY,MMA_N,MMA_K)

#if 0
  if(thread0()) {
    print("  mA : "); print(  mA); print("\n");
    print("  gA : "); print(  gA); print("\n");
    print("  sA : "); print(  sA); print("\n");
    print("tAgA : "); print(tAgA); print("\n");
    print("tAsA : "); print(tAsA); print("\n");
  }
#endif

#if 0
  if(thread0()) {
    print("  mB : "); print(  mB); print("\n");
    print("  gB : "); print(  gB); print("\n");
    print("  sB : "); print(  sB); print("\n");
    print("tBgB : "); print(tBgB); print("\n");
    print("tBsB : "); print(tBsB); print("\n");
  }
#endif

#if 0
  if(thread0()) {
    print("  mC : "); print(  mC); print("\n");
    print("  gC : "); print(  gC); print("\n");
    print("tCgC : "); print(tCgC); print("\n");
    print("tCrA : "); print(tCrA); print("\n");
    print("tCrB : "); print(tCrB); print("\n");
    print("tCrC : "); print(tCrC); print("\n");

    print("tXsA : "); print(tXsA); print("\n");
    print("tXrA : "); print(tXrA); print("\n");
    print("tXsB : "); print(tXsB); print("\n");
    print("tXrB : "); print(tXrB); print("\n");
  }
#endif

#if 1

  // 当前读取的 smem pipeline stage
  int smem_pipe_read  = 0;
  // 当前写入的 smem pipeline stage
  int smem_pipe_write = K_PIPE_MAX-1; // 0,1,2

  // 取得当前 pipeline stage 的 shared-memory source view。
  // 当前 Tensor Core 配置下：
  //   tXsA/tXsB  = (CPY=8, MMA_M/N=4, MMA_K=4, PIPE=3)
  //   tXsA_p/B_p = (CPY=8, MMA_M/N=4, MMA_K=4)
  //
  // 最后一维固定为 smem_pipe_read 后被切掉：
  //   tXsA(_,_,_,smem_pipe_read)
  //     → 当前 stage 中供 ldmatrix 读取的 A view。
  // 这里只创建 nonowning view，不会搬运 shared-memory 数据。
  Tensor tXsA_p = tXsA(_,_,_,smem_pipe_read);
  Tensor tXsB_p = tXsB(_,_,_,smem_pipe_read);

  // 寄存器流水级数
  auto K_BLOCK_MAX = size<2>(tCrA);
  CUTE_STATIC_ASSERT_V(K_BLOCK_MAX == size<2>(tXrA));

  // 预取寄存器流水
  if (K_BLOCK_MAX > 1) {
    // 等待第一个预取 tile 加载完成
    cp_async_wait<K_PIPE_MAX-2>();
    __syncthreads();

    // 从第一个 K tile 预取第一批寄存器数据
    copy(s2r_atom_a, tXsA_p(_,_,Int<0>{}), tXrA(_,_,Int<0>{}));
    copy(s2r_atom_b, tXsB_p(_,_,Int<0>{}), tXrB(_,_,Int<0>{}));
  }

  //
  // 流水化 MAINLOOP
  // 教程：使用 SM80 cp.async 对 shared memory 进行流水化的 GEMM 循环
  //           并在 shared memory 中显式维护多级流水
  //   数据从 global(k_tile_next) 读取到 shared(smem_pipe_write)
  //   数据从 shared(smem_pipe_read) 读取到 register(k_block_next)
  //   在 register(b_block) 上执行计算
  //
  //   这样可以重叠各级 copy 与计算：
  //     gmem→smem 可与 smem→rmem 以及寄存器计算重叠
  //     smem→rmem 可与寄存器计算重叠
  //


/**
 * +----------+--------------+--------------+----------------+
 * | Phase    | k_tile_count | Compute tile | Prefetch tile  |
 * +----------+--------------+--------------+----------------+
 * | Prologue |            8 | -            | tile 0         |
 * | Prologue |            7 | -            | tile 1         |
 * | Mainloop |            6 | tile 0       | tile 2         |
 * | Mainloop |            5 | tile 1       | tile 3         |
 * | Mainloop |            4 | tile 2       | tile 4         |
 * | Mainloop |            3 | tile 3       | tile 5         |
 * | Mainloop |            2 | tile 4       | tile 6         |
 * | Mainloop |            1 | tile 5       | tile 7         |
 * | Drain    |            0 | tile 6       | tile 7 (dummy) |
 * | Drain    |           -1 | tile 7       | tile 7 (dummy) |
 * | End      |           -2 | -            | -              |
 * +----------+--------------+--------------+----------------+
 */
  CUTE_NO_UNROLL
  // 初始时k_tile_count = 6 ，有俩以及预取
  while (k_tile_count > -(K_PIPE_MAX-1))  // while (k_tile_count > -2) ,因为三级流水线，tile为-1时计算tile 7
  {
    CUTE_UNROLL
    for (int k_block = 0; k_block < K_BLOCK_MAX; ++k_block)
    {
      if (k_block == K_BLOCK_MAX - 1)
      {
        // 切出当前 smem_pipe_read stage
        tXsA_p = tXsA(_,_,_,smem_pipe_read);
        tXsB_p = tXsB(_,_,_,smem_pipe_read);

        // 等待并提交当前 smem_pipe_read stage
        cp_async_wait<K_PIPE_MAX-2>();
        __syncthreads();
      }

      // 为下一个 k_block 加载 A、B：smem → register
      auto k_block_next = (k_block + Int<1>{}) % K_BLOCK_MAX;      // 编译期静态值
      copy(s2r_atom_a, tXsA_p(_,_,k_block_next), tXrA(_,_,k_block_next));
      copy(s2r_atom_b, tXsB_p(_,_,k_block_next), tXrB(_,_,k_block_next));
      // 在每个 K pipeline stage 的 GEMM 前发起 gmem → smem
      if (k_block == 0)
      {
        copy(copy_a, tAgA(_,_,_,k_tile_next), tAsA(_,_,_,smem_pipe_write));
        copy(copy_b, tBgB(_,_,_,k_tile_next), tBsB(_,_,_,smem_pipe_write));
        cp_async_fence();

        // 推进 gmem tile 编号
        --k_tile_count;
        if (k_tile_count > 0) { ++k_tile_next; }

        // 推进 smem pipeline stage
        smem_pipe_write = smem_pipe_read;
        smem_pipe_read = (smem_pipe_read == K_PIPE_MAX-1) ? 0 : smem_pipe_read+1;
      }
      // 对当前 k_block 执行 Tensor Core register GEMM
      // 完整 fragment：
      //   tCrA: ((_2,_2,_2),_4,_4) // MMA_A=8, MMA_M=4, MMA_K=4
      //   tCrB: ((_2,_2),   _8,_4) // MMA_B=4, MMA_N=8, MMA_K=4
      //   tCrC: ((_2,_2),   _4,_8) // MMA_C=4, MMA_M=4, MMA_N=8
      // 固定 k_block 后，本次 gemm 入参：
      //   A: ((_2,_2,_2),_4)       // MMA_A=8, MMA_M=4
      //   B: ((_2,_2),_8)          // MMA_B=4, MMA_N=8
      //   C: ((_2,_2),_4,_8)       // MMA_C=4, MMA_M=4, MMA_N=8
      // A/B/C 的 MMA value 数由各自的 Atom TV Layout 决定，不要求相同。
      gemm(mma, tCrA(_,_,k_block), tCrB(_,_,k_block), tCrC);
    }

  }

#endif

  //
  // Epilogue：将 accumulator 写回 C
  //

  axpby(alpha, tCrC, beta, tCgC);
}

template <class Alpha, class Beta>
void
gemm_nt(int m, int n, int k,
        Alpha alpha,
        cute::half_t const* A, int ldA,
        cute::half_t const* B, int ldB,
        Beta beta,
        cute::half_t      * C, int ldC,
        cudaStream_t stream = 0)
{
  assert(false && "Not implemented");
}

// 设置 TN HGEMM 参数
template <class Alpha, class Beta>
void
gemm_tn(int m, int n, int k,
        Alpha alpha,
        cute::half_t const* A, int ldA,
        cute::half_t const* B, int ldB,
        Beta beta,
        cute::half_t      * C, int ldC,
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

  // 定义静态 CTA tile 大小。这是面向当前 A100/SM80 教程的一组调优配置，
  // 不是 CuTe 根据 MMA Atom 唯一推导出的结果。
  //
  // bM=bN=128：
  //   一个 CTA 计算 128x128 的 C tile。当前 TiledMMA tile 是 32x32，
  //   所以在 M/N 方向各重复 128/32=4 次。
  //
  // bK=64：
  //   当前 Tensor Core TiledMMA 的 K tile 是 16，所以一个 CTA K tile
  //   包含 64/16=4 个 MMA k_block，并减少完整 K 维上的 k_tile 循环次数。
  //
  // bP=3：
  //   三份 shared-memory stage 分别用于当前计算、下一 tile 就绪、再下一 tile
  //   通过 cp.async 加载。
  //
  // FP16 A/B shared-memory 逻辑容量约为：
  //   2 matrices * 128 * 64 * 3 stages * 2 bytes = 98304 bytes（96 KiB）。
  // 修改 tile 时必须一起检查寄存器压力、shared-memory 上限和 occupancy。
  auto bM = Int<128>{};
  auto bN = Int<128>{};
  auto bK = Int< 64>{};// 综合考虑shm、寄存器上限、tensor core算力强，计算耗时久了可以更好隐藏访存耗时
  auto cta_tiler = make_shape(bM, bN, bK);                   // (BLK_M, BLK_N, BLK_K)
  auto bP = Int<3>{};  // Pipeline 级数

  // 定义静态 shared-memory Layout
  // 用于 LDSM 与 128-bit K-major load 的 Swizzle
  auto swizzle_atom = composition(Swizzle<3,3,3>{},
                                  Layout<Shape <_8,Shape <_8, _8>>,
                                         Stride<_8,Stride<_1,_64>>>{});

  auto sA = tile_to_shape(swizzle_atom, make_shape(bM,bK,bP)); // 以 swizzle_atom 为基本布局单元，按其布局规则重复铺开，最终覆盖 (bM, bK, bP) 这个逻辑 Shape
  auto sB = tile_to_shape(swizzle_atom, make_shape(bN,bK,bP));
  auto sC = make_layout(make_shape(bM, bN));

  // 定义静态线程 Layout

  TiledCopy copyA = make_tiled_copy(Copy_Atom<SM80_CP_ASYNC_CACHEALWAYS<uint128_t>, cute::half_t>{},
                                    Layout<Shape<_16,_8>,Stride<_8,_1>>{},  // 线程 Layout 16x8 K-major
                                    Layout<Shape< _1,_8>>{});               // Value Layout  1x8 K-major
  TiledCopy copyB = make_tiled_copy(Copy_Atom<SM80_CP_ASYNC_CACHEALWAYS<uint128_t>, cute::half_t>{},
                                    Layout<Shape<_16,_8>,Stride<_8,_1>>{},  // 线程 Layout 16x8 K-major
                                    Layout<Shape< _1,_8>>{});               // Value Layout  1x8 N-major

  // Tensor Core MMA Atom：
  //   SM80_16x8x16_F16F16F16F16_TN
  //   一个 warp 的 32 个 lanes 协作执行一次 16x8x16 矩阵乘加；
  //   A/B、初始 accumulator C 和结果 D 都是 FP16。
  //   底层对应 mma.sync/HMMA，而不是普通单线程 FFMA。
  //
  // 基础 Atom 为 16x8x16、一个 warp。
  // Atom Layout 2x2 在线程上复制 4 个 warp Atom：自然覆盖 32x16x16，
  // 共使用 4*32=128 threads。
  // 第三个参数将最终逻辑 tile 扩展为 32x32x16；额外的 N 范围由现有线程
  // 持有更多 value 覆盖，不再增加线程。
  TiledMMA mmaC = make_tiled_mma(SM80_16x8x16_F16F16F16F16_TN{},
                                 Layout<Shape<_2,_2>>{},    // 4 个 warp Atom，128 threads
                                 Tile<_32,_32,_16>{});      // 最终逻辑 TiledMMA tile

  // Shared → Register 使用 ldmatrix：
  //   SM75_U32x4_LDSM_N 对应非转置的 ldmatrix.x4；
  //   一个 warp 协作从 shared memory 读取四组 8x8 b16 matrix fragment；
  //   每个 lane 得到 4 个 32-bit register，每个 register 打包 2 个 FP16。
  // ldmatrix 负责把 shared 数据放入 Tensor Core 所要求的 lane/register 分布。
  //
  //Copy_Atom<DefaultCopy, half_t> s2r_atom_A;
  //Copy_Atom<UniversalCopy<half_t>, half_t> s2r_atom_A;
  //Copy_Atom<SM75_U32x1_LDSM_N, half_t> s2r_atom_A;
  //Copy_Atom<SM75_U32x2_LDSM_N, half_t> s2r_atom_A;
  Copy_Atom<SM75_U32x4_LDSM_N, half_t> s2r_atom_A;

  //Copy_Atom<DefaultCopy, half_t> s2r_atom_B;
  //Copy_Atom<UniversalCopy<half_t>, half_t> s2r_atom_B;
  //Copy_Atom<SM75_U32x1_LDSM_N, half_t> s2r_atom_B;
  //Copy_Atom<SM75_U32x2_LDSM_N, half_t> s2r_atom_B;
  Copy_Atom<SM75_U32x4_LDSM_N, half_t> s2r_atom_B;

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

  int smem_size = int(sizeof(SharedStorage<cute::half_t, cute::half_t, decltype(sA), decltype(sB)>));
  dim3 dimBlock(size(mmaC));
  dim3 dimGrid(size(ceil_div(M, bM)),
               size(ceil_div(N, bN)));

  auto kernel_fptr = gemm_device<
    decltype(prob_shape), decltype(cta_tiler),
    cute::half_t, decltype(dA), decltype(sA), decltype(copyA), decltype(s2r_atom_A),
    cute::half_t, decltype(dB), decltype(sB), decltype(copyB), decltype(s2r_atom_B),
    cute::half_t, decltype(dC), decltype(sC), decltype(mmaC),
    decltype(alpha), decltype(beta)>;

  // 允许该 kernel 的每个 thread block 使用最多 smem_size 字节的
  // 动态 shared memory。这里只设置可申请的上限，实际分配量由下面
  // kernel launch 的第三个参数 <<<dimGrid, dimBlock, smem_size>>> 指定。
  cudaFuncSetAttribute(
    kernel_fptr,
    cudaFuncAttributeMaxDynamicSharedMemorySize, smem_size);

  // L1 cache 与 shared memory 共用片上资源时，优先将资源分配给
  // shared memory。100 表示尽可能选择最大的 shared-memory carveout；
  // 这是性能偏好提示，实际采用的比例由 GPU 和 CUDA 驱动决定。
  cudaFuncSetAttribute(
    kernel_fptr,
    cudaFuncAttributePreferredSharedMemoryCarveout, 100);

  kernel_fptr<<<dimGrid, dimBlock, smem_size, stream>>>
      (prob_shape, cta_tiler,
       A, dA, sA, copyA, s2r_atom_A,
       B, dB, sB, copyB, s2r_atom_B,
       C, dC, sC, mmaC,
       alpha, beta);
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
  auto bP = Int<3>{};  // Pipeline 级数

  // 定义静态 shared-memory Layout
  auto sA = make_layout(make_shape(bM, bK, bP));             // (m,k,p) -> smem 下标; M-major
  auto sB = make_layout(make_shape(bN, bK, bP));             // (n,k,p) -> smem 下标; N-major
  auto sC = make_layout(make_shape(bM, bN));                 // (m,n) -> smem 下标; M-major

  // 定义静态线程 Layout

  TiledCopy copyA = make_tiled_copy(Copy_Atom<SM80_CP_ASYNC_CACHEALWAYS<uint128_t>, TA>{},
                                    Layout<Shape<_32,_8>>{}, // 线程 Layout 32x8 M-major
                                    Layout<Shape< _4,_1>>{});// Value Layout  4x1 M-major
  TiledCopy copyB = make_tiled_copy(Copy_Atom<SM80_CP_ASYNC_CACHEALWAYS<uint128_t>, TB>{},
                                    Layout<Shape<_32,_8>>{}, // 线程 Layout 32x8 N-major
                                    Layout<Shape< _4,_1>>{});// Value Layout  4x1 N-major

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

  int smem_size = int(sizeof(SharedStorage<TA, TB, decltype(sA), decltype(sB)>));
  dim3 dimBlock(size(mmaC));
  dim3 dimGrid(size(ceil_div(M, bM)),
               size(ceil_div(N, bN)));
  gemm_device<<<dimGrid, dimBlock, smem_size, stream>>>
      (prob_shape, cta_tiler,
       A, dA, sA, copyA, Copy_Atom<AutoVectorizingCopy, TA>{},
       B, dB, sB, copyB, Copy_Atom<AutoVectorizingCopy, TB>{},
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
  auto bP = Int<3>{};  // Pipeline 级数

  // 定义静态 shared-memory Layout
  auto sA_atom                  = make_layout(make_shape (      bM,          bK),
                                              make_stride(Int<1>{}, bM+Int<1>{})); // (m,k) -> smem 下标; 带 padding 的 M-major
  [[maybe_unused]] auto sB_atom = make_layout(make_shape (      bN,          bK),
                                              make_stride(Int<1>{}, bN+Int<1>{})); // (n,k) -> smem 下标; 带 padding 的 N-major
  auto sA = tile_to_shape(sA_atom, make_shape(bM, bK, bP));
  auto sB = tile_to_shape(sA_atom, make_shape(bN, bK, bP));
  auto sC = make_layout(make_shape(bM, bN));                        // (m,n) -> smem 下标

  // 定义静态线程 Layout

  TiledCopy copyA = make_tiled_copy(Copy_Atom<SM80_CP_ASYNC_CACHEALWAYS<TA>, TA>{},
                                    Layout<Shape<_32,_8>,Stride<_8,_1>>{}, // 线程 Layout 32x8 K-major
                                    Layout<Shape< _1,_1>>{});              // Value Layout  1x1
  TiledCopy copyB = make_tiled_copy(Copy_Atom<SM80_CP_ASYNC_CACHEALWAYS<TB>, TB>{},
                                    Layout<Shape<_32,_8>,Stride<_8,_1>>{}, // 线程 Layout 32x8 K-major
                                    Layout<Shape< _1,_1>>{});              // Value Layout  1x1

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

  int smem_size = int(sizeof(SharedStorage<TA, TB, decltype(sA), decltype(sB)>));
  dim3 dimBlock(size(mmaC));
  dim3 dimGrid(size(ceil_div(M, bM)),
               size(ceil_div(N, bN)));
  gemm_device<<<dimGrid, dimBlock, smem_size, stream>>>
      (prob_shape, cta_tiler,
       A, dA, sA, copyA, Copy_Atom<AutoVectorizingCopy, TA>{},
       B, dB, sB, copyB, Copy_Atom<AutoVectorizingCopy, TB>{},
       C, dC, sC, mmaC,
       alpha, beta);
}


// sm80 文件
// ├─ half TN 特化 → Tensor Core
// ├─ half NT 特化 → 当前未实现
// └─ 泛型 NT/TN   → UniversalFMA

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
  cudaDeviceProp props;
  cudaError_t error = cudaGetDeviceProperties(&props, 0);
  if (error != cudaSuccess) {
    std::cerr << "cudaGetDeviceProperties() returned an error: " << cudaGetErrorString(error) << std::endl;
    return -1;
  }

  if (props.major < 8) {
    std::cout << "This example requires an Ampere GPU or newer (CC >= 80)" << std::endl;
    // 在不支持的架构或 CUDA Toolkit 上返回 0，使测试正常跳过
    return 0;
  }

  std::cout << "Using device 0: " << props.name
            << " (SM" << props.major * 10 + props.minor
            << ", " << props.multiProcessorCount
            << ")" << std::endl;

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

  using TA = cute::half_t;
  using TB = cute::half_t;
  using TC = cute::half_t;
  using TI = cute::half_t;

  TI alpha = static_cast<TI>(1.0f);
  TI beta  = static_cast<TI>(0.0f);

  std::cout << "M = " << m << std::endl;
  std::cout << "N = " << n << std::endl;
  std::cout << "K = " << k << std::endl;
  std::cout << "C = A^" << transA << " B^" << transB << std::endl;

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
