# CuTe Complement（补集）概念总结

> 更新：2026-09-11 —— 补充 cotarget 非整除、单射与 permutation 的边界条件。

> 配套文档：[`用循环理解Composition.md`](../02-Composition/用循环理解Composition.md)
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

### 🔑 一句话定义（最重要，先记住这个）

> **`A*` = 让「A 的副本」以无重叠方式覆盖到 cotarget `M` 的那组基址。**
>
> **若 `M` 恰好是完整重复周期的整数倍，则 `A 的像 + A* 的像 = {0, 1, ..., M-1}`，且一一对应（双射）。**
>
> **一般情形会向上取整：结果保证覆盖至少到 `M`，末尾可能超过 `M-1`。**

⚠️ **常见误解**：**A\* ≠ "A 漏掉的元素清单"**。
例：`A = 4:1`（像 `{0,1,2,3}`，漏 20 个），但 `A* = 6:4` 只有 **6 个值** `{0,4,8,12,16,20}` —— 每个值代表**一整份 A 的拷贝**，不是单个元素。

**实测五组全部"铺满 + 零重叠"**：

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

## 1.5 🔑 Concatenation（拼接）的定义 —— 简单但至关重要

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
| **`(B, B*)` 是完整下标表** | 因偏移可加 → 像集 = `B的像 + B*的像` = 笛卡尔和；再由 complement 保证无重叠铺满 → **双射** |
| **divide 结果是 permutation** | 正因 `(B,B*)` 是双射（见 §11） |
| **`R(i,j) = (A∘B)(i) + (A∘B*)(j)`** | 两 mode 独立 → 偏移天然可加 → **所有 block 是纯平移**（见 §13） |

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

## 1.6 🎭 Layout 的八种物理身份（多视角速查）

同一个 layout，换"物理身份"看，很多靠记的东西会变成常识。
统一用 `A = (4,2,3):(2,1,8)`（size=24）贯穿。

| # | 物理身份 | shape 是 | stride 是 | 最擅长解释 |
|---|---|---|---|---|
| 1 | **函数 / 映射** | 定义域 | 系数 | 数学本质、"无越界" |
| 2 | **一维数组** | 维度长度 | — | 像集、gather |
| 3 | **混合进制计数器** | 每位**基数** | 每位**位权** | `idx2crd`、硬边界 |
| 4 | **向量空间 / 点积** | 各维长度 | **基向量** | 线性性、单 mode 无界 |
| 5 | **齿轮 / 里程表** | **齿数** | 每格走多远 | coalesce（咬合） |
| 6 | **地址生成器（硬件）** | 计数器上限 | 累加增量 | 编译期零开销 |
| 7 | **图章 / 印花** ⭐ | 图案尺寸 | 图案内间距 | tiling、complement |
| 8 | **递归层级** ⭐ | 图案长度 | 复制间距 | `(A0,A1,A2,...)` |

### ③ 混合进制计数器（解释 `idx2crd` 与硬边界）

```
shape  = (4,2,3)  → mode-0 是 4 进制、mode-1 是 2 进制、mode-2 是 3 进制
stride = (2,1,8)  → 各位的"位权"
```

`n` 是读数，`idx2crd` 是把它拆成各位数字：

```
n= 5 → (1,1,0)      n= 7 → (3,1,0)
n=13 → (1,1,1)      n=23 → (3,1,2)  ← 读满
```

- **多 mode 有硬边界** —— 每位被限制在 `[0, sᵢ)`，超出就溢出/绕回 → `/d` 要求整除
- **单 mode 无界** —— 只有一位，`crd = n` 直接是读数，**基数不参与** → 无限延伸

### ④ 向量空间 / 点积（解释线性性）

```
offset = 坐标向量 · stride 向量
n=23 → (3,1,2)·(2,1,8) = 6+1+16 = 23 ✓
```

- **concatenation 偏移相加** ← 点积的线性性（两基各贡献，天然独立）
- **`A(n+m) ≠ A(n)+A(m)`** ← `idx2crd`（进制拆分）非线性；单 mode 时 `crd=n` 才退化为线性
- **stride=0 = 零向量** ← 该维基向量长度为 0 → **广播**

### ⑤ 齿轮 / 里程表（解释 coalesce）

