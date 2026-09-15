# CuTe Complement（补集）概念总结

> 更新：2026-09-15 —— 补充 pure complement，并按 NVIDIA CUTLASS 当前官方文档、`layout.hpp` 与 complement 单元测试复核性质、边界和措辞。

> 配套文档：[`用循环理解Composition.md`](../02-Composition/用循环理解Composition.md)
> 本文所有数值均经 NVIDIA CuTe DSL 实跑验证。
> Pure/bounded 关系及补充推论的轻量验证：[`test_tiling_relations.py`](../代码实验/tests/test_tiling_relations.py)
> 官方原文出处：`media/docs/cpp/cute/02_layout_algebra.md` → **Complement** 一节
> 文中【疑问】标记 = 学习过程中真实提出过的问题，答案集中在 §9。

---

## 0. 为什么需要 Complement

Composition 回答的是"**从 A 里挑出某些元素**"。
但 **Tiling** 还要回答另一半："**被跳过的部分在哪、怎么摆**"。

```
A = 24 个元素，B = 一个 tile
→ 切成若干 tile 后，需要知道：
   · tile 内部长什么样   →  A ∘ B        （composition，已学）
   · 这堆 tile 怎么摆     →  complement(B, size(A))   ← 本文
```

> 官方原文：
> *"We can think of `composition` as a layout `B` that is 'selecting' certain coordinates from another layout `A`. But what about the coordinates that aren't 'selected'? To implement generic tiling, we want to be able to select arbitrary elements -- **the tile** -- and to describe the layout of those tiles -- **the leftovers, or the 'rest'**."*

后续 Division 的公式直接依赖它：

$$A \oslash B := A \circ (B, B^*)$$

其中 **`B* = complement(B, size(A))`**，读作"**tile 的布局**"。

---

## 1. 前置概念：像集（codomain / image）

Layout 是**函数** `A: [0, size) → 整数`。

> **像集 = 所有坐标喂进去后得到的那批 offset 值。**

```
A = 4:2  →  像集 = { A(0), A(1), A(2), A(3) } = {0, 2, 4, 6}
```

注意：像集是**值的集合**，不计顺序、不计重复。

### cosize vs size（complement 的关键区分）

| 量 | 数的是什么 | `4:2` 的值 |
|---|---|---|
| **size** | 有几个坐标（元素个数） | **4** |
| **cosize** | 占多大地盘（`max(像) + 1`） | **7** |

`4:2` 覆盖 `{0,2,4,6}`，只 4 个元素，但跨了 7 格 —— **中间有洞**。

---

## 2. 官方定义与三条性质

### 🔑 一句话定义（最重要，先记住这个）

NVIDIA 当前源码给出的核心定义是：

> **Complement 构造一个最小、ordered、且除共同原点外与输入 Layout 的像集不相交的 Layout。**

带 `cotarget` 的重载会继续扩展末端 mode，直到 `(A,A*)` 的 codomain 覆盖目标范围。

在标准的单射 tiling 场景中，可以进一步把它理解为：

> **`A*` = 让「A 的副本」以无重叠方式覆盖到 cotarget `M` 的那组基址。**
>
> **若 `M` 恰好是完整重复周期的整数倍，则 `A 的像 + A* 的像 = {0, 1, ..., M-1}`，且一一对应（双射）。**
>
> **一般情形会向上取整：结果保证覆盖至少到 `M`，末尾可能超过 `M-1`。**

⚠️ **常见误解**：**A\* ≠ "A 漏掉的元素清单"**。
例：`A = 4:1`（像 `{0,1,2,3}`，漏 20 个），但 `A* = 6:4` 只有 **6 个值** `{0,4,8,12,16,20}` —— 每个值代表**一整份 A 的拷贝**，不是单个元素。

**下面五组官方例子在 `(A,A*)` 层面全部“铺满 + 无重复坐标映射”**：

| A | A* | 覆盖 | 铺满 0..23？ | 重叠个数 |
|---|---|---|---|---|
| `4:1` | `6:4` | 24 | ✓ | 0 |
| `4:2` | `(2,3):(1,8)` | 24 | ✓ | 0 |
| `(2,2):(4,1)` | `(2,3):(2,8)` | 24 | ✓ | 0 |
| `(2,2):(1,6)` | `(3,2):(2,12)` | 24 | ✓ | 0 |
| `(4,6):(1,4)` | `1:0` | 24 | ✓ | 0 |

上表的 `M=24` 都恰好整除完整重复周期，所以确实“铺满 + 无重叠”。这是很重要的**整齐分块特例**；不要把它误记成任意 cotarget 的保证。

### ⚠️ cotarget 不整除时：保证“覆盖至少 M”，不保证“恰好到 M”

```text
complement(4:1, 10) = 3:4
(4,3):(1,4) 的像 = {0,1,...,11}
```

这里复制了 3 个长度为 4 的完整块，因此覆盖 `0..11`；它满足 `cosize((A,A*)) >= 10`，但并非只覆盖 `0..9`。

