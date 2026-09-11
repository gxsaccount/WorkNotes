# CuTe Division 与 Product（Tiling 的两半）

> 配套文档：`用循环理解Composition.md`、`Complement补集概念.md`
> 本文所有数值均经 NVIDIA CuTe DSL 实跑验证。
> 官方原文出处：`media/docs/cpp/cute/02_layout_algebra.md` → **Logical Divide / Product** 两节

---

## 0. 三件套：Division 与 Product 都不是新运算

官方在两处各写了一句（几乎一字不差）：

> *"Note that this is defined only in terms of **concatenation, composition, and complement**."*

| 运算 | 公式 | 三件套怎么用 |
|---|---|---|
| **Divide** | `A ∘ (B, B*)` | complement 求 `B*` → concat 成 `(B,B*)` → composition |
| **Product** | `(A, A*∘B)` | complement 求 `A*` → composition 算 `A*∘B` → concat |

**没有新概念** —— 只要 complement 通了，这两节只是"怎么把三件套组装起来"。

---

## 1. 为什么需要 Division

Composition 只回答"**从 A 里挑出某些元素**"，但**不告诉你被跳过的部分在哪**。

Tiling 要两样都得有：

```
A = 24 个元素，B = 一个 tile（4 个）

需要的：
  · tile 内部长什么样   →  A ∘ B        （composition 已有）
  · 这堆 tile 怎么摆    →  ???           （缺，靠 B* 补）
  · 取第 3 个 tile      →  offset = ?     （缺）
```

**Division = 把这两半拼成一个结构** —— 既能遍历 tile 内，也能遍历 tile 间。

---

## 2. Division：公式与三步

### 官方公式与实现

$$A \oslash B := A \circ (B, B^*)$$

```cpp
auto logical_divide(Layout const& layout, Layout const& tiler) {
  return composition(layout, make_layout(tiler, complement(tiler, size(layout))));
}
```

### 三步（1-D 官方例子，实测）

```
A = (4,2,3):(2,1,8)      24 个元素（数据源）
B = 4:2                  tile（切法：隔 2 取 4 个）
```

**① 算 `B*`**
```
complement(4:2, 24) = (2,3):(1,8)      ← 实测 ✓
（填洞 2:1，块大小 8；重复 3:8）
```

**② 拼接 `(B, B*)`**
```
(B, B*) = (4,(2,3)):(2,(1,8))
           mode-0 = 4:2      → tile 内（4 个元素）
           mode-1 = (2,3):(1,8) → tile 间（6 个 tile）
```

**③ composition**
```
logical_divide = ((2,2),(2,3)):((4,1),(2,8))    ← 实测 ✓
```

### 结果怎么读

```
R = ( (2,2) , (2,3) ) : ( (4,1) , (2,8) )
     └─tile内─┘ └─tile间─┘
      size = 4   size = 6
```

| mode | 含义 | size | 校验 |
|---|---|---|---|
| **mode-0 = `(2,2)`** | **tile 内部**的 4 个元素 | 4 | `= size(B)` ✓ |
| **mode-1 = `(2,3)`** | **6 个 tile** 的遍历方式 | 6 | `= 24/4` ✓ |

> 官方原文：*"the first mode of the result is **the tile of data** and the second mode **iterates over each tile**."*

⚠️ **mode-0 是 `(2,2)` 而不是 `4`** —— A 的存储顺序让采样跨了 A 的 mode 边界（composition 里见过的现象）。

### 两套循环（实测展开）

```c
for (j = 0; j < 6; j++)        // mode-1：tile 间
  for (i = 0; i < 4; i++)      // mode-0：tile 内
    offset = R(i, j);
```

```
tile 0: [0,  4,  1,  5]
tile 1: [2,  6,  3,  7]
tile 2: [8,  12, 9,  13]
tile 3: [10, 14, 11, 15]
tile 4: [16, 20, 17, 21]
tile 5: [18, 22, 19, 23]
```

**横向 = tile 内，纵向 = 跳到下一个 tile。**

> **本质是重排**：R 与 A 覆盖同一批元素（实测集合相同，都是 `0..23`），只是换了遍历顺序。
> 官方：*"can be viewed as a kind of `gather` operation or as simply a **permutation**."*

---

## 3. 🆚 Composition vs Divide：覆盖范围

> 【疑问 7】**"composition 只得到部分元素，divide 得到全部？"**

