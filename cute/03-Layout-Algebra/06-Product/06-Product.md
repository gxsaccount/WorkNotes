# Product（Tiling）

> 官方对应：NVIDIA CUTLASS `media/docs/cpp/cute/02_layout_algebra.md` → **Product (Tiling)**
>
> 当前实现核对：`include/cute/layout.hpp`、`test/unit/cute/core/logical_product.cpp`
>
> 更新：2026-09-15

## 核心公式

```text
Repeat = complement(Tile)           // pure complement
Tile ⊗ Grid = (Tile, Repeat ∘ Grid)
```

NVIDIA 公式中的 `A*` 在当前源码语境下指 pure complement。本文改名为 `Repeat`，避免与
`complement(A,M)` 的 bounded 结果混用。

## 先建立物理直觉

> **Product 根据一个 tile 的内部 Layout A 和重复方式 B，构造一个新的 Layout；
> 它把结果坐标组织成“tile 内坐标 + tile 位置”，从而给出所有重复 tile 中所有元素的
> offset。**

统一写成：

```text
R(tile 内坐标, tile 编号) = 对应元素在构造后布局中的 offset
```

这里的“重复 tile”只是**构造 offset 映射**，不会物理复制或移动数据。

### 为什么它听起来和 Divide 一样

两者的结果都可以写成：

```text
R(tile 内坐标, tile 编号) → offset
```

区别不在结果长相，而在输入和构造方向：

```text
Divide ：完整布局 A_full + tile 选取规则 B
         → 把 A_full 已有的 offset 重组为多个 tile

Product：单个 tile 布局 A_tile + tile 排列规则 B
         → 主动构造重复后的 offset Layout
```

所以匹配得当时，两者可以产生完全相同的 Layout；但它们不是一般意义上的互逆运算，也不
保证任意输入都会得到相同的 offset 集合。

### “tile 选取规则”和“tile 排列规则”的关系

它们分别描述 tiled layout 的内外两层：

```text
tile 选取规则：一个 tile 内部选哪些位置
tile 排列规则：多个 tile 按什么数量和顺序排列
```

这里的“tile 排列规则”确实来自 Complement，但要区分两个层次：

```text
Complement     → 生成规范、无冲突的基础重复位置
Composition    → 根据另一个 Layout 对这些位置进行选择或重排
```

在 Divide 中：

```text
TileSelector = tile 选取规则
Rest         = complement(TileSelector,size(FULL))
FULL∘Rest    = tile 在 FULL 的 offset 空间中的基址 Layout
```

在 Product 中：

```text
Tile         = 已经给定的 tile 内部 Layout
Repeat       = complement(Tile)，即 pure complement
Grid         = 产生哪些 Repeat 的逻辑 index及其顺序
Repeat∘Grid  = 最终 tile 基址 Layout
```

所以两种 B 虽然都是 Layout，但作用在不同空间：

```text
Divide 的 TileSelector：tile 内坐标 → FULL 的逻辑 index
Product 的 Grid：        tile 编号   → Repeat 的逻辑 index
```

物理含义：

```text
Tile          = 一个 tile 的内部 Layout
Repeat        = 逻辑 index → tile 基址 offset
Grid          = 需要多少份 tile，以及这些 tile 的排列顺序
Repeat ∘ Grid = 最终选中的 tile 基址 Layout
```

## 官方例子教程

1. [Logical Product 1-D：用一个 tile 构造完整布局](01-Logical-Product-1D.md)
2. [Product 中的 Repeat 与 Grid：逻辑 index 和排列顺序](02-Logical-Index-and-Ordering.md)
3. [Blocked / Raked 与 Product 变体](03-Product-Variants.md)

## 官方文档与当前源码的差异

官方 Layout Algebra 文档使用带 cotarget 的推导：

```text
complement(A, size(A) × cosize(B))
```

当前 CUTLASS `main` 源码则使用：

```text
complement(A)
```

即 pure complement。它保留末端 shape-1 mode，使 `Repeat ∘ Grid` 可以根据 Grid 自动延伸。
官方单元测试 `LogicalProductUsesPureComplement` 专门检查了这一行为。两种写法在官方教程
示例中产生相同的最终 product。

## 综合笔记

- [Division 与 Product：统一关系](../Division与Product.md)
- [Complement / Divide / Product 关系测试](../代码实验/tests/test_tiling_relations.py)

## 官方子主题

- Logical Product 1-D/2-D
- Blocked Product
- Raked Product
- Zipped Product
- Tiled Product
