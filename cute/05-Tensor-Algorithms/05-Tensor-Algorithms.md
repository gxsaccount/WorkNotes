# 05 Tensor Algorithms

> 官方对应：`media/docs/cpp/cute/04_algorithms.md`
>
> 官方基线：NVIDIA CUTLASS `main`，核对日期 2026-09-16
>
> 前置章节：[Tensor](../04-Tensor/04-Tensor.md)

前一章解决了“如何描述数据”，本章开始解决“如何在 Tensor 上计算”：

```text
Tensor = Engine + Layout
Algorithm = 根据 Tensor 类型选择实现，并按逻辑坐标访问数据
```

CuTe 算法的关键不是把一个固定循环包装成函数，而是让参数类型携带元素类型、
存储空间、Shape、Layout、Atom、对齐和向量化信息。算法据此在编译期分派到
通用循环、向量化访存、异步 copy 或 MMA/FMA 等实现。

## 推荐学习顺序

1. [copy](01-Copy/01-Copy.md)
   - 默认接口与 `Copy_Atom` 接口
   - 逻辑坐标遍历
   - 类型驱动的指令分派
   - 并行范围、异步完成与同步责任
2. [copy_if](02-Copy-If/02-Copy-If.md)
   - predicate Tensor
   - 越界元素为什么必须跳过
   - false predicate 下目标元素保持不变
3. [gemm](03-GEMM/03-GEMM.md)
   - 五种 mode 组合
   - `V`、`M`、`N`、`K` 的顺序
   - `C += A * B` 与 `D = A * B + C`
   - 默认 FMA 与 `MMA_Atom` 分派
4. [axpby、fill、clear](04-Elementwise/04-Elementwise.md)
   - Tensor 上的逐元素算法
   - predicate 与零初始化

## 统一心智模型

### 1. 算法按逻辑坐标配对元素

最朴素的 `copy` 可以理解为：

```cpp
for (int i = 0; i < size(dst); ++i) {
  dst(i) = src(i);
}
```

这里的 `i` 是一维逻辑坐标。`src(i)` 与 `dst(i)` 分别通过自己的 Layout
计算地址。因此，源 Tensor 和目标 Tensor 不必具有相同 stride，也不必位于
同一种存储空间。

### 2. 算法调用不等于同步完成

必须分别回答三个问题：

1. 哪些线程参与了这次操作？
2. 底层指令是同步还是异步？
3. 消费结果前需要什么 barrier / wait？

`copy(...)` 这个函数名本身不能回答这些问题。答案取决于参数类型、所选
Copy Atom 以及目标架构。

### 3. Layout 决定“谁和谁对应”，Atom 决定“怎样执行”

```text
Tensor Layout
  └─ 描述每个逻辑元素的位置

Copy_Atom / MMA_Atom
  └─ 描述一条基础 copy / multiply-accumulate 操作

TiledCopy / TiledMMA
  └─ 把 Atom 扩展并分配给线程和值
```

本章先理解算法接口；Copy Atom、TiledCopy 和 MMA Atom 的完整构造会在后续
章节继续展开。

## API 速查

| 算法 | 核心语义 | 主要头文件 |
|---|---|---|
| `copy(src, dst)` | 复制对应逻辑元素 | `cute/algorithm/copy.hpp` |
| `copy(atom, src, dst)` | 使用指定 Copy Atom | `cute/algorithm/copy.hpp` |
| `copy_if(pred, src, dst)` | predicate 为真时复制 | `cute/algorithm/copy.hpp` |
| `gemm(A, B, C)` | 原地执行 `C += A * B` | `cute/algorithm/gemm.hpp` |
| `gemm(D, A, B, C)` | 执行 `D = A * B + C` | `cute/algorithm/gemm.hpp` |
| `axpby(alpha, x, beta, y)` | `y = alpha*x + beta*y` | `cute/algorithm/axpby.hpp` |
| `fill(tensor, value)` | 所有元素写入指定值 | `cute/algorithm/fill.hpp` |
| `clear(tensor)` | 所有元素写入值类型的零值 | `cute/algorithm/clear.hpp` |

## 本章最容易混淆的点

| 误解 | 正确认识 |
|---|---|
| `copy` 一定是单线程标量循环 | 它会根据参数类型分派，也可能使用并行或异步硬件指令 |
| `copy` 返回就能立刻读取目标 | 异步或多线程 copy 可能还需要 wait/barrier |
| 源和目标 Layout 必须相同 | 需要逻辑元素可配对；物理 stride 可以不同 |
| `copy_if` 的 false 分支会写零 | false 时不写目标，旧值保持不变 |
| CuTe 的 B 矩阵写成 `(K,N)` | CuTe GEMM 接口使用 `(N,K)` |
| `gemm(A,B,C)` 会覆盖 C | 三参数接口执行累加，语义是 `C += A*B` |
| `clear` 等于清空底层分配 | 它把 Tensor 的逻辑元素赋为 `value_type{}` |

## 建议练习

### 练习 1：不同 Layout 的 copy

取两个 shape 都为 `(2,3)` 的 Tensor：

```text
src: (2,3):(1,2)
dst: (2,3):(3,1)
```

逐个展开 `src(i)` 与 `dst(i)` 的物理 offset，观察逻辑顺序相同但物理访问顺序
不同。

### 练习 2：predicate

令：

```text
src  = [10, 20, 30, 40]
dst  = [-1, -1, -1, -1]
pred = [true, false, true, false]
```

手算 `copy_if` 后的 `dst`，并解释为什么结果不是 `[10, 0, 30, 0]`。

### 练习 3：GEMM mode

分别写出以下接口中每个 mode 的意义：

```text
(M,K)   x (N,K)   => (M,N)
(V,M,K) x (V,N,K) => (V,M,N)
```

说明 `V` 为什么放在最左边，`K` 为什么放在最右边。

## 本章完成标准

学完后应能回答：

1. `copy` 为什么能根据 Tensor 类型选择不同指令？
2. 源、目标 Layout 不同时，`copy` 按什么规则配对元素？
3. 为什么不能仅凭 `copy` 函数名判断线程范围和同步语义？
4. `Copy_Atom` 解决什么问题？
5. `copy_if` 遇到 false predicate 时会怎样处理目标元素？
6. CuTe GEMM 的五种 mode 组合分别表示什么？
7. 三参数和四参数 `gemm` 有什么区别？
8. `axpby` 在 `beta == 0` 时为什么可以不读取原来的 `y`？
9. `fill(t, 0)` 与 `clear(t)` 有什么关系？

## 官方资料

- [NVIDIA CuTe Tensor Algorithms](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/04_algorithms.html)
- [NVIDIA/CUTLASS 官方 Markdown](https://github.com/NVIDIA/cutlass/blob/main/media/docs/cpp/cute/04_algorithms.md)
- [算法头文件目录](https://github.com/NVIDIA/cutlass/tree/main/include/cute/algorithm)
- 主要头文件：`copy.hpp`、`gemm.hpp`、`axpby.hpp`、`fill.hpp`、`clear.hpp`
