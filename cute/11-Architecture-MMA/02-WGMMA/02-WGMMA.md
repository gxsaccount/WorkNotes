# Hopper WGMMA：从寄存器 Operand 到异步 SMEM Operand

> 官方文档：[Warpgroup MMA Programming Guide](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/mma/wgmma_programming.html)
>
> 更新：2026-09-28

## 本节边界

本节默认已经掌握第 06～09 章的 TiledMma、partition、GEMM mainloop、
SMEM layout 和 TMA，只讨论 WGMMA 相对 SM80 Warp MMA 的变化。

```text
Warp MMA                     Hopper WGMMA
──────────────────────       ─────────────────────────
1 warp                       1 warpgroup = 4 warps
A/B 位于 RMEM                B 位于 SMEM；A 可在 SMEM/RMEM
同步 mma.sync                异步 wgmma.mma_async
```

## 1. 为什么 SMEM 路径不再显式调用 `ldmatrix`

### Warp MMA 的接口需要寄存器值

```text
sA/sB [SMEM]
    │ ldmatrix
    ▼
tCrA/tCrB [RMEM values]
    │
    ▼
mma.sync
```

`ldmatrix` 的作用是满足 `mma.sync` 的寄存器入参要求。

### WGMMA 可以接收 SMEM descriptor

```text
sA/sB [SMEM]
    │ make_fragment 生成 descriptor
    ▼
tCrA/tCrB [SMEM descriptors]
    │
    ▼
wgmma 根据 descriptor 读取 SMEM
```

descriptor 只描述“数据在哪里、怎样解释”，不保存 A/B 数据副本。

所以 WGMMA 删除的是 kernel 中显式的：

```text
SMEM values → A/B register fragment
```

数据仍会在硬件内部送入 Tensor Core，只是不再表现为独立的
`ldmatrix` 指令。

适用范围：

- B 始终从 SMEM descriptor 读取；
- A 选择 `OperandSource.SMEM` 时使用 descriptor；
- A 选择 `OperandSource.RMEM` 时仍需预先准备寄存器值。

## 2. Warpgroup 执行范围

一条 WGMMA 由 4 个连续 warp，即 128 个线程共同参与。

F16/BF16 instruction：

```text
M = 64
N = 8, 16, ..., 256
K = 16
```

FP8 和 INT8 的 K 为 32。

示例：

```python
op = warpgroup.MmaF16BF16Op(
    cutlass.Float16,
    cutlass.Float32,
    (64, 256, 16),
    warpgroup.OperandSource.SMEM,
    OperandMajorMode.K,
    OperandMajorMode.K,
)
tiled_mma = cute.make_tiled_mma(op)
```

`(64,256,16)` 是整个 warpgroup 的 instruction shape，不是一个 warp
或一个线程的工作量。

多个 warpgroup 共存时，应先得到逻辑 warpgroup id，再传给
`get_slice`。128 个参与线程必须以一致控制流发射 collective WGMMA。

## 3. Fragment 的物理含义

```python
tCsA = thr_mma.partition_A(sA)
tCsB = thr_mma.partition_B(sB)
tCgC = thr_mma.partition_C(gC)

tCrA = tiled_mma.make_fragment_A(tCsA)
tCrB = tiled_mma.make_fragment_B(tCsB)
acc = cute.make_rmem_tensor(tCgC.shape, cutlass.Float32)
```

| 对象 | 物理含义 |
|---|---|
| `tCsA/tCsB` | MMA-partitioned SMEM view |
| `tCrA/tCrB` | 指向 SMEM tile 的 descriptor |
| `acc` | 128 个线程持有的 RMEM accumulator |

变量名中的 `r` 不能证明对象位于 RMEM，应检查 `OperandSource` 和
fragment 类型。

## 4. MMA 本身是异步的

WGMMA 的基本顺序：

```text
等待 TMA 填好当前 SMEM stage
→ warpgroup.fence()
→ 发射一个或多个 wgmma.mma_async
→ warpgroup.commit_group()
→ warpgroup.wait_group(n)
```

