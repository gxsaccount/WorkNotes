# 03 坐标与兼容性

> 官方对应：`01_layout.md` 的 Layout Concepts
>
> 更新：2026-09-11

这一节是本章最重要的部分。很多 Layout 误解都来自混淆了：

```text
输入坐标
自然坐标
一维自然序号
最终 index
```

---

## 1. 一个 Layout 可以接受多种坐标

考虑 Shape：

```text
(3,(2,3))
```

它可以从三种视角被访问。

### 1.1 一维坐标

```text
i, 0 <= i < 18
```

### 1.2 rank-D 坐标

`rank-D` 是 **rank-dimensional coordinate（rank 维坐标）** 的简写。

它包含的坐标分量数量等于 Shape 的**顶层 rank**。如果某个顶层 mode 内部还是 tuple，就先把这个 multi-mode 看成一个整体，其范围由该 mode 的 `size` 决定。

对于：

```text
Shape = (3,(2,3))
```

顶层包含 `3` 和 `(2,3)` 两个 mode，所以：

```text
rank = 2
```

因此 rank-D 坐标是一个二维坐标：

```text
(m,n)
0 <= m < 3
0 <= n < 6
```

第二个顶层 mode `(2,3)` 被整体视为大小为：

```text
size((2,3)) = 6
```

的一维 mode。

例如，rank-D 坐标：

```text
(1,5)
```

会被进一步展开成自然坐标：

```text
(1,5)
  -> (1,(1,2))
```

再看另一个例子：

```text
Shape = ((2,2),3)
```

它虽然有三个叶子 mode，但顶层只有两个 mode，所以：

```text
rank-D 坐标：  (u,v)，其中 0 <= u < 4，0 <= v < 3
自然坐标：     ((i,j),k)
```

因此：

```text
rank-D 看顶层有几个 mode
natural coordinate 保留 Shape 的完整嵌套结构
```

### 1.3 自然坐标

自然坐标与 Shape 的层级 congruent：

```text
(m,(p,q))
```

这三种坐标可以表示同一个逻辑位置。CuTe 会先把兼容的输入坐标转换为自然坐标。

---

## 2. Colexicographical order

CuTe 使用 colexicographical order 枚举坐标。学习时可以把它记成：

```text
左边的 mode 最先变化
mode-0 是最低位
```

对于 depth-1 Shape：

```text
(s0,s1,s2)
```

一维序号 `i` 对应：

```text
c0 = i % s0
i  = i / s0

c1 = i % s1
i  = i / s1

c2 = i % s2
```

因此自然序是一个混合进制计数器，进制依次为 `s0、s1、s2`。

重要区别：

```text
自然序由 Shape 决定
最终 index 顺序由 Stride 决定
```

换 Stride 不会改变自然坐标的枚举顺序，只会改变每个坐标映射到哪里。

---

## 3. idx2crd：坐标归一化

先记住它最常见的用途：

```text
idx2crd

输入：一维自然序号
输出：与 Shape 层级一致的自然坐标
用途：回答“第 i 个逻辑位置对应哪个多维坐标？”
```

### 3.1 简单二维例子

给定：

```text
Shape = (4,3)
```

mode-0 的大小是 4，而且最先变化。因此：

| 输入 `idx` | 输出自然坐标 |
|---:|---|
| `0` | `(0,0)` |
| `1` | `(1,0)` |
| `2` | `(2,0)` |
| `3` | `(3,0)` |
| `4` | `(0,1)` |
| `5` | `(1,1)` |
| `6` | `(2,1)` |

例如：

```text
idx2crd(5, (4,3)) = (1,1)
```

计算过程：

```text
c0 = 5 % 4 = 1
c1 = 5 / 4 = 1

输出 = (1,1)
```

这里输出的是**逻辑坐标**，还不是最终内存 index。`idx2crd` 只使用 Shape，不使用 Stride。

### 3.2 层级 Shape 例子

给定：

```text
Shape = (3,(2,3))
```

调用：

```text
idx2crd(16, Shape)
```

得到：

```text
(1,(1,2))
```

输出坐标与 Shape 具有相同层级：

```text
Shape： (3,(2,3))
Coord： (1,(1,2))
```

