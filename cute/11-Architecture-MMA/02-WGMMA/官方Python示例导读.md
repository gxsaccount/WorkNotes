# Hopper WGMMA 官方 Python 示例导读

> 官方源码：
> [`examples/python/CuTeDSL/cute/hopper/kernel/dense_gemm/dense_gemm.py`](https://github.com/NVIDIA/cutlass/blob/main/examples/python/CuTeDSL/cute/hopper/kernel/dense_gemm/dense_gemm.py)
>
> 更新：2026-09-28

## 1. 阅读目标

不要试图一次读懂这个生产级 kernel。第一次只验证从 Ampere 到 Hopper
发生的三处变化：

```text
Ampere                         Hopper
────────────────────────      ────────────────────────
warp MMA                      warpgroup MMA
A/B RMEM fragment             A/B SMEM descriptor
同步 mma.sync                 异步 WGMMA group
```

TMA、CTA tiling 和通用 epilogue 已在前面章节学习，本导读只标出它们与
WGMMA 的连接位置。

## 2. 运行入口

在 CUTLASS 仓库根目录执行：

```bash
python examples/python/CuTeDSL/cute/hopper/kernel/dense_gemm/dense_gemm.py \
  --mnkl 8192,8192,8192,1 \
  --tile_shape_mn 128,256 \
  --cluster_shape_mn 1,1 \
  --a_dtype Float16 \
  --b_dtype Float16 \
  --c_dtype Float16 \
  --acc_dtype Float32 \
  --a_major k \
  --b_major k \
  --c_major n
```

需要 Hopper SM90a 兼容环境。

## 3. 先画出唯一需要追踪的路径

```text
mA/mB [GMEM]
    │ TMA
    ▼
sA/sB[stage] [SMEM]
    │ descriptor
    ▼
tCrA/tCrB
    │ WGMMA
    ▼
acc [RMEM]
```

这一图中最容易误解的是：

```text
tCrA/tCrB 是 descriptor，不是从 SMEM 复制出的 A/B register values。
```

## 4. 按五个检查点阅读

### 检查点 1：WGMMA Operation

搜索：

```text
make_trivial_tiled_mma
MmaF16BF16Op
MmaF8Op
MmaI8Op
```

官方 helper 根据数据类型、major mode 和 tile shape 选择具体 WGMMA
Operation。最终得到的 `tiled_mma` 仍然遵守第 06 章接口。

### 检查点 2：TMA pipeline

搜索：

```text
PipelineTmaAsync.create
```

这一 pipeline 回答：

```text
哪个 SMEM stage 正在由 TMA 写入？
哪个 stage 已经可以被 WGMMA 消费？
哪个 stage 可以交还给 producer？
```

不要把它与 WGMMA 的 async group 混为一谈：

```text
TMA pipeline:       管输入是否到达 SMEM
WGMMA async group:  管矩阵乘加是否完成
```

### 检查点 3：Descriptor fragment

搜索：

```text
make_fragment_A
make_fragment_B
```

对应关系：

```text
tCsA/tCsB = partition 后的 SMEM view
tCrA/tCrB = WGMMA 可读取的 SMEM descriptor
```

然后在整个文件中搜索 `LdMatrix`。标准 SMEM×SMEM WGMMA 主路径没有
Ampere 示例中的 A/B `ldmatrix` tiled copy。

### 检查点 4：WGMMA group

搜索：

```text
warpgroup.fence
warpgroup.commit_group
warpgroup.wait_group
```

把它们和 `cute.gemm` 连起来阅读：

```text
等待 TMA stage
→ fence
→ 一次或多次 cute.gemm
→ commit_group
→ wait_group(n)
```

状态变化：

```text
SMEM stage:
LOADING → FULL → WGMMA_READING → REUSABLE

accumulator:
旧值 → 被异步 group 更新 → wait 后可安全读取
```

### 检查点 5：最终 drain

搜索：

```text
wait_group(0)
```

确认它位于依赖最终 accumulator 的 epilogue 之前。

主循环中的 `wait_group(n)` 可以保留若干 group 在 flight；只有
`wait_group(0)` 才表示所有已提交 WGMMA 都已排空。

## 5. 用 Ampere diff 阅读代码

不要从文件第一行顺序读到最后一行。把它与 Ampere 示例做差：

```text
删除：
- A/B LdMatrix copy atom
- A/B register fragment 的 retile
- 每个 K-block 的显式 SMEM→RMEM copy

新增：
- warpgroup 角色和 warpgroup slice
- SMEM descriptor fragment
- fence/commit_group/wait_group
- TMA producer 与 WGMMA consumer 的 stage 生命周期

保持不变：
- CTA 选择 GMEM tile
- TMA 把输入送到 staged SMEM
- accumulator 沿 K 累加
- epilogue 把结果写回 GMEM
```

## 6. Mainloop 的最小还原

```python
# pseudocode — illustrative, not runnable
# 输入已经由 TMA 写入 staged SMEM。

acc.fill(0.0)

for k_tile in cutlass.range(num_k_tiles):
    full_stage = ab_consumer.wait_and_advance()
    stage = full_stage.index

    warpgroup.fence()
    tile = (None, None, None, stage)
    cute.gemm(tiled_mma, acc, tCrA[tile], tCrB[tile], acc)
    warpgroup.commit_group()
    warpgroup.wait_group(max_groups_in_flight)

    full_stage.release()

warpgroup.wait_group(0)
```

完整伪代码已写到 `/tmp/wgmma-official-example-pseudocode.py`。

这段骨架中：

- `tCrA/tCrB` 没有保存完整 A/B 值；
- `cute.gemm` 发射 WGMMA，但不保证已经完成；
- descriptor 指向的 stage 不能在 WGMMA 消费结束前被覆盖；
- `acc` 位于 RMEM。

## 7. 读完基础示例再看什么

### Persistent GEMM

```text
examples/python/CuTeDSL/cute/hopper/kernel/dense_gemm/
  dense_gemm_persistent.py
```

新增问题：一个常驻 CTA/cluster 如何连续领取多个 output tile。

### A 来自 RMEM

```text
examples/python/CuTeDSL/cute/hopper/kernel/attention/fmha.py
```

新增问题：前一次计算产生的 RMEM 数据怎样成为下一次 WGMMA 的 A。

不要在第一次阅读 `dense_gemm.py` 时同时学习这两项扩展。

## 检查理解

1. 为什么代码中仍有 `tCrA`，却找不到对应的 `ldmatrix`？

   > Hint：检查它的内容是 value 还是 descriptor。

2. `PipelineTmaAsync` 和 `wait_group(0)` 分别等待什么？

   > Hint：前者保护输入，后者保护计算结果。

3. 如果 descriptor 指向 stage 1，而 producer 提前覆盖 stage 1，会发生
   什么？

   > Hint：descriptor 不保存数据副本。
