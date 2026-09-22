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
          class TA, class AStride, class ASmemLayout, class AThreadLayout,
          class TB, class BStride, class BSmemLayout, class BThreadLayout,
          class TC, class CStride, class CSmemLayout, class CThreadLayout,
          class Alpha, class Beta>
__global__ static
__launch_bounds__(decltype(size(CThreadLayout{}))::value)
void
gemm_device(ProblemShape shape_MNK, CtaTiler cta_tiler,
            TA const* A, AStride dA, ASmemLayout sA_layout, AThreadLayout tA,
            TB const* B, BStride dB, BSmemLayout sB_layout, BThreadLayout tB,
            TC      * C, CStride dC, CSmemLayout          , CThreadLayout tC,
            Alpha alpha, Beta beta)
{
  using namespace cute;

  // 前置条件
  CUTE_STATIC_ASSERT_V(rank(shape_MNK) == Int<3>{});                   // (M, N, K)
  CUTE_STATIC_ASSERT_V(rank(cta_tiler) == Int<3>{});                   // (BLK_M, BLK_N, BLK_K)

  static_assert(is_static<AThreadLayout>::value);
  static_assert(is_static<BThreadLayout>::value);
  static_assert(is_static<CThreadLayout>::value);

  CUTE_STATIC_ASSERT_V(size(tA) == size(tB));                          // 线程总数
  CUTE_STATIC_ASSERT_V(size(tC) == size(tA));                          // 线程总数

  CUTE_STATIC_ASSERT_V(size<0>(cta_tiler) % size<0>(tA) == Int<0>{});  // BLK_M 必须能被 THR_M 整除
  CUTE_STATIC_ASSERT_V(size<2>(cta_tiler) % size<1>(tA) == Int<0>{});  // BLK_K 必须能被 THR_K 整除
  CUTE_STATIC_ASSERT_V(size<1>(cta_tiler) % size<0>(tB) == Int<0>{});  // BLK_N 必须能被 THR_N 整除
  CUTE_STATIC_ASSERT_V(size<2>(cta_tiler) % size<1>(tB) == Int<0>{});  // BLK_K 必须能被 THR_K 整除
  CUTE_STATIC_ASSERT_V(size<0>(cta_tiler) % size<0>(tC) == Int<0>{});  // BLK_M 必须能被 THR_M 整除
  CUTE_STATIC_ASSERT_V(size<1>(cta_tiler) % size<1>(tC) == Int<0>{});  // BLK_N 必须能被 THR_N 整除

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

  // 教程：使用线程 Layout tA/tB 对 A/B tile 进行简单的 raked partition

  Tensor tAgA = local_partition(gA, tA, threadIdx.x);                  // (THR_M,THR_K,k)
  Tensor tAsA = local_partition(sA, tA, threadIdx.x);                  // (THR_M,THR_K)

  Tensor tBgB = local_partition(gB, tB, threadIdx.x);                  // (THR_N,THR_K,k)
  Tensor tBsB = local_partition(sB, tB, threadIdx.x);                  // (THR_N,THR_K)

  CUTE_STATIC_ASSERT_V(size<0>(tAgA) == size<0>(tAsA));                // THR_M
  CUTE_STATIC_ASSERT_V(size<1>(tAgA) == size<1>(tAsA));                // THR_K
  CUTE_STATIC_ASSERT_V(size<0>(tBgB) == size<0>(tBsB));                // THR_N
  CUTE_STATIC_ASSERT_V(size<1>(tBgB) == size<1>(tBsB));                // THR_K

  //
  // 定义 A/B 的计算分区与 C accumulator
  //

  // 教程：通过投影线程 Layout tC 完成计算分区

  // 使用 tC 的 M/行方向分区 sA (BLK_M, BLK_K)。
  // Step<_1,X> 表示 M 线程坐标生效、N 线程坐标被忽略；X 不是把 N 设为 1。
  Tensor tCsA = local_partition(sA, tC, threadIdx.x, Step<_1, X>{});   // (THR_M,BLK_K)
  // 使用 tC 的 N/列方向分区 sB (BLK_N, BLK_K)。
  // Step<X,_1> 表示 N 线程坐标生效、M 线程坐标被忽略；X 不是把 M 设为 1。
  // 因此 M 不同但 N 相同的线程会得到相同的 B view，B 的 K mode 仍完整保留。
  Tensor tCsB = local_partition(sB, tC, threadIdx.x, Step< X,_1>{});   // (THR_N,BLK_K)
  // 使用完整 tC tile 分区 gC (M,N)
  Tensor tCgC = local_partition(gC, tC, threadIdx.x, Step<_1,_1>{});   // (THR_M,THR_N)

  // 分配 accumulator，其 Shape/Layout 与分区后的数据相同、make_tensor_like，因为没有传入指针，所以它创建自己的静态数组存储（寄存器）。
  Tensor tCrC = make_tensor_like(tCgC);                                // (THR_M,THR_N)

  CUTE_STATIC_ASSERT_V(size<0>(tCrC) == size<0>(tCgC));                // THR_M
  CUTE_STATIC_ASSERT_V(size<0>(tCrC) == size<0>(tCsA));                // THR_M
  CUTE_STATIC_ASSERT_V(size<1>(tCrC) == size<1>(tCgC));                // THR_N
  CUTE_STATIC_ASSERT_V(size<1>(tCrC) == size<0>(tCsB));                // THR_N
  CUTE_STATIC_ASSERT_V(size<1>(tCsA) == size<1>(tCsB));                // BLK_K

  // 清零 accumulator
  clear(tCrC);

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
    print("tCsA : "); print(tCsA); print("\n");
    print("tCsB : "); print(tCsB); print("\n");
    print("tCgC : "); print(tCgC); print("\n");
    print("tCrC : "); print(tCrC); print("\n");
  }
