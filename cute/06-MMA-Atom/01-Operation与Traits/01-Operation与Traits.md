# MMA Operation 与 Traits

> 官方对应：`media/docs/cpp/cute/0t_mma_atom.md` 的 “CuTe MMA Atoms”
>
> 更新：2026-09-16

本节从一条硬件 MMA 指令开始，理解 CuTe 如何把“物理寄存器 ABI”转换为
“逻辑矩阵坐标”。

## 1. 四层抽象

| 层次 | 负责内容 | 不负责 |
|---|---|---|
| Operation | 包装具体 PTX 指令、声明物理寄存器参数 | Tensor、Layout 和逻辑坐标 |
| `MMA_Traits` | 描述逻辑类型、Shape 和 thread-value 映射 | 扩展到更大 tile |
| `MMA_Atom` | 组合 Operation 与 Traits，提供 Tensor 调用和 fragment API | CTA 级完整 GEMM |
| `TiledMMA` | 复制、交错和重排 Atom | global/shared copy 与同步 |

可以记为：

```text
Operation = 怎么发指令
Traits    = 这条指令在逻辑上是什么意思
Atom      = 可被 Tensor 算法调用的一次 MMA
TiledMMA  = 多个 Atom 组成的线程/value tile
```

## 2. Operation struct

Operation 位于 `include/cute/arch/` 下以 `mma` 开头的头文件中。它尽量不依赖
CuTe Layout 或 Tensor，只描述具体指令的物理接口。

### 2.1 从名称读取信息

以官方 Volta 示例为例：

```cpp
SM70_8x8x4_F32F16F16F32_NT
```

可以拆成：

| 名称片段 | 含义 |
|---|---|
| `SM70` | 首次支持该操作的架构是 Volta |
| `8x8x4` | 指令级逻辑 Shape：`M=8, N=8, K=4` |
| `F32F16F16F32` | 按 D、A、B、C 的顺序编码数据类型 |
| `NT` | A 为 M-major/column-major，B 为 N-major/row-major |

类型顺序容易记错，应从公式读取：

```text
D = A × B + C

名字中的类型顺序：D, A, B, C
```

### 2.2 寄存器类型别名

Operation 定义：

```cpp
using DRegisters = float[8];
using ARegisters = uint32_t[2];
using BRegisters = uint32_t[2];
using CRegisters = float[8];
```

它们描述的是**每个参与线程传给 PTX 指令的物理寄存器接口**。

例如 `ARegisters = uint32_t[2]` 不代表 A 的逻辑值类型是 `uint32_t`。这里两个
32-bit 寄存器各自可以打包两个 FP16，所以逻辑上是四个 half。

```text
物理接口：2 × uint32 register
逻辑数据：4 × half value
```

Operation 与 Traits 分开的原因之一，就是物理寄存器类型不能完整表达逻辑数据
类型和矩阵位置。

### 2.3 `fma`

Operation 提供静态函数：

```cpp
MMA_Operation::fma(d..., a..., b..., c...);
```

它负责：

- 按 PTX 要求组织参数；
- 发出具体 MMA 指令；
- 在目标架构未启用时进入明确的错误路径。

普通使用者通常不直接调用该函数，而是通过 `MMA_Atom::call` 或 `cute::gemm`
调用，让 CuTe 先完成类型、rank 和 fragment 检查。

## 3. MMA_Traits

Traits 位于 `include/cute/atom/` 下以 `mma_traits` 开头的头文件中。

典型 specialization：

```cpp
template <>
struct MMA_Traits<SM70_8x8x4_F32F16F16F32_NT>
{
  using ValTypeD = float;
  using ValTypeA = half_t;
  using ValTypeB = half_t;
  using ValTypeC = float;

  using Shape_MNK = Shape<_8,_8,_4>;
  using ThrID   = SM70_QuadPair;
  using ALayout = SM70_8x4_Col;
  using BLayout = SM70_8x4_Col;
  using CLayout = SM70_8x8_32b;
};
```

### 3.1 逻辑 value type

```text
ValTypeD / ValTypeA / ValTypeB / ValTypeC
```

它们描述逻辑计算类型，而不是 PTX 参数为了打包采用的物理寄存器类型。

### 3.2 `Shape_MNK`

```cpp
using Shape_MNK = Shape<_8,_8,_4>;
```

表示整个协作线程组的一次指令计算：

```text
A: (8,4)
B: (8,4)  // CuTe 使用 (N,K)
C/D: (8,8)
```

总共有：

```text
A values = M*K = 32
B values = N*K = 32
C values = M*N = 64
```

这些值会分散到参与该指令的线程中。

