# Math Partitioning 与 Mainloop

> 官方示例：`sgemm_1.cu`、`sgemm_2.cu`
>
> 更新：2026-09-22

copy partition 回答“每个线程搬哪些数据”，math partition 回答：

```text
每个线程计算 C tile 中哪些元素？
为了计算这些元素，它需要 A、B 中哪些行/列？
```

## 1. 从 C 的线程布局出发

基础示例：

```cpp
auto tC =
    make_layout(make_shape(Int<16>{}, Int<16>{}));
```

CTA 的 C tile 是：

```text
128×128
```

线程布局是：

```text
16×16 = 256 threads
```

所以每个线程负责：

```text
M：128/16 = 8
N：128/16 = 8

每线程 C subtensor = 8×8
```

## 2. 从 C 投影到 A 和 B

C 的一个元素：

```text
C(m,n) += Σ_k A(m,k) * B(n,k)
```

因此：

- 当前线程负责哪些 `m`，决定它需要 A 的哪些行；
- 当前线程负责哪些 `n`，决定它需要 B 的哪些行；
- K mode 对所有线程都要保留。

官方代码：

```cpp
Tensor tCsA =
    local_partition(
        sA, tC, threadIdx.x,
        Step<_1, X>{});

Tensor tCsB =
    local_partition(
        sB, tC, threadIdx.x,
        Step<X, _1>{});

Tensor tCgC =
    local_partition(
        gC, tC, threadIdx.x,
        Step<_1,_1>{});
```

结果：

```text
tCsA: (THR_M,BLK_K)
tCsB: (THR_N,BLK_K)
tCgC: (THR_M,THR_N)
```

投影关系：

```text
tC(M,N)
 ├─ 保留 M，丢弃 N → partition A(M,K)
 ├─ 丢弃 M，保留 N → partition B(N,K)
 └─ 保留 M、N      → partition C(M,N)
```

这里的 `X` 容易误解：

```text
Step<_1,X>：
  M 线程坐标参与 A 的分区
  N 线程坐标不参与

Step<X,_1>：
  M 线程坐标不参与 B 的分区
  N 线程坐标参与
```

`X` 表示忽略该线程 mode，**不是把该 mode 的坐标或 Shape 设为 1**。
`_1` 表示保留该 mode，并使用单位步长。

因此对于 B：

```text
(thread_m,thread_n)
        ↓ Step<X,_1>
     thread_n
```

M 不同但 N 相同的线程会得到相同的 `tCsB` view，因为：

```text
C(m,n) += Σk A(m,k) * B(n,k)
```

`B(n,k)` 与 `m` 无关。与此同时，B 自身的 K mode 没有被删除，结果仍为：

```text
tCsB: (THR_N,BLK_K)
```

## 3. Accumulator

```cpp
Tensor tCrC = make_tensor_like(tCgC);
clear(tCrC);
```

区别：

```text
tCgC：global-memory C tile 上的每线程 nonowning view
tCrC：当前线程拥有的 accumulator Tensor
```

`tCrC` 通常位于寄存器，Shape 与当前线程负责的 C subtensor 一致。

## 4. Shape 检查

GEMM 需要：

```text
tCrC.M == tCsA.M
tCrC.N == tCsB.N
tCsA.K == tCsB.K
```

官方代码使用静态断言验证：

```cpp
CUTE_STATIC_ASSERT_V(
    size<0>(tCrC) == size<0>(tCsA));

CUTE_STATIC_ASSERT_V(
    size<1>(tCrC) == size<0>(tCsB));

CUTE_STATIC_ASSERT_V(
    size<1>(tCsA) == size<1>(tCsB));
```

这正是：

```text
(M,K) × (N,K) → (M,N)
```

在每线程 subtensor 上的体现。

## 5. 最简单的 mainloop

```cpp
auto K_TILE_MAX = size<2>(tAgA);

for (int k_tile = 0;
     k_tile < K_TILE_MAX;
     ++k_tile)
{
  copy(tAgA(_,_,k_tile), tAsA);
  copy(tBgB(_,_,k_tile), tBsB);

  cp_async_fence();
  cp_async_wait<0>();
  __syncthreads();

  gemm(tCsA, tCsB, tCrC);

  __syncthreads();
}
```

按阶段理解：

```text
1. 当前 K tile：global → shared
2. 等待 copy 完成
3. 所有线程共同消费 shared tile
4. 将结果累加到各自 register accumulator
5. 确认所有线程读完，再覆盖 shared memory
```

## 6. `gemm(tCsA,tCsB,tCrC)` 展开

这里调用的是 CuTe 算法：

```cpp
cute::gemm(tCsA, tCsB, tCrC);
```