| | 齿轮参数 |
|---|---|
| **shape** | **齿数** |
| **stride** | 每格推动走多远 |

**coalesce 判据 `d₁ == s₀×d₀` 翻译成齿轮语言**：

> **内层转满一圈的距离（`s₀d₀`）必须正好等于外层走一格（`d₁`）→ 两齿轮咬合，可换成大齿轮。**

| 判据 | 含义 |
|---|---|
| `d₁ == s₀d₀` | 严丝合缝 → 合并 |
| `d₁ > s₀d₀` | 外层跳太远 → 中间脱开有空洞 |
| `d₁ < s₀d₀` | 落回内圈 → 齿打滑（offset 撞车） |

> 这就是"合并后 stride 抄 `d₀`"的物理原因 —— 大齿轮沿用内层的每格步距。

### ⑥ 地址生成器（解释"为什么值得这么复杂"）

```
address = base + Σ coord_i × stride_i
```

| layout 概念 | 硬件对应 |
|---|---|
| shape | 各级**计数器上限** |
| stride | 各级**累加增量** |
| coalesce | 优化掉一层嵌套（两级合成一级） |
| composition | 预计算地址变换，div/mod 降级成乘加 |
| stride=0 | 该级不累加（广播，省带宽） |

- **为什么敢搬到编译期** —— layout 是纯符号表达式，`constexpr` 全算完，运行时只剩乘加，**零开销**
- **为什么允许"走出去"** —— 地址生成器没有越界检查电路（调用者责任），只管按公式算偏移

### ⑦ ⭐ 图章 / 印花（把 tiling 三件套一次性钉死）

| layout 概念 | 图章类比 |
|---|---|
| **tile**（Product 的 A / Divide 的 B） | **印章本身**（刻的图案） |
| **A\* / B\*** | **盖章位置表**（往哪盖、盖几次） |
| **(tile, 位置表)** 拼接 | **盖完的整张纸** |
| **stride** | 图案内间距 / 相邻盖章点间距 |
| **shape** | 图案元素数 / 盖几次 |

**Product = 刻章 + 印（构造式）**；**Divide = 纸上已有内容，按图章读（查询式）**

```
图章 A = 4:1，图案 = [0,1,2,3]
B=6:1  → 位置 [0,4,8,12,16,20]
  第0次 base= 0 |0000                    |
  第1次 base= 4 |    1111                |
  第2次 base= 8 |        2222            |
  第3次 base=12 |            3333        |
  第4次 base=16 |                4444    |
  第5次 base=20 |                    5555|   → 盖满 24 格，无重叠 ✓

B=3:1  → 位置 [0,4,8]            只盖 3 次，纸只有 12 格
B=6:2  → 位置 [0,8,16,24,32,40]  隔位挑 → 间距 4→8，中间留洞
```

⚠️ **注意 A\* 随 B 重算** —— cotarget = `size(A) × cosize(B)`，B 变了 A\* 也变。

**blocked vs raked = 盖章顺序不同**

```
blocked（A 在前）: [t0e0, t0e1, t1e0, t1e1, t2e0, t2e1]  ← tile 是实心块
raked  （B 在前）: [t0e0, t1e0, t2e0, t0e1, t1e1, t2e1]  ← 交错/耙开
```

**用图章视角回看之前的困惑**：

| 困惑 | 图章视角 |
|---|---|
| A\* 为什么不是"漏掉的元素清单" | 位置表记"往哪盖"（6 个位置），不是"哪些格空着"（20 格）——**每个位置代表一整份图案** |
| 为什么拼起来就铺满 | 图章无重叠盖满 = complement 的 disjoint + complete |
| 为什么 `A∘B` 只有 tile 0 | `B*(0)=0` → 第一个盖章位置是 0 |
| stride=0 为什么是广播 | 印章那一维没有图案变化，盖到哪都一样 |
| 单 block 为何能推广到全部 | **同一枚章，换个位置再盖** —— 图案相同，只差 base |

### ⑧ ⭐ 递归层级观：`(A0, A1, A2, ...)`

> **`A₀` 是基础图案；`A₁` 描述"这个图案（及其补洞）如何铺成 block 并复制"；`A₂` 描述"这个 block 如何复制"…… 依此类推。**

实测递归验证（紧密情形）：