#endif

#if 1

  // 教程：简单 mainloop 示例，先将数据 tile 读入 shared memory，
  //           然后在这些 tile 上进行计算
  //   copy(.) 通过 tA/tB 分区操作 global 与 shared memory
  //   gemm(.) 通过 tC 分区操作 shared 与 register memory

  auto K_TILE_MAX = size<2>(tAgA); // tAgA sahpe: (BLK_M,BLK_K,k)  ， k个（BLK_M,BLK_K）的快

  for (int k_tile = 0; k_tile < K_TILE_MAX; ++k_tile)
  {
    // 使用按 tA/tB 分区的每线程 Tensor 将 gmem 搬到 smem
    copy(tAgA(_,_,k_tile), tAsA);      // A   (THR_M,THR_K) -> (THR_M,THR_K)
    copy(tBgB(_,_,k_tile), tBsB);      // B   (THR_N,THR_K) -> (THR_N,THR_K)

    // 教程：上面的 copy(tAgA(_,_,k_tile), tAsA) 等价于
    //   Tensor tAgAk = tAgA(_,_,k_tile);
    //   CUTE_UNROLL
    //   for (int i = 0; i < size(tAsA); ++i) {
    //     tAsA(i) = tAgAk(i);
    //   }

    cp_async_fence();        // 标记当前一组潜在 cp.async 指令的结束
    cp_async_wait<0>();      // 等待此前所有潜在 cp.async 指令完成
    __syncthreads();         // 等待所有线程完成 smem 写入

    // 在按 tC 分区的 shared-memory Tensor 上执行 GEMM
    // 这是 cute::gemm，并非 CUDA/C++ 内置函数
    // 三参数形式执行原地累加：tCrC += tCsA * tCsB
    // 此处未传入 MMA Atom，因此 CuTe 分派到默认 UniversalFMA
    gemm(tCsA, tCsB, tCrC);            // (THR_M,THR_N) += (THR_M,BLK_K) * (THR_N,BLK_K) =》 (8,8) += (8,8) * (8,8)

    // 教程：上面的 gemm(tCsA, tCsB, tCrC) 等价于
    //   CUTE_UNROLL
    //   for (int k = 0; k < size<1>(tCsA); ++k) {
    //     CUTE_UNROLL
    //     for (int m = 0; m < size<0>(tCrC); ++m) {
    //       CUTE_UNROLL
    //       for (int n = 0; n < size<1>(tCrC); ++n) {
    //         tCrC(m,n) += tCsA(m,k) * tCsB(n,k);
    //       }
    //     }
    //   }

    __syncthreads();         // 等待所有线程完成 smem 读取
  }

#endif

  //
  // Epilogue：将 accumulator 写回 C
  //

  axpby(alpha, tCrC, beta, tCgC);

  // 教程：上面的 axpby(alpha, tCrC, beta, tCgC) 等价于
  //   CUTE_UNROLL
  //   for (int i = 0; i < size(tCrC); ++i) {
  //     tCgC(i) = alpha * tCrC(i) + beta * tCgC(i);
  //   }
}

