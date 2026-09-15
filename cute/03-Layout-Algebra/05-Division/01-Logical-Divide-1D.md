# Logical Divide 1-D：从公式到循环

> 官方例子：NVIDIA CUTLASS Layout Algebra → Logical Divide 1-D Example
>
> 更新：2026-09-15

## 1. Division 要解决什么

> **Division 把 A 的全局逻辑坐标重组为 `(tile 内坐标, tile 编号)`，并返回对应
> 元素的 offset。**

它不会物理切割或移动数据，只是改变 Layout 的坐标组织方式。

给定：

```text
A：完整数据的 Layout
B：一个 tile 在 A 的逻辑 index 空间中的选取方式
```

`composition(A,B)` 只能得到一个 tile。Division 还需要找到其余 tile 在哪里，因此引入
`B* = complement(B,size(A))`：

```text
logical_divide(A,B) = A ∘ (B,B*)
```

官方对两个结果 mode 的解释是：

```text
mode-0：tile 内的元素
mode-1：遍历各个 tile
```

更准确地说：

```text
(B,B*)                → 枚举所有 tile 的逻辑 index
A ∘ (B,B*)            → 将这些逻辑 index 映射为 A 的 offset
logical_divide(A,B)   → 按 (tile 内坐标, tile 编号) 组织这些 offset
```

所以“获得所有 tile 的逻辑 index”描述的是中间下标表 `(B,B*)`；最终
`logical_divide(A,B)` 已经再经过 A，得到的是 tiled offset Layout。

---

## 2. 官方 1-D 例子

```text
A = (4,2,3):(2,1,8)
B = 4:2
```

A 有 24 个逻辑坐标。B 表示一个包含 4 个元素、逻辑 index 间隔为 2 的 tile：

```text
B 的像 = [0,2,4,6]
```

注意：这里的 `0,2,4,6` 是喂给 A 的**逻辑 index**，不是最终内存 offset。

---

## 3. 第一步：求 B*

官方结果：

```text
B* = complement(4:2,24)
   = (2,3):(1,8)
```

B* 的自然序列是：

```text
[0,1,8,9,16,17]
```

这些值描述 6 个 tile 在 A 的逻辑 index 空间中的起点。

为什么是 `(2,3):(1,8)`：

```text
2:1  → 用起点 0、1 填满 4:2 留下的奇偶空隙
3:8  → 将填满后的 8 个逻辑 index 重复 3 次
```

于是：

```text
B 的像 + B* 的像
```

无重复地覆盖 `0..23`。

---

## 4. 第二步：拼接 `(B,B*)`

```text
(B,B*)
  = (4,(2,3)):(2,(1,8))
```

其映射是：

```text
(B,B*)(i,j) = B(i) + B*(j)
```

循环形式：

```c
for (t1 = 0; t1 < 3; ++t1)
  for (t0 = 0; t0 < 2; ++t0)
    for (e = 0; e < 4; ++e)
      logical_index = 2*e + t0 + 8*t1;
```

其中：

```text
e       ：tile 内坐标
(t0,t1) ：tile 编号
```

---

## 5. 第三步：与 A composition

官方结果：

```text
A ∘ (B,B*)
  = ((2,2),(2,3)):((4,1),(2,8))
```

利用左分配律理解：

```text
A ∘ (B,B*) = (A∘B, A∘B*)
```

### 5.1 tile mode

```text
A ∘ B
  = A ∘ 4:2
  = (2,2):(4,1)
```

它的 offset 序列是：

```text
[0,4,1,5]
```

逐点计算：

| tile 内 index | B 输出的逻辑 index | A 的 offset |
|---:|---:|---:|
| 0 | 0 | 0 |
| 1 | 2 | 4 |
| 2 | 4 | 1 |
| 3 | 6 | 5 |

### 5.2 rest mode

```text
A ∘ B*
  = (2,3):(2,8)
```

它给出各个 tile 在 A 的 offset 空间中的基址：

```text
[0,2,8,10,16,18]
```

注意区分：

```text
B*       = [0,1,8,9,16,17]    // A 的逻辑 index
A ∘ B*   = [0,2,8,10,16,18]   // A 的最终 offset
```

---

## 6. 最终循环

将结果 Layout：

```text
((2,2),(2,3)):((4,1),(2,8))
```

直接翻译成循环：

```c
for (t1 = 0; t1 < 3; ++t1)
  for (t0 = 0; t0 < 2; ++t0)
    for (e1 = 0; e1 < 2; ++e1)
      for (e0 = 0; e0 < 2; ++e0)
        offset = 4*e0 + e1 + 2*t0 + 8*t1;
```

前两个变量：

```text
(e0,e1) → tile 内部
```

后两个变量：

```text
(t0,t1) → 第几个 tile
```

六个 tile 分别是：

| tile | 基址 | offset |
|---:|---:|---|
| 0 | 0  | `[0,4,1,5]` |
| 1 | 2  | `[2,6,3,7]` |
| 2 | 8  | `[8,12,9,13]` |
| 3 | 10 | `[10,14,11,15]` |
| 4 | 16 | `[16,20,17,21]` |
| 5 | 18 | `[18,22,19,23]` |

---

## 7. 本节结论

```text
B       决定 tile 内选哪些逻辑 index
B*      决定这些 tile 在逻辑 index 空间如何排列
A∘B     是 tile 本身
A∘B*    是 tile 的 offset 基址表
(A∘B,A∘B*) 是完整 divide 结果
```

最容易混淆的一点：

> **Complement 作用在 B 上，得到的是逻辑 index 布局；最后必须再经过 A，才得到真实 offset。**