| 运算 | 定义域 | 覆盖 | 实测 |
|---|---|---|---|
| **`composition(A,B)`** | `size(B) = 4` | **4 / 24** | `[0,4,1,5]` ← **只是 tile 0** |
| **`divide(A,B)`** | `size((B,B*)) = 4×6 = 24` | **24 / 24** | 全部 ✓ |

**元素没丢，是 composition 这个函数"够不着"另外 20 个。**

```
B  像集大小 = 4   （tile 内部位置）
B* 像集大小 = 6   （6 个 tile 起点）
(B,B*)      = 4×6 = 24 = size(A)   ← 全覆盖
```

### 🔑 `A ∘ B` 一定只是 tile 0

> 【疑问 8】**"`A ∘ B` 一定只是 tile 0 是吧？"**

**是** —— 根本原因是 **`B*(0) = 0` 恒成立**（stride 全正，坐标全 0 → 偏移 0）。

实测六个 complement 结果 `B*(0)` 全为 0：`6:4`→0、`4:1`→0、`(2,3):(1,8)`→0、`(3,2):(2,12)`→0、`1:0`→0、`3:2`→0。

**因为 `B*(0)=0`，`(B,B*)` 展开的前 `size(B)` 个坐标 = `B的像 + 0` = tile 0 的索引集。**

官方佐证：
> *"...is **precisely the result we would have received if we had applied `composition` instead of `logical_divide`**."*

配合恒等式 **`layout<0>(zipped_divide(a,b)) == composition(a,b)`**（实测吻合）。

**更准的说法**：`A ∘ B` 是**原型 tile**（tile 的形状），同时恰好是 tile 0。其余 tile 在**索引**上是 `B的像 + B*(j)` 的平移。

⚠️ 前提：`composition` 得成功（若 divisibility condition 报错，divide 必然也失败）。

---

## 4. 四种 divide 变体

`logical_divide` 结果是嵌套的，取第 k 个 tile 不方便。四种重排：

```
Layout Shape : (M, N, L, ...)
Tiler Shape  : <TileM, TileN>

logical_divide : ((TileM,RestM), (TileN,RestN), L, ...)
zipped_divide  : ((TileM,TileN), (RestM,RestN,L,...))    ← 最常用
tiled_divide   : ((TileM,TileN), RestM, RestN, L, ...)
flat_divide    : (TileM, TileN, RestM, RestN, L, ...)
```

### 2-D 实测（by-mode tiler）

```
A = (9,(4,8)):(59,(13,1))     size = 288
tiler = <3:3, (2,4):(1,8)>
```

```
logical_divide : ((3,3),((2,4),(2,2))):((177,59),((13,2),(26,1)))
zipped_divide  : ((3,(2,4)),(3,(2,2))):((177,(13,2)),(59,(26,1)))
composition    : ((3),(2,4)):((177),(13,2))
```

`zipped_divide` 的 **mode-0 = `(3,(2,4))` 就是 tile 本身**（TileM × TileN = 3×8）。

### zipped_divide 为什么好用

```cpp
auto zd = zipped_divide(layout_a, tiler);   // ((3,8),(3,4))

zd(0, 3)                 // 第 3 个 tile 的 offset
zd(0, 7)                 // 第 7 个 tile
zd(0, make_coord(1,2))   // (1,2) 号 tile
layout<0>(zd)            // tile 本身的布局
```

**tile 索引在 mode-1，tile 内索引在 mode-0 —— 一层一用途。**

⚠️ 代价：**不保留 mode 语义**。

| | mode-0 含义 | mode-1 含义 |
|---|---|---|
| `logical_divide` | M-mode 还是 M-mode（**保留**） | N-mode 还是 N-mode |
| `zipped_divide` | **tile 模式**（跨 M/N 重组） | **rest 模式** |

> 官方：*"We note that `logical_divide` preserves the **semantics** of the modes... This is not the case with `zipped_divide`."*

---

## 5. Product：从 tile 拼出全图

### 公式（与 Divide 对称）

$$A \otimes B := (A,\; A^* \circ B)$$

```cpp
auto logical_product(Layout const& layout, Layout const& tiler) {
  return make_layout(layout,
                     composition(complement(layout, size(layout)*cosize(tiler)), tiler));
}
```

