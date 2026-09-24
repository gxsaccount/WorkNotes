# gemm 算法接口

> 官方对应：`include/cute/algorithm/gemm.hpp`
>
> 更新：2026-09-16

本节只学习 CuTe `gemm` 的算法接口和 mode 约定。完整 CUDA kernel、CTA
partition、shared-memory mainloop 和流水线放在
[GEMM Tutorial](../../07-GEMM-Tutorial/07-GEMM-Tutorial.md)。

## 1. 两种数学接口

### 三参数：原地累加

```cpp
gemm(A, B, C);
```

语义：

```text
C = A * B + C
```

也常写作：

```text
C += A * B
```

### 四参数：独立输入与输出

```cpp
gemm(D, A, B, C);
```

语义：

```text
D = A * B + C
```

三参数版本本质上把 `C` 同时作为初始累加器和输出：

```cpp
gemm(C, A, B, C);
```

两种形式都可额外传入 `MMA_Atom`：

```cpp
gemm(mma, A, B, C);
gemm(mma, D, A, B, C);
```

## 2. CuTe 的四个 mode 字母

| mode | 含义 |
|---|---|
| `V` | 一次 FMA/MMA 操作内部的独立 value |
| `M` | 输出矩阵 C/D 的行方向 |
| `N` | 输出矩阵 C/D 的列方向 |
| `K` | reduction 方向 |

顺序约定：

```text
V 总在最左侧，即 innermost
K 总在最右侧，即 outermost
```

因此完整形式是：

```text
A: (V,M,K)
B: (V,N,K)
C: (V,M,N)
D: (V,M,N)
```

注意，B 使用 `(N,K)`，不是教科书裸矩阵记号中的 `(K,N)`。CuTe 这里描述的是
各操作数 Tensor 的逻辑 mode。

## 3. 五种 dispatch

### 3.1 value-wise product

```text
(V) x (V) => (V)
D_v = A_v * B_v + C_v
```

这是最内层操作，直接分派给 FMA 或 MMA Atom。

### 3.2 outer product

```text
(M) x (N) => (M,N)
D_mn = A_m * B_n + C_mn
```

这里的 `x` 表示两个 GEMM 操作数相乘，不是 Shape 之间做普通乘法。可以先把它
理解成两次**逻辑广播**：

```text
A(M) 沿 N 广播为 A'(M,N)：A'(m,n) = A(m)
B(N) 沿 M 广播为 B'(M,N)：B'(m,n) = B(n)

D = A' ⊙ B' + C
```

例如：

```text
A = [2, 3]
B = [5, 7, 11]

A 广播后：          B 广播后：
[[2, 2, 2],         [[ 5,  7, 11],
 [3, 3, 3]]          [ 5,  7, 11]]

A' ⊙ B' =
[[10, 14, 22],
 [15, 21, 33]]
```

对应循环：

```cpp
for (int m = 0; m < M; ++m) {
  for (int n = 0; n < N; ++n) {
    D(m,n) = A(m) * B(n) + C(m,n);
  }
}
```

这里通常只是语义上的广播：CuTe 不需要真的创建两个 `(M,N)` 临时 Tensor，
而是直接让每个 `A(m)` 与每个 `B(n)` 两两配对。

可看成 `V = 1` 的 batched outer product。

### 3.3 matrix product

```text
(M,K) x (N,K) => (M,N)
D_mn = C_mn + Σ_k A_mk * B_nk
```

实现沿 K mode 迭代，每个 K slice 分派到 outer product。

### 3.4 batched outer product

```text
(V,M) x (V,N) => (V,M,N)
D_vmn = A_vm * B_vn + C_vmn
```

实现会针对寄存器复用安排 M/N 遍历顺序，再对每个 `(m,n)` 分派到最内层
value-wise FMA/MMA。

这里的 “batched” 是指存在 `V` mode，不应直接理解成通常 GEMM API 的 batch
维度。

### 3.5 batched matrix product

```text
(V,M,K) x (V,N,K) => (V,M,N)
D_vmn = C_vmn + Σ_k A_vmk * B_vnk
```

实现沿 K 迭代，并对每个 K slice 调用 batched outer product。

## 4. dispatch 层级

五种形式构成递归分派关系：

```text
(V,M,K) x (V,N,K)
          │ 遍历 K
          ▼
  (V,M) x (V,N)
          │ 遍历 M,N，并优化寄存器复用
          ▼
      (V) x (V)
          │
          ▼
       MMA/FMA
```

