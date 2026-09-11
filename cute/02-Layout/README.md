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

## 推荐学习顺序

1. [基础类型与概念](01-基础类型与概念/README.md)
   - Integer、Tuple、IntTuple
   - Shape、Stride、Layout、Tensor
   - 静态值、动态值、rank、depth、size
2. [创建与使用](02-创建与使用/README.md)
   - `make_shape`、`make_stride`、`make_layout`
   - `LayoutLeft` 与 `LayoutRight`
   - 向量、矩阵和层级 Layout
3. [坐标与兼容性](03-坐标与兼容性/README.md)
   - 一维坐标、rank-D 坐标、自然坐标
   - `idx2crd`、`crd2idx`
   - `compatible`、`size`、`cosize`
   - 单射、广播、空洞和地址别名
4. [Layout 操作](04-Layout操作/README.md)
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