```
(A0, A1)      A0 = 4:1    A1 = 6:4   → A1 说：A0 复制 6 份，每份 +4
                                        ↑ 4 == cosize(A0) = 4 ✓
(A0,A1,A2)    A2 = 2:24               → A2 说：24 格的 block 复制 2 份，每份 +24
                                        ↑ 24 == cosize(前两层) = 24 ✓
```

| 层 | stride | 前面所有层的 cosize | 相等？ |
|---|---|---|---|
| A1 | 4 | 4 | ✓ |
| A2 | 24 | 24 | ✓ |

> **紧密情形下：A₍ᵢ₊₁₎ 的 stride = 前 i 层拼成的 cosize —— 这正是 coalesce 判据 `d_next == s_cur×d_cur`。**

**这个视角把三件事统一成一句话**：concatenation（层级）+ complement（补洞）+ coalesce（是否紧密）。

**三处但书**：

**① A0 自身不连续时，A1 要先补洞**

```
A0 = 4:2（像 {0,2,4,6}，cosize=7，有洞）
A1 = (2,3):(1,8)
     ├─ mode-0 = 2:1   stride=1，先补 A0 的洞（补成 0..7）
     └─ mode-1 = 3:8   stride=8，才是"复制 3 份"
```

A1 自己可能是多层的 —— **这正是 complement 的"先填洞、再重复"，与层级观是同一件事的两种说法。**

**② stride 可以 > cosize（故意留洞）**

| A1 | 覆盖 | 铺满？ |
|---|---|---|
| `6:4`（= cosize(A0)） | 24 格 | ✓ 紧密 |
| `6:8`（> cosize(A0)） | 24 格，span 到 43 | ✗ **留洞** |

留洞正是 raked / 稀疏排布的来源。

**③ 谁是内层，决定谁连续**

```
blocked = (A的mode..., B的mode...)  → A0 实心块
raked   = (B的mode..., A的mode...)  → A0 被耙开
```

### 遇到问题用哪个视角

| 你困惑什么 | 用哪个视角 |
|---|---|
| `idx2crd` / 为什么有界 | **混合进制** |
| 单 mode 为什么无界 | **混合进制**（只有一位） |
| coalesce 为什么 `d₁==s₀d₀` | **齿轮咬合** |
| 拼接为什么偏移相加 | **点积线性性** |
| stride=0 为什么是广播 | **零向量** |
| 为什么能"走出 tile" | **函数 / 地址生成器** |
| tiling / complement / divide / product | **图章印花** ⭐ |
| `(A0,A1,A2,...)` 层级、blocked/raked | **递归层级** ⭐ |
| 这些抽象图啥 | **地址生成器**（编译期零开销） |

> **一句话**：同一个 layout，数学上是函数，结构上像混合进制计数器，几何上是基向量，机械上是齿轮组，硬件上是地址生成器，用法上是图章，组织上是递归层级。视角越多，越不容易记混。

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

- `complement(B, ...)` 需要 tiler `B` 能表示为不重叠的重复；CuTe 会在可静态判断时拒绝非单射 tiler。
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
| 7 | **composition 只得到部分元素，divide 得到全部？** | **在整齐分块且 A 单射时，对**。差别在定义域：`composition(A,B)` 定义域 = `size(B)`（1 个 tile）；`divide(A,B)` 的定义域是 `size((B,B*))`。若 cotarget 恰好整除完整周期，它才等于 `size(A)` 并覆盖 A 的全部元素；否则可能向上取整、末尾超过目标。A 若广播或其他非单射，结果还会有重复 |
| 8 | **`A ∘ B` 一定只是 tile 0 吗？** | **是**，因为 **`B*(0) = 0` 恒成立** → `(B,B*)` 展开的前 `size(B)` 个坐标 = `B 的像 + 0` = tile 0 的索引集。更准的说法：`A ∘ B` 是**原型 tile**（tile 的形状），同时恰好是 tile 0。注意前提：`composition` 得成功 |
| 9 | **单 block 的 `A∘B` 能推广到所有 block 吗？** | **能，官方认可**。官方 API `local_tile` / `inner_partition` 就是干这个：`cta_a = tiled_a(_, blockIdx)`，每个 block 拿到的 **形状恒为 `(_4,_8)`**。官方称 `B*` 为 "layout of the tiles"、用 "repeats/repetition" 描述。实测 divide = `(A∘B, A∘B*)`，你的 layout 原封不动 |

