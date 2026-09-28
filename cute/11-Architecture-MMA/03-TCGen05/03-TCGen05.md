# Blackwell TCGen05：从 RMEM Accumulator 到 TMEM

> 官方文档：[TCGen05 MMA Programming Guide](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/mma/tcgen05_programming.html)
>
> 更新：2026-09-28

## 本节边界

本节沿用第 06～09 章的 TiledMma、partition、TMA、SMEM pipeline 和
GEMM 主循环，只解释 TCGen05 相对 WGMMA 的新增机制：

```text
WGMMA                         TCGen05
─────────────────────        ─────────────────────────
accumulator 在 RMEM          accumulator 在 TMEM
warpgroup collective issue   一个线程 issue
单 CTA                       1 CTA 或 CTA pair
epilogue 从 RMEM 开始        先做 TMEM → RMEM
```

## 1. 主要优化

1. **TMEM accumulator**：大型 C/D tile 不再长期占用通用寄存器。
2. **异步 MMA**：通过 UMMA pipeline 管理完成和 stage 复用。
3. **Single-thread issue**：一个 elected lane 发出大粒度 MMA。
4. **CTA pair**：两个 CTA 可协作完成一次更大的 MMA。
5. **更深的角色分工**：TMA、MMA 和 epilogue 更容易分配给不同 warp。

## 2. 先钉死 Dense 数据路径

最常见的 `A=SMEM、B=SMEM` 路径是：

```text
A/B [GMEM]
    │ TMA
    ▼
A/B [SMEM]
    │ descriptor
    │
    │     C [TMEM]
    │         │
    ▼         ▼
      TCGen05 MMA
           │
           ▼
        D [TMEM]
           │ T2R
           ▼
        D [RMEM]
           │ store
           ▼
        D [GMEM]
```

即：

```text
D_TMEM = A_SMEM × B_SMEM + C_TMEM
```

普通 dense 路径不存在：

```text
A/B: SMEM → RMEM
A/B: SMEM → TMEM
```

TCGen05 直接消费 SMEM 中的 A/B，并把**计算结果**更新到 TMEM。
“直接”描述编程模型；硬件内部的数据通路不表现为独立的
`ldmatrix` 或普通 S2T copy。

## 3. TMEM 替代了寄存器的哪一部分

```text
WGMMA:
128 个线程的 RMEM fragment
共同保存完整 accumulator

TCGen05:
完整 accumulator 保存在 TMEM
Tensor Core 直接读写
```

TMEM 替代的是：

```text
大型 Tensor Core accumulator fragment 的长期 RMEM 占用
```

它没有替代线程通用寄存器。RMEM 仍用于：

- descriptor、地址和指令参数；
- 循环变量与 pipeline 状态；
- 标量/向量临时计算；
- epilogue 的 TMEM→RMEM 接收；
- 类型转换、激活和最终 store。

部分高级模式还可把 A 或 block-scale factor 放入 TMEM。

## 4. 创建 Operation 与 Operand

单 CTA、A/B 来自 SMEM 的 F16 示例：

```python
op = tcgen05.MmaF16BF16Op(
    cutlass.Float16,
    cutlass.Float32,
    (128, 256, 16),
    tcgen05.CtaGroup.ONE,
    tcgen05.OperandSource.SMEM,
    OperandMajorMode.K,
    OperandMajorMode.K,
)
tiled_mma = cute.make_tiled_mma(op)
```

Shape、major mode 和 TiledMma 的通用含义沿用第 06 章。新增选择是：

- `CtaGroup.ONE/TWO`；
- A 的 `OperandSource.SMEM/TMEM`。

A/B 来自 SMEM 时：

```python
tCrA = tiled_mma.make_fragment_A(sA)
tCrB = tiled_mma.make_fragment_B(sB)
```

这两行只创建 descriptor，没有执行 SMEM→RMEM 或 SMEM→TMEM copy。
真正读取 A/B 发生在 `cute.gemm` 中。

## 5. 创建 TMEM Accumulator

先确定布局：

```python
acc_shape = tiled_mma.partition_shape_C(mma_tiler_mnk[:2])
tCtAcc_layout = tiled_mma.make_fragment_C(acc_shape).layout
```

再提供真实 TMEM storage：

```python
tmem = cutlass.memory.TmemAllocator(...)
tmem.allocate(num_cols=num_tmem_columns)
tmem.wait_for_alloc()

tmem_ptr = tmem.retrieve_ptr(cutlass.Float32)
tCtAcc = cute.make_tensor(tmem_ptr, tCtAcc_layout)
```

三步职责：

```text
make_fragment_C       决定 accumulator layout
TmemAllocator         分配 TMEM storage
make_tensor            绑定 pointer 与 layout
```

## 6. Dense Mainloop 新增的规则

完整代码见
[Blackwell TCGen05 官方 Python 示例导读](官方Python示例导读.md)。
这里只保留三个架构规则：

