# 用循环理解 CuTe Composition（完整版 · 含官方术语）

> 核心思想一句话：
> **把 Layout A 看成一个数组（按自然序展开），composition 就是对这个数组做「隔 d 取 1，再只取前 s 个」。**
>
> 更新：2026-09-11 —— 修正配套 Python 模型的单 mode 标量坐标语义，并补充其适用边界。
> 文中所有数值结果均经 NVIDIA CuTe DSL 实跑验证（部分为该 DSL 报错信息）。
> 官方术语已对照 `media/docs/cpp/cute/02_layout_algebra.md` 校订。

---

## 0. 预备：Layout 就是一段循环

Layout `S:D` 描述「坐标 → offset」，更直观的看法是**它描述了一段嵌套循环的遍历方式**。

CuTe 自然序是 **column-major（mode-0 变化最快）**：

> **mode-0 = 最内层循环；mode 号越大，循环越靠外。**

`(4,5):(1,4)`：

```c
for (j = 0; j < 5; j++)        // mode-1, stride 4   ← 外层
  for (i = 0; i < 4; i++)      // mode-0, stride 1   ← 内层
    offset = 1*i + 4*j;
```

内层走一遍 `0,1,2,3`（**跨度** `4×1 = 4`），外层每步 `+4`。
外层步长 = 内层跨度 → 两层严丝合缝，可拍平：

```c
for (k = 0; k < 20; k++) offset = k;    // 20:1
```

### 三个基础函数（本文的"循环"就是它们）

```python
from math import prod

class L:                          # Layout：shape/stride 都是扁平 list
    def __init__(self, shape, stride):
        self.shape, self.stride = list(shape), list(stride)
    def size(self):  return prod(self.shape)
    def crd(self, n):             # idx2crd：整数 -> 各 mode 坐标
        c = []
        for s in self.shape:
            c.append(n % s); n //= s
        return c
    def __call__(self, n):        # 内积：坐标 × stride
        if len(self.shape) == 1:  # integral layout 的标量坐标不按 shape 回绕
            return n * self.stride[0]
        return sum(ci*di for ci, di in zip(self.crd(n), self.stride))
    def seq(self): return [self(n) for n in range(self.size())]
```

---

## 0.5 Coalesce：两层循环能否拍平

设内层 `s0:d0`、外层 `s1:d1`：

| 循环概念 | 公式 | 含义 |
|---|---|---|
| 内层步长 | `d0` | 内层每迭代一次跳多远 |
| 内层跨度 | `s0 * d0` | 内层跑完一整遍后下一格在哪 |
| 外层步长 | `d1` | 外层每迭代一次跳多远 |

**拍平条件：`d1 == s0 * d0`** —— 拍平后步长就是 **`d0`**（直接抄内层，不做任何计算）。

| 情况 | 循环含义 | 结果 |
|---|---|---|
| `d1 == s0*d0` | 外层恰好接在内层走完的位置 | ✅ 合并 |
| `d1 > s0*d0` | 外层跳太远，中间**有空洞** | ❌ 保持 |
| `d1 < s0*d0` | 外层落在内层跨度**之内**，offset 撞车 | ❌ 保持 |

**退化**：`s0 == 1` 或 `s1 == 1` 的层只跑一趟 → **整个删掉，它的 stride 也一起消失**（不累加给邻居）。

> **⚠️ 双射/紧凑 ≠ 可合并。** `(2,2,2):(2,1,4)` 展开是 `0,2,1,3,4,6,5,7`（8 个值不重不漏），但两对 mode 都不满足 `d_next == s_cur*d_cur`，**合不了** —— 因为合并会改变遍历顺序。

---

## 1. Composition：谁给骨架，谁给数值

`R = A ∘ B`，`R(c) = A(B(c))`：

```c
// B 提供"循环骨架"（shape 来自 B）
for (q = 0; q < 3; q++)        // B 的 mode-1，外层
  for (p = 0; p < 4; p++)      // B 的 mode-0，内层
    n = 3*p + 1*q;             // B 的输出：一个自然数
    offset = A(n);             // A 的作用：拿这个数去查表
```

- **B 决定循环长什么样**（几层、每层几次）
- **A 决定循环体里算出什么 offset**

