# 09 TMA Tensors：把 CuTe View 坐标映射回原 Tensor 坐标

> 官方对应：`media/docs/cpp/cute/0z_tma_tensors.md`
>
> 官方基线：NVIDIA CUTLASS `main`，文档最近一次修改提交
> `0d2b201e8c1c4a03efa6e9c468161916e2334725`，核对日期 2026-09-24
>
> 前置章节：[Tensor](../04-Tensor/04-Tensor.md)、
> [Layout Algebra](../03-Layout-Algebra/03-Layout-Algebra.md) 与
> [Predication](../08-Predication/08-Predication.md)

## 本章要回答的问题

**TMA Tensor 的作用，是把经过 CuTe tile、reshape 或 partition 等变换后的
view 坐标，映射回 TMA descriptor 所描述的原 Tensor 逻辑坐标。**

**TMA coordinate 就是 TMA descriptor 所描述 Tensor 的逻辑下标。**

假设 descriptor 描述二维矩阵：

```text
A[M,N]
```

那么：

```text
TMA coordinate = (m,n)
```

表示本次 TMA 搬运从 `A(m,n)` 开始。它通常是待搬运 tile 在 global-memory
Tensor 中的起始坐标。

有了这个定义，再看它与常见 CuTe Tensor 的区别。对于以 GMEM pointer 为
Iterator 的 CuTe Tensor，Layout 计算线性
offset，Iterator 再用这个 offset 定位数据：

```text
逻辑坐标 → Layout → 线性 offset → GMEM pointer 指向的元素
```

TMA 的接口不同：GMEM 基址和 Stride 已经记录在 descriptor 中，指令执行时需要
额外提供的是 **descriptor 所描述的原始 Tensor 的逻辑坐标**：

```text
TMA descriptor + 原始 Tensor 逻辑坐标 → 本次搬运的 GMEM tile
```

因此本章真正的问题是：CuTe 如何实现这个坐标映射？

答案分三步：

```text
Implicit Tensor
    ↓
ArithmeticTupleIterator
    ↓
Basis stride
```

理解这三步后，就能看懂下面的 TMA Tensor：

```text
ArithTuple(0,_0,_0,_0) o
((_128,_64),2,3,1):((_1@0,_1@1),_64@1,_1@2,_1@3)
```

---

## 1. TMA 指令需要什么

Hopper 引入的 Tensor Memory Accelerator（TMA）可以在 global memory 和
shared memory 之间搬运一个多维 tile。

TMA 指令依赖三类输入：

```text
TMA descriptor
SMEM 地址
GMEM Tensor 中的多维坐标
```

### 1.1 TMA descriptor

Descriptor 描述完整的 global-memory Tensor，包括：

- global-memory 基址；
- 元素类型；
- 1～5 个维度的大小；
- 各维度的 Stride；
- shared-memory box；
- swizzle 和越界行为等配置。

它在 kernel 启动前由 host 创建。

### 1.2 TMA coordinate

Descriptor 说明“整个 Tensor 如何存储”，coordinate 说明“本次从哪里开始搬”。

第 0 节已经给出了基本定义。这里还要进一步区分两个逻辑坐标系：

如果当前 CuTe view 没有经过任何坐标变换，那么二者确实相同：

```text
CuTe view 坐标 (m,n) → TMA descriptor 坐标 (m,n)
```

但经过 tiling 或 mode 合并后，当前 view 的坐标可能是：

```text
((i,j),k)
```

而 descriptor 仍要求原始二维坐标：

```text
(i, j + 64*k)
```

因此 TMA Tensor 的作用不是创造一种不同于逻辑坐标的新概念，而是在两个逻辑
坐标系之间做映射：

```text
当前 CuTe view 的逻辑坐标
        ↓
descriptor 原始 Tensor 的逻辑坐标
```

以三维 TMA store 的接口形态为例：

```cpp
copy(desc_ptr,
     smem_ptr,
     crd0,
     crd1,
     crd2);
```

注意这里没有单独传入 GMEM pointer，因为 global-memory 基址已经包含在 descriptor
中。TMA 指令需要的是 descriptor 坐标，而不是一个重新计算出的数据指针。

---

## 2. Pointer Tensor 与 TMA 接口有什么不同

常见的 pointer-backed CuTe Tensor 可以近似理解为：

```text
Tensor = Iterator o Layout
```