另外，`idx2crd` 也能将其他兼容坐标归一化为自然坐标：

```cpp
auto shape = Shape<_3, Shape<_2,_3>>{};

idx2crd(16, shape);                              // (1,(1,2))
idx2crd(make_coord(1,5), shape);                 // (1,(1,2))
idx2crd(make_coord(1,make_coord(1,2)), shape);   // (1,(1,2))
```

上面三种输入描述同一个逻辑位置，因此会得到等价的自然坐标。

可以把它理解成：

```text
compatible coordinate
  -> natural coordinate congruent with Shape
```

名字里虽然有 `idx`，但官方语义比“整数下标转坐标”更一般。

---

## 4. crd2idx：产生最终 index

先记住它的输入、输出和用途：

```text
crd2idx

输入：坐标、Shape 和 Stride
输出：一个整数 index
用途：回答“这个逻辑坐标最终访问哪个线性位置？”
```

`crd2idx(c, shape, stride)` 完成两步：

```text
1. 将输入坐标转换为自然坐标
2. 将自然坐标与 Stride 做内积
```

### 4.1 简单二维例子

给定同一个 Shape，但使用两种不同的 Stride：

```text
Shape = (4,3)
Coord = (1,1)
```

第一种 Layout：

```text
Stride = (1,4)

crd2idx((1,1), (4,3), (1,4))
  = 1*1 + 1*4
  = 5
```

第二种 Layout：

```text
Stride = (3,1)

crd2idx((1,1), (4,3), (3,1))
  = 1*3 + 1*1
  = 4
```

两个调用输入的是同一个逻辑坐标 `(1,1)`，但 Stride 不同，所以输出的线性 index 不同。

### 4.2 层级坐标例子

给定：

```text
Shape  = (3,(2,3))
Stride = (3,(12,1))
Coord  = (1,(1,2))
```

计算：

```text
crd2idx((1,(1,2)), Shape, Stride)
  = 1*3 + 1*12 + 2*1
  = 17
```

所以 `crd2idx` 的输出是整数 `17`。当这个 Layout 与 Engine 组成 Tensor 后，这个结果可以用于访问：

```text
engine[17]
```

### 4.3 从一维序号到最终 index

`crd2idx` 也可以接收一维坐标。例如：

```text
Shape  = (3,(2,3))
Stride = (3,(12,1))
输入   = 16
```

第一步，转换为自然坐标：

```text
idx2crd(16, Shape) = (1,(1,2))
```

第二步，与 Stride 做内积：

```text
crd2idx(16, Shape, Stride)
  = 1*3 + 1*12 + 2*1
  = 17
```

这里的 `16` 是逻辑空间中的一维序号，`17` 是 Layout 产生的最终 index，二者不是同一种量。

### 4.4 与 Layout 调用的关系

在概念上：

```text
layout(c)
  = crd2idx(c, shape(layout), stride(layout))
```

---

## 5. `layout(i)` 的完整计算过程

一维调用：

```cpp
layout(i)
```

不能总是假设为：

```text
i * stride<0>(layout)
```

因为 `i` 首先是 Layout 坐标空间中的一维自然序号。对于多 mode 或层级 Shape，CuTe 会先将它转换成与 Shape congruent 的自然坐标：

```text
layout(i)
  = crd2idx(i, shape, stride)

i
  -> idx2crd(i, shape)
  -> natural coordinate
  -> inner product with stride
  -> index
```

可以把这个过程理解为展开嵌套循环，但不是在运行时重新生成 Stride：

```text
Shape 负责把 i 分解成各层循环计数器
Stride 已经保存在 Layout 中
每个计数器乘自己的 Stride，最后求和
```

对于自然坐标 `(c0,c1,...)`：

```text
layout(i) = c0*d0 + c1*d1 + ...
```

其中 `(c0,c1,...) = idx2crd(i, shape)`，`(d0,d1,...)` 是 Layout 已有的 Stride。

例如：

```text
L = (4,2):(2,1)
i = 4
```

先按照 Shape `(4,2)` 做混合进制分解：

```text
idx2crd(4, (4,2)) = (0,1)
```

再与 Stride 做内积：

```text
L(4) = 0*2 + 1*1 = 1
```