难度只有一件事：**A 是个"查表"，但我们要一个"能直接算的循环"**。`/d` 和 `%s` 就是把查表翻译成显式循环的两步。

### 官方后置条件

```cpp
// @post compatible(@a layout_b, @a result)
// @post for all i, 0 <= i < size(@a layout_b), @a result(i) == @a layout_a(@a layout_b(i))
Layout composition(LayoutA const& layout_a, LayoutB const& layout_b);
```

> **B 定义 R 的定义域** —— 所以 R 必须能接受 B 的**每一个**坐标。

---

## 2. 左分配律：按 B 的 mode 拆开

> 官方原文：*"A o B = A o (B_0, B_1, ...) = (A o B_0, A o B_1, ...). When B is injective, composition is left-distributive with concatenation."*

B 的每层循环各算各的。问题归约为：**`A ∘ s:d` 怎么算？**
（`s` = 该层 trip count，`d` = 该层每步让 n 增加多少）

---

## 3. `/d`：隔 d 个取 1

> 官方原文（"Computing Composition" 第 1 步）：
> *"Determine a layout that produces every `d`th element of `A`. The shape of this intermediate layout can be calculated by progressively 'dividing out' the first `d` elements from the shape of `A` starting from the left."*

```python
def slash_d(lay, d):
    sh, st, rem = [], [], d
    for s_i, d_i in zip(lay.shape, lay.stride):
        f = min(rem, s_i)                 # 这个 mode 能吸收多少
        if s_i % f != 0: raise ValueError("/d 失败：除不尽")
        sh.append(s_i // f)               # shape ÷ f
        st.append(d_i * f)                # stride × f
        rem //= f
        if rem == 1:
            sh += lay.shape[len(sh):]; st += lay.stride[len(st):]; break
    return sh, st
```

**不变量：总跨度不变**（`s0 × d0` 前后相等）—— 只改采样密度，不改覆盖范围。

### 官方的 `/` 例子

```
(6,2)/2 => (3,2)      (6,2)/3 => (2,2)     (6,2)/6 => (1,2)    (6,2)/12 => (1,1)
(3,6,2,8)/3  => (1,6,2,8)
(3,6,2,8)/6  => (1,3,2,8)
(3,6,2,8)/9  => (1,2,2,8)
(3,6,2,8)/72 => (1,1,1,4)
```

### stride 怎么算 —— 官方称之为 **residues**

> *"the residues of the above operation are used to scale the strides of `A`... `(3,6,2,8):(w,x,y,z) / 72` produces `(72*w, 24*x, 4*y, 2*z)`"*

即：**shape ÷ 因子，stride × 同一个因子**。

### ⚠️ stride divisibility condition

> *"we can only divide shapes by certain values and get a sensible result. This is called the **stride divisibility condition** and is statically checked in CuTe when possible."*

---

## 4. `%s`：只保留前 s 个

> 官方原文（第 2 步）：
> *"Keep the first `s` elements of the newly strided `A` so that the result has a compatible shape with `B`. This can be computed by 'modding out' the first `s` elements from the shape of `A` starting from the left."*

```python
def percent_s(shape, s):
    out, rem = [], s
    for s_i in shape:
        take = min(s_i, rem)
        out.append(take)
        rem //= take            # 整数除法！
    return out
```

**两点**：
1. **stride 一个都不碰** —— 截断只是"少跑几圈"
2. **`rem` 是整数除法**，所以 s 未必切得开

### 官方的 `%` 例子

```
(6,2)%2 => (2,1)      (6,2)%3 => (3,1)     (6,2)%6 => (6,1)    (6,2)%12 => (6,2)
(3,6,2,8)%6  => (3,2,1,1)
(3,6,2,8)%9  => (3,3,1,1)
(1,2,2,8)%2  => (1,2,1,1)
(1,2,2,8)%16 => (1,2,2,4)
```

### ⚠️ shape divisibility condition

> *"this operation must satisfy a **shape divisibility condition** to yield a sensible result and is statically checked in CuTe when possible."*

**失败示例**（实测 `A ∘ 8:1` 报错）：

```
rem=8
mode0: min(6,8)=6   rem = 8//6 = 1   ← 整数除法抹掉余下的 2 个
mode1: min(2,1)=1
→ (6,1)  size = 6 ≠ 8  →  失败
```