---

## 10. 速查表

### 概念

| 术语 | 含义 |
|---|---|
| **complement(A, M)** | 求 A 的"补" R，使得 A 的完整副本无重叠地覆盖**至少** M；若周期整除 M 才恰好铺满 M |
| **cotarget M** | 目标范围，通常只用 `size(M)` |
| **cosize** | `max(像) + 1`，占多大地盘 |
| **像集 / codomain** | layout 能取到的 offset 值的集合 |
| **B\* / A\*** | `complement` 的结果，读作"**重复的方式**" |

### 计算步骤

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
```

> `B` = tile 内部，`B*` = tile 的布局（这堆 tile 怎么摆）。
> 且 **`layout<0>(zipped_divide(a,b)) == composition(a,b)`** —— tile 本身的布局就是 composition 的结果。

---

## 11. Composition vs Divide：覆盖范围的对比

> 【疑问 7】**"composition 是组合 A 和 B 的映射方式，只得到部分元素；divide 可以遍历、得到所有元素？"**

**这个理解完全正确。** 两者的差别就在**定义域大小**。

### 核心对比（实测）

```
A = (4,2,3):(2,1,8)     24 个元素
B = 4:2                 tile = 隔 2 取 4 个
B* = complement(4:2,24) = (2,3):(1,8)
```

| 运算 | 定义域（坐标空间） | 覆盖元素 | 实测 |
|---|---|---|---|
| **`composition(A, B)`** | `size(B) = 4` | **4 个 / 24 个** | `[0,4,1,5]` ← **只是 tile 0** |
| **`divide(A, B)`** | `size((B,B*)) = 4×6 = 24` | **24 个 / 24 个** | 全部 ✓ |

### 这是“整齐分块”例子的数字结果

```
B  的像集大小 = 4    （tile 内部的位置）
B* 的像集大小 = 6    （6 个 tile 的起点）
(B, B*)       = 4 × 6 = 24 = size(A)   ← 正好全覆盖
```

**单靠 B 只够得着 1 个 tile；补上 B\* 的起点才得到其余 tile。** 本例恰好有 `4×6=24`，所以刚好覆盖 A 的全部。

⚠️ 一般不能从公式推出 `size((B,B*)) == size(A)`：`complement` 为了保持完整块会向上取整。比如 `A=10:1, B=4:1` 时，`B*=3:4`，因此 `size((B,B*))=12 > size(A)=10`。

### 两处措辞打磨

**① "只有部分元素" → 更准的说法是"定义域小"（元素没丢，是够不着）**

```
composition(A, B) 的定义域 = B 的坐标空间（size = 4）
divide(A, B)      的定义域 = (B,B*) 的坐标空间（size = 24）
```

元素一直在那儿（一个没丢），只是 composition 这个**函数够不着**另外 20 个。

**② "组合两种映射" → 应记为"链式代入"**

`R(c) = A(B(c))` 是**函数复合**（先算 B 再喂给 A），不是"把两种方式组合起来"：

```
坐标 c  --B-->  一个下标 n  --A-->  offset
```

---

## 12. 🔑 `A ∘ B` 就是 tile 0（为什么"一定"）

> 【疑问 8】**"composition `A ∘ B` 一定只是 tile 0 是吧？"**

**是的** —— 根本原因是：

> **`B*(0) = 0` 恒成立**（stride 全正时，坐标全 0 → 偏移 0）

实测六个 complement 结果，`B*(0)` 全部为 0：

| `B*` | `6:4` | `4:1` | `(2,3):(1,8)` | `(3,2):(2,12)` | `1:0` | `3:2` |
|---|---|---|---|---|---|---|
| `B*(0)` | 0 | 0 | 0 | 0 | 0 | 0 |

**因为 `B*(0) = 0`，所以 `(B, B*)` 展开的前 `size(B)` 个坐标
恰好 = `B 的像 + 0` = `B 的像本身` = tile 0 的索引集。**

### 实测（1-D 例子）

```
A ∘ B (composition)  = [0, 4, 1, 5]
divide 的 tile 0     = [0, 4, 1, 5]     ← 完全相同 ✓

