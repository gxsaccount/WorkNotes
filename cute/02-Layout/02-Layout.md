# 02 Layout

> 官方对应：`media/docs/cpp/cute/01_layout.md`
>
> 官方基线：NVIDIA CUTLASS `main`，核对日期 2026-09-11
>
> 本章重点：先理解 Layout 本身，再进入下一章的 Layout Algebra

Layout 是 CuTe 最核心的抽象之一。它把一个逻辑坐标映射为整数索引：

```text
Layout = Shape : Stride
coordinate -> index
```

后续的 Tensor、线程分工、Copy、MMA 和 GEMM，都会反复使用这个映射。

## 逻辑 index 与 offset

### 逻辑 index

逻辑 index 表示元素在 Layout 定义域中的自然序号：

```text
0, 1, 2, ..., size(Layout)-1
```

它只说明“这是第几个逻辑元素”，通常是将多维坐标按自然序拍平后的编号。

### offset

offset 是 Layout 输出的整数：

```text
offset = Layout(logical_index)
```

它表示相对于基址的位移，由 stride 决定。当 Layout 与 Tensor 的数据指针结合后：

```text
元素地址 = base_address + offset × sizeof(element)
```

因此可以把 offset 通俗地理解为“物理内存中的相对 index”，但它不是独立存在的绝对物理地址。

例如：

```text
L = (4,2):(2,1)
```

| 逻辑 index | 坐标 | offset |
|---:|---|---:|
| 0 | `(0,0)` | 0 |
| 1 | `(1,0)` | 2 |
| 2 | `(2,0)` | 4 |
| 3 | `(3,0)` | 6 |
| 4 | `(0,1)` | 1 |

所以逻辑 index `1` 表示“第 2 个逻辑元素”，但它位于相对基址 offset `2`。

还要注意：在纯 Layout Algebra 中，Layout 的输出只是一个整数。这个整数既可以作为最终
Tensor 的 offset，也可以继续作为另一个 Layout 的逻辑 index：

```text
c --B--> 逻辑 index n --A--> 最终 offset

(A ∘ B)(c) = A(B(c))
```

## 推荐学习顺序

1. [基础类型与概念](01-基础类型与概念/01-基础类型与概念.md)
   - Integer、Tuple、IntTuple
   - Shape、Stride、Layout、Tensor
   - 静态值、动态值、rank、depth、size
2. [创建与使用](02-创建与使用/02-创建与使用.md)
   - `make_shape`、`make_stride`、`make_layout`
   - `LayoutLeft` 与 `LayoutRight`
   - 向量、矩阵和层级 Layout
3. [坐标与兼容性](03-坐标与兼容性/03-坐标与兼容性.md)
   - 一维坐标、rank-D 坐标、自然坐标
   - `idx2crd`、`crd2idx`
   - `compatible`、`size`、`cosize`
   - 单射、广播、空洞和地址别名
4. [Layout 操作](04-Layout操作/04-Layout操作.md)
   - sublayout、select、take
   - concatenation
   - grouping、flattening
   - slicing 的章节边界

## 本章核心模型

看到一个 Layout 时，依次回答：

```text
1. Shape 描述了哪些逻辑坐标？
2. Shape 与 Stride 的层级是否 congruent？
3. 输入坐标如何转换为自然坐标？
4. 自然坐标如何与 Stride 做内积？
5. 自然序下会产生什么 index 序列？
6. 是否存在地址重叠、广播或空洞？
7. size 和 cosize 分别是多少？
8. 这个层级结构表达了怎样的逻辑组织？
```

## 四种理解视角

### 1. 函数

```text
L(c) = index
```

Layout 是独立于数据的整数函数。

### 2. 嵌套循环

Shape 决定循环层数和每层次数，Stride 决定每层循环使 index 增加多少。

### 3. 混合进制计数器

CuTe 使用 colexicographical order：自然遍历时 mode-0 最先变化，再向更高 mode 进位。

### 4. 地址生成器

当 Layout 与指针或数组组成 Tensor 后，Layout 产生的 index 被用于访问实际数据。

### 5. Tile 排布与复制规则

Layout 也可以描述一个 tile 内部的元素位置，以及多个 tile 副本的基址排布：

```text
tile 内部 Layout：4:1      -> 0,1,2,3
tile 副本 Layout：3:4      -> 0,4,8

组合后的排布：
(4,3):(1,4)
L(i,j) = i + 4*j
```

其中 `i` 选择 tile 内元素，`j` 选择第几个 tile 副本。

但 Layout 只描述 index 规则，本身不会执行数据复制；实际搬运由 Tensor/Copy 等算法完成。Complement 和 Product 会在 Layout Algebra 章节中正式构造这类 tile 副本规则。

## 本章边界

本章只介绍 Layout 的表示、坐标语义和结构操作。下列内容放在下一章：

- `coalesce`
- `composition`
- `complement`
- `logical_divide` 等 division
- product

尤其注意：

```text
flatten != coalesce
```

`flatten` 只删除层级括号；`coalesce` 会在保持映射的前提下合并模式，属于 Layout Algebra。

## 配套材料

- [Python Layout 模型](../03-Layout-Algebra/02-Composition/代码实验/sim.py)
- [Coalesce 练习](../03-Layout-Algebra/02-Composition/代码实验/quiz.py)
- [NVIDIA CuTe Layouts 官方文档](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/01_layout.html)
- [NVIDIA/CUTLASS 官方 Markdown 源文件](https://github.com/NVIDIA/cutlass/blob/main/media/docs/cpp/cute/01_layout.md)
- 主要头文件：`include/cute/int_tuple.hpp`、`include/cute/layout.hpp`

## 本章练习

请自行展开和判断以下 Layout，本章文档不提供直接答案：

```text
(4,3):(1,4)
(4,3):(3,1)
(2,2):(1,1)
(2,2,2):(2,1,4)
```

对每个 Layout 分析：

- rank、depth、size、cosize
- 一维自然序对应的坐标序列
- index 序列
- 是否单射
- 是否有广播
- 是否有地址重叠
- 像集在 `[0, cosize)` 中是否有空洞

## 完成标准

能从函数、嵌套循环、混合进制计数器和地址生成器四个视角解释 Layout，并能明确区分：

```text
逻辑坐标
自然坐标
一维自然序号
Layout 产生的 index
Tensor 实际访问的数据
```