**合法 s 的通用规则**（B = `(6,2,3)`，三层不合并，实测）：

```
合法 s = {1,2,3,4,5,6, 12, 24, 36}      7..11、18、30 全部报错
```

即 **s 必须落在某个完整前缀积的整数倍上**（倍数 ≤ 下一层 shape）。
18 死在 `rem=3` 除 `s1=2` 那一步（需要 1.5 页，非整数）。

> **每层都是一道关卡**：`rem > sᵢ` 时 `sᵢ` 必须整除 `rem`，否则静默丢料 → 最后 `size ≠ s` 才报错。

---

## 5. 🔑 Composition 的真实流程：先展平，再分支

> 官方原文（Computing Composition 开头）：
> *"We can also assume that **A is a flattened, coalesced layout**."*

**完整的算法流程是这样的：**

```
① 先把 A 做 flatten + coalesce
② 判断 A 是不是 integral（单 mode）
   ├─ 是 → 走闭式解  R = s:(b*d)                    ← 无约束，完事
   └─ 否 → 才进入 /d 和 %s 两步                       ← 两条 divisibility condition 上线
```

**关键：判据不是"A 字面写了几个 mode"，而是"A 能不能 coalesce 成一条"。**

> 官方原文（分支 ②）：
> *"When `A` is integral, `A = a:b`, the result is rather trivial: `R = A o B = a:b o s:d = `s:(b*d)`."*
> *"When `A` is multimodal, we need to be more careful."*

### 为什么先 coalesce 很关键

实测对照（同样"取 100 个"）：

| A | `coalesce(A)` | 走哪条分支 | `∘ 100:1` |
|---|---|---|---|
| `(4,4):(1,4)` | **`16:1`** ✅ 展平 | 闭式解 | **`100:1`** 成功 |
| `(2,3):(1,2)` | **`6:1`** ✅ 展平 | 闭式解 | **`50:1`** 成功 |
| `(6,2):(8,2)` | `(6,2)` ❌ 展不平 | `/d`+`%s` | **报错** |
| `(3,4):(4,1)` | `(3,4)` ❌ 展不平 | `/d`+`%s` | **报错** |

**`(4,4):(1,4)` 字面上是 2 个 mode，却也能取 100 个** —— 因为它被展平成了 `16:1`，退化成 integral，走闭式解。

### 闭式解里没有 `a`

**结果 `s:(b*d)` 中，`A` 的 shape `a` 完全消失。**

| 部分 | 来源 | 是否用 min |
|---|---|---|
| shape = `s` | 直接从 B 抄 | ❌ **不是 `min(a, s)`** |
| stride = `b*d` | A 的 stride × B 的 d | ❌ **不是 `shape ÷ d`** |

**所以单 mode 时 `/d` 和 `%s` 两步根本不执行，`min` 和 `rem` 贪心也用不上。**

> `min` / `rem` 那套贪心是**多 mode 专用工具**，只在 A 展不平的时候才登场。

### 实测极端对照

```
2:2 ∘ 100:1    =  100:2     ← A 只有 2 个元素，取 100 个，成功！（R(99)=198）
4:3 ∘ 1000:2   =  1000:6    ← 只有 4 个，取 1000 个
6:8 ∘ 5:4      =  5:32      ← 4 ∤ 6，但单 mode 无所谓
(6,2):(8,2) ∘ 5:4  =  报错  ← 展不平，4 ∤ 6
(6,2):(8,2) ∘ 8:1  =  报错
```

> **一句话：两条 divisibility condition 只卡「coalesce 不成单 mode 的 A」。**
> 展平后 `A(n) = b·n` 无取模 → 无界直线；展不平则 `idx2crd` 含取模 → 边界是硬的。

### 三种行为别混淆

| 类型 | 序列（n = 0..9） | stride | 语义 |
|---|---|---|---|
| **广播** `10:0` | `[0,0,0,0,0,0,0,0,0,0]` | `0` | 所有坐标同一偏移（**斜率 0**） |
| **单 mode 延伸** `2:2 ∘10:1` | `[0,2,4,6,8,10,12,14,16,18]` | `b*d` | 线性无界（**斜率 b·d**） |
| **多 mode 绕回** `(6,2)` 越界 | `[...42, 0, 8]`（n≥12 后重复） | — | 周期重复，**composition 会先报错拦下** |

