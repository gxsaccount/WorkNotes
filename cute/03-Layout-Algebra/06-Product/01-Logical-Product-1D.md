# Logical Product 1-D：用一个 tile 构造完整布局

> 官方例子：NVIDIA CUTLASS Layout Algebra → Logical Product 1-D Example
>
> 更新：2026-09-15

## 1. Product 想做什么

> **Product 根据 tile 内部 Layout A 和重复方式 B，将结果坐标组织为
> `(tile 内坐标, tile 编号)`，并返回所有重复 tile 中所有元素的 offset。**

它不会物理复制或移动数据，只是在构造新的 Layout 映射。

Division 的输入 A 是完整布局。它不会真的切割或移动数据，而是把 A 原来的全局逻辑
index 重新表示为：

```text
(tile 内坐标, tile 编号)
```

从结果上看，就是一次性得到所有 tile 中所有元素的 offset。“把 A 拆成 tile”只是对这种
**坐标重组**的简称。

Product 的输入 A 则直接是一个 tile，它要回答：

> **按照 B 给出的数量和顺序，把这个 tile 重复成什么布局？**

公式：

```text
Repeat = complement(A)              // pure complement
logical_product(A,B) = (A, Repeat ∘ B)
```

两个结果 mode：

```text
mode-0：tile 内部，直接保留 A
mode-1：各个 tile 的基址，由 Repeat ∘ B 决定
```

---

## 2. 官方 1-D 例子

```text
A = (2,2):(4,1)
B = 6:1
```

A 是一个包含 4 个元素的 tile：

```text
A 的 offset 序列 = [0,4,1,5]
```

B 表示：

```text
产生 6 份 tile，顺序为 0,1,2,3,4,5
```

---

## 3. 第一步：求 Repeat

官方 Markdown 使用 bounded complement 推导。这里将它明确记为 `Repeat_24`：

```text
Repeat_24 = complement((2,2):(4,1),24)
          = (2,3):(2,8)
```

`Repeat_24` 的 offset 序列：

```text
[0,2,8,10,16,18]
```

它表示覆盖 cotarget 24 所需的 6 个 tile 基址。

当前 CUTLASS 源码使用 pure complement，本文记作：

```text
Repeat = complement(A) = (2,1):(2,8)
```

`Repeat` 保留末端 shape-1 mode，用来定义可继续延伸的重复规律；它与
`Repeat_24` 不是同一个有限 Layout。

---

## 4. 第二步：用 B 选择重复位置

```text
Repeat ∘ B
  = (2,1):(2,8) ∘ 6:1
  = (2,3):(2,8)
```

因为 `B=6:1` 依次产生 `Repeat` 的前 6 个逻辑 index，所以得到的有限结果恰好等于
`Repeat_24`。

---

## 5. 第三步：把 tile 和 tile 基址拼起来

```text
logical_product(A,B)
  = (A, Repeat∘B)
  = ((2,2),(2,3)):((4,1),(2,8))
```

循环形式：

```c
for (t1 = 0; t1 < 3; ++t1)
  for (t0 = 0; t0 < 2; ++t0)
    for (e1 = 0; e1 < 2; ++e1)
      for (e0 = 0; e0 < 2; ++e0)
        offset = 4*e0 + e1 + 2*t0 + 8*t1;
```

其中：

```text
(e0,e1) → tile 内部坐标
(t0,t1) → 第几个 tile
```

六个 tile：

| tile | 基址 | offset |
|---:|---:|---|
| 0 | 0  | `[0,4,1,5]` |
| 1 | 2  | `[2,6,3,7]` |
| 2 | 8  | `[8,12,9,13]` |
| 3 | 10 | `[10,14,11,15]` |
| 4 | 16 | `[16,20,17,21]` |
| 5 | 18 | `[18,22,19,23]` |

---

## 6. 为什么结果与官方 1-D Divide 示例相同

官方指出，这个 Product 示例与前面的 1-D Divide 示例结果相同：

```text
((2,2),(2,3)):((4,1),(2,8))
```

原因是两边恰好选择了同一个：

```text
tile 内部 Layout = (2,2):(4,1)
tile 基址 Layout = (2,3):(2,8)
```

这只是这组输入最终构造出相同的 tiled layout，不能推广成任意 Product 与 Divide 都互逆。

---

## 7. 一句话总结

```text
Division：从完整布局中找出 tile 和 tile 基址
Product ：已知 tile，主动构造 tile 基址并拼成完整布局
```

Product 的第一个 mode 永远兼容 A；在普通 `logical_product` 中，它就是 A 本身。
