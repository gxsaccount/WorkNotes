# 11 Architecture-specific MMA

> 官方对应：`media/docs/pythonDSL/guides/mma/`
>
> 更新：2026-09-28
>
> 参考版本：NVIDIA CUTLASS `main`，commit
> `418ba45013423731194f8c487348a5da2511298a`。

## 本章边界

前面章节已经讲过：

- [Tensor Partitioning](../04-Tensor/03-Partitioning/03-Partitioning.md)；
- [MMA Atom 与 TiledMma](../06-MMA-Atom/06-MMA-Atom.md)；
- [CTA GEMM、`cp.async`、`ldmatrix` 和 epilogue](../07-GEMM-Tutorial/07-GEMM-Tutorial.md)；
- [TMA tensor 与坐标](../09-TMA-Tensors/09-TMA-Tensors.md)。

本章不重复这些通用机制，只比较不同架构的 MMA 数据位置、执行范围和同步
协议。

## 三代 MMA 的演进

```text
Warp MMA
warp 级同步
A/B/C/D 主要在 RMEM
       ↓
WGMMA
warpgroup 级异步
A/B 使用 SMEM descriptor，C/D 仍在 RMEM
       ↓
TCGen05
单线程发射、CTA/CTA pair 协作
A/B 来自 SMEM/TMEM，C/D 位于 TMEM
```

对应的改进重点：

1. **Warp MMA**：让一个 warp 使用 Tensor Core 执行矩阵乘加。
2. **WGMMA**：扩大到 warpgroup，允许直接消费 SMEM operand，并让
   MMA 本身异步。
3. **TCGen05**：把 accumulator 从 RMEM 移到 TMEM，并进一步解耦
   TMA、MMA 和 epilogue。

WGMMA 的 SMEM descriptor 可以减少 A/B 的显式寄存器 staging，但不保证
kernel 总寄存器数或 occupancy 一定改善，因为 accumulator 仍在 RMEM。

TCGen05 的 single-thread issue 可以从 active-mask 角度看成一段受控且
很短的单-lane 分化。它不是零成本，但发射路径短、MMA 异步，且一次发射
对应大规模 Tensor Core 工作，因此开销容易被摊薄。它与 Warp
specialization 不是同一个概念。

## TMA 位于哪里

TMA 是 MMA 的输入生产者，不是 MMA 指令的一部分：

```text
Ampere:
GMEM ─cp.async→ SMEM ─ldmatrix→ RMEM ─Warp MMA→ RMEM

Hopper:
GMEM ───TMA──→ SMEM ─descriptor→ WGMMA ─→ RMEM

Blackwell:
GMEM ───TMA──→ SMEM ─descriptor→ TCGen05 ─→ TMEM ─T2R→ RMEM
```

TMA 与 MMA 可以重叠：

```text
TMA 加载 K tile k+1
          ║
MMA 计算 K tile k
```

详细说明：

- [TMA 相比 `cp.async` 的优化](TMA相比cp.async的优化.md)
- [TMA Multicast](TMA-Multicast.md)

## 差异速查

| 问题 | Warp MMA | WGMMA | TCGen05 |
|---|---|---|---|
| 执行范围 | 1 warp | 1 warpgroup | 单线程发射，1 CTA/CTA pair 协作 |
| A | RMEM | SMEM 或 RMEM | SMEM 或 TMEM |
| B | RMEM | SMEM | SMEM |
| C/D | RMEM | RMEM | TMEM |
| MMA 模型 | 同步 | 异步 group | 异步 UMMA pipeline |
| 特有步骤 | `ldmatrix` | `fence/commit/wait` | TMEM allocation、T2R |

## 学习材料

1. [Warp-Level MMA](01-WMMA/01-WMMA.md)
   - [官方 Python 示例导读](01-WMMA/官方Python示例导读.md)
2. [Hopper WGMMA](02-WGMMA/02-WGMMA.md)
   - [官方 Python 示例导读](02-WGMMA/官方Python示例导读.md)
3. [Blackwell TCGen05](03-TCGen05/03-TCGen05.md)
   - [官方 Python 示例导读](03-TCGen05/官方Python示例导读.md)

## 官方资料

- [Warp-Level MMA](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/mma/wmma_programming.html)
- [Warpgroup MMA](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/mma/wgmma_programming.html)
- [TCGen05 MMA](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/mma/tcgen05_programming.html)

## 完成标准

1. 能解释三代 MMA 的 operand 和 accumulator 分别位于哪里；
2. 能区分同步 MMA、异步 group 和 UMMA pipeline；
3. 能说明 TMA 与 MMA 各自负责哪段数据流；
4. 能从 SM80 kernel 推导出 SM90、SM100 需要替换的架构专属步骤。
