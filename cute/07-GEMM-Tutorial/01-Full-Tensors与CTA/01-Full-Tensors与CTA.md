# Full Tensors 与 CTA Partitioning

> 官方示例：`examples/cute/tutorial/sgemm_1.cu`
>
> 更新：2026-09-22

本节只解决两个问题：

1. 如何把 A、B、C 指针描述成完整 CuTe Tensor；
2. 如何让每个 CTA 取得自己负责的矩阵 tile。

暂时不讨论线程怎样搬数据，也不讨论 MMA。

## 1. GEMM 的统一坐标约定

CuTe 使用：

```text
ProblemShape = (M,N,K)
A            = (M,K)
B            = (N,K)
C            = (M,N)
```

数学公式：

```text
C(m,n) = alpha * Σ_k A(m,k) * B(n,k) + beta * C(m,n)
```

注意 B 写成 `(N,K)`，而不是传统教材中的 `(K,N)`。这样 A、B 的 reduction
mode 都位于最后：

```text
A(_,k)
B(_,k)
```

K-loop 可以对两者使用一致的切片方式。

## 2. 完整 Tensor

问题 Shape：

```cpp
auto M = int(m);
auto N = int(n);
auto K = int(k);
auto problem_shape = make_shape(M, N, K);
```

从指针、Shape 和 Stride 构造：

```cpp
Tensor mA =
    make_tensor(make_gmem_ptr(A),
                select<0,2>(problem_shape),  // (M,K)
                dA);

Tensor mB =
    make_tensor(make_gmem_ptr(B),
                select<1,2>(problem_shape),  // (N,K)
                dB);

Tensor mC =
    make_tensor(make_gmem_ptr(C),
                select<0,1>(problem_shape),  // (M,N)
                dC);
```

`mA/mB/mC` 都是 nonowning global-memory Tensor：

```text
Engine：带 gmem tag 的指针
Layout：对应 Shape 与 Stride
```

## 3. 不要只说 row-major / column-major

CuTe 更强调哪个逻辑 mode 的 stride 为 1：

```text
A(M,K)
  M-major：M mode stride=1
  K-major：K mode stride=1

B(N,K)
  N-major：N mode stride=1
  K-major：K mode stride=1
```

官方示例中的 NT：

```cpp
auto dA = make_stride(Int<1>{}, ldA); // (dM,dK)：M-major
auto dB = make_stride(Int<1>{}, ldB); // (dN,dK)：N-major
auto dC = make_stride(Int<1>{}, ldC); // (dM,dN)：M-major
```

TN：

```cpp
auto dA = make_stride(ldA, Int<1>{}); // K-major
auto dB = make_stride(ldB, Int<1>{}); // K-major
auto dC = make_stride(Int<1>{}, ldC); // M-major
```

对应关系：

| BLAS 表述 | A Layout | B Layout |
|---|---|---|
| NT | `(M,K):(1,ldA)` | `(N,K):(1,ldB)` |
| TN | `(M,K):(ldA,1)` | `(N,K):(ldB,1)` |
| NN | `(M,K):(1,ldA)` | `(N,K):(ldB,1)` |
| TT | `(M,K):(ldA,1)` | `(N,K):(1,ldB)` |

阅读 kernel 时优先问：

```text
A 的 M/K 哪个连续？
B 的 N/K 哪个连续？
```

比单独看 N/T 标志更直接。

### 哪部分描述输入矩阵的物理存储

输入矩阵的物理存储方式不是由 `gemm_nt` 或 `gemm_tn` 这个函数名直接决定的，
而是由：

```text
数据指针 + Shape + Stride
```

共同决定。

例如：

```cpp
Tensor mA =
    make_tensor(
        make_gmem_ptr(A),
        select<0,2>(problem_shape),
        dA);
```

其中：

```text
A 指针：数据从哪块 global memory 开始
Shape：  逻辑上把它看成 (M,K)
dA：     (m,k) 怎样映射到实际内存 offset
```

真正决定连续方向的是 `dA/dB`：