> **记忆法**：`complement` 不会切半个副本；它用完整、规整的副本覆盖到目标，因此重复次数是 `ceil(M / block)`，而不是总能写成 `M / block`。

### 函数签名

```cpp
Layout complement(LayoutA const& layout_a, Shape const& cotarget)
//                ↑ 输入 A                ↑ 范围 M        ↑ 返回值（官方记作 R）
```

> 【疑问 1】**"R 是怎么突然冒出来的？"**
>
> **R 就是返回值**，官方在写后置条件时给"输出"起的名字（就像 composition 的 post-condition 里用 `result`）。
> 记号对照：`A` = 输入 layout，`M` = cotarget（通常只用 `size(M)`），**`R` = `complement(A, M)` 的结果**。

### 2.1 Pure complement：不带 cotarget 的基础补集

CuTe 还提供不传 `cotarget` 的形式：

```cpp
Layout complement(LayoutA const& layout_a)
```

本文称它为 **pure complement**，以便和带范围的 **bounded complement** 区分：

```text
Pure:    R       = complement(A)
Bounded: R_M     = complement(A, M)
```

两者不是两个互不相关的算法。可以把它们理解成两个阶段：

1. `complement(A)` 构造由 A 自身决定的、最小且 ordered 的基础重复规则；
2. `complement(A,M)` 在此基础上扩展末端 mode，使 `(A,R_M)` 覆盖至少 `M`。

关键区别是：**pure complement 不决定最终要复制多少份 A**。它会保留末端
`shape=1` 的扩展方向，供后续 composition 根据另一个 Layout 的逻辑 index
自动延伸。

#### 例 1：连续的一维 tile

```text
A = 4:1

complement(A)     = 1:4    // pure：只保留“每份 A 相隔 4”的规则
complement(A,24)  = 6:4    // bounded：明确扩展成 6 份，覆盖 24
```

这里 `1:4` 不能理解成“只允许复制一份”。当它与重复布局 `B=6:1`
做 composition 时：

```text
(1:4) ∘ (6:1) = 6:4
```

因此复制数量由 B 提供，而 tile 基址间距由 pure complement 提供。

#### 例 2：内部有洞的 tile

```text
A = (2,2):(4,1)

complement(A)     = (2,1):(2,8)
complement(A,24)  = (2,3):(2,8)
```

pure 结果中的：

- `2:2` 负责填补 A 内部的洞；
- `1:8` 保留“完整块之间相隔 8”的扩展方向。

若后续需要 3 个完整块，该末端 mode 才会被扩展为 `3:8`。

#### 为什么 Product 使用 pure complement

当前 CUTLASS `logical_product` 的核心形式是：

```cpp
make_layout(layout,
            composition(complement(layout), tiler))
```

也就是：

```text
Repeat = complement(A)
logical_product(A,B) = (A, Repeat ∘ B)
```

Product 中，重复数量与顺序本来就由 `B` 描述。如果先调用
`complement(A,M)`，就必须提前根据 B 人工计算 cotarget；使用 pure
complement 后，`Repeat` 只描述 A 的基础重复规则，再由 `Repeat∘B`
自然生成所需的 tile 基址。

> **记忆法**
>
> - `complement(A)`：回答“**A 的下一份应该往哪里放**？”
> - `complement(A,M)`：回答“**为了覆盖 M，要把 A 的副本铺到多远**？”

后文如果没有特别注明，`complement(A,M)` 指 bounded complement；
Product 章节中的 `Repeat=complement(A)` 则专指 pure complement。

### 三条性质（官方文档）

> 1. The size (and cosize) of `R` is ***bounded*** by `size(M)`.
> 2. `R` is ***ordered***. That is, the strides of `R` are positive and increasing. **This means that `R` is unique.**
> 3. `A` and `R` have ***disjoint*** codomains. `R` attempts to "complete" the codomain of `A`.

**第 2 条最有力**：stride 正且递增 → **R 是唯一确定的**，不是"随便找一个补"。

### 四条 post-condition

NVIDIA 官方 Markdown 当前把第 2 条写成了 `>=`，但这与官方单元测试及示例
`complement(4:1,10)=3:4` 冲突。官方测试实际检查的是 `<=`，因此这里按测试修正：

```cpp
// @post cosize(make_layout(@a layout_a, @a result))) >= size(@a cotarget)
// @post cosize(@a result) <= round_up(size(@a cotarget), cosize(@a layout_a))
// @post for all i, 1 <= i < size(@a result),
//         @a result(i-1) < @a result(i)
// @post for all i, 1 <= i < size(@a result),
//         for all j, 0 <= j < size(@a layout_a),
//           @a result(i) != layout_a(j)
```

- 第 1 条：**A 和 R 拼起来**的 cosize ≥ M；cotarget 不整除时可以超过 M
- 第 2 条：`R` 的 cosize ≤ `round_up(M, cosize(A))`
- 第 3 条：R 严格递增
- 第 4 条：**`i` 从 1 开始** —— 见 §3

