# MMA 架构映射

> 官方对应：`media/docs/cpp/cute/0t_mma_atom.md` 的 Volta 与 Hopper 示例
>
> 更新：2026-09-21

不同 GPU 架构的 MMA 协作范围和 operand 传递方式不同，但 CuTe 最终都将其
描述为：

```text
ThrID
ALayout: (thread,value) → (m,k)
BLayout: (thread,value) → (n,k)
CLayout: (thread,value) → (m,n)
```

本节重点不是背诵某个 Layout，而是学会从架构图或 ISA 说明构造映射。

## 1. 架构层级概览

| 示例层级 | 典型协作线程数 | 特点 |
|---|---:|---|
| 标量 FMA | 1 | 单线程寄存器运算 |
| Volta MMA | 8 | 一个 quadpair，来自同一 warp 的两组 4 lanes |
| Ampere MMA | 32 | 一个完整 warp 协作 |
| Hopper GMMA/WGMMA | 128 | 四个 warp，即一个 warpgroup |

不能把某一代架构的线程映射直接套到另一代。即使两条指令拥有相似的
`Shape_MNK`，其 fragment 分配和 operand 来源也可能完全不同。

### 各架构的 lane id 分组

下面列出本章涉及的代表性 MMA 指令族。具体代码仍应以所选 Operation 的
`MMA_Traits::ThrID` 为准。

#### 单线程 FMA

单线程 FMA 不需要其他 lane 协作。warp 中的每个 lane 都可以独立执行：

```text
lane 0  → 自己的一次 FMA
lane 1  → 自己的一次 FMA
...
lane 31 → 自己的一次 FMA
```

这里没有固定的多 lane 分组。Atom 内只有一个 logical thread，但这个 logical
thread 可以由当前 warp 中任意一个实际线程承担。

#### Volta `m8n8k4` FP16 MMA

一个 warp 被分成四个 quadpair，每个 quadpair 包含 8 个 lanes：

```text
quadpair 0：lanes  0,  1,  2,  3, 16, 17, 18, 19
quadpair 1：lanes  4,  5,  6,  7, 20, 21, 22, 23
quadpair 2：lanes  8,  9, 10, 11, 24, 25, 26, 27
quadpair 3：lanes 12, 13, 14, 15, 28, 29, 30, 31
```

每个 quadpair 独立完成一个 `8×8×4` MMA。CuTe 描述单个 quadpair 时使用：

```cpp
Layout<Shape<_4,_2>, Stride<_1,_16>>
```

#### Ampere warp-level MMA

Ampere 常见的 `mma.sync` Atom 由整个 warp 协作：

```text
一个 MMA 线程组：lanes 0..31
```

CuTe Traits 通常写成：

```cpp
using ThrID = Layout<_32>;
```

与 Volta 不同，这里不再把一个 warp 划成四个独立的 8-thread Atom。

#### Hopper

Hopper 同时存在不同协作层级。

普通 warp-level MMA 仍使用：

```text
一个 MMA 线程组：lanes 0..31
```

GMMA/WGMMA 使用一个 warpgroup，即四个连续 warp：

```text
warpgroup warp 0：lane 0..31
warpgroup warp 1：lane 0..31
warpgroup warp 2：lane 0..31
warpgroup warp 3：lane 0..31
```

若使用 warpgroup 内的线性线程编号表示：

```text
warpgroup thread 0..31   = warp 0 的 lane 0..31
warpgroup thread 32..63  = warp 1 的 lane 0..31
warpgroup thread 64..95  = warp 2 的 lane 0..31
warpgroup thread 96..127 = warp 3 的 lane 0..31
```

必须注意：

```text
lane id 始终是单个 warp 内的 0..31
0..127 是 warpgroup-local thread id，不是 lane id
```

CuTe 对代表性的 Hopper GMMA 使用：

```cpp
using ThrID = Layout<_128,_1>;
```

### 分组速查

| 架构/指令族 | 协作范围 | lane id 分组 |
|---|---:|---|
| 单线程 FMA | 1 thread | 每个 lane 独立，无固定多 lane 分组 |
| Volta `m8n8k4` FP16 | 8 threads | `0..3 + 16..19` 等四个 quadpair |
| Ampere warp MMA | 32 threads | `0..31` |
| Hopper warp MMA | 32 threads | `0..31` |
| Hopper GMMA/WGMMA | 128 threads | 4 个 warp，各自拥有 `lane 0..31` |

