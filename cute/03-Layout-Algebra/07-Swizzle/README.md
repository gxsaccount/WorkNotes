# CuTe Swizzle：先看地址，再看公式

> 更新：2026-09-24
>
> CUTLASS 官方 CuTe Layout Algebra 文档没有独立的 Swizzle 章节。本章根据
> `cute/swizzle.hpp`、`cute/swizzle_layout.hpp`、
> `cute/pointer_swizzle.hpp` 和官方 GEMM 示例整理。

## 0. 先记住一句话

CuTe Swizzle 做的是：

> **逻辑坐标不变，用高位地址 bit XOR 低位地址 bit，重新排列 shared-memory
> 物理地址，从而减少 bank conflict。**

学习顺序应该是：

```text
Layout 产生什么地址
→ 为什么这些地址访问同一批 bank
→ 希望怎样重新排列地址
→ 这个排列如何写成 XOR
→ 最后再看 Swizzle<B,M,S>
```

---

## 1. 第一步：把 base Layout 的 offset 写成 bit 分段

这一节只做一件事：

> 把 `base_layout(m,(k0,k1))` 生成的整数 offset 写成
> `[k1][m][k0]`，供后面分析 Swizzle 修改哪些 bit。

使用的具体组合是：

```cpp
auto base_layout =
    Layout<Shape <_8, Shape <_8, _8>>,
           Stride<_8, Stride<_1,_64>>>{};

auto swizzle_atom = composition(
    Swizzle<3,3,3>{},
    base_layout
);
```

这个例子中的 shared-memory 元素类型是：

```cpp
using Element = cute::half_t;
```

也就是 FP16，每个元素占 2 bytes。这里的 `base_layout` 返回的是
**FP16 元素下标**，不是 byte address：

```text
offset = 1 → 第 1 个 FP16 元素 → byte address 增加 2
offset = 8 → 第 8 个 FP16 元素 → byte address 增加 16
```

逻辑坐标写成：

```text
(m, (k0, k1))
```

根据 stride：

```text
offset = m * 8 + k0 * 1 + k1 * 64
```

三个坐标都在 `0..7`，所以各自可以用 3 个二进制 bit 表示。但这只能说明它们
各需要 3 bit，还不能直接推出它们位于 offset 的什么位置。

这里的“位置”是指：每一项写成二进制后，对 offset 最终数值的哪些 bit 有贡献。
不是把数据写入某个地址。

直接看一个具体坐标更清楚：

```text
k1 = 6 = 0b110
m  = 2 = 0b010
k0 = 5 = 0b101

k1 * 64 = 6 * 64 = 384 = 0b110_000_000
m  * 8  = 2 * 8  =  16 = 0b000_010_000
k0 * 1  = 5 * 1  =   5 = 0b000_000_101

offset                     = 0b110_010_101
```

可以看到：

```text
bit 8........6  bit 5........3  bit 2........0
    [   k1   ]      [   m    ]      [   k0   ]
```

在这个例子中，`k0`、`m`、`k1` 都只有 3 bit，而乘以 `1`、`8`、`64`
分别将它们左移 `0`、`3`、`6` 位，所以恰好得到连续的三段：

```text
[ k1 ][ m ][ k0 ]
```

把 offset 写成这种分段形式，只是为了下一步能够明确说明：
`Swizzle<3,3,3>` 到底读取和修改其中的哪几位。

---

## 2. 证明这个 Layout 的 bank aliasing （为什么可能back conflict）

Bank aliasing 指：**两个不同的 shared-memory 地址映射到同一个 bank。**

因此需要证明：

```text
1. 地址不同；
2. bank 编号相同。
```

### 2.1 计算地址

对任意坐标 `(m,(k0,k1))`，元素 offset 为：

```text
offset(m,k0,k1) = m * 8 + k0 + k1 * 64
```

元素类型是 FP16，每个元素 2 bytes：

```text
address(m,k0,k1)
= offset(m,k0,k1) * sizeof(half)
= (m * 8 + k0 + k1 * 64) * 2
= m * 16 + k0 * 2 + k1 * 128
```

### 2.2 计算 bank

Shared memory 有 32 个 bank，每个 bank 宽 4 bytes：

```text
bank(m,k0,k1)
= floor(address(m,k0,k1) / 4) % 32
= (m * 4 + floor(k0 / 2) + k1 * 32) % 32
= (m * 4 + floor(k0 / 2)) % 32
```

**化简结果不含 `k1`，因此固定 `m、k0` 时，bank 编号与 `k1` 无关。**

### 2.3 代入两个地址

