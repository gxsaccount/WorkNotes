# TiledMMA

> 官方对应：`media/docs/cpp/cute/0t_mma_atom.md` 的 “TiledMMAs”
>
> 更新：2026-09-21

一个 MMA Atom 只描述一次硬件操作。`TiledMMA` 把一个或多个 Atom 在
M/N/K 空间中复制、交错和重排，并提供每线程的数据分区。

## 1. 从 Atom 到 TiledMMA

最简单的 Atom：

```cpp
using MMAOp = SM70_8x8x4_F32F16F16F32_NT;
MMA_Atom<MMAOp> mma;
```

它也可以写成只含一个 Atom 的 TiledMMA：

```cpp
auto tiled_mma =
    make_tiled_mma(
        MMAOp{},
        Layout<Shape<_1,_1,_1>>{},
        Tile<_8,_8,_4>{});
```

三个主要输入分别是：

```text
MMA Operation / Atom
AtomLayoutMNK
PermutationMNK（也充当目标 tiler）
```

### `AtomLayoutMNK`

描述 Atom 实例怎样分布到 M、N、K：

```text
AtomLayoutMNK: (atom_m, atom_n, atom_k) → 线程组位置
```

### `PermutationMNK`

分别描述 M、N、K mode 的目标 tile 或坐标重排。默认 `_` 表示使用由 Atom
Shape 和 AtomLayout 自然产生的范围。

一个真正包含非平凡 permutation 的例子：

```cpp
using PermM =
    Layout<Shape <_4,_4,_2>,
           Stride<_1,_8,_4>>;

auto tiled_mma =
    make_tiled_mma(
        SM70_8x8x4_F32F16F16F32_NT{},
        Layout<Shape <_2,_2>,
               Stride<_2,_1>>{},
        Tile<PermM, _32, _4>{});
```

这里：

```text
M：大小为 32，并按 PermM 重排
N：大小为 32，保持自然顺序
K：大小为 4，保持自然顺序
```

因此第三个参数不再只是扩大 tile，而是确实对 M 坐标执行 permutation。

### AtomLayoutMNK 与 PermutationMNK 速记

#### 1. `AtomLayoutMNK`

- 决定复制多少个 MMA Atom；
- 决定各 Atom 使用哪些线程组；
- 会影响总线程数和自然 MMA tile 大小。

#### 2. `PermutationMNK`

```text
Tile<_32,_32,_4>
```

只扩大目标 tile，不改变坐标顺序。

```text
Tile<Layout<...>, ...>
```

既指定目标 tile，又重排相应 mode 的坐标。它不增加线程，而是改变每线程负责的
value 数量和坐标组织。

#### 3. 非平凡 permutation

```cpp
Layout<Shape<_4,_4,_2>,
       Stride<_1,_8,_4>>
```

自然坐标 `m` 先按 Shape 拆成：

```text
m → (i0,i1,i2)
```

再映射为：

```text
new_m = i0 + 8*i1 + 4*i2
```

它把层级的连续变化顺序从：

```text
i0 → i1 → i2
```

改为：

```text
i0 → i2 → i1
```

#### 4. 如何理解 permutation

交换循环顺序是理解 permutation 的直观入口，但更准确的定义是：

```text
permutation = 重新映射逻辑坐标
```

Layout 本身只定义坐标映射，并没有真的执行循环。当算法按自然坐标遍历时，这种
坐标重排才会表现得像交换了循环顺序。循环交换只是 permutation 的一种情况。

## 2. 两种扩展方式

### 2.1 在线程上复制 Atom

官方 Volta 示例：

```cpp
auto tiled_mma =
    make_tiled_mma(
        SM70_8x8x4_F32F16F16F32_NT{},
        Layout<Shape <_2,_2>,
               Stride<_2,_1>>{});
```

基础 Atom 是 `8×8×4`，使用一个 8-thread quadpair。`2×2` 的 Atom layout
在 M/N 方向复制四份 Atom：

```text
输出 tile：16×16×4
线程数量：4 × 8 = 32
```

四个 quadpair 分别负责输出矩阵的四个 `8×8` 象限。

### 2.2 在 value 上继续扩展

