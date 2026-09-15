# Composition Tilers

> 官方对应：NVIDIA CUTLASS `media/docs/cpp/cute/02_layout_algebra.md`
>
> 更新：2026-09-15

本节按照 NVIDIA 官方文档的定义和例子学习。

> **先说结论：Composition Tilers 不是一个新的运算。**
>
> 它是官方对 composition 右操作数类型的总结。其中 tuple Tiler 和 Shape Tiler
> 采用的正是前面所说的 **by-mode composition**；本节新增的重点只是把这套规则推广到
> 任意嵌套层级，并说明单个 Layout、tuple 和 Shape 三种输入如何分派。

---

## 0. 官方定义

CuTe 中，`composition(A, B)` 的第二个参数 `B` 可以是以下三类 **Tiler**：

1. 一个 `Layout`
2. 一个由 Tiler 组成的 tuple
3. 一个 `Shape`；CuTe 会把它解释成由 stride-1 Layout 组成的 tuple

关键区别是：

| Tiler 类型 | composition 的含义 |
|---|---|
| 单个 `Layout` | 把 A、B 都看作“整数到整数”的函数，计算普通 `A(B(i))` |
| tuple of Tilers | A 与 B 按对应 mode 递归 composition |
| `Shape` | 先解释成 stride-1 的 tuple tiler，再按 mode composition |

因此，首先要看的是右操作数的**类型和层级结构**，不能只看其中的数字。

换句话说：

```text
Composition Tilers（概念总称）
├─ Layout Tiler       → 普通 composition
├─ tuple Tiler        → by-mode composition
└─ Shape Tiler        → 转成 stride-1 tuple，再做 by-mode composition
```

tuple 可以继续嵌套，CuTe 会递归地按 mode 配对，直到遇到单个 Layout：

```text
A = (A0,(A10,A11))
T = <T0,<T10,T11>>

composition(A,T)
  = (A0∘T0, (A10∘T10, A11∘T11))
```

---

## 1. 单个 Layout：普通 Composition

当 B 是一个 Layout 时，无论 A、B 各有几个 mode，都把它们看成：

```text
逻辑 index → 整数
```

然后直接计算：

```text
R(i) = A(B(i))
```

如果 B 是由多个 sublayout 拼成的 Layout：

```text
B = (B0,B1,...)
```

则使用左分配：

```text
A ∘ (B0,B1,...) = (A∘B0, A∘B1, ...)
```

注意：每个 `Bi` 都与**完整的 A** composition。

---

## 2. Tuple Tiler：官方 by-mode 例子

NVIDIA 官方文档给出的 A 是：

```text
A = (12,(4,8)):(59,(13,1))
```

A 有两个顶层 mode：

```text
A.mode-0 = 12:59
A.mode-1 = (4,8):(13,1)
```

官方 tuple tiler 是：

```text
T = <3:4, 8:2>
```

尖括号表示两个 tiler，分别作用于 A 的两个顶层 mode：

```text
R.mode-0 = A.mode-0 ∘ 3:4
R.mode-1 = A.mode-1 ∘ 8:2
```

### 2.1 计算 mode-0

```text
12:59 ∘ 3:4
```

左侧是单 mode integral layout，直接使用：

```text
s:(b×d)
```

所以：

```text
12:59 ∘ 3:4 = 3:(59×4) = 3:236
```

对应循环：

```c
for (j0 = 0; j0 < 3; ++j0)
  offset0 = 236*j0;
```

### 2.2 计算 mode-1

```text
(4,8):(13,1) ∘ 8:2
```

`8:2` 产生的逻辑 index 是：

```text
0, 2, 4, 6, 8, 10, 12, 14
```

拿这些 index 查询 `(4,8):(13,1)`：

| 新 index | 原 index | 原坐标 `(i0,i1)` | offset |
|---:|---:|---|---:|
| 0 | 0  | `(0,0)` | 0 |
| 1 | 2  | `(2,0)` | 26 |
| 2 | 4  | `(0,1)` | 1 |
| 3 | 6  | `(2,1)` | 27 |
| 4 | 8  | `(0,2)` | 2 |
| 5 | 10 | `(2,2)` | 28 |
| 6 | 12 | `(0,3)` | 3 |
| 7 | 14 | `(2,3)` | 29 |

这个序列可以表示为：

```text
(2,4):(26,1)
```

因为：

```c
for (j1 = 0; j1 < 4; ++j1)
  for (j0 = 0; j0 < 2; ++j0)
    offset1 = 26*j0 + j1;
```