固定 `m=0, k0=0`，分别取 `k1=0` 和 `k1=1`：

```text
k1=0:
address(0,0,0) = 0 bytes
bank(0,0,0)    = 0

k1=1:
address(0,0,1) = 128 bytes
bank(0,0,1)    = 0
```

地址 `0` 和 `128` 不同，但 bank 都是 `0`，所以存在 bank aliasing。

这还不能证明实际 kernel 存在 bank conflict。只有当同一条 shared-memory 指令并发
访问这些地址时，aliasing 才会变成 conflict；这需要结合线程访问映射判断。

---

## 3. 用 XOR 让 `k1` 参与 bank 选择

第二节已经得到：

```text
bank = (m * 4 + floor(k0 / 2)) % 32
```

如果某次并行访问固定 `m、k0`，只改变 `k1`，这些地址的 bank 编号就不会变化。
为了让这组地址分散到不同 bank，需要让 bank 公式依赖 `k1`。

同时又不希望打乱 `k0` 表示的连续元素(stride(k0) = 1)，因此保留 `k0`，改动原本就参与 bank
计算的 `m`。一种可逆的做法是：

```text
physical_m = m XOR k1
```

新的元素 offset：

```text
swizzled_offset
= k1 * 64 + (m XOR k1) * 8 + k0
```

对应的 bank：

```text
swizzled_bank
= (4 * (m XOR k1) + floor(k0 / 2)) % 32
```

现在 `k1` 会影响 bank。例如固定 `m=0, k0=0`：

```text
offset          = k1 * 64
swizzled_offset = k1 * 64 + k1 * 8 = k1 * 72
```

| `k1` | 原 offset | Swizzle 后 offset | 原 bank | Swizzle 后 bank |
|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 | 0 |
| 1 | 64 | 72 | 0 | 4 |
| 2 | 128 | 144 | 0 | 8 |
| 3 | 192 | 216 | 0 | 12 |
| 4 | 256 | 288 | 0 | 16 |
| 5 | 320 | 360 | 0 | 20 |
| 6 | 384 | 432 | 0 | 24 |
| 7 | 448 | 504 | 0 | 28 |

这一步只说明 XOR 如何改变 bank 映射。下一节再把它写成
`Swizzle<3,3,3>`。

---

## 4. 把手工重排翻译成地址 bit

原地址是：

```text
offset = [ k1 ][ m ][ k0 ]
```

希望得到：

```text
result = [ k1 ][ m XOR k1 ][ k0 ]
```

也就是说，只执行三个动作：

```text
1. 保留最低的 k0
2. 取出高位的 k1
3. 把 k1 XOR 到中间的 m
```

CuTe 用 `Swizzle<3,3,3>` 描述这三个动作。

---

## 5. 现在再看 `Swizzle<B,M,S>`

```cpp
template <int BBits, int MBase, int SShift = BBits>
struct Swizzle;
```

先只考虑最常用的 `S > 0`。不要先记 `Y` 和 `Z`，直接按下面的机械规则理解：

```text
1. 最低 M 个 bit 保持不变
2. 从 bit M 开始，选 B 个“目标 bit”
3. 从 bit M+S 开始，选 B 个“源 bit”
4. 目标 bit = 目标 bit XOR 源 bit
```

等价伪代码：

```python
mask = (1 << B) - 1

destination = (offset >> M) & mask
source      = (offset >> (M + S)) & mask

new_destination = destination ^ source
```

三个参数：

| 参数 | 含义 |
|---|---|
| `B` | 源位域和目标位域各有多少个 bit |
| `M` | 目标位域从 bit 几开始，也表示最低多少个 bit 不变 |
| `S` | 源位域相对目标位域的距离 |

CuTe 要求：

```text
B >= 0
M >= 0
abs(S) >= B
```

`abs(S) >= B` 用来保证源位域与目标位域不重叠。

### 对应到当前例子

```text
offset = [ k1 ][ m ][ k0 ]
           3      3     3 bits
```

所以：

```text
B = 3
  源 k1 和目标 m 都有 3 bit

M = 3
  最低 3 bit 的 k0 不动
  目标 m 从 bit 3 开始

S = 3
  源 k1 从 bit M+S=6 开始
  它与目标 m 相隔 3 bit
```

得到：

```cpp
Swizzle<3,3,3>
```

---

## 6. 与 CuTe 源码公式逐项对应

理解完“源位域 XOR 到目标位域”之后，再看源码中的名字：

```text
yyy_mask = source_mask       // 选中源位域
zzz_mask = destination_mask  // 标记目标位域
```

`YYY`、`ZZZ` 只是源码给两个位域起的名字，本身没有额外含义。