## 2. 从架构图推导 TV Layout

通用步骤：

1. 确定协作线程集合；
2. 给这些线程定义连续的 logical thread id；
3. 记录 logical thread id 对应的实际 lane；
4. 对每个 operand，列出 `(thread,value)` 对应的矩阵坐标；
5. 选定矩阵坐标的整数编码；
6. 从坐标增量识别层级 Shape 和 Stride；
7. 验证覆盖、重复和总元素数。

例如 C 的 column-major 坐标编码：

```text
(m,n) → m + n*M
```

然后把：

```text
(logical_tid, value_id) → m + n*M
```

写成一个 CuTe Layout。

## 3. Volta：quadpair

官方示例：

```cpp
SM70_8x8x4_F32F16F16F32_NT
```

一次 Atom 由 8 个线程协作完成 `8×8×4` MMA。

### 3.1 ThrID

这 8 个线程对应 warp lanes：

```text
0, 1, 2, 3, 16, 17, 18, 19
```

CuTe 写成：

```cpp
using ThrID = Layout<Shape <_4, _2>,
                     Stride<_1,_16>>;
```

展开：

```text
(0,0) → 0
(1,0) → 1
(2,0) → 2
(3,0) → 3
(0,1) → 16
(1,1) → 17
(2,1) → 18
(3,1) → 19
```

这里 Layout 的 domain 是 8 个 logical threads，codomain 是 warp lane id。

### 3.2 C/D accumulator 映射

FP32 accumulator 示例：

```cpp
// (T8,V8) → encoded (m,n)
using CLayout =
    Layout<
      Shape <Shape <_2, _2, _2>, Shape <_2, _2, _2>>,
      Stride<Stride<_1,_16, _4>, Stride<_8, _2,_32>>
    >;
```

含义：

```text
8 threads × 8 values/thread = 64 accumulator values
8 × 8 output tile          = 64 matrix coordinates
```

以 thread 0 为例：

```text
V0 → (0,0) →  0
V1 → (0,1) →  8
V2 → (2,0) →  2
V3 → (2,1) → 10
V4 → (0,4) → 32
V5 → (0,5) → 40
V6 → (2,4) → 34
V7 → (2,5) → 42
```

看起来复杂，是因为同一线程持有的 accumulator 并不要求在矩阵坐标上连续。

### 3.3 A/B operand 映射

A 与 B 各有：

```text
8 threads × 4 logical values/thread = 32 values
M*K 或 N*K                         = 8*4 = 32
```

对于较简单的 TN 映射，可写成：

```cpp
using ALayout = Layout<Shape <_8,_4>,
                       Stride<_1,_8>>;

using BLayout = Layout<Shape <_8,_4>,
                       Stride<_1,_8>>;
```

虽然 Layout 形式相同，两者的输出坐标含义不同：

```text
ALayout → (m,k)
BLayout → (n,k)
```

NT 映射则需要层级 mode 表达非平凡的线程和值交错：

```cpp
using ALayout =
    Layout<
      Shape <Shape <_4,_2>, _4>,
      Stride<Stride<_8,_4>, _1>
    >;
```

因此不能仅看 `size(ALayout)`；必须展开 `(thread,value)` 到矩阵坐标的映射。

## 4. Ampere：warp-level MMA

Ampere 的常见 `mma.sync` 由一个完整 warp，即 32 个线程协作。

与 Volta 相比，思考方式不变：

```text
Operation
  ├─ 每线程物理寄存器参数
  └─ PTX mma.sync

Traits
  ├─ Shape_MNK
  ├─ ThrID
  ├─ ALayout
  ├─ BLayout
  └─ CLayout
```

变化的是具体：

- 指令 Shape；
- 支持的数据类型；
- sparse / dense 形式；
- A/B arrangement；
- 每线程 fragment 数量与位置。

所以面对一个 Ampere Atom，正确做法是读取对应
`mma_sm80.hpp` 和 `mma_traits_sm80.hpp`，而不是从 Volta 图猜测。

## 5. Hopper：warpgroup GMMA

Hopper GMMA 使用 128 个线程，即四个 warp。

### 5.1 ThrID

官方示例中的线程编号是连续的：

```cpp
using ThrID = Layout<_128, _1>;
```