---

## 2.5 🔑 Concatenation（拼接）的定义 —— 简单但至关重要

> **拼接 `(X, Y)` 的偏移 = 各 mode 偏移之和：**
> **`(X, Y)(i, j) = X(i) + Y(j)`**
>
> **且 `size((X,Y)) = size(X) × size(Y)` —— 各 mode 完全独立，互不干扰。**

### 官方原文（Composition 一节的 "few observations"）

> *"`B = (B_0, B_1, ...)`. A layout can be expressed as the **concatenation of its sublayouts**."*
>
> *"`A o B = A o (B_0, B_1, ...) = (A o B_0, A o B_1, ...)`. When `B` is injective, composition is **left-distributive with concatenation**."*

**注意**：官方把 concatenation 列为 composition 的**两条前提性质**之一（另一条是左分配律）——
**Divide 和 Product 的公式都声明"只用 concatenation + composition + complement 三件套"**：

```cpp
// Divide:  composition(layout, make_layout(tiler, complement(tiler, size(layout))))
//                              └─ concat ─┘
// Product: make_layout(layout, composition(complement(...), tiler))
//          └─ concat ─┘
```

### 实测验证（偏移可加）

```
B  = 4:2            B* = (2,3):(1,8)
C  = (B, B*) = (4,(2,3)):(2,(1,8))

C(i,j) == B(i) + B*(j)   →  24/24 全部成立 ✓
size(C) = 24 = size(B) × size(B*) = 4 × 6 ✓
```

样例（`j=2`，`B*(2)=8`）：

```
C(0,2), C(1,2), C(2,2), C(3,2) = [8, 10, 12, 14]
B 的像 + 8                      = [8, 10, 12, 14]   ← 一致
```

### 为什么它重要（三处关键应用）

| 应用 | 说明 |
|---|---|
| **`(B, B*)` 构造完整下标表** | 在 B 可补、拼接结果单射且 cotarget 整齐时，像集 `B的像 + B*的像` 无重复地铺满目标范围 |
| **divide 结果何时是 permutation** | 还取决于 A 是否单射及 cotarget 是否整齐分块；详见 [Division 与 Product](../Division与Product.md) |
| **`R(i,j) = (A∘B)(i) + (A∘B*)(j)`** | 来自 concatenation 的偏移相加；详见 [Division 与 Product](../Division与Product.md) |

### 与 by-mode（尖括号）的区别

| 写法 | 含义 |
|---|---|
| `(X, Y)` | **concatenation** —— 拼成多 mode，偏移相加 |
| `<X, Y>` | **by-mode tiler** —— 各 mode 分别与 A 的对应 mode 复合 |

### 🔗 拼接 vs 组合：完全不同的两种运算

| | 拼接 `(X, Y)` | 组合 `A ∘ B` |
|---|---|---|
| **方向** | **横向并列**（多摆一个维度） | **纵向串联**（输出喂给下一个） |
| **offset** | **相加** `X(i) + Y(j)` | **嵌套代入** `A(B(c))` |
| **size** | **相乘** `size(X)×size(Y)` | **`size(B)`**（外层入参决定） |

实测（同一对 `2:3` 与 `2:1`）：

```
拼接 (2:3, 2:1) = (2,2):(3,1)   size = 4   ← 2×2 相乘
组合 B₁∘B₂                       size = 2   ← 不乘
```

**连接两者的唯一桥梁：左分配律**（官方原文）
*`A o (B_0, B_1, ...) = (A o B_0, A o B_1, ...)`*

```
实测 A=6:8, B=(2:3, 2:1)：
  LHS  A ∘ (B₀,B₁)  = [0, 24, 8, 32]
  RHS  (A∘B₀, A∘B₁) = [0, 24, 8, 32]   ✓
```

**在 Divide / Product 里的层级正好相反**：

| | 结构 | 谁在外 |
|---|---|---|
| **Divide** | `A ∘ (B, B*)` | 组合在外、拼接在内 |
| **Product** | `(A, A*∘B)` | 拼接在外、组合在内 |

> 判断诀窍：**看 `∘` 在括号外还是内** —— 在外则组合是外层。

---

## 3. "像集不相交" 与 0 的例外

> 【疑问 2】**"什么叫像集不相交？"**

字面意思：**A 能取到的 offset，R 一个都不能碰。**

但实测发现一个必然的例外：

| 例子 | A 的像 | R 的像 | 交集 |
|---|---|---|---|
| `complement(4:1,24)=6:4` | `{0,1,2,3}` | `{0,4,8,12,16,20}` | **`{0}`** |
| `complement(4:2,24)=(2,3):(1,8)` | `{0,2,4,6}` | `{0,1,8,9,16,17}` | **`{0}`** |
| `complement((2,2):(1,6),24)=(3,2):(2,12)` | `{0,1,6,7}` | `{0,2,4,12,14,16}` | **`{0}`** |

