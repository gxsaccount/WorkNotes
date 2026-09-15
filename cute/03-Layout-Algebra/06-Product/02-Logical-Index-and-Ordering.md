# Product 中的 Repeat 与 Grid：逻辑 index 和排列顺序

> 官方依据：Product (Tiling) 与 Logical Product 1-D Example
>
> 更新：2026-09-15

## 1. Repeat 和 Grid 分别负责什么

公式：

```text
Repeat = complement(Tile)       // pure complement
logical_product(Tile,Grid) = (Tile, Repeat ∘ Grid)
```

可以把第二个 mode 分成两层：

```text
Repeat：将逻辑 index 映射为 Tile 的重复基址 offset
Grid  ：将 tile 坐标映射为 Repeat 的逻辑 index
```

所以：

```text
Repeat        = 逻辑 index → tile 基址 offset
Repeat ∘ Grid = 按 Grid 排列后的实际 tile 基址 Layout
```

Repeat 只由 Tile 决定；Grid 再通过 composition 决定需要延伸多远、选择哪些逻辑 index。

---

## 2. Grid 控制重复数量

固定：

```text
Tile = (2,2):(4,1)
```

若：

```text
Grid = 6:1
```

则 Grid 有 6 个逻辑坐标，最终 Product 有 6 份 Tile：

```text
tile 基址 = [0,2,8,10,16,18]
```

因此：

```text
size(logical_product(Tile,Grid))
  = size(Tile) × size(Grid)
  = 4 × 6
  = 24
```

---

## 3. Grid 还控制重复顺序

NVIDIA 官方文档进一步把 Grid 改成：

```text
Grid = (4,2):(2,1)
```

Grid 的自然序列：

```text
[0,2,4,6,1,3,5,7]
```

这表示仍然使用 8 个 tile，但顺序不再是简单的：

```text
0,1,2,3,4,5,6,7
```

而是：

```text
0,2,4,6,1,3,5,7
```

对同一个 Tile，按该顺序选出的 tile 基址为：

```text
[0,8,16,24,2,10,18,26]
```

可以表示成：

```text
(4,2):(8,2)
```

因此 Product 为：

```text
((2,2),(4,2)):((4,1),(8,2))
```

---

## 4. bounded 推导中为什么使用 cosize

在官方文档的 bounded 推导中：

```text
Repeat_M = complement(Tile,M)
M = size(Tile) × cosize(Grid)
```

因为：

```text
size(Grid)   → Grid 有多少个坐标，即需要多少份 tile
cosize(Grid) → Grid 输出的逻辑 index 范围有多大
```

例如 `Grid=6:2`：

```text
size(Grid)   = 6
Grid 的像    = [0,2,4,6,8,10]
cosize(Grid) = 11
```

虽然只需要 6 份 tile，但 Grid 输出的逻辑 index 最大为 10，因此其 codomain 范围大小为 11。

当前源码使用 pure `Repeat = complement(Tile)`，不再显式构造 `Repeat_M`；随后通过
`Repeat ∘ Grid` 得到所需的有限 tile 基址 Layout。

---

## 5. 与内存复制的区别

Product 只构造 Layout：

```text
(tile 内坐标, tile 编号) → offset
```

它不会真正复制任何数据。只有当这个 Layout 与 Tensor、Copy 或 kernel 中的实际读写结合时，
这些重复位置才对应真实内存访问。

一句话：

> **Grid 描述的不是“复制指令”，而是重复出来的 tile 应该以什么逻辑顺序出现。**
