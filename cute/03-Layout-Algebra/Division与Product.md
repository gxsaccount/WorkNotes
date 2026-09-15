# CuTe Division 与 Product（Tiling 的两半）

> 更新：2026-09-15 —— 删除与 `05-Division`、`06-Product` 重复的逐步推导与变体说明，只保留两类运算的统一关系。
> 配套文档：[`Complement补集概念.md`](04-Complement/Complement补集概念.md)
> 补充推论的可运行验证：[`test_tiling_relations.py`](代码实验/tests/test_tiling_relations.py)
> 官方出处：NVIDIA CUTLASS `media/docs/cpp/cute/02_layout_algebra.md` → **Division / Product**

---

## 0. 本文范围

本文只回答两个跨章节问题：

1. Divide 和 Product 的构造方向有什么区别？
2. 它们什么时候产生相同的 Layout？

具体推导和变体分别放在：

- [Division：章节入口](05-Division/README.md)
  - [Logical Divide 1-D](05-Division/01-Logical-Divide-1D.md)
  - [Logical Divide 2-D](05-Division/02-Logical-Divide-2D.md)
  - [Zipped / Tiled / Flat Divide](05-Division/03-Divide-Variants.md)
- [Product：章节入口](06-Product/README.md)
  - [Logical Product 1-D](06-Product/01-Logical-Product-1D.md)
  - [Repeat 与 Grid](06-Product/02-Logical-Index-and-Ordering.md)
  - [Blocked / Raked 与 Product 变体](06-Product/03-Product-Variants.md)

---

## 1. 一句话记忆：Divide 是切，Product 是铺

| 运算 | 公式 | 方向 |
|---|---|---|
| **Divide** | `FULL ∘ (TileSelector,Rest)` | 从已有 FULL 中向内切出 tile，并得到它们在 FULL 中的 offset |
| **Product** | `(Tile,Repeat∘Grid)` | 以 Tile 为模板，向外铺出完整 offset Layout |

其中：

```text
Rest   = complement(TileSelector, size(FULL))
Repeat = complement(Tile)                     // pure complement
```

- **Divide 是查询式**：`TileSelector` 和 `Rest` 都经过 `FULL`，查询已有全局布局中的 offset。
- **Product 是构造式**：保留 `Tile` 的内部 offset，再由 `Repeat∘Grid` 构造 tile 基址。

两者都只组合已有的 Layout 运算，不会物理切割、复制或移动数据。

---

## 2. 统一记号与相等条件

```text
FULL          = 完整布局
TileSelector  = 在 FULL 中选取一个 tile 的逻辑 index 规则
Tile          = FULL ∘ TileSelector，实际的 tile offset Layout
Rest          = complement(TileSelector, size(FULL))
Repeat        = complement(Tile)，即 pure complement
Grid          = tile 的数量、索引和排列顺序
```

Divide 的结果：

```text
FULL ∘ (TileSelector,Rest)
  = (FULL∘TileSelector, FULL∘Rest)
  = (Tile, FULL∘Rest)
```

这里使用了 composition 对 concatenation 的左分配；要求
`(TileSelector,Rest)` 构成合法的单射 tiling。

Product 的结果：

```text
(Tile, Repeat∘Grid)
```

因为 `Tile := FULL∘TileSelector` 已由定义保证，所以两者相等只需满足：

1. 两个结果的外层坐标结构相同；
2. 对每个外层坐标 `j`，tile 基址及顺序一致：

```text
FULL(Rest(j)) = Repeat(Grid(j))
```

即：

```text
FULL∘Rest = Repeat∘Grid
```

因此一般不能直接写成 `Grid=Rest`。两者位于不同映射层次：

```text
Rest        ：tile 编号 → FULL 的逻辑 index
Grid        ：tile 坐标 → Repeat 的逻辑 index
FULL∘Rest   ：Divide 得到的实际 tile 基址
Repeat∘Grid ：Product 构造的实际 tile 基址
```

### 连续对齐例子

```text
FULL          = 24:1
TileSelector  = 4:1
Rest          = complement(4:1,24) = 6:4

Tile           = FULL ∘ TileSelector = 4:1
Repeat         = complement(Tile)    = 1:4
Grid           = 6:1
Repeat ∘ Grid  = 6:4
```

于是：

```text
FULL∘Rest = Repeat∘Grid = 6:4
```

Divide 与 Product 得到相同的 tiled Layout。

---

## 3. 两者不是一般意义上的互逆

Divide 与 Product 可以产生相同结果，但输入含义不同：

| | Divide | Product |
|---|---|---|
| 第一个输入 | 已有的完整布局 `FULL` | 作为模板的 `Tile` |
| 第二个输入 | tile 内部选取规则 `TileSelector` | tile 数量与排列规则 `Grid` |
| mode-0 | `FULL∘TileSelector` | 直接保留 `Tile` |
| mode-1 | `FULL∘Rest` | `Repeat∘Grid` |
| 方向 | 从全局向内切 | 从 tile 向外铺 |

它们得到相同结果，表示两种构造方法选中了相同的 tile 内部 offset 和 tile 基址；这不表示任意 Divide 和 Product 都互逆。

---

## 4. 工程上的完整用法链

```text
composition(FULL,TileSelector)
    → 设计或确认单个 tile 的布局

zipped_divide / local_tile
    → 将同一种 tile 结构推广到所有 block

composition + TV-layout / local_partition
    → 在单个 tile 内继续分配到线程
```

典型用法：

```cpp
auto tiled = zipped_divide(tensor, tiler);
auto tile  = tiled(make_coord(_, _), block_coord);
```

`zipped_divide` 将结果组织为：

```text
(tile 内坐标, tile 位置)
```

因此所有 block 共享相同的 tile Layout，只通过外层坐标选择不同基址。