**每组交集都恰好是 `{0}`，且只来自 `R(0)`。**

### 为什么 0 必然例外

stride 全正时，坐标全 0 → 偏移必为 0：

```
A(0) = Σ 0 × dᵢ = 0
R(0) = Σ 0 × dᵢ = 0
```

两边都含 0 **不可避免**，所以官方在 post-condition 里显式从 `i = 1` 开始（第 4 条）。

> **准确表述：R 除 `R(0)=0` 外的所有值，都不在 A 的像集里。**

---

## 3.5 单射（injective）≠ 只有“没有广播”

> 【新增问题】**“不是单射的情况，是不是就是有广播时？”**
>
> **不是。广播是最直观的一类非单射，但正 stride 也可能让不同坐标撞到同一个 offset。**

**定义**：layout `L` 是单射，当且仅当

```text
L(c) = L(c')  =>  c = c'
```

也就是：不同坐标绝不映射到同一个 offset。

| 情形 | 例子 | offset 序列 | 单射？ |
|---|---|---|---|
| 有洞但不撞车 | `4:2` | `0,2,4,6` | ✓ |
| 广播（shape > 1 的 stride=0） | `4:0` | `0,0,0,0` | ✗ |
| **没有广播，仍撞车** | `(2,2):(1,1)` | `0,1,1,2` | ✗ |
| stride 都正且递增，仍可能撞车 | `(4,2):(2,4)` | `0,2,4,6,4,6,8,10` | ✗ |

`(2,2):(1,1)` 的碰撞很直观：

```text
L(1,0) = 1×1 + 0×1 = 1
L(0,1) = 0×1 + 1×1 = 1
```

所以应当记：

> **广播 ⇒（只要该 mode 的 shape > 1）非单射；但非单射 ⇏ 广播。**
>
> **有洞也不等于非单射**：`4:2` 有洞，却完全单射。

对 complement / divide 的影响：

- 不能简单写成“`complement` 拒绝所有非单射 Layout”。当前实现会先
  `filter(layout)`，shape-1 和 stride-0 mode 会先被过滤；官方单元测试也覆盖了
  `4:0`。
- 某些无法形成合法补布局的静态 Layout 会触发
  `Non-injective Layout detected in complement`。更准确地说，这是 complement
  算法无法为该 Layout 构造有效的 ordered 补布局。
- 即使 `(B,B*)` 是单射，下游的 `A∘(B,B*)` 仍可能因 **A** 广播或别名而非单射。
- 因而“divide 是 permutation”必须同时要求：`A` 单射、tiler 可补、目标整齐分块。

---

## 4. 算法：填洞 + 重复（官方口径 hole → filled → repeated）

> 【疑问 3】**"官方怎么说的？"**

官方原话（例 4 的注解）：

> *"The **'hole'** in `4:2` is **filled** with `2:1` first, then everything is **repeated** 3 times with `3:8`."*

以及总结性比喻：

> *"The complement effectively '**repeats**' the original layout... can be viewed as the **'layout of the repetition'**."*

**所以"填洞 → 填 → 重复"就是官方口径**（hole / filled / repeated）。

### 计算框架

> **【填洞】** 找规整布局 H（stride 正且递增），使 **A 的像 + H 的像 = 铺满 `0..B-1`**，B 即"块大小"
> **【重复】** 这样的块复制 **`ceil(M / B)`** 份，间距 **B**
> **【合并】** `R = (H, 重复)`，shape=1 的层删掉

⚠️ **"填洞"不是把洞逐个列出来**（`6:4` 有 15 个洞），而是**找一个规整 H 让 A+H 铺满** —— 因为官方要求 R ordered，H 必须规整。

若 `M % B == 0`，才恰好是 `M / B` 份、并恰好覆盖 `0..M-1`；否则最后一份完整块会越过 `M-1`。

---

## 4.5 🔑 手推 ↔ 算法 完整对应（不用猜，有确定公式）

> 【疑问】**"多 mode 补洞只能靠写数手推吗？"**
> **不是 —— 有确定算法，源码在 `include/cute/layout.hpp` 的 `detail::complement_prefix`（L1182）。**

### 源码核心（附官方吐槽）

```cpp
// Should just be a sort and a fold...
auto [shape_, stride_, result_shape_, result_stride] =
  fold(..., [](auto const& init, auto i) {
    auto min_stride = cute::min(stride);
    auto min_idx    = cute::find(stride, min_stride);
    auto new_shape  = min_stride / get<i>(result_stride);     // 复制几份填缝
    auto new_stride = min_stride * get<min_idx>(shape);       // 复制间距
    ...
  });
```

**它干的事：按 stride 排序 → 逐个 mode 填缝。**

### 手算五步

```
① Filter：删掉 shape=1 与 stride=0 的 mode
② 排序：各 mode 按 stride 升序
③ Fold：cur = 1，对每个 mode (s,d) 按升序：
        new_shape  = d / cur          ← 复制几份填缝
        new_stride = d × s            ← 复制间距
        cur = new_stride
    最后：block = d_R × s_R           ← 最大 stride mode 的 stride×shape
④ 重复层：ceil(M / block) 块，stride = block
⑤ coalesce 删 shape=1 的层
```

