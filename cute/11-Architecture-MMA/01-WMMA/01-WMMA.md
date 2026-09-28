# Warp-Level MMA：从第 07 章映射到 CuTe DSL

> 官方文档：[Warp-Level MMA Instructions Programming Guide](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/mma/wmma_programming.html)
>
> 更新：2026-09-28

## 本节边界

第 07 章已经详细讲过 SM80 Tensor Core GEMM，包括：

- `cp.async` 多级 SMEM pipeline；
- `ldmatrix`；
- `make_tiled_copy_A/B` 与 `retile_D`；
- warp MMA fragment；
- K-loop 和 epilogue。

本节不再推导这些机制，只完成三件事：

1. 把第 07 章的 C++ 概念映射到 CuTe Python DSL；
2. 明确 warp MMA fragment 在 DSL 中仍然是寄存器值；
3. 说明后续架构在保持 warp 执行模型时新增了哪些数据类型。

需要复习完整 SM80 数据流时，回到
[SM70 与 SM80 演进](../../07-GEMM-Tutorial/04-SM70与SM80/04-SM70与SM80.md)。

## 直觉：这里没有新的数据流

Warp MMA 的硬件约束仍然是：

> `mma.sync.aligned` 只能读取参与线程寄存器中的 A/B fragment，
> 并把 accumulator 保存在寄存器中。

所以第 07 章的数据路径原样成立：

```text
GMEM
  │ cp.async
  ▼
SMEM
  │ ldmatrix
  ▼
A/B register fragment
  │ mma.sync.aligned
  ▼
C/D register fragment
```

本节只是换成 Python DSL API，并没有删除 `ldmatrix` 这一层。

## C++ 与 Python DSL 对照

| 第 06～07 章中的概念 | CuTe Python DSL |
|---|---|
| 选择一条 MMA Operation | `warp.MmaF16BF16Op(...)` |
| `make_mma_atom(op)` | `cute.make_mma_atom(op)` |
| `make_tiled_mma(...)` | `cute.make_tiled_mma(...)` |
| 当前线程的 `ThrMMA` | `tiled_mma.get_slice(tidx)` |
| `partition_A/B/C` | 同名 Python API |
| 创建 A/B/C fragment | `make_fragment_A/B/C` |
| S2R tiled copy | `cute.make_tiled_copy_A/B(...)` |
| 执行 MMA | `cute.gemm(...)` |

这些 API 的职责没有改变。尤其是：

```text
partition_*       只建立 view
make_fragment_*   建立寄存器 fragment
cute.copy         真正执行 SMEM → RMEM
cute.gemm         真正执行 MMA
```

## 创建 Warp MMA Op

F16、FP32 accumulation：

```python
import cutlass
import cutlass.cute as cute
from cutlass.cute.nvgpu import warp

op = warp.MmaF16BF16Op(
    cutlass.Float16,
    cutlass.Float32,
    (16, 8, 16),
)
tiled_mma = cute.make_tiled_mma(op)
```

`(16,8,16)` 仍表示整个 warp 合作完成的 instruction shape，不是每个
线程各自计算 `16×8×16`。它与第 06 章的 `Shape_MNK` 含义完全相同。

`atom_layout_mnk` 和 `permutation_mnk` 的含义也没有变化，本节不重复
展开，参见
[TiledMMA](../../06-MMA-Atom/02-TiledMMA/02-TiledMMA.md)。

## 在同一 warp 模型上新增的数据类型

当前官方 DSL 指南列出：

| 输入类型 | DSL op | 最早对应架构 |
|---|---|---|
| F16/BF16 | `warp.MmaF16BF16Op` | SM80 |
| FP8 E4M3/E5M2 | `warp.MmaFP8Op` | SM89 |
| MXF4 block scale | `warp.MmaMXF4Op` | SM120a |
| MXF4/NVF4 block scale | `warp.MmaMXF4NVF4Op` | SM120a |

这些 op 扩展了数据类型和 instruction shape，但没有改变本节的核心
内存关系：

```text
A/B/C/D 都由 warp 的寄存器 fragment 承载。
```

Block-scaled op 还需要 scale-factor tensor；这是 SM120a 的扩展主题，
不影响理解下一节 Hopper WGMMA。

## 为什么下一代要改

Warp MMA 的主要限制现在可以直接从数据流看出来：

```text
每个 K-block:
SMEM → tCrA/tCrB → MMA
```

A/B 必须先成为寄存器 fragment。tile 越大、流水越深，需要同时保留的
operand 和 accumulator 寄存器就越多。寄存器占用会限制：

- 一个 SM 上能同时驻留多少 warp；
- 能否使用更大的 tile；
- copy 与 compute 能重叠多少阶段。

Hopper WGMMA 的关键改变正是：

> 不再要求 B、以及 SMEM 路径下的 A，先整体进入寄存器；
> Tensor Core 根据 descriptor 直接读取 staged SMEM。

## 常见误解

1. **“`make_fragment_A` 已经把 SMEM 数据读入寄存器。”**
   没有。它创建 storage；真正的读取发生在 `cute.copy(s2r, ...)`。
2. **“`mma.sync` 是同步指令，所以不需要等待 `cp.async`。”**
   两者同步的是不同阶段。消费 SMEM 前仍要确认异步 copy 已完成。
3. **“Python DSL 的 `cute.gemm` 自动决定是否使用 `ldmatrix`。”**
   `cute.gemm` 只消费已经准备好的 fragment；S2R copy 仍由 kernel 构造。

## 下一步

下一节只改变三处：

```text
32-thread warp       → 128-thread warpgroup
RMEM A/B fragment    → SMEM descriptor
同步 mma.sync        → 异步 WGMMA group
```

其余 CTA tiling、TMA、partition 和 epilogue 概念继续沿用前面章节。

## 检查理解

1. `partition_A(sA)`、`make_fragment_A(...)` 和 `cute.copy(s2r, ...)`
   分别产生什么？

   > Hint：区分 view、storage 和数据搬运。

2. 为什么 Warp MMA 不能把 `sA` 直接传给 `cute.gemm`？

   > Hint：回忆 `mma.sync.aligned` 实际读取什么。

3. 如果删除 `ldmatrix`，下一代指令必须新增什么能力才能继续读取 A/B？

   > Hint：下一节的关键词是 descriptor。

## 官方示例

- [Ampere Warp MMA 官方 Python 示例导读](官方Python示例导读.md)
- `examples/python/CuTeDSL/cute/ampere/kernel/dense_gemm/tensorop_gemm.py`
- `examples/python/CuTeDSL/cute/blackwell_geforce/kernel/blockscaled_gemm/dense_blockscaled_gemm_persistent_pingpong.py`