**广播和单 mode 延伸都"无界"，但一个平的、一个斜的 —— 完全相反。**

### 🧠 "走出去"为什么不越界：Layout 是函数，不是容器

看到 `2:2 ∘ 100:1 = 100:2`（`R(99) = 198`）或 `(4,4):(1,4) ∘ 100:1 = 100:1`，
第一反应通常是"这不越界了吗？" —— **答案是：Layout 层面不存在越界。**

> **Layout 不持有内存，它只是一个「坐标 → 偏移」的映射规则（函数）。**

| | 持有内存？ | `f(100)` 越界吗 |
|---|---|---|
| 数组 `int arr[16]` | ✅ 有 | **越界**（UB） |
| 函数 `f(n) = n` | ❌ 无 | **不越界**，就是 100 |
| **Layout `16:1`** | ❌ 无 | **不越界**，就是 100 |

CuTe 只保证后置条件：

```cpp
// @post for all i: result(i) == layout_a(layout_b(i))
```

单 mode 下 `A(n) = n`，故 `A(99) = 99` —— **等式严格成立**。CuTe 检查的是这个，不是"有没有超出 `size(A)`"。

#### 从循环上看"走出去"

`(4,4):(1,4) ∘ 100:1` 的三步演化：

```c
// ① A 原本：两层循环，一个 4×4 tile
for (b = 0; b < 4; b++)       // 步长 4
  for (a = 0; a < 4; a++)     // 步长 1
    offset = 1*a + 4*b;       // → 0..15

// ② coalesce：拍平（d1=4 == s0*d0=4）→ 16:1
for (k = 0; k < 16; k++) offset = k;

// ③ ∘ 100:1：闭式解 s:(b*d) = 100:1
for (k = 0; k < 100; k++) offset = k;      // 一趟走出 tile
```

```
A 覆盖:  [0 ... 15]                          ← 一个 tile
R 覆盖:  [0 ... 15][16 ... 31][32 ... 99]    ← 顺着 stride 1 进入后续 tile
                   ↑
            下一步正好落在下一个 tile 的起点
```

**拍平消掉了取模** → 函数变成无界直线 `A(n)=n` → 循环自然延伸。

#### 为什么这是必需的设计

A 通常描述**"一个 tile 内的布局规律"，而实际内存远大于 tile**。

```
128×128 矩阵，用 4×4 tile 铺：
  tile #0: [0...15]   tile #1: [16...31]   tile #2: [32...47] ...
```

若 Layout 卡死在 `0..15`，就**没法用同一个 A 描述所有 tile**，每铺一个都要重新造 Layout。
**"走出去"正是让 tile 的规律延拓到整个矩阵** —— 这是 tiled repeat、跨 tile 连续访问的基础。

#### 谁来保证安全

> **CuTe 做符号计算，不检查内存边界；安全由调用者保证。**

```c
int* ptr = tensor.data();                    // 大内存（16384 个元素）
Layout A = (4,4):(1,4);                      // tile 内部规律
Layout R = composition(A, 100:1);            // 走出去 → 100:1
offset = R(k);        // 可能 0..99
value  = ptr[offset]; // 只有 offset < 16384 才安全 ← 调用者责任
```

**越的是 tile 的界，不是内存的界。**

#### 那多 mode 为什么报错

不是"内存保护"，而是**算法算不下去**：多 mode 含取模，CuTe 的 `/d`、`%s` 依赖 shape 逐级分解，边界变成算法内部的硬约束（divisibility condition 过不去），没法用合法层级 shape 表达"跨过后继续"。

> **单 mode 是"算法恰好能算所以算了"，多 mode 是"算法算不了所以报错" —— 两者都不是在做越界检查。**

### 官方完整例子

```
(3,6,2,8):(w,x,y,z) ∘ 16:9  =  (1,2,2,4):(9*w, 3*x, y, z)
```

---

## 6. 拼接：重建 B 的嵌套结构

B 有几层，R 就有几层，**每个分支按 B 的 mode 顺序排回去**。

> **`compatible(B, R)` 判的是逐 mode 容量相等，不是字面 shape 相同。**

