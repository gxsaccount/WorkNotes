# CuTe Complement（补集）概念总结

> 配套文档：`用循环理解Composition.md`
> 本文所有数值均经 NVIDIA CuTe DSL 实跑验证。
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

## 1. 官方定义与三条性质

### 函数签名

```cpp
Layout complement(LayoutA const& layout_a, Shape const& cotarget)
//                ↑ 输入 A                ↑ 范围 M        ↑ 返回值（官方记作 R）
```

> 【疑问 1】**"R 是怎么突然冒出来的？"**
>
> **R 就是返回值**，官方在写后置条件时给"输出"起的名字（就像 composition 的 post-condition 里用 `result`）。
> 记号对照：`A` = 输入 layout，`M` = cotarget（通常只用 `size(M)`），**`R` = `complement(A, M)` 的结果**。

### 三条性质（官方原文）

> 1. The size (and cosize) of `R` is ***bounded*** by `size(M)`.
> 2. `R` is ***ordered***. That is, the strides of `R` are positive and increasing. **This means that `R` is unique.**
> 3. `A` and `R` have ***disjoint*** codomains. `R` attempts to "complete" the codomain of `A`.

**第 2 条最有力**：stride 正且递增 → **R 是唯一确定的**，不是"随便找一个补"。

### 四条 post-condition（官方原文）

```cpp
// @post cosize(make_layout(@a layout_a, @a result))) >= size(@a cotarget)
// @post cosize(@a result) >= round_up(size(@a cotarget), cosize(@a layout_a))
// @post for all i, 1 <= i < size(@a result),
//         @a result(i-1) < @a result(i)
// @post for all i, 1 <= i < size(@a result),
//         for all j, 0 <= j < size(@a layout_a),
//           @a result(i) != layout_a(j)
```

- 第 1 条：**A 和 R 拼起来**的 cosize ≥ M（实测：正好铺满）
- 第 2 条：`R` 的 cosize ≥ `round_up(M, cosize(A))`
- 第 3 条：R 严格递增
- 第 4 条：**`i` 从 1 开始** —— 见 §3

---

## 2. 像集（codomain / image）

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

## 4. 算法：填洞 + 重复（官方口径 hole → filled → repeated）

> 【疑问 3】**"官方怎么说的？"**

官方原话（例 4 的注解）：

> *"The **'hole'** in `4:2` is **filled** with `2:1` first, then everything is **repeated** 3 times with `3:8`."*

以及总结性比喻：

> *"The complement effectively '**repeats**' the original layout... can be viewed as the **'layout of the repetition'**."*

**所以"填洞 → 填 → 重复"就是官方口径**（hole / filled / repeated）。

### 计算框架

> **【填洞】** 找规整布局 H（stride 正且递增），使 **A 的像 + H 的像 = 铺满 `0..B-1`**，B 即"块大小"
> **【重复】** 这样的块复制 **`M / B`** 份，间距 **B**
> **【合并】** `R = (H, 重复)`，shape=1 的层删掉

⚠️ **"填洞"不是把洞逐个列出来**（`6:4` 有 15 个洞），而是**找一个规整 H 让 A+H 铺满** —— 因为官方要求 R ordered，H 必须规整。

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

> **真正的约束：除 `A+0` 外，其余副本 `A+r`（r ≠ 0）必须两两不交，且都不碰 A。**

### 六例实测（全部通过）

| 例子 | R 的像（各副本偏移） | `A+0 == A` | 副本两两不交 | 并集铺满 `0..M-1` |
|---|---|---|---|---|
| `4:1 → 6:4` | `{0,4,8,12,16,20}` | ✓ | ✓ | ✓ |
| `6:4 → 4:1` | `{0,1,2,3}` | ✓ | ✓ | ✓ |
| `(4,6) → 1:0` | `{0}` | ✓ | ✓ | ✓ |
| `4:2 → (2,3):(1,8)` | `{0,1,8,9,16,17}` | ✓ | ✓ | ✓ |
| `(2,4) → 3:2` | `{0,2,4}` | ✓ | ✓ | ✓ |
| `(2,2) → (3,2):(2,12)` | `{0,2,4,12,14,16}` | ✓ | ✓ | ✓ |

**A 和 R 的所有副本加起来，无重叠、无遗漏地铺满 `0..M-1`** —— 这就是官方说的 *"disjoint codomains"* + *"complete the codomain"*。

> ⚠️ 重叠**只发生在 `A+0` 这一处**（且是原件本身）。一旦两个不同副本 `A+r₁`、`A+r₂` 撞车，tiling 会重复覆盖同一块内存 —— 这是不允许的。

---

## 8. "ordered" 性质是结构的自然结果

官方第 2 条要求 R 的 stride 正且递增。用 §6 模型立刻得到解释：

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
| 6 | **A+0 是允许重叠吗？** | **不是"允许"，是必然** —— `A+0` 就是 A 本身（原件）。因 `R(0)=0` 恒成立。约束真正说的是：**其余副本 `A+r`（r≠0）必须两两不交** |

---

## 10. 速查表

### 概念

| 术语 | 含义 |
|---|---|
| **complement(A, M)** | 求 A 的"补" R，使得 A 与 R 的副本无重叠铺满 M |
| **cotarget M** | 目标范围，通常只用 `size(M)` |
| **cosize** | `max(像) + 1`，占多大地盘 |
| **像集 / codomain** | layout 能取到的 offset 值的集合 |
| **B\* / A\*** | `complement` 的结果，读作"**重复的方式**" |

### 计算步骤

```
① 算 A 的像集与 cosize
② 【填洞】找规整 H 使 A+H 铺满 0..B-1，得块大小 B
③ 【重复】块复制 M/B 份，间距 B
④ 【合并】R = (H, 重复)，删掉 shape=1 的层
⑤ 自检：A 与 R 的所有副本，无重叠铺满 0..M-1
```

### 与后续 Division 的关系

```
logical_divide(A, B) = composition(A, (B, complement(B, size(A))))
                                        ↑ 本文的 R，即 B*
```

> `B` = tile 内部，`B*` = tile 的布局（这堆 tile 怎么摆）。
> 且 **`layout<0>(zipped_divide(a,b)) == composition(a,b)`** —— tile 本身的布局就是 composition 的结果。

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
