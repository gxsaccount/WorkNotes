# Division（Tiling）

> 官方对应：NVIDIA CUTLASS `media/docs/cpp/cute/02_layout_algebra.md` → **Division (Tiling)**
>
> 更新：2026-09-15

## 核心公式

```text
A ⊘ B = A ∘ (B, B*)
B* = complement(B, size(A))
```

## 先建立物理直觉

> **Division 返回一个重新组织后的 Layout：它把 A 的全局坐标改写成
> “tile 内坐标 + tile 位置”，从而给出所有 tile 中所有元素的 offset。**

统一写成：

```text
R(tile 内坐标, tile 编号) = 对应元素在 A 中的 offset
```

这里的“拆成 tile”只是**坐标重组**，不会物理切割或移动数据。

```text
A：完整数据的 Layout，负责把逻辑 index 映射成最终 offset
B：一个 tile 内部包含哪些逻辑 index
B*：通过移动 B，使各个 tile 覆盖 A 的逻辑 index 空间
```

因此：

```text
(B,B*)                → 所有 tile 的逻辑 index
A ∘ (B,B*)            → 所有 tile 中所有元素的 offset
logical_divide(A,B)   → 按 (tile 内坐标, tile 编号) 组织这些 offset
```

在 tiler 可补、A 单射且目标能够整齐分块时，结果会无重复地覆盖 A 的全部 offset。
如果目标不能被完整 tile 整除，Complement 会向上覆盖，末尾可能包含超出目标范围的坐标。

Division 不是一套新的底层算法，而是三步组合：

```text
① 求 B 的 complement：B*
② 拼接 tile 与 rest：(B,B*)
③ 用它重新索引 A：A ∘ (B,B*)
```

## 官方例子教程

1. [Logical Divide 1-D：从公式到循环](01-Logical-Divide-1D.md)
2. [Logical Divide 2-D：by-mode tiling](02-Logical-Divide-2D.md)
3. [Zipped / Tiled / Flat Divide：mode 如何重组](03-Divide-Variants.md)

## 与完整笔记的关系

- 本目录：严格沿 NVIDIA 官方 Division 章节的顺序讲解
- [Division 与 Product](../Division与Product.md)：Division、Product 及工程应用的综合总结

## 官方子主题

- Logical Divide 1-D
- Logical Divide 2-D
- Zipped Divide
- Tiled Divide
- Flat Divide