| | 字面 shape | 逐 mode 容量 |
|---|---|---|
| B | `(4, 3)` | 4, 3 |
| R | `((2,2), 3)` | `2×2=4`, `3` |

字面不同但容量相等 → 兼容 ✓

**⚠️ 分支是多 mode 时要带括号**（那是"血缘标记"，记录它来自 B 的哪个 mode）。

**⚠️ 只能逐 mode 内部化简（by-mode coalesce），不能拍平后全局 coalesce。**

实测：`(2,1,3,1,1,2):(8,2,16,2,48,2)` 拍平后全局 coalesce 得 `(6,2):(8,2)` —— **数值与正确答案 `(2,3,2):(8,16,2)` 完全相同，但 mode 数从 3 塌成 2**，`compatible(B, R)` 直接崩。

---

## 7. 完整走一遍官方例子

`A = (6,2):(8,2)`，`B = (4,3):(3,1)`

**分支 1 `A ∘ 4:3`**
```
/3 → (6/3, 2):(8*3, 2) = (2,2):(24,2)     总跨度 6×8 = 2×24 = 48 ✓
%4 → size = 4 = s，恒等
→ (2,2):(24,2)
```
取到的 4 个点是 `[0, 24, 2, 26]` —— 前两个在 A 的 mode-0，后两个跳到 mode-1，**采样跨越了 A 自己的 mode 边界** → 一个循环装不下 → 嵌套 `(2,2)`。

**分支 2 `A ∘ 3:1`**
```
/1 → (6,2):(8,2) 不变
%3 → rem=3: mode0=min(6,3)=3, rem=1 → mode1=min(2,1)=1 → (3,1)
coalesce → 3:8
```

**拼接 → `R = ((2,2),3):((24,2),8)`**

```c
for (q = 0; q < 3; q++)            // 外层，步长 8
  for (b = 0; b < 2; b++)          // 步长 2
    for (a = 0; a < 2; a++)        // 步长 24
      offset = 24*a + 2*b + 8*q;
```

12 个坐标逐点验证 `R(c) == A(B(c))`，**零误差**。

---

## 8. by-mode Tiler（与 concat 不同！）

> 官方原文：
> *"a `Tiler` is one of: (1) A `Layout`. (2) A tuple of `Tiler`s. (3) A `Shape`... With (2) and (3), the composition is performed on each pair of corresponding modes of `A` and `B`."*

| | 写法 | 规则 |
|---|---|---|
| **concat** | `(s₀:d₀, s₁:d₁)` | A **整体** ∘ 每个 mode |
| **by-mode** | `<t₀, t₁>` | A 的 **mode-i** ∘ tiler 的 **mode-i**，各层独立 |

### 实测对照（同一组数字，两种结果）

```
A = (6,2):(8,2)

by-mode  A ∘ <2:3, 2:1>   =  (2,2):(24,2)    ← mode-1 stride = 2（A 原封不动）
concat   A ∘ (2,2):(3,1)  =  (2,2):(24,8)    ← mode-1 stride = 8（来自 A 的 mode-0）
```

**一眼区分**：by-mode 的 mode-1 stride 就是 A 原本的 mode-1 stride。

推导（by-mode）：
```
mode-0:  6:8 ∘ 2:3  →  /3: 2:24 → %2: 2:24  →  2:24
mode-1:  2:2 ∘ 2:1  →  /1: 2:2  → %2: 2:2   →  2:2
→ (2,2):(24,2)
```

---

## 9. 广播：stride = 0

三种场景，算法各不相同：

| 场景 | 走 `/d`/`%s` 吗 | 结果 |
|---|---|---|
| **B 的 `d = 0`** | ❌ **短路**（除零非法） | **`s:0`**，与 A 无关 |
| **A 自带 stride-0 mode** | ✅ 照常 | `0×d = 0`，广播保留 |
| **coalesce 两个 stride-0** | — | `0 == 0` → **可合并** |
| **coalesce 广播 + 正常** | — | ❌ 不能合并 |

### 为什么 `d=0` 结果是 `s:0`

`R(k) = A(k*0) = A(0)`，而 **`A(0)` 恒等于 0**（索引 0 展开的坐标全为 0）。
所以 s 个坐标全映射到偏移 0 → stride = 0。

