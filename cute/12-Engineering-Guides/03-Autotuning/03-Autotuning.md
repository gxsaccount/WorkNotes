# GEMM Autotuning：搜索、测量与缓存

> 官方文档：[Autotuning with the DSL](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/autotuning_gemm.html)
>
> 更新：2026-09-28

## 核心目标

Autotuning 不是寻找“全局最优 GEMM 配置”，而是为一类具体输入选择
最快的合法 kernel：

```text
输入特征
  = GPU + dtype + layout + M/N/K + batch + 对齐

候选配置
  = tile + cluster + stage + 指令模式 + 调度策略

输出
  = 已编译 kernel + 测量结果
```

## 1. 正确顺序

```text
生成候选
→ 静态过滤非法配置
→ 编译并缓存
→ 数值正确性检查
→ warmup
→ 多次计时
→ 选择最佳配置
→ 缓存输入到配置的映射
```

不能把编译失败、运行失败或结果错误的配置简单记成“比较慢”。它们应记录为
明确的 invalid/error 状态。

## 2. 搜索空间

以 Blackwell persistent GEMM 为例，官方指南列出的核心参数包括：

- `mma_tiler_mn`；
- `cluster_shape_mn`；
- `use_2cta_instrs`；
- `use_tma_store`。

实际 kernel 还常包含：

- A/B pipeline stage 数；
- accumulator/epilogue stage 数；
- persistent 或非 persistent scheduler；
- dtype、major mode 和输出布局；
- split-K、prefetch distance 等算法选项。

搜索空间必须由 kernel 的合法性约束生成，而不是任意做笛卡尔积。

### 常见静态约束

```text
tile 必须兼容 MMA instruction shape
cluster shape 必须满足架构限制
SMEM 总量不能超过每 CTA 上限
TMEM column 数不能超过架构上限
线程数不能超过 block 上限
向量 copy 必须满足对齐和整除
2CTA 指令必须配套正确 cluster
```

先过滤这些配置，可以避免大量无意义编译。

## 3. 两层缓存

### 编译缓存

同一个 kernel 配置只编译一次：

```python
kernel_key = (
    ab_dtype,
    c_dtype,
    acc_dtype,
    use_2cta_instrs,
    mma_tiler_mn,
    cluster_shape_mn,
    use_tma_store,
)

if kernel_key not in compiled_kernels:
    compiled_kernels[kernel_key] = cute.compile(
        kernel,
        a,
        b,
        c,
        stream,
    )

compiled = compiled_kernels[kernel_key]
```

如果输入 layout 中包含静态 Shape/Stride，它们也会影响生成代码，应进入
cache key。

### 调优结果缓存

一个输入类别只调优一次：

```python
input_key = (
    gpu_arch,
    m,
    n,
    k,
    batch,
    a_dtype,
    b_dtype,
    c_dtype,
    a_layout,
    b_layout,
    c_layout,
)

best_config = tuning_results[input_key]
```

可将 Shape 映射到 bucket 以减少 key 数量，但必须测量 bucket 化是否造成
明显性能损失。

## 4. 最小调优循环

```python
# pseudocode — illustrative, not runnable
best = None

for config in candidate_configs:
    validity = validate_static_constraints(config, problem, hardware)
    if not validity.ok:
        record(config, status="invalid", reason=validity.reason)
        continue

    try:
        compiled = get_or_compile(config, problem)
        verify_against_reference(compiled, problem)
        timing = benchmark_with_cuda_events(
            compiled,
            warmup=10,
            iterations=200,
        )
    except Exception as error:
        record(config, status="error", reason=str(error))
        continue

    record(config, status="ok", timing=timing)

    if best is None or timing.median < best.timing.median:
        best = Result(config, compiled, timing)

if best is None:
    raise RuntimeError("no valid and correct kernel configuration")
```

完整伪代码已写到 `/tmp/cute-gemm-autotuning-pseudocode.py`。

与官方最小示例相比，这里额外强调：

- 失败必须保留原因，不能静默跳过；
- 性能比较前必须验证数值正确性；
- 使用 median/分位数比只看一次耗时更稳健。

## 5. Benchmark 规则

```text
warmup:       通常 5～10 次起步
timed runs:   根据 kernel 时长选择足够样本
计时工具:     CUDA event
同步位置:     计时区间结束后明确等待
统计量:       min + median + P90/P95
环境:         固定 GPU、频率策略和输入
```

不要把下面时间混入 kernel 时间：

- 第一次 import；
- JIT compilation；
- DLPack conversion；
- tensor allocation；
- CPU reference；
- profiler instrumentation。

除非测量目标本来就是端到端延迟。

## 6. 根据瓶颈缩小搜索空间

### Register/occupancy 受限

优先尝试：

- 减小每 warp/warpgroup 的 output tile；
- 减少 accumulator 数量；
- 调整 warpgroup 数；
- 检查 register spill。

### SMEM 容量受限

优先尝试：

- 减少 A/B stage；
- 调整 tile；
- 使用 2CTA 后重新计算每 CTA 的 operand storage；
- 检查 epilogue buffer 是否可以缩小。

### DRAM latency 受限

优先尝试：

- 增加合法 pipeline stage；
- TMA multicast；
- persistent scheduling；
- prefetch。

### Tensor Core 利用率低

优先检查：

- tile 数量是否足够填满 GPU；
- MMA warp 是否长期等待；
- instruction shape 是否适合问题 Shape；
- 边界 tile 比例是否过高。

Autotuning 应验证 profiling 提出的假设，而不是替代 profiling。

## 7. 结果记录

至少记录：

```text
GPU/SM architecture
CUDA、driver、CUTLASS DSL 版本
git commit
M/N/K/batch
dtype 和 layout
全部 kernel 参数
编译状态
正确性结果和容差
warmup/iterations
min/median/P95
TFLOP/s 或 bandwidth
失败原因
```

否则最优配置无法复现，也无法判断性能变化来自代码还是环境。

## 常见错误

1. **把 JIT 时间算入每个候选的 kernel 时间。**
2. **所有输入共用一个最佳配置。**
3. **cache key 漏掉 dtype、layout 或静态 Shape。**
4. **只测一次并选择偶然的最小值。**
5. **不检查结果正确性。**
6. **同时改变 tile、stage、cluster 和算法，无法解释结果。**
7. **把异常吞掉，只留下 `inf`，之后无法定位非法配置原因。**

## 检查理解

1. 编译缓存和调优结果缓存分别以什么为 key？

   > Hint：一个对应生成的程序，一个对应实际输入类别。

2. 为什么 occupancy 低不能直接推出“应该减小 tile”？

   > Hint：先判断当前是否已经有效隐藏延迟。

3. 某配置性能最好但偶尔结果错误，能否保留为候选？

   > Hint：正确性是进入性能比较的门槛。