```cpp
// NT
dA = (1,ldA); // A 的 M mode 连续
dB = (1,ldB); // B 的 N mode 连续

// TN
dA = (ldA,1); // A 的 K mode 连续
dB = (ldB,1); // B 的 K mode 连续
```

对应地址公式：

```text
NT：
A_offset(m,k) = m + k*ldA
B_offset(n,k) = n + k*ldB

TN：
A_offset(m,k) = m*ldA + k
B_offset(n,k) = n*ldB + k
```

因此 `gemm_nt/gemm_tn` 的作用是准备不同配置：

```text
global-memory Stride
shared-memory Layout
copy Thread Layout
```

它们不会物理转置 A/B，也不会重新排列输入数组。

还要区分：

```text
dA/dB：描述输入 global-memory 数据的物理存储
sA/sB：描述 shared-memory tile 的物理存储
tA/tB：描述线程如何参与 copy，不是矩阵存储格式
```

## 4. CTA Tiler

官方基础示例选择：

```cpp
auto bM = Int<128>{};
auto bN = Int<128>{};
auto bK = Int<  8>{};

auto cta_tiler = make_shape(bM, bN, bK);
```

含义：

```text
一个 CTA 计算 C 的 128×128 tile
每轮 K-loop 消费 K=8
```

一个 CTA 需要：

```text
A tile：128×8
B tile：128×8
C tile：128×128
```

## 5. CTA 坐标

```cpp
auto cta_coord =
    make_coord(blockIdx.x, blockIdx.y, _);
```

三个 mode：

```text
M tile 坐标 = blockIdx.x
N tile 坐标 = blockIdx.y
K tile 坐标 = _
```

K 使用 `_`，因为当前 CTA 要保留所有 K tiles，并在 mainloop 中逐个归约。

## 6. `local_tile`

```cpp
Tensor gA =
    local_tile(mA, cta_tiler, cta_coord,
               Step<_1, X,_1>{});

Tensor gB =
    local_tile(mB, cta_tiler, cta_coord,
               Step< X,_1,_1>{});

Tensor gC =
    local_tile(mC, cta_tiler, cta_coord,
               Step<_1,_1, X>{});
```

结果：

```text
gA: (BLK_M,BLK_K,k)  // 当前 CTA 的 A tile；保留所有 K tiles
gB: (BLK_N,BLK_K,k)  // 当前 CTA 的 B tile；保留所有 K tiles
gC: (BLK_M,BLK_N)    // 当前 CTA 最终负责的 C tile
```

这里要区分：

```text
BLK_K：一个 K tile 内有多少个 K 元素
k：    完整 K 维被分成多少个 K tiles，对应 mainloop 的 k_tile mode
```

例如：

```text
K=512，BLK_K=8
则 k=512/8=64
```

所以：

```cpp
gA(_,_,0); // K=0..7
gA(_,_,1); // K=8..15
```

`gC` 没有 `k` mode，因为同一个 C tile 会跨所有 K tiles 持续累加。

`Step` 表示从三维 CTA tiler 中选哪些 mode：

| Tensor | 需要的 mode | Step |
|---|---|---|
| A `(M,K)` | M、K | `Step<_1,X,_1>` |
| B `(N,K)` | N、K | `Step<X,_1,_1>` |
| C `(M,N)` | M、N | `Step<_1,_1,X>` |

这里的 `X` 表示该 tiler mode 不参与当前 Tensor。

## 7. 展开 A 的 `local_tile`

下面两步等价于 `local_tile`：

### 先 divide

```cpp
Tensor tiled_A =
    zipped_divide(
        mA,                         // 完整 A Tensor，Shape=(M,K)
        select<0,2>(cta_tiler));    // 从 (BLK_M,BLK_N,BLK_K) 选出 (BLK_M,BLK_K)
```

`select<0,2>` 只是因为 A 不存在 N mode：

```text
cta_tiler = (BLK_M,BLK_N,BLK_K)
                  │ 丢弃 N
                  ▼
A tiler   = (BLK_M,BLK_K)
```

`zipped_divide` 分别把 M、K 拆成：