```cpp
auto tiled_mma =
    make_tiled_mma(
        SM70_8x8x4_F32F16F16F32_NT{},
        Layout<Shape <_2,_2>,
               Stride<_2,_1>>{},
        Tile<_32,_32,_4>{});
```

线程数仍是一个 warp，但 tile 从 `16×16×4` 扩展到 `32×32×4`。新增区域不能
再分配给新线程，于是成为原有线程持有的更多 value。

对比：

```text
线程复制：增加参与线程组，单线程 value 数不一定增加
value 复制：线程组不变，每个线程负责更多 fragment value
```

## 3. Thread Layout 与 Tile Shape

可以使用：

```cpp
auto thr_layout = tiled_mma.get_thr_layout_vmnk();
auto shape      = tile_shape(tiled_mma);
auto threads    = thr_size(tiled_mma);
```

其中线程布局内部可理解为：

```text
(ThrV, ThrM, ThrN, ThrK) → physical thread index
```

- `ThrV`：单个 Atom 内部的逻辑线程；
- `ThrM/N/K`：Atom 在对应 mode 上复制产生的线程坐标。

不要把它与 operand 的 `(V,M,K)` fragment Shape 混淆。一个描述线程组织，
另一个描述每线程持有的数据。

## 4. 取得当前线程的 ThrMMA

```cpp
auto thr_mma = tiled_mma.get_slice(threadIdx.x);
```

`get_slice` 会把物理线程编号反解为该 TiledMMA 中的逻辑线程坐标：

```text
threadIdx.x
    ↓ ThrLayoutVMNK 的逆映射
(ThrV, ThrM, ThrN, ThrK)
    ↓
ThrMMA
```

`ThrMMA` 保存当前线程在 MMA tile 中的位置，并提供 A/B/C 分区函数。

## 5. `partition_A/B/C`

假设传入的 Tensor 逻辑 Shape 分别为：

```text
A: (M,K,...)
B: (N,K,...)
C: (M,N,...)
```

调用：

```cpp
auto tCgA = thr_mma.partition_A(gA);
auto tCgB = thr_mma.partition_B(gB);
auto tCgC = thr_mma.partition_C(gC);
```

得到当前线程负责的视图，其典型逻辑形式为：

```text
tCgA: (V, RestM, RestK, ...)
tCgB: (V, RestN, RestK, ...)
tCgC: (V, RestM, RestN, ...)
```

第一个 `V` mode 满足 MMA Atom 的 value layout；其余 mode 表示该线程还需
重复处理的 tile 位置。

### partition 不搬运数据

和 Tensor 章节一样：

```text
partition = 重排/切分坐标并返回视图
```

它不会自动执行：

- global → shared copy；
- shared → register copy；
- MMA；
- 同步。

## 6. `partition_fragment_A/B/C`

当需要拥有寄存器数据时，可直接：

```cpp
auto tCrA = thr_mma.partition_fragment_A(tensor_A);
auto tCrB = thr_mma.partition_fragment_B(tensor_B);
auto tCrC = thr_mma.partition_fragment_C(tensor_C);
```

它们概念上组合了：

```text
partition_X(tensor)
      +
make_fragment_X(partitioned_tensor)
```

区别：

- `partition_X` 通常得到指向原 Tensor 的视图；
- `partition_fragment_X` 得到符合 Atom fragment 类型要求的 Tensor；
- C fragment 通常是 accumulator 寄存器；
- A/B fragment 在某些架构上是寄存器值，在另一些架构上可能是描述符视图。

## 7. 一个典型使用骨架

```cpp
auto tiled_mma = make_tiled_mma(mma_op, atom_layout, tile);
auto thr_mma   = tiled_mma.get_slice(threadIdx.x);

// 对 shared-memory tile 进行每线程 MMA 分区
auto tCsA = thr_mma.partition_A(sA);
auto tCsB = thr_mma.partition_B(sB);

// 创建 accumulator fragment
auto tCrC = thr_mma.partition_fragment_C(gC);
clear(tCrC);

// 架构需要时，先把 A/B 搬到寄存器 fragment
auto tCrA = thr_mma.make_fragment_A(tCsA);
auto tCrB = thr_mma.make_fragment_B(tCsB);
copy(tCsA, tCrA);
copy(tCsB, tCrB);

gemm(tiled_mma, tCrA, tCrB, tCrC);
```