也就是：

```text
logical thread id 0..127 → warpgroup thread index 0..127
```

### 5.2 accumulator 的层级铺排

以 `64×128` 输出为例，官方从 `8×8` core matrix 开始：

```text
8×8 core matrix
  ↓ 沿 M 堆叠
64×8 strip
  ↓ 沿 N 重复 16 次
64×128 tile
```

对应 FP16 accumulator 的 CLayout：

```cpp
// (T128,V64) → (M64,N128)
using CLayout =
    Layout<
      Shape <Shape <_4,_8,_4>, Shape <_2,_2,_16>>,
      Stride<Stride<_128,_1,_16>, Stride<_64,_8,_512>>
    >;
```

校验元素数：

```text
128 threads × 64 values/thread = 8192
64 × 128 output values         = 8192
```

### 5.3 shared-memory operand descriptor

某些 Hopper GMMA 直接通过 shared-memory descriptor 消费 A 或 B，而不是让
每个线程各自持有一小段普通寄存器 fragment。

官方用如下 ALayout 表达：

```cpp
// (T128,V64x16) → (M64,K16)
using ALayout =
    Layout<
      Shape <_128, Shape <_64,_16>>,
      Stride<  _0, Stride< _1,_64>>
    >;
```

线程 mode 的 stride 是 0：

```text
所有线程都看到同一个完整 shared-memory tile 描述
```

这不表示 128 个线程在同一时刻逐元素读同一个地址，而是表示 operand 由
warpgroup 级 descriptor 描述，不能套用“每线程拥有若干 A 寄存器”的传统模型。

## 6. 如何读一张 MMA 映射图

看到图上的 `T3V2` 时：

```text
T3 = Atom 内 logical thread 3
V2 = 该线程的 logical value 2
```

然后分别查看：

```text
C 图：T3V2 对应哪个 (m,n)
A 图：T3V2 对应哪个 (m,k)
B 图：T3V2 对应哪个 (n,k)
```

不要默认同一个 `T3V2` 在三个 operand 中代表相同矩阵坐标。A/B/C 各自拥有
独立的 TV Layout。

## 7. 必做校验

对任意 Atom 至少检查：

### 元素数量

```text
size(ALayout) == M*K
size(BLayout) == N*K
size(CLayout) == M*N
```

若存在 descriptor 或广播语义，还应解释 stride-0 和重复映射的原因。

### thread 范围

```text
size(ThrID) == 参与一条指令的逻辑线程数
```

### 坐标覆盖

展开所有 `(thread,value)` 后，应与指令文档要求的 operand 坐标一致。

### 类型打包

检查逻辑 `ValType*` 与物理 `*Registers` 之间的 bit 数是否一致。

## 8. 常见错误

### 错误 1：把 logical thread id 当 lane id

Volta quadpair 已经证明两者可能不同。

### 错误 2：看到 stride 0 就认为存在数据竞争

在 descriptor 型 operand 中，它表示所有线程共享同一 operand 描述语义。

### 错误 3：用 CLayout 推导 ALayout

A、B、C 的坐标空间不同，必须分别读取架构映射。

### 错误 4：只校验元素总数

总数相同不代表坐标归属正确；映射错一个位置就会算出错误矩阵。

### 错误 5：跨架构复用 fragment 假设

Volta、Ampere 和 Hopper 的协作粒度、寄存器 ABI、operand 来源都可能不同。

## 9. 自测

1. Volta quadpair 的 8 个 logical threads 对应哪些 warp lanes？
2. `CLayout` 的 domain 和 codomain 分别是什么？
3. 为什么相同形式的 ALayout 与 BLayout 可以表达不同坐标？
4. `128×64` 与 `64×128` 中哪个对应 threads × values，哪个对应 M × N？
5. Hopper descriptor 型 ALayout 为什么在线程 mode 上使用 stride 0？
6. 判断一个 TV Layout 正确，为什么不能只比较元素总数？

## 官方资料

- [CuTe MMA Atom：Volta](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0t_mma_atom.html#volta)
- [CuTe MMA Atom：Hopper](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0t_mma_atom.html#hopper)
- [MMA architecture wrappers](https://github.com/NVIDIA/cutlass/tree/main/include/cute/arch)
- [MMA traits](https://github.com/NVIDIA/cutlass/tree/main/include/cute/atom)