```text
M → (tile 内 M, 第几个 M tile)
K → (tile 内 K, 第几个 K tile)
```

然后把所有 tile 内坐标和所有 Rest 坐标分别打包：

```text
mA(M,K)
   ↓ zipped_divide by (BLK_M,BLK_K)
((BLK_M,BLK_K),(m_tile,k_tile))
```

其中：

```text
第一组 (BLK_M,BLK_K)：一个 tile 内部的坐标
第二组 (m_tile,k_tile)：tile 在完整矩阵中的编号
```

当前 `512×512` 例子：

```text
M=512，K=512
BLK_M=128，BLK_K=8

m_tile = 512/128 = 4
k_tile = 512/8   = 64
```

所以实际 Shape：

```text
((128,8),(4,64))
```

`zipped_divide` 仍然只创建 Tensor view，不会复制 A 的数据。

### 再 slice

```cpp
Tensor gA =
    tiled_A(
        make_coord(_,_),           // 保留 tile 内的 (BLK_M,BLK_K)
        make_coord(blockIdx.x,_)); // 固定 M tile，保留所有 K tiles
```

结果：

```text
(BLK_M,BLK_K,k)
```

含义是：

```text
固定当前 CTA 的 M tile
保留 tile 内 M/K
保留所有 K tile
```

因此：

```text
local_tile = divide + 在 Rest mode 上切片
```

## 8. 一个小例子

假设：

```text
ProblemShape = (M=256,N=384,K=24)
CtaTiler     = (128,128,8)
blockIdx     = (1,2)
```

当前 CTA 负责：

```text
C：
  M = 128..255
  N = 256..383

A：
  M = 128..255
  K tile = 0,1,2

B：
  N = 256..383
  K tile = 0,1,2
```

因此：

```text
gA shape = (128,8,3)
gB shape = (128,8,3)
gC shape = (128,128)
```

mainloop 的 `k_tile=0,1,2` 分别处理 K：

```text
0..7、8..15、16..23
```

## 9. Grid

通常：

```cpp
dim3 dimGrid(
    size(ceil_div(M, bM)),
    size(ceil_div(N, bN)));
```

也就是：

```text
grid.x = ceil(M / BLK_M)
grid.y = ceil(N / BLK_N)
```

但基础教程的 kernel 仍假设实际访存不会越界。若 M/N/K 不能整除 tile，必须加入
predicate，而不是仅依赖 `ceil_div`。

## 10. 静态检查

官方 kernel 会检查：

```cpp
CUTE_STATIC_ASSERT_V(rank(shape_MNK) == Int<3>{});
CUTE_STATIC_ASSERT_V(rank(cta_tiler) == Int<3>{});

CUTE_STATIC_ASSERT_V(
    congruent(select<0,2>(shape_MNK), dA));
CUTE_STATIC_ASSERT_V(
    congruent(select<1,2>(shape_MNK), dB));
CUTE_STATIC_ASSERT_V(
    congruent(select<0,1>(shape_MNK), dC));
```

`congruent` 关注 Shape 与 Stride 的层级结构兼容，不要求三者完全相等。

## 11. 按源码顺序理解 `sgemm_1.cu`

本地源码：[sgemm_1.cu](../代码实验/sgemm_1.cu)。

下面固定使用：

```text
M = 512
N = 512
K = 512
transA = N
transB = T
```

逐段追踪每个 Tensor 的 Shape、存储空间和职责。

### 11.1 Host 端选择配置

```cpp
auto bM = Int<128>{};
auto bN = Int<128>{};
auto bK = Int<  8>{};
auto cta_tiler = make_shape(bM, bN, bK);

auto tA = make_layout(make_shape(Int<32>{}, Int< 8>{}));
auto tB = make_layout(make_shape(Int<32>{}, Int< 8>{}));
auto tC = make_layout(make_shape(Int<16>{}, Int<16>{}));
```

先把这些数字翻译成人话：

```text
一个 CTA：
  计算 C 的 128×128 区域
  每轮处理 K=8

一个 block：
  tC 有 16×16=256 个线程位置
  所以启动 256 threads
```