### 2.3 拼回顶层结构

两个 mode 分别得到：

```text
R.mode-0 = 3:236
R.mode-1 = (2,4):(26,1)
```

所以官方结果是：

```text
A ∘ <3:4, 8:2>
  = (3,(2,4)):(236,(26,1))
```

这里的嵌套括号不能拍掉，因为它记录了结果仍然对应 A 的两个顶层 mode。

---

## 3. Shape Tiler：官方例子

对同一个 A：

```text
A = (12,(4,8)):(59,(13,1))
```

官方使用：

```text
T = (3,8)    // Shape，不是 Layout
```

CuTe 将 Shape Tiler 解释为：

```text
<3:1, 8:1>
```

于是仍然按 mode 计算：

```text
A.mode-0 ∘ 3:1
  = 12:59 ∘ 3:1
  = 3:59

A.mode-1 ∘ 8:1
  = (4,8):(13,1) ∘ 8:1
  = (4,2):(13,1)
```

最终得到官方结果：

```text
A ∘ Shape(3,8)
  = (3,(4,2)):(59,(13,1))
```

它表达的是：从 A 的 mode-0 取前 3 个逻辑坐标，同时从 mode-1 取前 8 个逻辑坐标。

### Shape Tiler 与 Tuple Tiler 的区别

两者都会进行 by-mode composition，区别在于每个 mode 能否显式指定 Layout：

| | Shape Tiler | Tuple Tiler |
|---|---|---|
| 示例 | `(3,8)` | `<3:4, 8:2>` |
| CuTe 的解释 | `<3:1, 8:1>` | 保持 `<3:4, 8:2>` |
| 每个 mode 的 stride | 固定为 `1` | 可以任意指定 |
| 能力 | 从每个 mode 的开头连续取一段 | 可以间隔采样、重排或使用嵌套 Layout |

因此：

```text
Shape(3,8)
  ≡ <3:1, 8:1>
```

但它不等于：

```text
<3:4, 8:2>
```

前者分别选取逻辑 index：

```text
mode-0：0,1,2
mode-1：0,1,2,3,4,5,6,7
```

后者分别选取：

```text
mode-0：0,4,8
mode-1：0,2,4,6,8,10,12,14
```

一句话：

> **Shape Tiler 是只能表达大小、各 mode 默认 stride 为 1 的 Tuple Tiler 简写；Tuple
> Tiler 可以为每个 mode 指定完整的 Layout。**

---

## 4. 为什么圆括号和尖括号不能混

用一个较小的辅助例子对比：

```text
A = (6,2):(8,2)
```

### 普通 Layout

```text
A ∘ (2,2):(3,1)
  = (2,2):(24,8)
```

右侧是**一个 Layout**。它的两个 mode 都会分别与完整 A composition。

### Tuple Tiler

```text
A ∘ <2:3, 2:1>
  = (2,2):(24,2)
```

右侧是 **tuple of Tilers**：

```text
6:8 ∘ 2:3 = 2:24
2:2 ∘ 2:1 = 2:2
```

第二个结果的 stride 不同：

```text
普通 Layout：8   ← 第二个分支仍从完整 A 的 mode-0 开始
Tuple Tiler：2   ← 第二个 tiler 只作用于 A.mode-1
```

---

## 5. 官方总结的两类用途

### By-mode 子布局

对张量各维分别取子布局，例如：

```text
从 M×N×L 张量中取一个 3×5×8 子块
```

这种情况使用 tuple 或 Shape tiler。

### 把整个 tile 当作一维序列重排

例如把一个 `8×16` tile 的元素按照某种顺序重新组织成 `32×4`。此时使用单个 Layout
作为 tiler，把整个布局看成一维函数进行 composition。

---

## 6. 判断流程

看到 `composition(A, T)` 时：

```text
T 是单个 Layout？
├─ 是：计算普通 A(T(i))，T 的每个 sublayout 都作用于完整 A
└─ 否：
   T 是 tuple 或 Shape？
   └─ 是：A.mode-i 与 T.mode-i 递归 composition
          直到某一层遇到单个 Layout
```

一句话总结：

> **Layout Tiler 重排整体；tuple / Shape Tiler 按 mode 切子布局。**

## 当前材料

- [Composition 笔记：拼接](../02-Composition/用循环理解Composition.md#6-拼接重建-b-的嵌套结构)
- [Composition 笔记：by-mode Tiler](../02-Composition/用循环理解Composition.md#8-by-mode-tiler与-concat-不同)