如果错误地只乘第一个 stride：

```text
4 * stride<0>(L) = 4 * 2 = 8
```

就会得到错误结果。

只有单 mode Layout，或者映射恰好满足特殊条件时，`layout(i)` 才可能直接表现为 `i * stride<0>`。

### 5.1 `layout(i)` 的物理含义

`layout(i)` 本身不读取内存。它回答的是：

> 第 `i` 个逻辑元素应该映射到底层 Engine 的第几个元素？

可以把 Layout 看成逻辑编号到存储编号的地址生成器：

```text
逻辑序号 i
  -> layout(i)
  -> 底层元素偏移 offset
```

当 Layout 与数据组成 Tensor 后：

```text
tensor(i) = engine[layout(i)]
```

如果 Engine 可以简化理解为类型为 `T*` 的普通指针，那么实际字节地址近似为：

```text
address = base_address + layout(i) * sizeof(T)
```

因此 `layout(i)` 通常表示的是**以元素为单位的偏移**，而不是字节地址，也不是元素值。

例如：

```text
L = (4,2):(2,1)
i = 4
```

计算得到：

```text
idx2crd(4, (4,2)) = (0,1)
layout(4) = 0*2 + 1*1 = 1
```

其物理含义是：

```text
第 4 号逻辑元素
  -> 映射到底层第 1 号存储元素
  -> tensor(4) 访问 engine[1]
```

假设元素类型是 4 字节的 `float`，并且 Engine 是普通连续指针，则相对基地址的字节偏移为：

```text
1 * sizeof(float) = 4 bytes
```

Layout 的不同映射会产生不同物理效果：

```text
layout(i) 连续变化   -> 连续访问
layout(i) 跳跃变化   -> 跨步访问或空洞
多个 i 得到同一结果 -> 地址 alias 或广播
layout(i) 顺序重排   -> 逻辑顺序与存储顺序不同
```

最简洁的理解是：

```text
i         是“逻辑上的第几个”
layout(i) 是“底层存储中的第几个”
tensor(i) 是“取出该位置的数据”
```

---

## 6. compatible

Layout A 与 Layout B 是否 compatible，取决于它们的 Shape。

官方定义要求：

1. 两个 Shape 的 `size` 相同；
2. A 中的所有坐标同时也是 B 的有效坐标。

compatibility 不是简单的：

```text
size(A) == size(B)
```

层级结构和可接受的坐标集合也参与判断。

官方示例包括：

```text
24                compatible with (4,6)
(4,6)             compatible with ((2,2),6)
((2,2),6)         compatible with ((2,2),(3,2))
24                compatible with ((2,3),4)
((2,3),4)     not compatible with ((2,2),(3,2))
(24)           not compatible with 24
```

最后一个例子说明：

```text
24
```

与：

```text
(24)
```

拥有相同 size，但不是相同层级的 Shape。compatibility 具有方向，不能看到 size 相同就默认双向兼容。

### 6.1 为什么 `24` compatible with `(24)`，反过来却不成立

这里比较的不是二者包含多少个逻辑位置，而是它们接受的**坐标表示形式**。

标量 Shape：

```text
24
```

其自然坐标是标量：

```text
0, 1, 2, ..., 23
```

单元素 tuple Shape：

```text
(24)
```

其自然坐标具有一层 tuple：

```text
(0), (1), (2), ..., (23)
```

同时，CuTe Layout 可以接受一维整数坐标，并将它转换成与 Shape congruent 的自然坐标。因此，对于 Shape `(24)`：

```text
输入 7
  -> idx2crd(7, (24))
  -> (7)
```

这说明标量 Shape `24` 的所有坐标都可以作为 Shape `(24)` 的输入：

```text
24 ~ (24)       # true
```

反过来，Shape `(24)` 还具有 `(7)` 这样的 tuple 坐标；标量 Shape `24` 没有对应的 tuple 层级，不能把 `(7)` 当作自身的自然坐标：

```text
(24) ~ 24       # false
```

可以把二者的坐标能力近似理解为：

```text
24    接受：标量坐标
(24)  接受：标量坐标，并能归一化为单元素 tuple 坐标
```

所以：

```text
size(24) == size((24)) == 24
```

