# 06 MMA Atom

> 官方对应：`media/docs/cpp/cute/0t_mma_atom.md`
>
> 官方基线：NVIDIA CUTLASS `main`，核对日期 2026-09-16
>
> 前置章节：[Tensor Algorithms](../05-Tensor-Algorithms/README.md)

MMA（Matrix Multiply-Accumulate）执行：

```text
D = A × B + C
```

困难不在公式，而在硬件指令对线程、寄存器和值的位置有严格规定。CuTe 用四层
抽象把这些架构细节逐步封装起来：

```text
Operation
  │ 包装一条 PTX MMA 指令及其物理寄存器接口
  ▼
MMA_Traits
  │ 补充数据类型、M/N/K Shape、线程和值的映射
  ▼
MMA_Atom
  │ 把 Operation 与 Traits 组合成一次可调用的逻辑 MMA
  ▼
TiledMMA
    在更多线程和 value 上复制、交错或重排 Atom
```

## 推荐学习顺序

1. [Operation 与 Traits](01-Operation与Traits/README.md)
   - Operation 名称与寄存器接口
   - `fma`
   - `MMA_Traits`
   - `(thread,value) → operand coordinate`
2. [TiledMMA](02-TiledMMA/README.md)
   - Atom 的线程复制与 value 复制
   - `get_slice`
   - `partition_A/B/C`
   - `make_fragment_A/B/C`
3. [架构映射](03-架构映射/README.md)
   - 单线程、Volta quadpair、Ampere warp、Hopper warpgroup
   - accumulator 与 A/B operand 映射
   - shared-memory descriptor 的特殊含义

## 核心心智模型

### 1. 指令只认识寄存器，不认识矩阵

PTX MMA 指令接收的是每个参与线程中的若干寄存器。所谓矩阵坐标，是 CuTe
通过 Traits 解释出来的：

```text
线程号 + 该线程的 value 编号
             │
             ▼
        A(m,k) / B(n,k) / C(m,n)
```

### 2. TV Layout 是本章核心

例如：

```text
CLayout: (logical_thread_id, logical_value_id) → (m,n)
```

CuTe Layout 实际返回整数，因此 `(m,n)` 常按 column-major 编码：

```text
encoded(m,n) = m + n*M
```

只要能解释 TV Layout，就能回答：

- 某线程持有哪些 accumulator？
- 某个寄存器对应矩阵中的哪个坐标？
- A/B fragment 应如何装载？
- 多个 Atom 怎样拼成更大的 MMA tile？

### 3. Atom 的 Shape 不等于每线程持有的数据量

`Shape_MNK = (8,8,4)` 表示整个协作线程组共同完成一个 `8×8×4` MMA，不表示
每个线程都拥有完整的 A、B、C tile。

每线程持有多少值由 `ALayout`、`BLayout`、`CLayout` 的 value mode 决定。

## 一条完整使用链

```cpp
auto tiled_mma = make_tiled_mma(mma_op, atom_layout, tile);
auto thr_mma   = tiled_mma.get_slice(threadIdx.x);

auto tCrC = thr_mma.partition_fragment_C(gC);
auto tCrA = thr_mma.partition_fragment_A(gA);
auto tCrB = thr_mma.partition_fragment_B(gB);

clear(tCrC);
gemm(tiled_mma, tCrA, tCrB, tCrC);
```

这段代码表达的是：

1. 选择硬件 MMA；
2. 决定怎样把 Atom 铺到线程和值上；
3. 根据线程编号取得该线程的视图；
4. 按 MMA 要求分区 A、B、C；
5. 创建正确类型和布局的寄存器 fragment；
6. 调用上一章学习的 `gemm` 算法。

具体 kernel 中 A/B 可能来自 shared memory，fragment 的创建和 copy 顺序也会因
架构而不同，上述代码只展示关系。

## 本章完成标准

学完后应能回答：

1. Operation、Traits、Atom、TiledMMA 各负责什么？
2. `DRegisters/ARegisters/BRegisters/CRegisters` 描述的是什么？
3. `Shape_MNK` 为什么不是每线程 Shape？
4. `ThrID` 与 CUDA 的物理 thread index 有什么区别？
5. `ALayout/BLayout/CLayout` 的输入和输出分别是什么？
6. `TiledMMA` 的 thread replication 与 value replication 有何区别？
7. `partition_A/B/C` 和 `make_fragment_A/B/C` 各做什么？
8. 为什么 Hopper GMMA 的某些 A/B Layout 在线程 mode 上使用 stride 0？

## 官方资料

- [CuTe MMA Atom 官方文档](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0t_mma_atom.html)
- [NVIDIA/CUTLASS 官方 Markdown](https://github.com/NVIDIA/cutlass/blob/main/media/docs/cpp/cute/0t_mma_atom.md)
- [mma_atom.hpp](https://github.com/NVIDIA/cutlass/blob/main/include/cute/atom/mma_atom.hpp)
- [MMA Operation 目录](https://github.com/NVIDIA/cutlass/tree/main/include/cute/arch)
- [MMA Traits 目录](https://github.com/NVIDIA/cutlass/tree/main/include/cute/atom)