其余 tile 的索引集 = B 的像 + B*(j)：
  tile 0: 索引 {0,2,4,6}     值 [0,4,1,5]
  tile 1: 索引 {1,3,5,7}     值 [2,6,3,7]      ← B*(1)=1
  tile 2: 索引 {8,10,12,14}  值 [8,12,9,13]    ← B*(2)=8
  tile 3: 索引 {9,11,13,15}  值 [10,14,11,15]  ← B*(3)=9
  tile 4: 索引 {16,18,20,22} 值 [16,20,17,21]  ← B*(4)=16
  tile 5: 索引 {17,19,21,23} 值 [18,22,19,23]  ← B*(5)=17
```

### 官方佐证

> *"the first mode of each mode of the result is the sublayout `(3,(2,4)):(177,(13,2))` and is **precisely the result we would have received if we had applied `composition` instead of `logical_divide`**."*

配合恒等式 **`layout<0>(zipped_divide(a,b)) == composition(a,b)`** —— 实测 2-D 例子两者完全一致。

### 两个注意点

**① 更准确的说法：`A ∘ B` 是"原型 tile"（tile 的形状）**

它**同时恰好是 tile 0**（因 `B*(0)=0`）。其余 tile 在**索引**上是 `B 的像 + B*(j)` 的平移，但**值**上一般不等于 `tile0 + B*(j)`（因 A 非线性，`A(n+m) ≠ A(n)+A(m)`）。

**② "一定"有个前提：`composition` 得成功**

若 `A ∘ B` 因 divisibility condition 报错，则 `divide` 必然也失败（divide 内部就包含这一步）。

**③ 退化情形：`B* = 1:0`（B 已铺满 A）**

此时只有 **1 个 tile**，`A ∘ B` 既是 tile 0，也是**全部**。

### 附带：`tile 0` 总包含偏移 0

因 `B` 的像含 0、且 `A(0) = 0` 恒成立 → **tile 0 必含偏移 0**，是"最靠前"的那个 tile。

---

## 13. 🔑 单 block 设计 → 推广到所有 block（**官方认可**）

> 【疑问 9】**"我的一个 block 用了 `A ∘ B`，可以通过 divide 推广到其他 block 吗？"**
>
> **可以 —— 这正是 CuTe 最核心的惯用法，官方有专门 API：`local_tile` / `inner_partition`。**

### 官方原文（Tensor 文档 · Inner and outer partitioning）

```cpp
Tensor A = make_tensor(ptr, make_shape(8,24));  // (8,24)
auto tiler = Shape<_4,_8>{};                    // (_4,_8)

Tensor tiled_a = zipped_divide(A, tiler);       // ((_4,_8),(2,3))

// 给每个 threadgroup 一个 4x8 tile
Tensor cta_a = tiled_a(make_coord(_,_), make_coord(blockIdx.x, blockIdx.y));  // (_4,_8)
```

> *"We call this an **inner-partition** because it keeps the inner "tile" mode. This pattern of applying a tiler and then slicing out that tile by indexing into the remainder mode is common and has been wrapped into its own function `inner_partition(Tensor, Tiler, Coord)`. You'll often see **`local_tile(Tensor, Tiler, Coord)`** which is just another name for `inner_partition`. **The `local_tile` partitioner is very often applied at the threadgroup level to partition tensors into tiles across threadgroups.**"*

**注意那句注释 `// (_4,_8)`** —— 无论 `blockIdx.x/y` 是多少，取出来的 tile **形状恒为 `(_4,_8)`**。

> **这就是"所有 block 共享同一份 layout"的官方铁证**：用 `blockIdx` 索引第二个 mode，每个 block 拿到的都是同样结构的 tile。

### 官方原文：`B*` 就是"tile 的布局"

| 出处 | 原文 |
|---|---|
| Divide（§413） | *"If `B` is the "tiler", then **`B*` is the layout of the tiles**."* |
| Complement（§379） | *"The complement effectively **"repeats" the original layout**... can be viewed as the **"layout of the repetition"**."* |
| Product（§512） | *"If `A` is the "tile", then `A*` is the **layout of repetitions** that are available for `B`."* |
| Product（§525） | *"The layout `B` describes the **number and order of repetitions of `A`**."* |

**"repeats / repetition"（重复）这个措辞本身就意味着：同一份 layout 再来一次 —— 即所有 block 共享同一份内部 layout。**