### ⭐ 逐行对应（以 `(2,2):(1,6)`，M=24 为例 → 官方 `(3,2):(2,12)`）

| 手推在做什么 | 算法哪一步 | 数值 |
|---|---|---|
| 看 A 的像 `{0,1,6,7}`、找洞 `{2,3,4,5}` | **排序 + 第一个 fold** | mode(2,1) 铺出 `{0,1}`，`cur=2` |
| 决定"副本间距 = 2" | **`new_stride = d×s = 1×2 = 2`** | **= 当前块大小 `cur`** |
| 决定"副本数 = 3" | **`new_shape = 6/2 = 3`** | **= 下一个 stride ÷ cur** |
| 得到 H = `3:2` | 补洞层 `(1,3):(1,2)` | 像 = `{0,2,4}` ✓ |
| 算出 B = 12 | **`block = d_R×s_R = 6×2 = 12`** | ✓ |
| 重复 2 块、间距 12 | **重复层 `2:12`** | ✓ |
| 结果 `(3,2):(2,12)` | coalesce 后 | ✓ |

### 算法核心的物理含义

> **"把当前已铺好的那一整块（大小 `cur`），复制 `d/cur` 份、间距 `cur` —— 正好填满到下一个 mode 想落的位置 `d`。"**

```
cur = 2（已铺 {0,1}）
下一个 mode 要落在 d = 6
→ 复制 6/2 = 3 份，间距 2  →  {0,1} {2,3} {4,5} 铺满 0..5，正好接上 6 ✓
```

**手推靠肉眼看出"洞在 2,3,4,5，间距得是 2"；算法用 `d/cur` 和 `cur` 算出同一个答案。**

**为什么按 stride 排序** —— 填缝必须**从小到大**：先拿最细的颗粒（stride 最小）铺底，才知道下一个落点前要填多少。

### 8 例验证（含 3 个算法先算、CuTe 后验的新预测）

| A | 算法给出 | CuTe 实测 | 官方答案 |
|---|---|---|---|
| `4:2` | `(2,3):(1,8)` | ✓ | ✓ 官方 |
| `6:4` | `4:1` | ✓ | ✓ 官方 |
| `(2,2):(1,6)` | `(3,2):(2,12)` | ✓ | ✓ 官方 |
| `(2,4):(1,6)` | `3:2` | ✓ | ✓ 官方 |
| `(4,6):(1,4)` | `1:0` | ✓ | ✓ 官方 |
| `4:1` | `6:4` | ✓ | ✓ 官方 |
| **`(2,2):(4,1)`** | **`(2,3):(2,8)`** | ✓ | 新预测 |
| **`2:8`** | **`(8,2):(1,16)`** | ✓ | 新预测 |
| **`3:3`** | **`(3,3):(1,9)`** | ✓ | 新预测 |

### 副产品：1-D 单 mode 的补洞恒为 `b:1`

单 mode `(a,b)` 没有中间步骤：`new_shape = b/1 = b`，`block = b×a`。

| A | 补洞 H | block = `a×b` |
|---|---|---|
| `4:2` | `2:1` | 8 |
| `6:4` | `4:1` | 24 |
| `8:3` | `3:1` | 24 |
| `2:8` | `8:1` | 16 |
| `2:5` | `5:1` | 10 |

⚠️ **多 mode 不成立** —— `new_stride = d×s` 不一定得 1。反例 `(2,2):(1,6) → 3:2`（stride=2）。

---

## 4.6 🔑 block（块大小）到底是什么 —— **不是**物理内存

> 【疑问】**"block 大小为什么不是物理内存大小？"**

### 三重身份（同一个数）

| 身份 | 含义 | `(2,2):(1,6)` |
|---|---|---|
| **① 填补后的单元** | `A 的像 + H 的像` 铺满的连续区间长度 | **12** |
| **② 重复周期** | 重复层的 stride = 相邻副本起点间距 | `2:12` → 起点 0, 12 ✓ |
| **③ 算法公式** | `d_R × s_R`（最大 stride × 它的 shape） | `6 × 2 = 12` ✓ |

**图章视角：block = 图章印一次（含补满的空白）占据的完整宽度。**

实测六例全部 `A + H` 铺满 `[0, block-1]`：

| A | size | cosize | **block** | M | 块数 | 铺满 `[0,block-1]`？ |
|---|---|---|---|---|---|---|
| `4:2` | 4 | 7 | **8** | 24 | 3 | ✓ |
| `6:4` | 6 | 21 | **24** | 24 | 1 | ✓ |
| `(2,2):(1,6)` | 4 | 8 | **12** | 24 | 2 | ✓ |
| `(2,4):(1,6)` | 8 | 20 | **24** | 24 | 1 | ✓ |
| `(4,6):(1,4)` | 24 | 24 | **24** | 24 | 1 | ✓ |
| `2:8` | 2 | 9 | **16** | 24 | 2 | ✓ |