对于普通 global-memory Tensor：

```text
Iterator = GMEM pointer
Layout   = 逻辑坐标到整数 offset 的映射
```

访问 `(i,j)` 时：

```text
(i,j)
  ↓ Layout
integer offset
  ↓ pointer + offset
GMEM address
```

例如：

```text
shape  = (M,N)
stride = (1,M)

layout(i,j) = i + M*j
```

但 TMA 不需要 `pointer + offset`，而需要：

```text
(crd0, crd1, ...)
```

因此我们需要一种新的 Tensor，使它的“元素”不是内存中的数据，而是按需生成的
多维坐标。

---

## 3. 第一步：Implicit Tensor

CuTe Tensor 的 Iterator 不一定是 pointer，也可以是其他支持随机访问语义的
对象。

官方首先给出 counting iterator：

```cpp
Tensor A =
    make_tensor(counting_iterator<int>(42),
                make_shape(4,5));
```

其默认紧凑 Layout 是：

```text
(4,5):(1,4)
```

因此：

```text
A(i,j) = 42 + i + 4*j
```

打印结果为：

```text
42  46  50  54  58
43  47  51  55  59
44  48  52  56  60
45  49  53  57  61
```

这 20 个整数并没有作为数组存放在内存中。Tensor 只保存起点和映射规则，访问时
即时计算结果。

这就是 Implicit Tensor：

```text
Tensor 的值由 Iterator 和 Layout 计算得到，
不要求背后存在一份真实数组。
```

既然可以隐式生成整数，也就可以隐式生成 TMA coordinate。

---

## 4. 第二步：ArithmeticTupleIterator

TMA coordinate 是一个 tuple：

```text
(crd0, crd1, crd2, ...)
```

因此需要一个“坐标版本的 counting iterator”。它必须支持：

1. 解引用后得到当前坐标；
2. 加上一个坐标增量后得到新坐标。

CuTe 为此提供：

```text
ArithmeticTuple
ArithmeticTupleIterator
```

`ArithmeticTuple` 可以理解为支持逐元素算术的 `cute::tuple`：

```text
(42,2,7) + (0,5,2) = (42,7,9)
```

官方示例：

```cpp
ArithmeticTupleIterator citer_1 =
    make_inttuple_iter(42, Int<2>{}, Int<7>{});

ArithmeticTupleIterator citer_2 =
    citer_1 + make_tuple(Int<0>{}, 5, Int<2>{});

print(*citer_2);  // (42,7,_9)
```

其含义是：

```text
citer_1 保存坐标 (42,2,7)
加上坐标增量     ( 0,5,2)
得到新坐标       (42,7,9)
```

普通 pointer 使用一个整数 offset 移动；`ArithmeticTupleIterator` 使用一个 tuple
形式的坐标 offset 移动。

现在 Iterator 已经能保存坐标，剩下的问题是：Layout 如何生成 tuple offset？

---

## 5. 第三步：Basis Stride

Layout 的核心计算是坐标与 Stride 的内积：

```text
layout(coord) = coord · stride
```

普通 Stride 是整数：

```text
(i,j) · (1,M) = i + M*j
```

输出是一个整数 offset。

如果把 Stride 换成坐标基向量：

```text
1@0 = (1,0,...)
1@1 = (0,1,...)
```

那么：

```text
(i,j) · (1@0,1@1)
= i*(1@0) + j*(1@1)
= (i,j)
```

Layout 的输出就从整数变成了 tuple coordinate。

这就是 TMA Tensor 能成立的关键：

```text
Stride 不一定是整数，
也可以是表示坐标方向的 basis element。
```

---

## 6. 如何阅读 `E<>` 和 `1@...`

CuTe 使用 `E` 表示 basis element，定义位于：

```text
cute/numeric/arithmetic_tuple.hpp
```

常见写法：

| C++ 写法 | 打印形式 | 坐标意义 |
|---|---|---|
| `E<>{}` | `1` | 普通标量 1 |
| `E<0>{}` | `1@0` | `(1,0,...)` |
| `E<1>{}` | `1@1` | `(0,1,0,...)` |
| `E<2>{}` | `1@2` | `(0,0,1,...)` |

因此：

```text
5@1 = 5 * E<1>{} = (0,5,0,...)
```

### 6.1 Basis 可以缩放

```text
5 * (1@1) = 5@1
```

它表示对输出坐标的第 1 维贡献 `5`。