```c
for (k = 0; k < s; k++) { n = k * 0;  offset = A(n); }   // n 永远停在 0
```

### 实测

```
(6,2):(8,2) ∘ 3:0  =  (3):(0)     序列 [0,0,0]
(4,4):(1,4) ∘ 5:0  =  (5):(0)     ← 换 A 结果一样
(3,4):(0,1) ∘ 2:1  =  2:0          ← A 自带广播，/d 保留
coalesce((2,3):(0,0)) = 6:0        ← 两个广播可合并
coalesce((3,4):(0,1)) = (3,4):(0,1) 不变
```

---

## 10. 官方术语对照表

| 我们的说法 | 官方术语 |
|---|---|
| `/d`（隔 d 取 1）的整除约束 | **stride divisibility condition** |
| `%s`（取前 s 个）的整除约束 | **shape divisibility condition** |
| stride × 因子 | **residues ... scale the strides** |
| 拆 B 的 mode | **left-distributive with concatenation** |
| 单 mode A | **integral layout**（`a:b`，闭式解 `s:(b*d)`） |
| 多 mode A | **multimodal layout** |
| 先展平再判断 | **"assume A is a flattened, coalesced layout"** |
| 拼接保结构 | **`compatible(B, R)`** |
| 各层独立复合 | **by-mode**（Tiler = tuple of Tilers） |

> 文档：`https://github.com/NVIDIA/cutlass/blob/main/media/docs/cpp/cute/02_layout_algebra.md`
> 章节：Composition → Computing Composition

---

## 11. 常见错误清单

| # | 坑 | 正确做法 |
|---|---|---|
| 1 | 合并后 stride 算成 `d1` 或乘出来的数 | **抄 `d0`**（内层），shape 才相乘 |
| 2 | 忘记删 shape=1 的 mode | 收尾**从左到右扫一遍**，看到 1 就删（stride 一起丢） |
| 3 | `%s` 后忘了自检 | **size 必须 == s**，不等就重算 |
| 4 | 拍平后全局 coalesce | 只能**逐 mode 内部**化简，否则跨分支合并毁结构 |
| 5 | 拼接少/多 mode | R 的 mode 数必须 == B 的 mode 数 |
| 6 | s/d 串位 | **按位置配对**，先写成 `(4:1, 2:2)` 摆出来再算 |
| 7 | 把"紧凑/双射"当可合并 | 唯一标准是 `d_next == s_cur*d_cur` |
| 8 | 以为整除约束处处适用 | **只卡 coalesce 不成单 mode 的 A** |
| 9 | by-mode 当 concat | 尖括号 `<>` = 各层独立 |
| 10 | `d=0` 还想走 `/d` | 短路返回 `s:0` |

---

## 12. 一句话总结

> **把 A 看成一个数组：**
> `/d` 是**按步长 d 采样**（shape ÷ d，stride × d，总跨度不变，受 stride divisibility condition 约束）；
> `%s` 是**取前 s 个**（截断 shape，stride 不动，受 shape divisibility condition 约束）；
> 最后**按 B 的结构拼回去**（保 mode 数与括号）。
>
> 若 A 能 coalesce 成单 mode，直接套闭式解 **`s:(b*d)`**（`min`/`rem` 都不用），两条约束都不适用。

**Composition 的本质**（编译器视角）：
**loop fusion + strength reduction** —— 两级合成一级，把 div/mod 降级成乘加，且全部在编译期完成（`constexpr`），运行时零开销。

---

## 附：可运行脚本

| 文件 | 内容 |
|---|---|
| `sim.py` | 四个 composition 例子的逐步演示（`/d` → `%s` → coalesce → 验证） |
| `sim2.py` | 失败案例 `A∘8:1` 的贪心过程 + 循环融合前后逐点对比 |
| `sim3.py` | "隔 d 取 1" vs "隔 d 取 m" 的对照 |
| `tests/test_note_invariants.py` | 非整除 cotarget、非单射与单 mode 外延的边界测试 |

```bash
python3 sim.py
python3 sim2.py
python3 sim3.py
python3 -m unittest -v tests/test_note_invariants.py
```

> `sim.py` 的多 mode 轻量模型只用于合法定义域内的手推例子；真正的 CuTe composition 仍应以 DSL / C++ 测试为准。