Grid：

```text
grid.x = 512/128 = 4
grid.y = 512/128 = 4
```

总共 16 个 CTA，每个负责不同的 C tile。

### 11.2 `__launch_bounds__`

```cpp
__launch_bounds__(
    decltype(size(CThreadLayout{}))::value)
```

`CThreadLayout` 就是 `tC`：

```text
size(tC) = 16*16 = 256
```

因此这里告诉编译器：

```text
该 kernel 的 block size 是 256 threads
```

Host 端也使用：

```cpp
dim3 dimBlock(size(tC));
```

两侧保持一致。

### 11.3 为什么有大量 Static Assert

这些断言不是 GEMM 计算，而是在编译期证明配置彼此兼容。

例如：

```cpp
size(tA) == size(tB)
size(tC) == size(tA)
```

保证：

```text
copy A 使用 256 threads
copy B 使用 256 threads
compute C 也使用 256 threads
```

整除检查：

```cpp
BLK_M % THR_M == 0
BLK_N % THR_N == 0
BLK_K % THR_K == 0
```

保证 Thread Layout 可以无残缺地重复覆盖 CTA tile。

### 11.4 完整 Tensor

```cpp
Tensor mA = make_tensor(...); // (512,512)
Tensor mB = make_tensor(...); // (512,512)
Tensor mC = make_tensor(...); // (512,512)
```

三者都是 global-memory nonowning view：

```text
mA：A 指针 + (M,K) Layout
mB：B 指针 + (N,K) Layout
mC：C 指针 + (M,N) Layout
```

这里没有复制矩阵，也没有重新分配显存。

### 11.5 CTA Tile

```cpp
auto cta_coord =
    make_coord(blockIdx.x, blockIdx.y, _);
```

假设：

```text
blockIdx = (2,1)
```

当前 CTA 的 C 范围：

```text
M = 256..383
N = 128..255
```

`local_tile` 后：

```text
gA: (128,8,64)
gB: (128,8,64)
gC: (128,128)
```

其中：

```text
64 = K / BLK_K = 512/8
```

`gA/gB/gC` 仍然是 global-memory view，没有搬运数据。

### 11.6 Shared Tensor

```cpp
__shared__ TA smemA[cosize_v<ASmemLayout>];
__shared__ TB smemB[cosize_v<BSmemLayout>];

Tensor sA = make_tensor(...); // (128,8)
Tensor sB = make_tensor(...); // (128,8)
```

每个 CTA 只需要保存当前一个 K tile：

```text
sA：128×8 float
sB：128×8 float
```

因此 mainloop 每轮都会覆盖它们。

### 11.7 Copy partition：线程具体搬什么

A 的 Thread Layout：

```cpp
tA = Layout<Shape<_32,_8>>
```

默认 Layout 是：

```text
(32,8):(1,32)
```

线程编号 `tid` 转换为：

```text
thread_m = tid % 32
thread_k = tid / 32
```

例如 thread 35：

```text
thread_m = 35 % 32 = 3
thread_k = 35 / 32 = 1
```

A tile 是 `128×8`，Thread Layout 是 `32×8`，所以该线程负责：

```text
A( 3,1)
A(35,1)
A(67,1)
A(99,1)
```

即：

```text
M 方向每隔 32 取一个，共 4 个
K 方向固定为 1
```

因此：

```text
tAgA shape = (4,1,64)
tAsA shape = (4,1)
```

`tAgA` 多出的最后一维 `64` 是 K tile 编号。

### 11.8 256 个线程是否完整覆盖 A tile

每线程搬 4 个 A：

```text
256 threads * 4 values = 1024 values
```

整个 A tile：

```text
128 * 8 = 1024 values
```

数量一致。

B 的分区完全相同：

```text
256 threads * 4 values = 128 * 8
```

### 11.9 Copy 真正发生的位置

```cpp
copy(tAgA(_,_,k_tile), tAsA);
copy(tBgB(_,_,k_tile), tBsB);
```

这之前：