它不是 CUDA/C++ 内置函数，定义在：

```text
include/cute/algorithm/gemm.hpp
```

三参数形式表示原地累加：

```text
tCrC += tCsA × tCsB
```

`sgemm_1.cu` 没有显式传入 `MMA_Atom`，因此 CuTe 使用默认
`UniversalFMA`。后续 SM80 示例显式写成：

```cpp
cute::gemm(mma, tCrA, tCrB, tCrC);
```

才会根据指定的 MMA Atom 分派到对应硬件指令。

概念上相当于：

```cpp
for (int k = 0; k < size<1>(tCsA); ++k) {
  for (int m = 0; m < size<0>(tCrC); ++m) {
    for (int n = 0; n < size<1>(tCrC); ++n) {
      tCrC(m,n) +=
          tCsA(m,k) * tCsB(n,k);
    }
  }
}
```

也就是每轮 K tile 完成一次：

```text
每线程 A subtensor
    ×
每线程 B subtensor
    ↓
累加到每线程 C accumulator
```

## 7. 为什么有两个 `__syncthreads`

第一个：

```text
copy 完成后
等待所有线程写完 shared memory
```

否则某线程可能读取到其他线程尚未写入的 sA/sB。

第二个：

```text
gemm 完成后
等待所有线程读完 shared memory
```

否则较快线程可能开始下一轮 copy，覆盖仍被其他线程读取的数据。

异步 copy 还需要额外的 instruction-specific wait；block barrier 不能代替
异步事务完成。

## 8. 使用 TiledMMA

`sgemm_2.cu` 将手工 `tC` 替换为：

```cpp
TiledMMA mma =
    make_tiled_mma(
        UniversalFMA<TC,TA,TB>{},
        Layout<Shape<_16,_16,_1>>{});
```

这里 `UniversalFMA` 是 `1×1×1` Atom。在线程上铺成 `16×16×1` 后：

```text
256 threads
每个线程代表一个基础 FMA 位置
```

每线程分区：

```cpp
ThrMMA thr_mma = mma.get_slice(threadIdx.x);

Tensor tCsA = thr_mma.partition_A(sA);
Tensor tCsB = thr_mma.partition_B(sB);
Tensor tCgC = thr_mma.partition_C(gC);

Tensor tCrC = thr_mma.make_fragment_C(tCgC);
```

计算：

```cpp
gemm(mma, tCsA, tCsB, tCrC);
```

这与手工 Thread Layout 的数学分工相同，但把：

```text
MMA 指令
线程布局
value 布局
operand partition
```

统一交给 TiledMMA 描述。

## 9. Register staging mainloop

`sgemm_2.cu` 提前把下一 K tile 从 global memory 搬到 register：

```text
tArA / tBrB：下一轮 global 数据
tAsA / tBsB：当前 shared tile
tCrC：持续累加的结果
```

循环中的时序：

```text
register → shared：提交当前 tile
global   → register：预取下一 tile
shared   → compute：计算当前 tile
```

这是一种单级预取。它仍需要 shared-memory barrier，但可以把部分 global load
延迟隐藏在当前计算后面。

## 10. Epilogue

K-loop 结束后：

```cpp
axpby(alpha, tCrC, beta, tCgC);
```

逐元素执行：

```text
C = alpha * accumulator + beta * C
```

这里：

```text
tCrC：register accumulator
tCgC：global-memory C view
```

`axpby` 完成类型允许范围内的读取、缩放和写回。

## 11. 一轮 mainloop 的对象关系

```text
gA/gB
  │ copy partition
  ▼
tAgA/tBgB
  │ copy
  ▼
tAsA/tBsB → sA/sB
                │ math partition
                ▼
             tCsA/tCsB
                │ gemm
                ▼
               tCrC
                │ axpby
                ▼
               tCgC
```

## 本节完成标准

能够解释：

1. 为什么 math partition 必须从 C 的线程分工投影到 A 和 B；
2. `tCgC` 与 `tCrC` 的区别；
3. K-loop 每轮 copy、wait、gemm、barrier 的原因；
4. accumulator 为什么跨所有 K tiles 保持不清零；
5. epilogue 为什么发生在 K-loop 之后。

## 官方资料

- [CuTe GEMM Tutorial：Math Partitioning 与 Mainloop](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0x_gemm_tutorial.html)
- [sgemm_1.cu](https://github.com/NVIDIA/cutlass/blob/main/examples/cute/tutorial/sgemm_1.cu)
- [sgemm_2.cu](https://github.com/NVIDIA/cutlass/blob/main/examples/cute/tutorial/sgemm_2.cu)