无 `V` 的形式可以通过补一个大小为 1 的 `V` mode 接入同一体系：

```text
(M,K) x (N,K)
      ↓ prepend V=1
(1,M,K) x (1,N,K)
```

## 5. 默认 FMA 与显式 MMA Atom

不传 Atom 时，当前官方实现根据 D、A、B、C 的 value type 构造
`UniversalFMA`：

```text
gemm(D, A, B, C)
  ↓
MMA_Atom<UniversalFMA<...>>
  ↓
gemm(mma, D, A, B, C)
```

显式传入 `MMA_Atom` 时，调用者可以选择适合架构和数据类型的 MMA 操作：

```cpp
gemm(mma_atom, D, A, B, C);
```

Atom 还携带 A/B/C/D 的数据类型关系、单次操作的逻辑 Shape、thread/value 到
fragment 的映射，以及 operand 和 accumulator 的布局约束。

这些内容在下一章 [MMA Atom](../../06-MMA-Atom/06-MMA-Atom.md) 展开。

## 6. Shape 兼容条件

以完整形式为例：

```text
A: (V, M, K)
B: (V, N, K)
C: (V, M, N)
D: (V, M, N)
```

至少需要：

```text
A.V == B.V == C.V == D.V
A.M == C.M == D.M
B.N == C.N == D.N
A.K == B.K
```

具体 Atom 还会检查 `V` mode 是否与指令的 A/B/C value layout 兼容。

## 7. 不要把算法接口当成完整 kernel

当前头文件的主要重载包括：

- thread-local register-memory GEMM；
- 从 shared-memory A/B 构造 fragment，再输出 register accumulator 的 GEMM。

这不表示：

```cpp
gemm(global_A, global_B, global_C);
```

就自动生成一个高性能、完整同步、带分块的设备级 GEMM kernel。

完整 kernel 仍需负责：

1. CTA tile；
2. global → shared copy；
3. shared → register fragment；
4. K-loop；
5. barrier / pipeline；
6. epilogue 与 global store；
7. 边界 predication。

`cute::gemm` 更接近“对已经正确分区和组织的 Tensor fragment 执行乘加”的算法层。

## 8. 一个小型手算例子

取：

```text
A(M,K) = [[1, 2],
          [3, 4]]

B(N,K) = [[5, 6],
          [7, 8],
          [9,10]]
```

注意 B 的每一行对应一个 `n`，该行沿 K：

```text
C(0,0) += 1*5 + 2*6
C(0,1) += 1*7 + 2*8
C(0,2) += 1*9 + 2*10

C(1,0) += 3*5 + 4*6
C(1,1) += 3*7 + 4*8
C(1,2) += 3*9 + 4*10
```

输出 shape 为 `(M,N) = (2,3)`。

## 9. 常见错误

### 错误 1：把 B 写成 `(K,N)`

CuTe 的该算法接口约定是 `(N,K)`。

### 错误 2：忘记 C 是累加输入

三参数 `gemm(A,B,C)` 不会隐式清零 C。若需要纯 `A*B`：

```cpp
clear(C);
gemm(A, B, C);
```

### 错误 3：把 `V` 当普通 batch

`V` 表示 Atom 内部的独立 value mode，与普通 batched GEMM 的 batch 维语义不同。

### 错误 4：只看元素总数

GEMM 需要各 mode 分别兼容，而不是 `size(A)`、`size(B)`、`size(C)` 凑得上即可。

### 错误 5：认为 `gemm` 自动处理任意 memory space

应先阅读具体重载的 rank、memory space 和 Atom 约束。

## 10. 自测

1. `gemm(A,B,C)` 和 `gemm(D,A,B,C)` 分别计算什么？
2. 为什么 B 的 mode 是 `(N,K)`？
3. 五种 dispatch 中，哪一种直接调用 MMA/FMA？
4. `(V,M,K)` 形式怎样逐层分派？
5. `V` 和普通 batch 维有什么区别？
6. 为什么完整高性能 GEMM kernel 不能只写一次 `cute::gemm` 调用？

## 官方资料

- [CuTe Tensor Algorithms：gemm](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/04_algorithms.html#gemm)
- [gemm.hpp](https://github.com/NVIDIA/cutlass/blob/main/include/cute/algorithm/gemm.hpp)
- [CuTe GEMM Tutorial](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0x_gemm_tutorial.html)