### 6.2 Basis 可以相加

```text
3@0 + 4@1 = (3,4,...)
```

### 6.3 Basis 可以嵌套

对于 hierarchical coordinate：

| C++ 写法 | 打印形式 | 近似展开 |
|---|---|---|
| `E<0,0>{}` | `1@0@0` | `((1,0,...),0,...)` |
| `E<0,1>{}` | `1@1@0` | `((0,1,...),0,...)` |
| `E<1,0>{}` | `1@0@1` | `(0,(1,0,...),...)` |

初学时不用死记嵌套规则。先记住：

```text
1@n 表示对输出坐标第 n 维贡献 1；
多层 @ 表示输出坐标本身也具有嵌套结构。
```

---

## 7. 两个最小 TMA Tensor

### 7.1 保持坐标顺序

```cpp
Tensor a =
    make_tensor(
        make_inttuple_iter(0,0),
        make_shape (     4,      5),
        make_stride(E<0>{}, E<1>{}));
```

打印形式：

```text
ArithTuple(0,0) o (4,5):(_1@0,_1@1)
```

映射为：

```text
a(i,j) = (i,j)
```

例如：

```text
a(2,3) = (2,3)
```

### 7.2 交换坐标顺序

```cpp
Tensor b =
    make_tensor(
        make_inttuple_iter(0,0),
        make_shape (     4,      5),
        make_stride(E<1>{}, E<0>{}));
```

映射为：

```text
b(i,j) = (j,i)
```

例如：

```text
b(2,3) = (3,2)
```

两个例子只改变了 Stride：

```text
(1@0,1@1) → 保持坐标顺序
(1@1,1@0) → 交换坐标顺序
```

因此可以把 TMA Tensor 的三个部分分别理解为：

```text
Iterator：坐标原点
Shape：   CuTe 逻辑坐标的定义域
Stride：  逻辑坐标如何贡献到 TMA coordinate
```

---

## 8. 解读官方的复杂打印

现在分析本章开头的 Tensor：

```text
ArithTuple(0,_0,_0,_0) o
((_128,_64),2,3,1):((_1@0,_1@1),_64@1,_1@2,_1@3)
```

### 8.1 Iterator

```text
ArithTuple(0,0,0,0)
```

表示输出是一个四维坐标，当前原点为：

```text
(0,0,0,0)
```

### 8.2 Shape

```text
((128,64),2,3,1)
```

因此输入逻辑坐标可以写成：

```text
((i,j),k,l,m)
```

### 8.3 Stride

```text
((1@0,1@1),64@1,1@2,1@3)
```

逐项解释：

```text
i → TMA coordinate 0
j → TMA coordinate 1
k → 以 64 为倍率贡献到 TMA coordinate 1
l → TMA coordinate 2
m → TMA coordinate 3
```

因此完整映射为：

```text
((i,j),k,l,m)
  →
(i, j + 64*k, l, m)
```

例如：

```text
输入：((5,7),1,2,0)
输出：(5,71,2,0)
```

因为：

```text
71 = 7 + 64*1
```

以后遇到 TMA Tensor 打印，固定按以下顺序阅读：

```text
1. `o` 左边：坐标原点是什么？
2. `:` 左边：输入逻辑坐标是什么结构？
3. `:` 右边：每个逻辑 mode 贡献到输出坐标的哪一维？
4. 计算 coord · stride，再加 Iterator 原点。
```

---

## 9. 为什么 TMA Tensor 仍能 Tile 和 Partition

Pointer Tensor 与 TMA Tensor 的 Layout 操作没有本质区别：

```text
Pointer Tensor：
  tile/partition 后生成正确的数据地址

TMA Tensor：
  tile/partition 后生成正确的 descriptor coordinate
```

假设：

```text
tma_tensor(i,j) = (i,j)
```

某个 tile 的起点是 `(128,64)`，那么 tile 内坐标 `(u,v)` 对应：

```text
(128+u,64+v)
```

这里没有移动真实数据。`local_tile`、slice 和 partition 只是继续组合坐标映射。

这正是 CuTe 构造隐式 TMA Tensor 的目的：

```text
复用已有 Layout Algebra，
让坐标和普通数据 Tensor 一样参与 tile 与 partition。
```

---

## 10. Descriptor、TMA Tensor 与 TMA Copy 的关系

三个概念不要混淆。

### Descriptor

