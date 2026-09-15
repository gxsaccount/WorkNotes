# Zipped / Tiled / Flat Divide：mode 如何重组

> 官方对应：NVIDIA CUTLASS Layout Algebra → Zipped, Tiled, Flat Divides
>
> 更新：2026-09-15

## 1. 为什么需要变体

`logical_divide` 的结构忠实保留原始 mode：

```text
((TileM,RestM),(TileN,RestN),L,...)
```

这适合观察每个原始 mode 如何被切分，但不方便直接表达：

```text
给我整个 tile
给我第 k 个 tile
```

因此 CuTe 提供三种 mode 重组方式。

---

## 2. 官方结构对照

设：

```text
Layout Shape = (M,N,L,...)
Tiler Shape  = <TileM,TileN>
```

这里的 `L,...` 表示原 Layout 中**没有被 Tiler 覆盖的其余 mode**。Tiler 只有两个
顶层 mode，因此只切分 M 和 N；L 以及后续 mode 原样保留。

例如：

```text
Layout = (M,N,L)
Tiler  = <TileM,TileN>

M → (TileM,RestM)
N → (TileN,RestN)
L → L                  // 没有对应 tiler，不参与 divide
```

如果输入本来就是 2-D `(M,N)`，下面公式中的 `L,...` 直接不存在。

官方给出的四种结构是：

```text
logical_divide : ((TileM,RestM),(TileN,RestN),L,...)
zipped_divide  : ((TileM,TileN),(RestM,RestN,L,...))
tiled_divide   : ((TileM,TileN),RestM,RestN,L,...)
flat_divide    : (TileM,TileN,RestM,RestN,L,...)
```

它们包含同一套 tile/rest 子布局，只改变 mode 的分组与排列方式。

`zipped_divide` 把 `L,...` 放进 rest 组，是因为这些 mode 不属于 tile 内坐标，仍属于
选择“哪一份数据”的外层坐标。

---

## 3. 套入官方 2-D 例子

```text
A = (9,(4,8)):(59,(13,1))
B = <3:3, (2,4):(1,8)>
```

### logical_divide

```text
((3,3),((2,4),(2,2)))
:((177,59),((13,2),(26,1)))
```

shape 可以概括成：

```text
((3,3),(8,4))
```

含义是：

```text
((TileM,RestM),(TileN,RestN))
```

### zipped_divide

```text
((3,(2,4)),(3,(2,2)))
:((177,(13,2)),(59,(26,1)))
```

shape 可以概括成：

```text
((3,8),(3,4))
```

含义变成：

```text
(整个 tile, 所有 tile 的排列)
```

---

## 4. zipped_divide 为什么最常用

对：

```text
Z = zipped_divide(A,B)
```

有：

```text
Z(tile_coord, rest_coord)
```

其中：

```text
Z(_, rest_coord)  → 取出指定 tile
Z(0, rest_coord)  → 得到指定 tile 的起始 offset
layout<0>(Z)      → tile 自身的 Layout
```

官方示例使用：

```cpp
Z(0, 3);                  // 第 3 个 tile 的 offset
Z(0, 7);                  // 第 7 个 tile 的 offset
Z(0, make_coord(1,2));    // rest 坐标为 (1,2) 的 tile
```

最重要的官方恒等式：

```text
layout<0>(zipped_divide(A,B)) == composition(A,B)
```

所以 zipped divide 的 mode-0 就是前面已经设计好的 tile。

---

## 5. 四种形式该怎么选

| API | 顶层结构 | 适合场景 |
|---|---|---|
| `logical_divide` | 每个原 mode 内含 `(tile,rest)` | 需要保留 M/N/L 等原始 mode 语义 |
| `zipped_divide` | `(完整 tile,完整 rest)` | 最方便按 tile 坐标切片 |
| `tiled_divide` | `完整 tile` 放前面，rest modes 分开 | 保留 tile 整体，同时单独访问各 rest mode |
| `flat_divide` | tile 与 rest modes 全部平铺 | 需要最扁平的 mode 列表 |

---

## 6. logical 与 zipped 的关键区别

### logical_divide 保留原 mode 语义

```text
mode-0 仍是 M
mode-1 仍是 N
```

只是在每个 mode 内部拆成 `(tile,rest)`。

### zipped_divide 改成 tile/rest 语义

```text
mode-0 = tile
mode-1 = rest
```

因此 zipped 后不能再把顶层 mode-0、mode-1 直接称为原来的 M、N mode。

---

## 7. 学习顺序

```text
先用 logical_divide 看懂每个原始 mode 怎么切
                    ↓
再用 zipped_divide 把 tile modes 和 rest modes 分组
                    ↓
最后根据接口需要选择 tiled / flat
```

一句话：

> **四种 Divide 来自同一套 tile/rest 子布局，差别在 mode 层级及坐标结构如何组织。**