1. 第一 K tile 使用 `ACCUMULATE=False`，覆盖未初始化的 TMEM；
2. 后续 K tile 使用 `ACCUMULATE=True`；
3. `cute.gemm` 异步返回，SMEM 复用和 TMEM 读取由 UMMA pipeline 管理。

```text
第一个 K tile: D = A0 × B0
后续 K tile:   D = Ak × Bk + D
```

## 7. Single-thread Issue

从 active-mask 角度看，它是一段受控、很短的单-lane 分化：

```text
整个 warp 执行 elect.sync
→ 一个 lane 的 predicate=true
→ 该 lane 发射 TCGen05
→ 其他 lane 在这条指令上 inactive
→ warp 立即重新汇合
```

这种分化不是零成本，但损害较低：

- 只有少量选举和发射指令；
- 没有两个长分支需要串行执行；
- TCGen05 异步提交，发射 lane 不执行整个矩阵乘法；
- 一次发射对应大量 Tensor Core 工作，固定开销容易被摊薄。

异步不会消除 inactive-lane 开销，只会缩短单线程路径占用 warp 的时间。

Single-thread issue 与 Warp specialization 不同：

```text
Single-thread issue:
  一个 warp 内选择一个 lane 发射

Warp specialization:
  一个 CTA 内不同 warp 分别负责 TMA、MMA、epilogue
```

## 8. CTA Group

`CtaGroup.ONE`：一个 CTA 拥有并计算完整 MMA tile。

`CtaGroup.TWO`：两个相邻 CTA 各自拥有 M 方向的一部分，共同完成更大的
MMA。

2CTA 模式还会改变：

- cluster launch；
- GMEM/TMA partition；
- TMA multicast；
- TMEM ownership；
- pipeline/barrier 的参与者。

不能只修改 `CtaGroup` 枚举。

## 9. Epilogue 必须先做 T2R

TCGen05 结束后，结果仍在 TMEM。普通 GMEM store 不能直接读取它：

```text
tCtAcc [TMEM]
  │ tcgen05 T2R copy
  ▼
tTR_rAcc [RMEM]
  │ 类型转换/激活/store
  ▼
gC [GMEM]
```

T2R 前必须由 UMMA pipeline 确认对应 accumulator 已经完成。

## 10. 两个扩展

### A 来自 TMEM

融合 kernel 可以把已有 TMEM 结果作为下一次 MMA 的 A。需要把 A
fragment layout 绑定到对应 TMEM 地址。TMEM 以 32-bit column 组织，
窄类型必须正确换算地址偏移。

### Block-scaled MMA

Dense：

```text
A[SMEM], B[SMEM] → MMA → accumulator[TMEM]
```

Block-scaled：

```text
A[SMEM] + SFA[TMEM]
B[SMEM] + SFB[TMEM]
→ MMA
→ accumulator[TMEM]
```

新增路径是 scale factor 的：

```text
GMEM → SMEM → TMEM
```

因此 SFA/SFB 需要额外的 S2T copy；普通 dense A/B 不需要。

## 11. 相对 WGMMA 的最小差异

| Hopper WGMMA | Blackwell TCGen05 |
|---|---|
| accumulator 位于 RMEM | accumulator 位于 TMEM |
| warpgroup collective issue | elected lane issue |
| `fence/commit/wait_group` | UMMA pipeline/barrier |
| epilogue 从 RMEM 开始 | 先做 T2R |
| 单 CTA | 可选 CTA pair |

## 常见误解

1. **`make_fragment_C` 已经分配 TMEM。**
   它只确定 layout，仍需 `TmemAllocator`。
2. **单线程发射等于单线程计算。**
   一个 lane 只负责提交；矩阵计算由 Tensor Core 完成。
3. **`cute.gemm` 返回后可以立即 T2R。**
   结果完成仍需 UMMA pipeline 保证。
4. **A/B 会先复制到 TMEM。**
   普通 dense 路径直接从 SMEM descriptor 消费 A/B。

## 检查理解

1. TMEM 替代了 RMEM 的哪一部分职责？

   > Hint：区分 accumulator fragment 与通用线程状态。

2. 为什么 single-thread issue 的分化损害较低？

   > Hint：比较发射指令的长度与后台 Tensor Core 工作量。

3. 为什么第一 K tile 使用 `ACCUMULATE=False`？

   > Hint：新分配的 TMEM 是否保证为零？

## 官方示例

- [Blackwell TCGen05 官方 Python 示例导读](官方Python示例导读.md)
- `examples/python/CuTeDSL/cute/blackwell/tutorial/tutorial_gemm/fp16_gemm_0.py`
- `examples/python/CuTeDSL/cute/blackwell/tutorial/tutorial_gemm/fp16_gemm_1.py` 至
  `fp16_gemm_6.py`
- `examples/python/CuTeDSL/cute/blackwell/tutorial/tutorial_gemm/nvfp4_gemm_0.py`
- `examples/python/CuTeDSL/cute/blackwell/kernel/dense_gemm/dense_gemm.py`