### 实测：divide = 你的 layout + 一份 block 偏移表

```
A ∘ B   = (2,2):(4,1)              ← 你的 per-block layout（原封不动）
A ∘ B*  = (2,3):(2,8)              ← block 偏移表（B* 带来的）
divide  = ((2,2),(2,3)):((4,1),(2,8))    ← 两者拼接
```

这是**左分配律**的直接结果：

```
A ∘ (B, B*) = (A ∘ B, A ∘ B*)
```

**你设计的 `A ∘ B` 一点没改，divide 只是给它配了一张"去哪找其他 block"的表。**

### 所有 block 是"纯平移"吗 —— **是，但这是数学结构的推论**

实测（1-D 例子，6 个 tile）：

| block j | base = `(A∘B*)(j)` | 值 | `== tile0 + base`？ |
|---|---|---|---|
| 0 | 0 | `[0, 4, 1, 5]` | ✓ |
| 1 | 2 | `[2, 6, 3, 7]` | ✓ |
| 2 | 8 | `[8, 12, 9, 13]` | ✓ |
| 3 | 10 | `[10, 14, 11, 15]` | ✓ |
| 4 | 16 | `[16, 20, 17, 21]` | ✓ |
| 5 | 18 | `[18, 22, 19, 23]` | ✓ |

**全部 `True`。** 结构上的原因：

```
R(i, j) = (A∘B)(i) + (A∘B*)(j)
          └─ block 内 ─┘   └─ block 基址 ─┘
```

因为 `(A∘B, A∘B*)` 是 **concatenation**，两个 mode 的 stride 互相独立 → **偏移天然可加**。

> ⚠️ **诚实标注**：官方**没有**直接写出 `R(i,j) = (A∘B)(i) + (A∘B*)(j)` 这个公式。
> 这是 **concatenation 定义的直接数学推论**（layout 的偏移 = 各 mode 偏移之和），加上我们实测验证（全部 True）。
> 官方用的是 *"repeats" / "layout of the repetition"* 来描述同一事实。

### 完整的官方用法链（两条腿）

单纯的 `local_tile` 只解决"block 拿哪块"。**block 内部按线程分配**要靠另一条腿 —— composition：

> *"With **`composition`** the target data layout is transformed according to our TV-layout and then we can simply slice into the thread-mode of the result with our thread index."*（Tensor 文档 · Thread-Value partitioning）

| 步骤 | 用什么 | 解决什么 |
|---|---|---|
| ① 切 tile | `zipped_divide` / `local_tile` | block 拿哪块（**推广到所有 block**） |
| ② tile 内分线程 | `composition` + TV-layout | 每个线程拿哪些元素（**你的 `A ∘ B`**） |

对应两种 partition：

| 名称 | 写法 | 保留的 mode | 用途 |
|---|---|---|---|
| **inner-partition** | `local_tile(T, tiler, coord)` | **tile mode** | CTA 拿哪块（`(_4,_8)`） |
| **outer-partition** | `local_partition(T, layout, idx)` | **rest mode** | 线程分块内元素 |

### 三个前提

**① `A ∘ B` 本身得成功** —— 若 divisibility condition 报错，divide 必然也失败。

**② 先区分“tiler 的下标表”与“最终 result”** —— 成功构造 complement 时，`(B,B*)` 是无重叠的完整下标表（cotarget 整齐时是该范围上的双射）。但 `divide = A∘(B,B*)` 是否单射，还取决于 **A**：

```text
A = 10:0       # 广播：任何坐标都映射到 0
B = 4:1
B* = 3:4
divide(A,B) = 12:0   # 12 个坐标全是 offset 0，不是 permutation
```

因此，只有在 **A 单射**、tiler 可补、并且 cotarget 恰好整齐分块时，才可以把 divide 结果称作覆盖 A 的 permutation；否则更稳妥的术语是 reindex / gather。

**③ 真实 kernel 通常要切两层** —— CTA tile → thread tile，每级都是同一套路。

### 官方佐证：Product 与 Divide 结果一致

> *"Note that the result is **identical** to the result of the 1-D Logical Divide example."*

Product `((2,2),(2,3)):((4,1),(2,8))` == Divide 的结果 —— 说明"从 tile 拼出全图"和"把全图切成 tile"是互逆的同一结构。

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