CuTe 定义 mask：

```cpp
bit_mask = (1 << B) - 1;

yyy_mask = bit_mask << (M + max(0, S));
zzz_mask = bit_mask << (M - min(0, S));
```

对于：

```cpp
Swizzle<3,3,3>
```

代入参数：

```cpp
bit_mask = 0b111;

yyy_mask = 0b111 << 6;  // source_mask，选中 k1
zzz_mask = 0b111 << 3;  // destination_mask，标记 m
```

真正执行：

```cpp
result = offset ^ shiftr(offset & yyy_mask, S);
```

因为 `S=3`：

```cpp
source         = offset & yyy_mask;  // 取出 bit 6..8
shifted_source = source >> 3;        // 移到 bit 3..5
result         = offset ^ shifted_source;
```

为什么公式中没出现 `zzz_mask`？

因为：

```text
yyy_mask 选出 bit 6..8
右移 3 位后自然落到 bit 3..5
bit 3..5 就是 zzz_mask 描述的位置
```

`zzz_mask` 描述目标位置，但 `apply()` 不需要再次用它做 AND。

### 完整数值例子

取：

```text
k1 = 6 = 0b110
m  = 2 = 0b010
k0 = 5 = 0b101
```

原 offset：

```text
offset = [110][010][101]
       = 405
```

抽出并移动源位域：

```text
offset          = [110][010][101]
shifted_source  = [000][110][000]
```

执行 XOR：

```text
result     = [110][100][101]
                    ↑
              010 XOR 110 = 100
```

所以：

```text
physical_m = 2 XOR 6 = 4
result offset = 421
```

---

## 7. 为什么 `M=3` 能保留 16-byte 向量

最低 `M=3` 个 element-offset bit 不变：

```text
2^3 = 8 elements
```

对于 FP16：

```text
8 elements × 2 bytes = 16 bytes
```

因此 `k0` 表示的 8 个连续 FP16 元素不会被 Swizzle 拆散。

但要注意地址单位：

```text
half  + M=3 → 16 bytes
float + M=3 → 32 bytes
```

同一个 `Swizzle<3,3,3>` 换了元素类型，物理含义就会变化。不能只看模板参数，
必须先确认 Swizzle 输入的 offset 以什么为单位。

---

## 8. CuTe 中如何使用

### 8.1 直接变换整数 offset

```cpp
#include <cute/swizzle.hpp>

using namespace cute;

auto swizzle = Swizzle<3,3,3>{};

int offset = 405;
int result = swizzle(offset);  // 421
```

这种写法适合理解和调试。

### 8.2 与 Layout 组合

```cpp
#include <cute/layout.hpp>
#include <cute/swizzle.hpp>

using namespace cute;

auto base_layout =
    Layout<Shape <_8, Shape <_8, _8>>,
           Stride<_8, Stride<_1,_64>>>{};

auto swizzle_atom = composition(
    Swizzle<3,3,3>{},
    base_layout
);
```

组合顺序是：

```text
swizzle_atom(coord)
= Swizzle(base_layout(coord))
```

即：

```text
逻辑坐标
→ base_layout
→ element offset
→ Swizzle
→ physical element offset
```

Swizzle 的对象是 Layout 输出的 offset，不是原始多维坐标。

### 8.3 扩展成完整 shared-memory Layout

```cpp
auto bM = Int<128>{};
auto bK = Int<64>{};
auto stages = Int<3>{};

auto sA = tile_to_shape(
    swizzle_atom,
    make_shape(bM, bK, stages)
);
```

`swizzle_atom` 描述一个重复单元，`tile_to_shape` 将其扩展到完整 CTA tile 和
pipeline stage。

### 8.4 创建 shared-memory Tensor

```cpp
extern __shared__ cute::half_t smem[];

auto tensor = make_tensor(
    make_smem_ptr(smem),
    sA
);
```

用户仍然通过逻辑坐标访问：

```cpp
tensor(coord)
```

但 Layout 返回的是 Swizzle 后的物理 offset。

---

## 9. Swizzle 的三个重要性质

### 9.1 逻辑坐标不变

Swizzle 只重新排列地址，不改变矩阵的逻辑 shape 和坐标含义。

### 9.2 它是自己的逆

因为：

```text
(Z XOR Y) XOR Y = Z
```

所以：

```cpp
swizzle(swizzle(offset)) == offset;
```

CuTe 的 `left_inverse` 和 `right_inverse` 对 Swizzle 都返回 Swizzle 自身。

### 9.3 它不是普通仿射 Layout

普通 Layout 主要使用整数乘加：