### 四个量全都不一样

| 量 | 含义 | 谁决定 | `(2,2):(1,6)` |
|---|---|---|---|
| `size(A)` | A 有几个元素 | A | **4** |
| `cosize(A)` | A 跨多远（**有洞**） | A | **8** |
| **block** | **补洞后的完整周期（无洞）** | A + 补洞 H | **12** |
| **M (cotarget)** | **总目标范围** | **你传入的参数** | **24** |

> **`block ≥ cosize(A)` 恒成立** —— 补洞把块**撑大**了（洞也要算进去）。
> 注意 `cosize=8` 但 `block=12`。

### 为什么不是物理内存（三个理由）

**① complement 根本不知道内存长什么样**

```cpp
complement(Layout const& layout, CoTarget const& cotarget)
//          ↑ 只有 layout        ↑ 和一个目标数
```

**输入里没有指针、没有 buffer、没有 `make_tensor`** —— 纯符号运算。物理内存多大由 `make_tensor` 的 `ptr` 决定，complement 从头到尾没见过它。

**② 三者完全独立，且可以不对齐**

| | 由谁定 |
|---|---|
| block（周期） | A 的结构 |
| M（cotarget） | 你传的参数 |
| 物理内存 | `ptr` 分配 |

源码用 `ceil_div(cotarget, new_stride)` —— `M=20, block=12` 时得 2 块，实际覆盖 `0..23`（**超出 M 是合法的**，post-condition 只要求 `>=`）。

**③ 两个不同层的问题**

```
block = 12     → 布局上，每 12 格重复一次（tile 怎么重复）
内存  = 16384  → 访问会不会段错误（安全性）
```

> **一句话**：block = A 补完洞后能连续铺满的最小完整单元 = 重复周期 = 相邻副本起点间距。**它是纯符号量，与物理内存无关。**

---

## 5. 六例逐步拆解（明确标注【填洞】/【重复】）

| 例子 | A 的像 | cosize | **【填洞】H** | 块 B | **【重复】** | R |
|---|---|---|---|---|---|---|
| `complement(4:1,24)` | `{0,1,2,3}` | 4 | 无（无洞）→ 删 | 4 | **`6:4`** | `6:4` |
| `complement(6:4,24)` | `{0,4,8,12,16,20}` | 21 | **`4:1`** | 24 | 无（1 块）→ 删 | `4:1` |
| `complement((4,6):(1,4),24)` | 全 `0..23` | 24 | 无 → 删 | 24 | 无 → 删 | `1:0` |
| `complement(4:2,24)` | `{0,2,4,6}` | 7 | **`2:1`** | 8 | **`3:8`** | `(2,3):(1,8)` |
| `complement((2,4):(1,6),24)` | 8 个 | 20 | **`3:2`** | 24 | 无 → 删 | `3:2` |
| `complement((2,2):(1,6),24)` | `{0,1,6,7}` | 8 | **`3:2`** | 12 | **`2:12`** | `(3,2):(2,12)` |

### ⭐ 例 4 详解（官方详解例）

```
A = 4:2   像 = {0,2,4,6}   cosize = 7   洞 = {1,3,5}

【填洞】找规整 H 让 A+H 铺满：
    0 1 2 3 4 5 6
A:  ● ○ ● ○ ● ○ ●        ●=A 覆盖  ○=洞
    A+0 = {0,2,4,6}
    A+1 = {1,3,5,7}
    合并 = {0,1,2,3,4,5,6,7}  → 铺满 0..7 ✓
  → H = 2:1，块大小 B = 8

【重复】24 / 8 = 3 块，间距 8  →  3:8

【合并】R = (2:1, 3:8) = (2,3):(1,8)
        R 的像 = {0,1, 8,9, 16,17}
                 └块0┘ └块1┘ └块2┘
```

### ⭐ 例 6 详解（官方配图例 complement1.png）

```
A = (2,2):(1,6)   像 = {0,1,6,7}   cosize = 8   洞 = {2,3,4,5}

【填洞】A+0={0,1,6,7}  A+2={2,3,8,9}  A+4={4,5,10,11} → 铺满 0..11 ✓
        → H = 3:2，块大小 B = 12
【重复】24 / 12 = 2 块，间距 12  →  2:12
【合并】R = (3:2, 2:12) = (3,2):(2,12)
```

---

## 6. 统一模型：每个 mode `s:d` = 复制 s 份，间距 d

> 【疑问 4】**"每个 mode `s:d` 在做的事都是重复 s 次、每次 +d？"**

**是的** —— 这是 layout mode 的定义，不限于 complement：

```
mode s:d  →  贡献偏移 = {0, d, 2d, ..., (s-1)d}   = s 个位置，间距 d
```