| 操作 | 作用 |
|---|---|
| TMA pipeline wait | 保证输入已经到达 SMEM |
| `fence()` | 建立 WGMMA 发射前所需的顺序 |
| `commit_group()` | 把此前发射的 WGMMA 组成一个异步 group |
| `wait_group(n)` | 等到最多剩 `n` 个较新 group 未完成 |
| `wait_group(0)` | 排空全部 WGMMA，允许读取最终 accumulator |

`cute.gemm` 返回只代表操作已发射，不代表 accumulator 已完成。

### Descriptor 的生命周期

WGMMA 可能仍在读取 descriptor 指向的 SMEM：

```text
TMA_LOADING → FULL → WGMMA_READING → REUSABLE
```

因此不能在 `cute.gemm` 返回后立即覆盖对应 stage。何时 release 由
pipeline 和 WGMMA completion 共同决定。

完整 mainloop 对照见
[Hopper WGMMA 官方 Python 示例导读](官方Python示例导读.md)。

## 5. WGMMA 真正优化了什么

主要收益：

1. 用更大的 warpgroup 级 instruction tile 摊薄控制开销；
2. SMEM operand 不再需要显式 `ldmatrix` 和完整 RMEM fragment；
3. MMA 可以分组异步发射，延后等待；
4. 更容易与 TMA producer 和 warp specialization 组成深流水。

它不保证：

- kernel 总寄存器数下降；
- occupancy 自动提高；
- TMA 与 MMA 自动正确重叠。

原因是 accumulator 仍在 RMEM，大 output tile 仍可能产生较高寄存器
压力。

## 6. A 来自 RMEM

WGMMA 的 B 必须来自 SMEM，A 可以来自 RMEM。融合 kernel 可以把前一次
计算的 RMEM 结果转换成下一条 WGMMA 所需的 A layout，再直接作为 A。

```text
A from SMEM:
sA → SMEM descriptor

A from RMEM:
已有 RMEM 值 → A fragment layout
```

切换 `OperandSource` 时必须同步修改 fragment 构造，不能只改枚举。

## 7. 相对 SM80 的最小代码差异

| SM80 Warp MMA | Hopper WGMMA |
|---|---|
| A/B `ldmatrix` copy | SMEM 路径删除 |
| A/B RMEM fragment | 改为 descriptor |
| 一个 warp | 一个 warpgroup |
| 同步 MMA | 异步 group |
| accumulator 在 RMEM | 不变 |

WGMMA 仍留下一个主要限制：大型 accumulator 长期占用 RMEM。下一节
TCGen05 将它移入 TMEM。

## 常见误解

1. **Descriptor 保存了 A/B 数据。**
   它只指向 SMEM，因此不能提前覆盖对应 stage。
2. **TMA wait 表示 WGMMA 也完成了。**
   前者保证输入就绪，后者需要 `wait_group`。
3. **CTA barrier 可以替代 `wait_group(0)`。**
   两者同步的事件不同。
4. **WGMMA 的主要目的就是提高 occupancy。**
   它主要改进运算粒度、供数和异步流水；occupancy 只是可能的结果。

## 检查理解

1. 为什么 WGMMA 的 `tCrA` 可能不是 RMEM tensor？

   > Hint：检查 `OperandSource`。

2. TMA pipeline wait 与 `wait_group(0)` 分别保护什么？

   > Hint：一个保护输入，一个保护计算结果。

3. 为什么 WGMMA 不保证总寄存器占用下降？

   > Hint：accumulator 在哪里？

## 官方示例

- [Hopper WGMMA 官方 Python 示例导读](官方Python示例导读.md)
- `examples/python/CuTeDSL/cute/hopper/kernel/dense_gemm/dense_gemm.py`
- `examples/python/CuTeDSL/cute/hopper/kernel/dense_gemm/dense_gemm_persistent.py`
- `examples/python/CuTeDSL/cute/hopper/kernel/attention/fmha.py`
