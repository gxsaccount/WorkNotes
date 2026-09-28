# Blackwell TCGen05 官方 Python 示例导读

> 官方教程目录：
> [`examples/python/CuTeDSL/cute/blackwell/tutorial/tutorial_gemm/`](https://github.com/NVIDIA/cutlass/tree/main/examples/python/CuTeDSL/cute/blackwell/tutorial/tutorial_gemm)
>
> 本地源码：[代码实验/fp16_gemm_0.py](代码实验/fp16_gemm_0.py)
>
> 更新：2026-09-28

## 1. 为什么 Blackwell 应从教程系列开始

Ampere 和 Hopper 的官方入口主要是完整 kernel。Blackwell 另外提供了
`fp16_gemm_0.py` 到 `fp16_gemm_6.py` 的渐进系列。

不要一开始阅读 production `dense_gemm.py`。先通过 `fp16_gemm_0.py`
确认最短数据链：

```text
TMA:   GMEM → SMEM
UMMA:  A/B[SMEM] → C/D[TMEM]
T2R:   C/D[TMEM] → RMEM
Store: RMEM → GMEM
```

## 2. 教程系列的演进

| 文件 | 在前一版本上增加的重点 |
|---|---|
| `fp16_gemm_0.py` | 单 CTA dense TCGen05 基础路径 |
| `fp16_gemm_1.py` | 2CTA MMA 与 TMA multicast |
| `fp16_gemm_2.py` | TMA、MMA、epilogue warp specialization；TMA store |
| `fp16_gemm_3.py` | 静态 persistent tile scheduler |
| `fp16_gemm_3_1.py` | 动态 persistent tile scheduler |
| `fp16_gemm_4.py` | dynamic/preferred cluster |
| `fp16_gemm_5.py` | TMA prefetch |
| `fp16_gemm_6.py` | Programmatic Dependent Launch |

推荐顺序：

```text
0 → 1 → 2
```

先建立 TCGen05、CTA pair 和 warp specialization。`3`～`6` 属于调度与
性能工程，可以在第 12 章继续。

## 3. 运行第一个例子

在 CUTLASS 仓库根目录执行：

```bash
python examples/python/CuTeDSL/cute/blackwell/tutorial/tutorial_gemm/fp16_gemm_0.py \
  --mnk 8192,8192,8192
```

该示例要求 M、N 能被默认 tile 的 M、N 整除，并需要 Blackwell SM100
兼容环境。

## 4. `fp16_gemm_0.py` 的固定配置

文件顶部给出：

```text
input/output dtype:  FP16
accumulator dtype:   FP32
instruction shape:   128×256×16
MMA tile:            128×256×64
threads per CTA:     128
A/B stages:          4
accumulator stages:  1
```

因此一个 CTA 的 K tile 包含：

```text
64 / 16 = 4 个 instruction K-block
```

这些数字会同时出现在 SMEM layout、descriptor fragment 和 pipeline
stage 中。

## 5. 按七个检查点阅读 `fp16_gemm_0.py`

### 检查点 1：TCGen05 Operation

搜索：

```text
tcgen05.MmaF16BF16Op
CtaGroup.ONE
OperandSource.SMEM
```

这三个信息说明：

```text
一个 CTA
A 从 SMEM 读取
B 从 SMEM 读取
C/D 位于 TMEM
```

### 检查点 2：TMA atom

搜索：

```text
CopyBulkTensorTileG2SOp
make_tiled_tma_atom_A
make_tiled_tma_atom_B
```

这一段只负责：

```text
A/B: GMEM → staged SMEM
```

它没有把 A/B 放入 TMEM。

### 检查点 3：TMEM allocator

搜索：

```text
TmemAllocator
allocate
wait_for_alloc
retrieve_ptr
```

把过程拆成：

```text
计算需要多少 TMEM column
→ 发起 TMEM allocation
→ 等待 allocation 完成
→ 取得 TMEM pointer
```

### 检查点 4：Accumulator fragment

搜索：

```text
partition_shape_C
make_fragment_C
make_tensor
```

这里有两个不同对象：

```text
fragment layout:
  accumulator 应该如何排布

TMEM pointer:
  accumulator 实际存放在哪里
```

`cute.make_tensor(tmem_ptr, layout)` 把二者绑定为 `tCtAcc`。

### 检查点 5：A/B descriptor

搜索：

```text
make_fragment_A
make_fragment_B
```

确认：

```text
tCrA/tCrB = SMEM descriptor
```

它们不是 A/B register fragment，也没有执行：

```text
SMEM → RMEM
SMEM → TMEM
```

### 检查点 6：UMMA mainloop

搜索：

```text
PipelineTmaUmma.create
Field.ACCUMULATE
cute.gemm
```

还原为：

```python
# pseudocode — illustrative, not runnable
for k_tile in cutlass.range(num_k_tiles):
    full_stage = ab_consumer.wait_and_advance()
    stage = full_stage.index

    tiled_mma.set(tcgen05.Field.ACCUMULATE, k_tile != 0)

    tile = (None, None, None, stage)
    cute.gemm(
        tiled_mma,
        tCtAcc,
        tCrA[tile],
        tCrB[tile],
        tCtAcc,
    )

    full_stage.release()
```

完整伪代码已写到 `/tmp/tcgen05-official-example-pseudocode.py`。

状态变化：

```text
第一个 K tile:
  未定义 TMEM → A0×B0

后续 K tile:
  D → Ak×Bk + D

mainloop 结束:
  最终 accumulator 仍在 TMEM
```

### 检查点 7：TMEM → RMEM

搜索：

```text
Ld32x32bOp
make_tmem_copy
partition_S
partition_D
```

确认 epilogue 起点：

```text
tCtAcc [TMEM]
→ tcgen05 T2R copy
→ register fragment
→ output store
```

如果没有找到这一步，就还没有解释结果如何离开 TMEM。

## 6. `fp16_gemm_1.py`：只观察两个增量

与 `fp16_gemm_0.py` 对比：

```text
CtaGroup.ONE → CtaGroup.TWO
普通 TMA     → TMA multicast
```

阅读时只问：

1. 两个 CTA 各自负责 M 方向的哪一部分？
2. 哪些 A/B 数据能够通过 multicast 复用？
3. 为什么 B 的每 CTA SMEM 占用可以降低？
4. cluster barrier 中需要哪些参与者？

不要重新分析 `make_fragment_C` 和 T2R；它们与第一个例子的核心目的相同。

## 7. `fp16_gemm_2.py`：只观察角色拆分

该版本把 CTA 中的 warp 分为：

```text
TMA warp
MMA warp
epilogue warp
```

与 `fp16_gemm_1.py` 相比，数学运算没有改变。新增的是任务并行：

```text
TMA warp:      准备后续 A/B stage
MMA warp:      消费当前 stage 并更新 TMEM
epilogue warp: 读取已完成的 TMEM accumulator
```

这一版本还使用 TMA store，因此输出路径变为：

```text
TMEM → RMEM → SMEM → GMEM
```

## 8. 后续版本放到性能工程阶段

### `fp16_gemm_3.py`

静态 persistent scheduler：CTA 常驻并按固定方式领取多个 output tile。

### `fp16_gemm_3_1.py`

动态 persistent scheduler：运行时分配 tile，更能适应负载不均。

### `fp16_gemm_4.py`

Dynamic/preferred cluster：提供 preferred 与 fallback cluster shape。

### `fp16_gemm_5.py`

TMA prefetch：在真正需要数据前，把后续 tile 提前带入 L2。

### `fp16_gemm_6.py`

Programmatic Dependent Launch：允许存在依赖的相邻 kernel 部分重叠。

这些版本主要回答“如何进一步提高利用率”，不是理解 TCGen05
数据路径的前置条件。

## 9. Block-scaled 入门

文件：

```text
examples/python/CuTeDSL/cute/blackwell/tutorial/tutorial_gemm/nvfp4_gemm_0.py
```

在 dense 路径之外增加：

```text
SFA/SFB: GMEM → SMEM → TMEM
```

先读懂 `fp16_gemm_0.py` 中：

```text
A/B[SMEM] → MMA → accumulator[TMEM]
```

再学习 scale factor 的 S2T copy，避免把普通 A/B 与 scale factor
的数据路径混在一起。

## 10. Production 示例

完成教程后再看：

```text
examples/python/CuTeDSL/cute/blackwell/kernel/dense_gemm/
├── dense_gemm.py
├── dense_gemm_persistent.py
├── dense_gemm_persistent_dynamic.py
└── dense_gemm_persistent_prefetch.py
```

Production kernel 会加入更多 dtype、布局、调度和性能分支，不适合作为
第一个 TCGen05 示例。

## 检查理解

1. 在 `fp16_gemm_0.py` 中，哪一步把 A/B 从 SMEM 复制到 TMEM？

   > Hint：普通 dense 路径中不存在这一步。

2. `make_fragment_C` 和 `TmemAllocator` 为什么缺一不可？

   > Hint：一个提供 layout，一个提供 storage。

3. `fp16_gemm_1.py` 相比 `fp16_gemm_0.py` 改变的是数学计算，还是
   CTA 协作与数据搬运方式？

   > Hint：两者都计算相同的 `D=A×B+C`。

4. 为什么 `fp16_gemm_2.py` 仍需要 pipeline，即使 MMA 只由一个线程
   发射？

   > Hint：考虑 TMA、UMMA 和 epilogue 三种角色之间的数据所有权。