// 设置 NT GEMM 参数
// 使用 M-major sA、N-major sB，以及 M/N-major 线程布局 tA/tB
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

  // A/B 指针本身只表示一维内存地址；dA/dB 才描述输入矩阵的物理存储方式。
  // gemm_nt 不会真的转置矩阵，而是用下面的 Stride 将内存解释成 A(M,K)、B(N,K)。
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
  auto tA = make_layout(make_shape(Int<32>{}, Int< 8>{}));   // (m,k) -> 线程下标
  auto tB = make_layout(make_shape(Int<32>{}, Int< 8>{}));   // (n,k) -> 线程下标
  auto tC = make_layout(make_shape(Int<16>{}, Int<16>{}));   // (m,n) -> 线程下标

  dim3 dimBlock(size(tC));
  dim3 dimGrid(size(ceil_div(M, bM)),
               size(ceil_div(N, bN)));
  gemm_device<<<dimGrid, dimBlock, 0, stream>>>
      (prob_shape, cta_tiler,
       A, dA, sA, tA,
       B, dB, sB, tB,
       C, dC, sC, tC,
       alpha, beta);
}

// 设置 TN GEMM 参数
// 使用带 padding 的 M-major sA、N-major sB，以及 K-major 线程布局 tA/tB

// C(128×128) += A(128×8) × B(128×8)
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

  // A/B 指针本身只表示一维内存地址；dA/dB 才描述输入矩阵的物理存储方式。
  // gemm_tn 不会真的转置矩阵，而是用下面的 Stride 将内存解释成 A(M,K)、B(N,K)。
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
  auto sA = make_layout(make_shape(bM,bK), LayoutRight{});   // (m,k) -> smem 下标; K-major
  auto sB = make_layout(make_shape(bN,bK), LayoutRight{});   // (n,k) -> smem 下标; K-major
  auto sC = make_layout(make_shape(bM, bN));                 // (m,n) -> smem 下标; M-major

  // 定义静态线程 Layout
  // 这是一组便于教学的线程分工，并不是唯一选择；只要线程总数一致、各 mode
  // 能整除 CTA tile，并且访存/计算映射合理，就可以设计其他 Thread Layout。
  //
  // tA/tB = 32x8：匹配 128x8 的 A/B copy tile。
  // LayoutRight 让 K mode 在线程编号中连续，每线程负责 (128/32)x(8/8)=4x1 个元素。
  auto tA = make_layout(make_shape(Int<32>{}, Int< 8>{}), LayoutRight{});  // (m,k) -> 线程下标; K-major
  auto tB = make_layout(make_shape(Int<32>{}, Int< 8>{}), LayoutRight{});  // (n,k) -> 线程下标; K-major
  //
  // tC = 16x16：匹配 128x128 的 C tile，每线程负责
  // (128/16)x(128/16)=8x8 个交错分布的 C accumulator。这个tile会需要gemm使用的atomic类型做调整
  auto tC = make_layout(make_shape(Int<16>{}, Int<16>{}));                 // (m,n) -> 线程下标; M-major

  dim3 dimBlock(size(tC));
  dim3 dimGrid(size(ceil_div(M, bM)),
               size(ceil_div(N, bN)));
  gemm_device<<<dimGrid, dimBlock, 0, stream>>>
      (prob_shape, cta_tiler,
       A, dA, sA, tA,
       B, dB, sB, tB,
       C, dC, sC, tC,
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
  // 为本教程实现的两种 Layout 组合进行运行时分派
  // 这些标志只决定如何解释 A/B 内存以及选择哪套
  // kernel 配置；不会真正执行矩阵转置
  if (transA == 'N' && transB == 'T') {
    // A 为 M-major（M mode stride=1），B 为 N-major（N mode stride=1）
    return gemm_nt(m, n, k, alpha, A, ldA, B, ldB, beta, C, ldC, stream);
  } else
  if (transA == 'T' && transB == 'N') {
    // A、B 均为 K-major（K mode stride=1）
    return gemm_tn(m, n, k, alpha, A, ldA, B, ldB, beta, C, ldC, stream);
  }
  // 为了保持教程简洁，此处省略 NN 和 TT
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