| | A 的身份 | B 的身份 | cotarget |
|---|---|---|---|
| **Divide** | **整块数据（数据源）** | tile 的切法 | `size(A)` |
| **Product** | **一个 tile（模板）** | 重复的次数/顺序 | **`size(A) × cosize(B)`** |

### 三步（1-D 官方例子，实测）

```
A = (2,2):(4,1)     tile（4 个元素）
B = 6:1             重复 6 次
```

**① complement**（注意 cotarget 不同！）
```
complement((2,2):(4,1), size(A)×cosize(B)) = complement((2,2):(4,1), 4×6=24) = (2,3):(2,8)
```

**② composition**：`A* ∘ B = (2,3):(2,8) ∘ 6:1 = (2,3):(2,8)`（B 是恒等，没变）

**③ concatenation**：`(A, A*∘B) = ((2,2),(2,3)):((4,1),(2,8))`

### 🔑 mode-0 就是 A 原样照抄

```cpp
return make_layout(layout, ...);   // ← 第一个参数就是 A，不经过任何变换
```

> 官方原文：*"where the first mode is the layout `A`... This is clearly **just a copy of `A`**."*

实测坐实：输入 `A = (2,2):(4,1)` → product 的 mode-0 = **`(2,2):(4,1)`**（一模一样）。

⚠️ **不是 `A∘B = A`** —— 实测 `A∘B = ((2,3)):((4,1))`，跟 A 完全不同。Product 公式里**压根没有 `A∘B` 这个运算**。

**"A 已站好位置"的含义**：结果的第一个坑已被 A 占住，不用算；需要算的只有 mode-1 的 `A*∘B`。

### 两种思维：查询式 vs 构造式

| | Divide | Product |
|---|---|---|
| 思维 | **查询式**（从大到小） | **构造式**（从小到大） |
| 类比 | 从已有大照片裁小图 | 拿图章盖满一面墙 |
| tile 形状 | **身不由己**（由 A 的存储结构决定） | **你说了算**（直接抄 A） |
| 需要数据源 | ✅ 必须有真数据 A | ❌ 凭空造 layout |

---

## 6. 🔑 Product 的 B：候选池 + 选择器

> **`A*` = 所有可用的重复槽位（候选池）**
> **`B` = 选哪些槽位、按什么顺序（选择器）**

固定 tile `A = 4:1`，只变 B（实测）：

| B | `cosize(B)` | cotarget | `A*` | `A*∘B` = mode-1 | product |
|---|---|---|---|---|---|
| `6:1` | 6 | 4×6=**24** | `6:4` | `(6):(4)` | `((4),(6)):((1),(4))` |
| `3:1` | 3 | 4×3=**12** | `3:4` | `(3):(4)` | `((4),(3)):((1),(4))` |
| `2:1` | 2 | 4×2=**8** | `2:4` | `(2):(4)` | `((4),(2)):((1),(4))` |
| `6:2` | **11** | 4×11=**44** | `11:4` | `(6):(8)` | `((4),(6)):((1),(8))` |

### B 的三个维度

| B 的什么 | 管什么 | 实测 |
|---|---|---|
| **size(B)** | **复制几个** | `6:1`→6 份，`3:1`→3 份，`2:1`→2 份 |
| **stride(B)** | **在槽位里怎么挑（跳过）** | `6:2` 隔槽挑 → 间距 4→**8** |
| **shape(B)** | **排布的维度结构** | `(2,3):(1,8)` → **2×3 二维网格** |

`B=6:2` 详解（最有意思）：
```
cosize(B)=11 → cotarget=44
A* = 11:4   槽位 = {0,4,8,...,40}    （11 个候选）
B  = 6:2    像 = {0,2,4,6,8,10}      （挑第 0,2,4,... 号槽）
A*∘B = 6:8  → {0,8,16,24,32,40}      （间距翻倍）
```

> 官方：*"The layout `B` describes the **number and order of repetitions of `A`**."*
> （number = `size(B)`，order = shape 维度 + stride 顺序）

⚠️ **cotarget 依赖 `cosize(B)` 而非 `size(B)`** —— `6:2` 的 cosize 是 11（覆盖到 offset 10）。

---

## 7. blocked vs raked：mode 重组顺序

2-D 的 `logical_product` 官方说 **"not the recommended approach"**（tiler 难构造），改用这两个：