```text
描述完整 GMEM Tensor 的物理存储与 TMA 配置
```

其中包含 global-memory base pointer。

### TMA Tensor

```text
将 CuTe 逻辑位置映射为 descriptor coordinate
```

它通常是隐式坐标 Tensor，不保存实际数据。

### TMA Copy

```text
使用 descriptor、coordinate 和 SMEM 地址发出硬件搬运
```

关系如下：

```text
TMA Tensor ────────► coordinate ──┐
                                  │
TMA descriptor ───────────────────┼─► TMA instruction
                                  │
SMEM address ─────────────────────┘
```

因此：

```text
TMA Tensor 负责“算坐标”，
TMA copy 负责“搬数据”。
```

---

## 11. 与上一章 Predication 的关系

上一章的 identity coordinate Tensor：

```text
逻辑坐标 → 原始数据坐标 → 与 Shape 比较
```

本章的 TMA Tensor：

```text
逻辑坐标 → descriptor coordinate → 交给 TMA 指令
```

共同点是：

```text
坐标也可以成为 Tensor 的值，
并跟随 tile、slice 和 partition 一起变化。
```

区别只是坐标的用途：

| Tensor | 坐标用于什么 |
|---|---|
| Identity coordinate Tensor | 判断是否越界 |
| TMA coordinate Tensor | 向 TMA 指令提供 descriptor coordinate |

---

## 12. 常见误解

### 误解 1：`ArithTuple` 是内存里存储的数据

它通常是按需计算的坐标，不存在一张真实的坐标数组。

### 误解 2：TMA Tensor 内保存 GMEM pointer

GMEM base pointer 在 descriptor 中；TMA Tensor 生成的是坐标。

### 误解 3：Stride 永远是整数距离

普通数据 Tensor 常使用整数 Stride；TMA Tensor 可以使用 Basis stride，使 Layout
输出 tuple coordinate。

### 误解 4：`1@1` 就是普通的 stride 1

`1@1` 表示对输出坐标的第 1 个分量贡献 1。

### 误解 5：TMA Tensor 会自动搬运数据

它只生成坐标。真正的搬运仍需要 descriptor、TMA copy 和正确的同步机制。

---

## 13. 最小心智模型

```text
Pointer-backed GMEM Tensor
──────────────────────────
GMEM pointer o integer-stride Layout

logical coordinate
      ↓
integer offset
      ↓
GMEM address


TMA Tensor
──────────
ArithmeticTupleIterator o basis-stride Layout

logical coordinate
      ↓
tuple offset
      ↓
TMA descriptor coordinate
```

一句话总结：

```text
TMA Tensor 是生成坐标的 Tensor，不是保存数据的 Tensor。
```

---

## 14. 自测

1. TMA descriptor 与 TMA coordinate 分别描述什么？
2. 为什么 TMA 指令不需要单独接收 GMEM pointer？
3. 什么是 Implicit Tensor？
4. `ArithmeticTupleIterator` 与普通 pointer 的 offset 有什么区别？
5. 为什么普通整数 Stride 只能生成线性 offset？
6. `(i,j) · (1@0,1@1)` 的结果是什么？
7. `(i,j) · (1@1,1@0)` 的结果是什么？
8. `64@1` 表示什么？
9. 如何解读 `Iterator o Shape:Stride`？
10. TMA Tensor、descriptor 和 TMA copy 各自负责什么？

## 学完标准

你应该能够：

1. 用一条数据流解释 pointer-backed GMEM Tensor 与 TMA Tensor 的区别；
2. 解释 Implicit Tensor、`ArithmeticTuple` 和 `ArithmeticTupleIterator`；
3. 把 `E<0>{}`、`E<1>{}` 和缩放 Basis 展开成坐标方向；
4. 手算逻辑坐标与 Basis stride 的内积；
5. 推导复杂打印对应的坐标映射；
6. 说明 TMA Tensor 为什么仍然可以使用 CuTe 的 tile 和 partition 操作。

## 官方资料

- [CuTe TMA Tensors](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0z_tma_tensors.html)
- [官方 Markdown](https://github.com/NVIDIA/cutlass/blob/main/media/docs/cpp/cute/0z_tma_tensors.md)
- [`arithmetic_tuple.hpp`](https://github.com/NVIDIA/cutlass/blob/main/include/cute/numeric/arithmetic_tuple.hpp)