```text
offset = coordinate · stride
```

Swizzle 使用 XOR，所以组合后的类型通常是 `ComposedLayout`，不能仅靠一组普通
stride 完整表示。

---

## 10. 不要混淆三种 Swizzle

### CuTe Layout Swizzle

```cpp
composition(Swizzle<...>{}, layout)
```

作用于 Layout 输出的相对 offset，通常是 position-independent 的。

### CuTe pointer Swizzle

```cpp
make_swizzle_ptr(pointer, Swizzle<...>{})
```

直接对 pointer address 的 bit 做变换，是 position-dependent 的。

### Threadblock/TMA Swizzle

- threadblock swizzle 改变 CTA tile 的调度顺序；
- TMA swizzle 是 Hopper TMA 描述符控制的硬件地址变换。

它们和本章的 Layout Swizzle 不是同一个接口。

---

## 11. 如何为新 Layout 推导 Swizzle

不要从“常见参数”开始套。按以下顺序：

### 第一步：写出 base Layout 的 offset

```text
offset = layout(coord)
```

明确每个逻辑维度对应哪些地址 bit。

### 第二步：写出真实指令的 lane 地址

例如：

```text
lane → cp.async 写入地址
lane → ldmatrix 读取地址
```

不是只看整个矩阵 Shape。

### 第三步：计算 bank

```text
bank = (byte_address / 4) % 32
```

找出哪些 lane 访问了相同 bank 的不同 word。

### 第四步：找 `X/Z/Y`

```text
X：必须保持的连续向量内部 bit
Z：导致 bank 重复、希望被改变的 bit
Y：能够区分冲突线程的高位 bit
```

### 第五步：转换为参数

```text
M = X 的 bit 数
B = Y/Z 的 bit 数
S = Y 和 Z 的 bit 距离
```

### 第六步：同时验证读写两侧

一个候选必须同时考虑：

```text
global → shared：cp.async / TMA
shared → register：ld.shared / ldmatrix
```

只优化其中一侧，可能让另一侧变差。

---

## 12. 自动搜索脚本

脚本位于：

```text
代码实验/swizzle_search.py
```

它会：

1. 穷举合法的 `Swizzle<B,M,S>`；
2. 使用与 CuTe 一致的 XOR 公式；
3. 检查地址域是否仍为排列；
4. 检查访问起始地址对齐；
5. 展开访问覆盖的 4-byte bank word；
6. 计算各访问组的静态 bank-conflict 分数；
7. 按分数输出候选。

### 运行内置转置例子

```bash
python3 03-Layout-Algebra/07-Swizzle/代码实验/swizzle_search.py
```

输出：

```text
Swizzle<5,0,5>: conflicts=0
```

### 使用 JSON 问题描述

```bash
python3 03-Layout-Algebra/07-Swizzle/代码实验/swizzle_search.py \
  --problem 03-Layout-Algebra/07-Swizzle/代码实验/transpose_float32.json \
  --top 20
```

配置示例：

```json
{
  "element_bytes": 4,
  "domain_size": 1024,
  "search": {
    "max_bits": 5,
    "max_base": 5,
    "max_shift": 10
  },
  "groups": [
    {
      "name": "row-load",
      "access_bytes": 4,
      "range": {"start": 0, "step": 1, "count": 32}
    },
    {
      "name": "column-load",
      "access_bytes": 4,
      "range": {"start": 0, "step": 32, "count": 32}
    }
  ]
}
```

一个 `group` 表示一次共同参与 bank 仲裁的访问。

对于不规则地址，也可以显式列出：

```json
{
  "name": "custom-load",
  "accesses": [
    {"element_index": 0, "access_bytes": 16},
    {"element_index": 8, "access_bytes": 16}
  ]
}
```

---

## 13. 自动搜索不能替代硬件验证

脚本不会自动知道：

- 一条宽 shared-memory 指令如何拆分 wavefront；
- `ldmatrix` 的实际 lane/address 语义；
- TMA 或 WGMMA 的额外 Layout 约束；
- 编译器最终生成了什么指令。

因此它适合：

- 验证 bit 推导；
- 排除明显冲突的候选；
- 缩小需要实际 benchmark 的搜索空间。

最终仍需检查：

1. `print_layout` 或地址表；
2. shared-memory 地址范围和重叠；
3. 向量访问对齐；
4. Nsight Compute 的 bank-conflict/excessive-wavefront 指标；
5. kernel 实际耗时。

真正合适的 Swizzle 不是参数看起来熟悉，而是实际 copy 和 MMA 访问都满足约束，
并且 kernel 性能得到改善。