只能说明逻辑位置数量相同，不能说明坐标结构双向兼容。

官方将 compatible 描述为 Shape 上的 weak partial order。

---

## 7. size

`size(layout)` 是 Layout 函数定义域的大小：

```text
size(layout) = size(shape(layout))
```

它回答：

```text
合法逻辑坐标一共有多少个？
```

例如：

```text
Layout = (2,3):(1,4)
size   = 6
```

无论 index 是否重复、是否有空洞，size 都只由 Shape 决定。

---

## 8. cosize（codomain size，陪域大小）

官方定义：

```text
cosize(A) = A(size(A) - 1) + 1
```

它表示 Layout 函数的 codomain size，官方特别注明：

```text
codomain 不一定等于实际 range（像集）
```

在常见的零起点、非负 Stride Layout 中，可以把它辅助记成 cover size：

```text
从 offset 0 开始，需要覆盖到最后一个角点 index 的区间大小
```

但正式定义仍应记住：

```text
A(size(A)-1) + 1
```

### 8.1 cosize 不是像集大小

例如：

```text
Layout = (2,2):(0,3)
```

其 index 序列为：

```text
0,0,3,3
```

实际像集是：

```text
{0,3}
```

像集大小为 2，但：

```text
cosize = 4
```

因此必须区分：

```text
size(layout)        定义域坐标数量
|range(layout)|     不同 index 的数量
cosize(layout)      官方定义的 codomain size
```

---

## 9. 像集连续、地址空洞与地址重叠

### 9.1 像集

像集是 Layout 实际产生的所有不同 index：

```text
range(L) = { L(c) | c 是合法坐标 }
```

重复 index 在集合中只出现一次。

### 9.2 像集连续

这里的“连续”指整数区间没有缺口，不是实数分析中的连续函数。

例如：

```text
index 序列：0,1,1,2
像集：      {0,1,2}
```

像集连续，但 index `1` 被多个坐标命中。

另一个例子：

```text
index 序列：0,1,3,4
像集：      {0,1,3,4}
```

像集不连续，因为中间缺少 `2`。

### 9.3 地址重叠

如果两个不同坐标产生同一个 index，则存在地址重叠或 alias：

```text
c1 != c2
L(c1) == L(c2)
```

此时 Layout 不是单射。

### 9.4 广播

Stride 为 0 的 mode 不会改变 index：

```text
4:0
```

该 mode 中所有坐标都映射到同一 index。这是广播，也是有规律的地址 alias。

### 9.5 地址空洞

如果 `[0, cosize)` 中存在 Layout 从未产生的 index，就存在地址空洞。

因此应分别检查：

1. 有没有重复 index；
2. `[0, cosize)` 中有没有未命中的 index。

不能只比较 `size` 和 `cosize`。例如：

```text
(2,2):(0,3)
```

虽然 `size == cosize == 4`，但仍同时存在重复与空洞。

---

## 10. 单射、满射与双射

以 `[0, cosize)` 作为当前讨论的目标集合：

### 单射 injective

不同坐标产生不同 index，即没有地址重叠。

### 满射 surjective

`[0, cosize)` 中每个 index 都至少被命中一次，即没有地址空洞。

### 双射 bijective

同时满足单射和满射：

```text
每个逻辑坐标对应唯一 index
每个目标 index 也恰好有一个逻辑坐标
```

在分析具体 Layout 时，不建议只凭 stride 大小猜测，最稳妥的方法是先展开完整 index 序列。

---

## 11. 本节自测

以下问题留给学习者作答：

1. 对 Shape `(3,(2,3))`，一维坐标、rank-D 坐标和自然坐标分别长什么样？
2. `idx2crd` 为什么不应只理解为“一维下标转二维坐标”？
3. `crd2idx` 内部包含哪两个概念步骤？
4. 一维调用 `layout(i)` 时，为什么不能总是假设结果等于 `i * stride<0>`？
5. 为什么相同 size 不能保证两个 Shape compatible？
6. `cosize`、像集大小和 `size` 分别回答什么问题？
7. 一个 Layout 能否同时存在地址重叠和地址空洞？
8. “像集连续”能否推出 Layout 是单射？

完成后参阅：[自测参考答案](自测参考答案.md)。