```cpp
A = (2,5):(5,1)     // 2×5 row-major tile
B = (3,4):(1,3)     // 3×4 column-major 排布

blocked_product = ((2,3),(5,4)):((5,10),(1,30))     ← A 的 mode 在前
raked_product   = ((3,2),(4,5)):((10,5),(30,1))     ← B 的 mode 在前
```

| | mode 顺序 | 视觉效果 |
|---|---|---|
| **blocked** | A 在前 | tile 是**实心块**（连续内存归同一 tile） |
| **raked** | B 在前 | tile 被**交错/耙开**（连续内存跨 tile） |

一维类比（3 个 tile，每个 2 元素）：
```
blocked: [t0e0, t0e1, t1e0, t1e1, t2e0, t2e1]
raked:   [t0e0, t1e0, t2e0, t0e1, t1e1, t2e1]
```

> 官方：*"the "tile" `A` now being **interleaved or "raked"**"*
> 判据：`rank(result)==2` 且 `compatible(A, layout<0>(result))`、`compatible(B, layout<1>(result))`

---

## 8. ⚠️ 互逆辨析：严格说**不是**数学互逆

> 【疑问】**"`A∘(B,B*)` 和 `(A, A*∘B)` 怎么理解它们是互逆的？"**

**官方只说 "identical"，没说 "inverse"** —— 这是两回事。

真正的关系是：**Divide 的输出 = Product 的输入**

```
Divide  输出 = ( tile内部 , tile间 )  = ((2,2),(2,3)):((4,1),(2,8))
                ↓            ↓
Product 输入  = (    A     ,   B   )  = (2,2):(4,1) , 6:1
Product 输出  = ((2,2),(2,3)):((4,1),(2,8))     ← 同一个结构
```

### 为什么不是严格互逆

**① 输入对象根本不同**

| | 第一个输入 | 第二个输入 |
|---|---|---|
| Divide | 全图（24 元素） | 切法 `4:2` |
| Product | 单个 tile（4 元素） | 重复方式 `6:1` |

**② 方向不对称** —— Divide 的 B（`4:2`，相对全图定义）≠ Product 的 B（`6:1`，相对 tile 定义）。

**③ 自由度不同**
- **Divide 不能选 tile 形状** —— 由全图存储结构决定（mode-0 是 `(2,2)` 不是 `4`）
- **Product 可以选任意 tile** —— 你想让 tile 是什么就是什么

> 官方：*"Of course, we can change the number and order of the tiles in the product by changing `B`."*

### 类比

```
Divide  = 把一本书拆成（目录, 各章节）
Product = 拿（目录, 各章节）装成一本书
```
但任意(目录,章节)拼起来不一定是"原来那本" —— 章节可换、顺序可变。

> **一句话**：它们共享同一个中间表示 `(tile, 重复方式)`，在这个中间表示上"殊途同归" ——
> 更像**"同一结构的两种构造法"**，而非严格互逆。

---

## 9. 🔑 单 block 设计 → 推广到所有 block（官方认可）

> 【疑问 9】**"我的一个 block 用了 `A ∘ B`，可以通过 divide 推广到其他 block 吗？"**
> **可以 —— 官方 API `local_tile` / `inner_partition` 就是干这个。**

### 官方原文（Tensor 文档 · Inner and outer partitioning）

```cpp
Tensor A = make_tensor(ptr, make_shape(8,24));  // (8,24)
auto tiler = Shape<_4,_8>{};                    // (_4,_8)

Tensor tiled_a = zipped_divide(A, tiler);       // ((_4,_8),(2,3))

// 给每个 threadgroup 一个 4x8 tile
Tensor cta_a = tiled_a(make_coord(_,_), make_coord(blockIdx.x, blockIdx.y));  // (_4,_8)
```

> *"We call this an **inner-partition** because it keeps the inner "tile" mode... **`local_tile(Tensor, Tiler, Coord)`**... **The `local_tile` partitioner is very often applied at the threadgroup level to partition tensors into tiles across threadgroups.**"*

**注意 `// (_4,_8)`** —— 无论 `blockIdx` 是多少，取出来的 tile **形状恒为 `(_4,_8)`**。这是"所有 block 共享同一份 layout"的官方铁证。

### 官方四处 "repeats / repetition" 原文

| 出处 | 原文 |
|---|---|
| Divide | *"If `B` is the "tiler", then **`B*` is the layout of the tiles**."* |
| Complement | *"The complement effectively **"repeats" the original layout**... **"layout of the repetition"**."* |
| Product | *"If `A` is the "tile", then `A*` is the **layout of repetitions**."* |
| Product | *"The layout `B` describes the **number and order of repetitions of `A`**."*