coalesce 里的 `s0*d0`（内层跑完一整遍的跨度）、composition 的 stride 语义，全部是它的特例。

### 在 complement 里：填洞和重复是**同一个操作**，区别只在【复制谁】

| 层 | 复制的对象 | stride 含义 | 结果 |
|---|---|---|---|
| **mode-0（填洞）** | **A 自己** | 副本间距 | 把 A 复制若干份 → **填满一个块** |
| **mode-1（重复）** | **整个块** | 块的大小 | 把块复制若干份 → **填满 M** |

```
complement(4:2, 24) 的层级：
  A = {0,2,4,6}
  mode-0 = 2:1  →  复制 A 2 份，间距 1  →  块 = {0..7}，大小 8
  mode-1 = 3:8  →  复制块 3 份，间距 8  →  铺满 0..23 ✓
```

**哪层退化成 1 份就删掉哪层** —— 又是 coalesce 那条规则（shape=1 删）在 complement 里同样适用。

---

## 7. A+0 的澄清：不是"允许重叠"，而是**原件本身**

> 【疑问 5】**"重复时 A+0 这个是可以允许重叠的？"**

**要更准确地说**：

> **`A+0 = A`，它是"原件"，不是"副本"。它跟 A 完全重合不是被允许的例外，是定义上必然。**

因为 **`R(0) = 0` 永远成立**（stride 全正，坐标全 0 → 偏移 0），所以 `A + R(0) = A + 0 = A` 必然出现。

**这正是官方把 post-condition 的 `i` 从 1 开始的原因**：

```cpp
// @post for all i, 1 <= i < size(result),    ← 跳过 i=0
//           result(i) != layout_a(j)
```

> 官方直接约束的是：除 `R(0)=0` 外，R 的值不能与 A 的值相同。若要把
> `(A,R)` 当作无重复 tiling，还应另外验证拼接后的 Layout 是单射。

### 六例实测（全部通过）

| 例子 | R 的像（各副本偏移） | `A+0 == A` | 副本两两不交 | 并集铺满 `0..M-1` |
|---|---|---|---|---|
| `4:1 → 6:4` | `{0,4,8,12,16,20}` | ✓ | ✓ | ✓ |
| `6:4 → 4:1` | `{0,1,2,3}` | ✓ | ✓ | ✓ |
| `(4,6) → 1:0` | `{0}` | ✓ | ✓ | ✓ |
| `4:2 → (2,3):(1,8)` | `{0,1,8,9,16,17}` | ✓ | ✓ | ✓ |
| `(2,4) → 3:2` | `{0,2,4}` | ✓ | ✓ | ✓ |
| `(2,2) → (3,2):(2,12)` | `{0,2,4,12,14,16}` | ✓ | ✓ | ✓ |

在上面六个整齐分块例子中，`(A,R)` 无重复、无遗漏地铺满了 `0..M-1`。
这是这些例子的验证结果；cotarget 不整除时只能保证覆盖至少到 M。

> ⚠️ `A(0)=R(0)=0` 是两个 Layout 像集的共同原点，不应描述成两个副本发生了重叠。
> 不同平移副本是否互不相交，应通过检查 `(A,R)` 的单射性来确认。

---

## 8. "ordered" 性质是结构的自然结果

官方第 2 条要求 R 的 stride 正且递增。用 §6 模型立刻得到解释：

这里说的是 R 按自然 index 得到的值严格递增。像 `1:0` 这种只有一个坐标的退化结果，
没有相邻元素需要比较，因此按 post-condition 是 vacuously true；不要据此要求它唯一的
stride `0` 也必须为正。

| 例子 | 填洞 stride（副本间距） | 重复 stride（块大小） | 递增？ |
|---|---|---|---|
| `4:2 → (2,3):(1,8)` | 1 | 8 | **1 < 8** ✓ |
| `(2,2) → (3,2):(2,12)` | 2 | 12 | **2 < 12** ✓ |

**副本间距必然 < 块大小**（副本在块内，块包含所有副本）—— 所以"递增"是结构的自然结果，不是额外约束。

---

## 9. 疑问记录 Q&A

