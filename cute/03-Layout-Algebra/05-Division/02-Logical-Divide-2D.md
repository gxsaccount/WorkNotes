# Logical Divide 2-D：by-mode tiling

> 官方例子：NVIDIA CUTLASS Layout Algebra → Logical Divide 2-D Example
>
> 更新：2026-09-15

## 1. 2-D Logical Divide 想做什么

> **2-D Logical Divide 把 A 的全局二维坐标重组为“tile 内二维坐标 + 二维 tile
> 位置”，并返回所有 tile 中所有元素的 offset。**

1-D Divide 把一个逻辑 index 拆成：

```text
(tile 内 index, 第几个 tile)
```

2-D Logical Divide 做的是同一件事，但会**分别拆分每个原始 mode**。

例如一个 `9×32` Layout 被切成 `3×8` tile，只看 shape：

```text
原 shape = (9,32)

M mode：9  → (TileM=3, RestM=3)
N mode：32 → (TileN=8, RestN=4)

logical_divide shape
  = ((3,3),(8,4))
  = ((TileM,RestM),(TileN,RestN))
```

结果坐标的含义是：

```text
((m_in_tile, m_tile), (n_in_tile, n_tile))
```

它仍然保留两个顶层 mode：

```text
顶层 mode-0 仍然是 M
顶层 mode-1 仍然是 N
```

如果希望把完整 tile 坐标和 tile 编号分别聚在一起，再做：

```text
zipped_divide shape
  = ((3,8),(3,4))
  = ((TileM,TileN),(RestM,RestN))
```

因此：

> **2-D logical divide 的主要目的，是将每个原始维度分别拆成“tile 内坐标”和
> “tile 编号”，同时保留 M/N 等原始 mode 语义。**

### 物理含义

与 1-D 完全一样，2-D logical divide 最终也是为了计算：

> **每个二维 tile 中，每个元素对应的 offset。**

区别只是坐标从：

```text
1-D：(tile 内 index, tile 编号)
```

变成：

```text
2-D：((tile 内 M 坐标, M 方向 tile 编号),
      (tile 内 N 坐标, N 方向 tile 编号))
```

以一个简单的 column-major Layout 为例：

```text
A = (6,8):(1,6)
tile shape = (2,4)
```

全局坐标可以拆成：

```text
m = m_in + 2*m_tile
n = n_in + 4*n_tile
```

因此每个 tile 中每个元素的 offset 是：

```text
offset
  = A(m,n)
  = m + 6*n
  = m_in + 2*m_tile + 6*n_in + 24*n_tile
```

对应 logical divide：

```text
shape  = ((2,3),(4,2))
stride = ((1,2),(6,24))
```

四个坐标分别控制：

| 坐标 | 物理含义 | 对 offset 的贡献 |
|---|---|---:|
| `m_in` | tile 内第几行 | `1*m_in` |
| `m_tile` | M 方向第几个 tile | `2*m_tile` |
| `n_in` | tile 内第几列 | `6*n_in` |
| `n_tile` | N 方向第几个 tile | `24*n_tile` |

所以它确实包含了**所有二维 tile 的全部 offset**，只是 logical divide 将坐标按原始
M/N mode 组织。`zipped_divide` 会把完全相同的信息重组为：

```text
((m_in,n_in),(m_tile,n_tile))
```

这时“tile 内坐标”和“第几个 tile”会更加直观。

---

## 2. 官方输入

```text
A = (9,(4,8)):(59,(13,1))
B = <3:3, (2,4):(1,8)>
```

A 有两个顶层 mode：

```text
A.mode-0 = 9:59
A.mode-1 = (4,8):(13,1)
```

B 是 tuple tiler，因此 Division 按 mode 递归：

```text
logical_divide(A,B)
  = (
      logical_divide(A.mode-0, B.mode-0),
      logical_divide(A.mode-1, B.mode-1)
    )
```

---

## 3. mode-0：沿列方向切分

```text
A0 = 9:59
B0 = 3:3
```

先求：

```text
B0* = complement(3:3,9) = 3:1
```

于是：

```text
logical_divide(A0,B0)
  = A0 ∘ (3:3,3:1)
  = (3,3):(177,59)
```

解释：

```text
3:177 → 一个 tile 内沿 mode-0 走 3 个元素
3:59  → 一共有 3 个这样的 tile
```

---

## 4. mode-1：沿行方向切分

```text
A1 = (4,8):(13,1)
B1 = (2,4):(1,8)
```

B1 选择的逻辑 index 是：

```text
[0,1,8,9,16,17,24,25]
```

其 complement 为：

```text
B1* = 4:2
```

因为：

```text
B1 的像 + {0,2,4,6}
```

可以无重复地覆盖 `0..31`。

分别 composition：

```text
A1 ∘ B1  = (2,4):(13,2)
A1 ∘ B1* = (2,2):(26,1)
```

所以：

```text
logical_divide(A1,B1)
  = ((2,4),(2,2)):((13,2),(26,1))
```

---

## 5. 拼回两个顶层 mode

最终：

```text
logical_divide(A,B)
  = ((3,3),((2,4),(2,2)))
    :((177,59),((13,2),(26,1)))
```

只看 shape：

```text
((TileM,RestM),(TileN,RestN))
  = ((3,3),(8,4))
```

这里仍然保留原来的 mode 语义：

```text
顶层 mode-0 仍表示 A 的 mode-0
顶层 mode-1 仍表示 A 的 mode-1
```

每个顶层 mode 内部再分成：

```text
(tile, rest)
```

---

## 6. tile 本身在哪里

取每个顶层 mode 的第一个子 mode：

```text
mode-0 tile = 3:177
mode-1 tile = (2,4):(13,2)
```

拼起来：

```text
tile = (3,(2,4)):(177,(13,2))
```

这正是：

```text
composition(A,B)
```

也就是说：

> **logical_divide 比 composition 多出来的部分，就是每个 mode 的 rest。**

---

## 7. 为什么 2-D 要使用 Tiler

如果 B 是一个普通 Layout，CuTe 会把 A 和 B 都看成一维函数做整体 composition。

这里使用：

```text
<3:3, (2,4):(1,8)>
```

是为了明确：

```text
3:3             只作用于 A.mode-0
(2,4):(1,8)     只作用于 A.mode-1
```

所以 2-D logical divide 的本质是：

> **先 by-mode divide，再保留每个原始 mode 的语义。**