### 3.3 `ThrID`

`ThrID` 把 MMA 内部的逻辑线程编号映射到硬件线程编号。

Volta quadpair 示例：

```cpp
using ThrID = Layout<Shape<_4,_2>,
                     Stride<_1,_16>>;
```

映射：

```text
logical tid: 0  1  2  3  4  5  6  7
warp lane:   0  1  2  3 16 17 18 19
```

所以：

```text
logical thread id != 必然等于 threadIdx.x 或 lane id
```

`TiledMMA` 会进一步把 Atom 的逻辑线程映射扩展到实际线程布局。

## 4. A/B/C Layout：TV 映射

三个 Layout 的共同输入都是：

```text
(logical_thread_id, logical_value_id)
```

输出分别是：

```text
ALayout → A 的 (m,k)
BLayout → B 的 (n,k)
CLayout → C/D 的 (m,n)
```

由于 CuTe Layout 返回整数，二维坐标通常先编码成：

```text
A: m + k*M
B: n + k*N
C: m + n*M
```

因此 `CLayout(t,v) = 17` 在 `M=8` 时表示：

```text
m = 17 % 8 = 1
n = 17 / 8 = 2

(m,n) = (1,2)
```

### TV Layout 不是内存 Layout

这点非常重要：

```text
内存 Layout：matrix coordinate → memory offset
TV Layout：   (thread,value) → matrix coordinate
```

TV Layout 描述数据归属，不直接说明数据位于 global、shared 还是 register。

## 5. MMA_Atom

最常见的构造：

```cpp
using MMA = MMA_Atom<SM70_8x8x4_F32F16F16F32_NT>;
MMA mma;
```

`MMA_Atom<Operation>` 会继承对应的 `MMA_Traits<Operation>`，并公开：

```text
ValTypeD/A/B/C
Shape_MNK
ThrID
LayoutA_TV / LayoutB_TV / LayoutC_TV
```

### 5.1 `call`

四参数形式：

```cpp
mma.call(D, A, B, C);
```

执行：

```text
D = A × B + C
```

三参数形式：

```cpp
mma.call(A, B, C);
```

等价于：

```cpp
mma.call(C, A, B, C);
```

Atom 的直接 `call` 接受 rank-1 Tensor，因为这里每个 Tensor 表示当前 MMA
调用所需的寄存器 value 列表。

### 5.2 fragment

Atom/TiledMMA 提供：

```cpp
make_fragment_A(partitioned_A);
make_fragment_B(partitioned_B);
make_fragment_C(partitioned_C);
```

fragment 是满足 MMA 操作数类型和布局要求的 Tensor，通常由寄存器拥有。

顺序应是：

```text
先 partition
再根据 partition 结果构造 fragment
```

因为 CuTe 会检查 partition 后的 value mode，并利用其 Layout 改善后续 copy 的
向量化。

## 6. 常见误解

### 误解 1：Operation Shape 是每线程计算量

它是整个 Atom 协作组共同完成的 Shape。

### 误解 2：寄存器别名就是逻辑元素类型

物理寄存器可能打包多个窄类型逻辑值。

### 误解 3：CLayout 是 C 的内存布局

它是 thread-value 到 C 矩阵坐标的映射。

### 误解 4：同一 Shape 的 MMA 可以任意替换

数据类型、线程范围、A/B arrangement、fragment packing 和架构要求也必须匹配。

### 误解 5：直接调用 Operation::fma 最简单

这样会绕过 Atom 提供的 Tensor 接口和布局检查。除非在实现新的 Atom，否则优先
使用 `MMA_Atom`、`TiledMMA` 和 `cute::gemm`。

## 7. 自测

1. Operation 和 Traits 为什么要分开？
2. `F32F16F16F32` 的四个类型按什么顺序解释？
3. 为什么 `ARegisters = uint32_t[2]` 仍可能表示四个 FP16？
4. `Shape_MNK = (8,8,4)` 属于单线程还是整个协作组？
5. TV Layout 与内存 Layout 的方向分别是什么？
6. `CLayout(t,v)=17` 在 M=8 时对应哪个 `(m,n)`？

## 官方资料

- [CuTe MMA Atom](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0t_mma_atom.html)
- [mma_atom.hpp](https://github.com/NVIDIA/cutlass/blob/main/include/cute/atom/mma_atom.hpp)
- [Volta MMA Operations](https://github.com/NVIDIA/cutlass/blob/main/include/cute/arch/mma_sm70.hpp)
- [Volta MMA Traits](https://github.com/NVIDIA/cutlass/blob/main/include/cute/atom/mma_traits_sm70.hpp)