```text
tAgA/tBgB：global-memory view
tAsA/tBsB：shared-memory view
```

调用 `copy` 后才真正发生：

```text
global → shared
```

### 11.10 Math partition：线程具体算什么

C 的 Thread Layout：

```cpp
tC = Layout<Shape<_16,_16>>
```

默认 Layout：

```text
(16,16):(1,16)
```

线程坐标：

```text
thread_m = tid % 16
thread_n = tid / 16
```

以 thread 35 为例：

```text
thread_m = 3
thread_n = 2
```

C tile 是 `128×128`，所以它负责的 M 坐标：

```text
3,19,35,51,67,83,99,115
```

N 坐标：

```text
2,18,34,50,66,82,98,114
```

二者做笛卡尔积，因此该线程负责：

```text
8 * 8 = 64 个 C 元素
```

这不是连续的 `8×8` 小方块，而是以 16 为间隔的交错网格。

### 11.11 从 C 分工投影到 A、B

当前线程负责：

```text
C(m,n)
```

计算需要：

```text
A(m,k)
B(n,k)
```

所以：

```cpp
tCsA = local_partition(
    sA, tC, threadIdx.x,
    Step<_1,X>{});
```

保留 tC 的 M 分工，丢弃 N：

```text
tCsA shape = (8,8)
             8 M × 8 K
```

```cpp
tCsB = local_partition(
    sB, tC, threadIdx.x,
    Step<X,_1>{});
```

保留 tC 的 N 分工，丢弃 M：

```text
tCsB shape = (8,8)
             8 N × 8 K
```

```cpp
tCgC = local_partition(
    gC, tC, threadIdx.x,
    Step<_1,_1>{});
```

保留 M/N：

```text
tCgC shape = (8,8)
```

### 11.12 Register accumulator

```cpp
Tensor tCrC = make_tensor_like(tCgC);
clear(tCrC);
```

`tCgC` 与 `tCrC`：

```text
tCgC：指向 global C 的 nonowning view
tCrC：当前线程 owning accumulator Tensor
```

`tCrC` 通常被编译到寄存器。

它只在进入 mainloop 前清零一次，因为后续 64 个 K tiles 都要累加到同一组
accumulator。

### 11.13 一轮 GEMM 的计算量

```cpp
gemm(tCsA, tCsB, tCrC);
```

展开：

```text
M values = 8
N values = 8
K values = 8
```

所以每线程每轮：

```text
8 * 8 * 8 = 512 次 FMA
```

整个 CTA：

```text
256 * 512 = 131072 次 FMA
```

从 CTA tile 计算：

```text
128 * 128 * 8 = 131072 次 FMA
```

两种计算完全一致，说明线程分区覆盖正确。

### 11.14 K-loop

```cpp
auto K_TILE_MAX = size<2>(tAgA);
```

在当前例子中：

```text
K_TILE_MAX = 64
```

每轮处理 K=8：

```text
k_tile 0：K=0..7
k_tile 1：K=8..15
...
k_tile 63：K=504..511
```

`tCrC` 跨 64 轮持续累加。

### 11.15 两个同步点

copy 后：

```cpp
__syncthreads();
```

保证：

```text
所有线程都写完 sA/sB
然后才允许任何线程读取
```

gemm 后：

```cpp
__syncthreads();
```

保证：

```text
所有线程都读完当前 sA/sB
然后下一轮才能覆盖 shared memory
```

### 11.16 Epilogue

```cpp
axpby(alpha, tCrC, beta, tCgC);
```

执行：

```text
global C =
    alpha * register accumulator
  + beta  * old global C
```

当前运行参数：

```text
alpha = 1
beta  = 0
```

所以等价于直接把 accumulator 写入 C。

### 11.17 本地增加的结果检查

官方代码只运行和计时。本仓库增加：

```cpp
check_gemm_result(...);
```

执行顺序：

```text
运行一次 CUDA GEMM
复制 C 回 Host
CPU 计算 reference GEMM
比较每个 C(m,n)
通过后再进行 100 次性能计时
```