### 实测：divide = 你的 layout + 一份 block 偏移表

```
A ∘ B   = (2,2):(4,1)              ← 你的 per-block layout（原封不动）
A ∘ B*  = (2,3):(2,8)              ← block 偏移表
divide  = ((2,2),(2,3)):((4,1),(2,8))    ← 两者拼接
```

**左分配律的直接结果**：`A ∘ (B, B*) = (A∘B, A∘B*)`

### 所有 block 是纯平移（实测 6/6）

| block j | base = `(A∘B*)(j)` | 值 | `== tile0 + base`？ |
|---|---|---|---|
| 0 | 0 | `[0, 4, 1, 5]` | ✓ |
| 1 | 2 | `[2, 6, 3, 7]` | ✓ |
| 2 | 8 | `[8, 12, 9, 13]` | ✓ |
| 3 | 10 | `[10, 14, 11, 15]` | ✓ |
| 4 | 16 | `[16, 20, 17, 21]` | ✓ |
| 5 | 18 | `[18, 22, 19, 23]` | ✓ |

结构原因：`R(i,j) = (A∘B)(i) + (A∘B*)(j)` —— concatenation 两 mode 独立 → 偏移可加。

> ⚠️ **诚实标注**：官方**没有**直接写出 `R(i,j) = (A∘B)(i) + (A∘B*)(j)` 这个公式。
> 这是 **concatenation 定义的数学推论**（偏移 = 各 mode 之和）+ 实测验证（6/6 True）。
> 官方用 *"repeats" / "layout of the repetition"* 描述同一事实。

### 完整的官方用法链（两条腿）

| 步骤 | 用什么 | 解决什么 |
|---|---|---|
| ① 切 tile | `zipped_divide` / `local_tile` | block 拿哪块（**推广到所有 block**） |
| ② tile 内分线程 | `composition` + TV-layout | 每个线程拿哪些（**你的 `A ∘ B`**） |

> *"With **`composition`** the target data layout is transformed according to our TV-layout and then we can simply slice into the thread-mode..."*

| 名称 | 写法 | 保留的 mode | 用途 |
|---|---|---|---|
| **inner-partition** | `local_tile(T, tiler, coord)` | **tile mode** | CTA 拿哪块 |
| **outer-partition** | `local_partition(T, layout, idx)` | **rest mode** | 线程分块内元素 |

---

## 10. 速查表

### 公式

| 运算 | 公式 | cotarget |
|---|---|---|
| **Composition** | `A ∘ B`，`R(c) = A(B(c))` | — |
| **Divide** | `A ∘ (B, B*)` | `size(A)` |
| **Product** | `(A, A*∘B)` | `size(A) × cosize(B)` |

### Divide vs Product 对照

| | Divide | Product |
|---|---|---|
| 公式 | `A ∘ (B, B*)` | `(A, A*∘B)` |
| A 的身份 | 数据源（被查的表） | 模板（直接抄进 mode-0） |
| B 的身份 | tile 的切法 | 重复的次数与顺序 |
| 谁在外 | 组合在外、拼接在内 | 拼接在外、组合在内 |
| mode-0 | `A∘B`（**算出来**） | `A`（**直接抄**） |
| mode-1 | — | `A*∘B`（算出来） |
| tile 形状 | 由 A 的存储决定（身不由己） | 你说了算 |
| 思维 | 查询式 | 构造式 |
| 官方 API | `local_tile` / `inner_partition` | `blocked_product` / `raked_product` |

### 官方恒等式

| 恒等式 | 含义 |
|---|---|
| `layout<0>(zipped_divide(a,b)) == composition(a,b)` | tile 的布局 = composition 的结果 |
| `A ∘ (B,B*) = (A∘B, A∘B*)` | 左分配律 |
| product 结果 == divide 结果（1-D 例） | 同一 tiling 结构的两种构造法 |

### 三种运算串起来

```
complement(B, size(A))  →  B*  =  tile 的布局（怎么摆）
composition(A, B)       →  tile 内部的布局
logical_divide(A, B)    →  (tile 内部, tile 间)  ← 两者合一
local_tile(T, tiler, blockIdx)  →  取第 blockIdx 个 tile（形状恒定）
```