| # | 疑问 | 答案 |
|---|---|---|
| 1 | **R 怎么突然冒出来的？** | R 就是 `complement(A,M)` 的**返回值**，官方写后置条件时给输出起的名字。A = 输入，M = cotarget，R = 结果 |
| 2 | **什么叫像集不相交？** | A 能取到的 offset，R 一个都不能碰。但 `R(0)=0` 与 `A(0)=0` 必然重合 → 官方把 `i=0` 排除（post-condition 第 4 条从 `i=1` 起）。实测六例交集都恰为 `{0}` |
| 3 | **(4,2) 怎么突然冒出来的？** | 那是我**临时拼的验证结构**（`A` + 补），用来验证"填完洞后一块铺满 0..7"。**官方没这么写，R 里也不含 A**。官方的结构是 `(A, R)` 拼整体（cosize ≥ M）。是我表述时没说清来源 |
| 4 | **官方怎么说的？** | 官方原话就是 **hole → filled → repeated**（*"The 'hole' in `4:2` is filled with `2:1` first, then everything is repeated 3 times with `3:8`"*），总结为 **"layout of the repetition"**。我一度说"填洞不准"是我讲岔了 —— "填洞"和"副本平移"是同一现象的两种视角（从缺什么看 / 从补什么看），算出来同一个 `2:1` |
| 5 | **每个 mode `s:d` 都是"重复 s 次、每次 +d"？** | **是的**，这是 layout mode 的通用定义。complement 里 mode-0 复制 A（填洞成块）、mode-1 复制块（重复铺满 M）—— 同一操作的两级 |
| 6 | **A+0 是允许重叠吗？** | **不是“允许”，是必然**——`A+0` 就是 A 本身。官方直接约束的是 `R(i)`（`i≥1`）不能等于任何 `A(j)`；若用于无重复 tiling，还应验证 `(A,R)` 的单射性 |

---

## 10. 速查表

### 概念

| 术语 | 含义 |
|---|---|
| **complement(A)** | **pure complement**：求只由 A 决定的最小基础重复规则；保留末端 `shape=1` 扩展 mode，不预先决定复制数量 |
| **complement(A, M)** | **bounded complement**：在 pure complement 的基础上扩展末端 mode，使 A 的完整副本覆盖**至少** M；若周期整除 M 才恰好铺满 M |
| **cotarget M** | 目标范围，通常只用 `size(M)` |
| **cosize** | `max(像) + 1`，占多大地盘 |
| **像集 / codomain** | layout 能取到的 offset 值的集合 |
| **B\* / A\*** | `complement` 的结果，读作"**重复的方式**" |

### Pure / bounded 对照

| 对比 | Pure complement | Bounded complement |
|---|---|---|
| 调用 | `complement(A)` | `complement(A,M)` |
| 是否依赖 M | 否，只由 A 决定 | 是 |
| 末端重复 mode | 保留 `shape=1`，等待后续扩展 | 按 M 扩展到足够的 shape |
| 回答的问题 | A 的副本应按什么基础间距摆放？ | 为覆盖 M，需要铺多少份 A？ |
| 典型用途 | `logical_product` | `logical_divide` |
| `A=4:1` | `1:4` | `M=24` 时为 `6:4` |

### 计算步骤

**Pure complement：**

```text
① 算 A 的像集与 cosize
② 【填洞】找规整 H，使 A+H 形成一个完整块
③ 【保留扩展方向】追加末端 shape=1 mode，stride 为完整块大小
④ 【合并】保留 Product 后续 composition 所需的末端 shape-1 mode
```

**Bounded complement：**

```
① 算 A 的像集与 cosize
② 【填洞】找规整 H 使 A+H 铺满 0..B-1，得块大小 B
③ 【重复】块复制 `ceil(M/B)` 份，间距 B
④ 【合并】R = (H, 重复)，删掉 shape=1 的层
⑤ 自检：A 与 R 的所有副本无重叠；覆盖范围至少到 M（周期整除时恰好铺满 `0..M-1`）
```

### 与后续 Division 的关系

```
logical_divide(A, B) = composition(A, (B, complement(B, size(A))))
                                        ↑ 本文的 R，即 B*

logical_product(A, B) = (A, complement(A) ∘ B)
                            ↑ pure complement
```

> `B` = tile 内部，`B*` = tile 的布局（这堆 tile 怎么摆）。
> 且 **`layout<0>(zipped_divide(a,b)) == composition(a,b)`** —— tile 本身的布局就是 composition 的结果。

---

## 11. 与 Division / Product 的关系

Complement 是后续 tiling 运算的基础，但详细的 Divide、Product、tile 0、
`local_tile` 和 permutation 讨论不属于 Complement 本节，统一移至：

- [Division 与 Product（Tiling 的两半）](../Division与Product.md)

本节只保留最直接的连接公式：

```text
logical_divide(A,B) = A ∘ (B, complement(B,size(A)))
```

---

## 附：官方 Complement 例子速查（cotarget = 24）

| 输入 | 输出 | 官方注解 |
|---|---|---|
| `complement(4:1, 24)` | `6:4` | `4:1` 被重复 6 次 |
| `complement(6:4, 24)` | `4:1` | `6:4` 的洞被 `4:1` 填上 |
| `complement((4,6):(1,4), 24)` | `1:0` | 已铺满，无需追加 |
| `complement(4:2, 24)` | `(2,3):(1,8)` | 先填 `2:1`，再重复 3 次 `3:8` |
| `complement((2,4):(1,6), 24)` | `3:2` | 拼后 cosize 24，索引唯一 |
| `complement((2,2):(1,6), 24)` | `(3,2):(2,12)` | 拼后 cosize 24，索引唯一（官方配图例） |

> 官方单元测试（更多例子）：
> `https://github.com/NVIDIA/cutlass/tree/main/test/unit/cute/core/complement.cpp`