结果检查不在计时区间内。

### 11.18 `gemm` 包装函数的运行时分派

```cpp
if (transA == 'N' && transB == 'T') {
  return gemm_nt(...);
} else if (transA == 'T' && transB == 'N') {
  return gemm_tn(...);
}
assert(false && "Not implemented");
```

这里根据运行时传入的 `transA/transB`，选择教程已经准备好的两套配置：

```text
NT → gemm_nt
     A 使用 M-major Layout
     B 使用 N-major Layout

TN → gemm_tn
     A、B 都使用 K-major Layout
```

这个分派不会真正创建转置矩阵，只会改变：

- A/B 指针的 Stride 解释；
- shared-memory Layout；
- copy Thread Layout；
- 最终调用的 kernel 配置。

当前教程没有实现 NN、TT，因此其他组合进入 assert。这是示例范围限制，不是
CuTe 的能力限制。

### 11.19 整体数据流

```text
mA/mB/mC
    │ local_tile
    ▼
gA/gB/gC
    │ local_partition(tA/tB)
    ▼
tAgA/tBgB
    │ copy
    ▼
sA/sB
    │ local_partition(tC projection)
    ▼
tCsA/tCsB
    │ gemm
    ▼
tCrC
    │ axpby
    ▼
tCgC → global C
```

## 本节完成标准

能够看到以下代码后立即说出三个 Tensor 的含义：

```cpp
gA = local_tile(...); // 当前 CTA 的 A tile，保留全部 K tiles
gB = local_tile(...); // 当前 CTA 的 B tile，保留全部 K tiles
gC = local_tile(...); // 当前 CTA 最终负责的 C tile
```

## 编译与运行 `sgemm_1`

以下命令已在 A100 SM80、CUDA 12.2 环境验证。

### 编译官方原始版本

在 CUTLASS 仓库根目录执行：

```bash
NVCC=/usr/local/cuda-12.2/bin/nvcc
BUILD=build-cute-tutorial

mkdir -p "$BUILD"

"$NVCC" \
  -std=c++17 \
  -O3 \
  -lineinfo \
  -arch=sm_80 \
  -Iinclude \
  -Itools/util/include \
  examples/cute/tutorial/sgemm_1.cu \
  -o "$BUILD/sgemm_1"
```

运行：

```bash
./build-cute-tutorial/sgemm_1 \
  512 512 512 N T
```

参数顺序：

```text
sgemm_1 M N K transA transB
```

基础示例要求 M、N、K 与 CTA tile 整除。这里的 `512` 可以被：

```text
BLK_M = 128
BLK_N = 128
BLK_K = 8
```

整除。

### 编译本仓库带结果检查的版本

本地源码：

```text
07-GEMM-Tutorial/代码实验/sgemm_1.cu
07-GEMM-Tutorial/代码实验/reference_check.hpp
```

在 CUTLASS 仓库根目录执行：

```bash
NVCC=/usr/local/cuda-12.2/bin/nvcc
SRC=/path/to/WorkNotes/cute/07-GEMM-Tutorial/代码实验
BUILD=build-cute-tutorial-checked

mkdir -p "$BUILD"

"$NVCC" \
  -std=c++17 \
  -O3 \
  -lineinfo \
  -arch=sm_80 \
  -Iinclude \
  -Itools/util/include \
  -I"$SRC" \
  "$SRC/sgemm_1.cu" \
  -o "$BUILD/sgemm_1"
```

运行：

```bash
./build-cute-tutorial-checked/sgemm_1 \
  512 512 512 N T
```

成功时会先输出：

```text
RESULT_CHECK: PASS
```

然后输出 GEMM 性能。

如果目标 GPU 不是 SM80，需要把：

```text
-arch=sm_80
```

替换为对应 Compute Capability。

## 官方资料

- [CuTe GEMM Tutorial：Full Tensors 与 CTA Partitioning](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0x_gemm_tutorial.html)
- [sgemm_1.cu](https://github.com/NVIDIA/cutlass/blob/main/examples/cute/tutorial/sgemm_1.cu)
