# Blocked / Raked 与 Product 变体

> 官方对应：NVIDIA CUTLASS Layout Algebra → Blocked and Raked Products、Zipped and Tiled Products
>
> 更新：2026-09-15

## 1. 为什么 2-D 不推荐直接构造 Logical Product 的 Tiler

> **2-D Product 将 tile 内部的二维坐标与二维 tile 位置组合起来，构造所有重复 tile
> 中所有元素的 offset。**

官方指出，2-D `logical_product` 虽然可行，但通常不推荐。

原因是它的 B 必须知道 A 的 shape 和 stride，才能手工构造正确的重复位置，二者耦合很强。

更常用的接口是：

```text
blocked_product(A,B)
raked_product(A,B)
```

它们会先让 A、B 的 rank 对齐，再调用 logical product，最后按对应 mode 重新组合结果。

---

## 2. 官方示例的物理目标

```text
A = (2,5):(5,1)    // 一个 2×5 row-major block
B = (3,4):(1,3)    // block 按 3×4 column-major 排列
```

目标都是产生：

```text
2×5 的小 block
排列成 3×4 的 block 网格
```

区别在于 A 的 mode 和 B 的 mode 谁排在内层。

---

## 3. Blocked Product

Blocked 按每个维度：

```text
(A.mode-i, B.mode-i)
```

组合，因此：

```text
blocked_product(A,B)
  = ((2,3),(5,4)):((5,10),(1,30))
```

拆开看：

```text
mode-0 = (2,3):(5,10)   // A.mode-0 在前，B.mode-0 在后
mode-1 = (5,4):(1,30)   // A.mode-1 在前，B.mode-1 在后
```

一维直觉：

```text
[tile0 的所有元素][tile1 的所有元素][tile2 的所有元素]...
```

所以每个 tile 更像一个完整的实心 block。

---

## 4. Raked Product

Raked 将每个维度内的顺序交换为：

```text
(B.mode-i, A.mode-i)
```

结果：

```text
raked_product(A,B)
  = ((3,2),(4,5)):((10,5),(30,1))
```

拆开看：

```text
mode-0 = (3,2):(10,5)   // B.mode-0 在前
mode-1 = (4,5):(30,1)   // B.mode-1 在前
```

一维直觉：

```text
[各 tile 的元素0][各 tile 的元素1][各 tile 的元素2]...
```

tile 被交错展开，因此官方使用 `raked`，其他资料也常称为 cyclic distribution。

---

## 5. Blocked 与 Raked 对比

| | Blocked | Raked |
|---|---|---|
| 每个维度的 mode 顺序 | `(A_i,B_i)` | `(B_i,A_i)` |
| tile 视觉效果 | 每个 tile 聚在一起 | 多个 tile 交错 |
| 结果 rank | `max(rank(A),rank(B))` | `max(rank(A),rank(B))` |
| 常见理解 | block distribution | cyclic/raked distribution |

两者使用同样的 A 和 B，只改变对应 mode 的重组顺序。

---

## 6. Logical / Zipped / Tiled / Flat Product

设：

```text
Layout Shape = (M,N,L,...)
Tiler Shape  = <TileM,TileN>
```

其中 `L,...` 是没有对应 tiler 的原始 mode，会原样保留。

官方结构：

```text
logical_product : ((M,TileM),(N,TileN),L,...)
zipped_product  : ((M,N),(TileM,TileN,L,...))
tiled_product   : ((M,N),TileM,TileN,L,...)
flat_product    : (M,N,TileM,TileN,L,...)
```

与 Divide 变体相同，它们来自同一套子布局，区别在 mode 如何分组。

---

## 7. Product 与 Divide 变体的对称关系

```text
Divide：
原 mode → (Tile,Rest)

Product：
原 block mode → (Block,Repetition)
```

两边都有 logical、zipped、tiled、flat 形式，但物理方向不同：

```text
Divide  = 从完整布局拆出 tile
Product = 将一个 block 重复成更大布局
```

一句话：

> **Blocked 保持 tile 成块，Raked 让不同 tile 的对应位置交错。**