这只是结构示意。真实 Tensor 的 rank 通常还包含 K tile 等外层 mode，具体
fragment 是否需要显式 copy 取决于 MMA Traits。

## 8. permutation 为什么存在

TiledMMA 不仅能放大 tile，还能重排逻辑坐标。

继续使用前面的非平凡 M Layout：

```cpp
using PermM =
    Layout<Shape <_4,_4,_2>,
           Stride<_1,_8,_4>>;
```

它的 size 仍然是：

```text
4 * 4 * 2 = 32
```

但自然的 identity Layout 应该是：

```text
Shape:  (4,4,2)
Stride: (1,4,16)
```

现在改成：

```text
Shape:  (4,4,2)
Stride: (1,8,4)
```

所以自然 M 坐标 `0..31` 被映射为：

```text
原坐标：
 0  1  2  3 |  4  5  6  7 |  8  9 10 11 | 12 13 14 15 |
16 17 18 19 | 20 21 22 23 | 24 25 26 27 | 28 29 30 31

重排后：
 0  1  2  3 |  8  9 10 11 | 16 17 18 19 | 24 25 26 27 |
 4  5  6  7 | 12 13 14 15 | 20 21 22 23 | 28 29 30 31
```

例如：

```text
原 M=4  → 新 M=8
原 M=8  → 新 M=16
原 M=16 → 新 M=4
```

也就是说，tile 大小仍为 32，但内部坐标次序发生了变化。

这种重排可以使某线程原本分散的 A value 在逻辑 M 方向上变得更连续，更容易
匹配：

- shared-memory Layout；
- register fragment Layout；
- 向量化 copy；
- 后续 epilogue 的访问顺序。

permutation 改变的是逻辑坐标组织，不改变底层 MMA 指令本身。

## 9. 调试方法

先打印，不要只靠模板类型脑补：

```cpp
print(tiled_mma);
print(thr_mma);
print(tile_shape(tiled_mma));
print(tiled_mma.get_layoutA_TV());
print(tiled_mma.get_layoutB_TV());
print(tiled_mma.get_layoutC_TV());
```

若环境支持，还可：

```cpp
print_latex(tiled_mma);
```

重点检查：

1. 线程总数是否符合 kernel block 配置；
2. tile shape 是否覆盖预期 M/N/K；
3. A/B/C 的 TV 映射是否与 copy 分区兼容；
4. 每线程 fragment 大小是否合理；
5. 是否出现重复覆盖或未覆盖坐标。

## 10. 常见错误

### 错误 1：把 TiledMMA 当成一个“大指令”

它是多个 Atom 的组织方式，底层仍会发出一个或多个 MMA 指令。

### 错误 2：以为扩大 tile 必然增加线程

tile 超出线程复制覆盖范围后，可以通过增加每线程 value 扩展。

### 错误 3：直接用 `threadIdx.x` 切 Tensor

应先通过 `get_slice`，让 TiledMMA 根据自身线程布局解释线程编号。

### 错误 4：partition 后忘记创建正确 fragment

视图的数据类型、存储空间或 Layout 不一定符合 MMA 指令寄存器接口。

### 错误 5：A/B/C 用同一种分区

它们分别对应 `(M,K)`、`(N,K)`、`(M,N)`，必须使用各自的 TV Layout。

## 11. 自测

1. AtomLayout 与目标 Tile 各控制什么？
2. `2×2` 个 `8×8×4` Atom 为什么得到 `16×16×4`？
3. tile 扩大但线程数不变时，多出的工作由谁承担？
4. `get_slice(threadIdx.x)` 返回的是什么？
5. `partition_C` 会创建 accumulator 存储吗？
6. `partition_fragment_C` 与 `partition_C` 有什么区别？

## 官方资料

- [CuTe TiledMMA](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0t_mma_atom.html#tiledmmas)
- [mma_atom.hpp](https://github.com/NVIDIA/cutlass/blob/main/include/cute/atom/mma_atom.hpp)
- [CuTe GEMM Tutorial](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0x_gemm_tutorial.html)
