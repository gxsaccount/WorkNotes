# Profiling：先回答“慢在哪里”

> 官方资料：
> [IKET Profiling](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/iket_profiling.html)
>
> 更新：2026-09-28

## 三类工具不要混用

| 工具 | 主要回答 |
|---|---|
| CUDA event/benchmark | 整个 kernel 到底多快？ |
| Nsight Compute | 指令、吞吐、occupancy、stall 的硬件原因是什么？ |
| IKET | kernel 内各 warp role、pipeline wait 和阶段边界在哪里？ |

如果需要观察 CPU/GPU 调度、多个 kernel 的 overlap 或 launch gap，应使用
Nsight Systems，而不是 IKET。

## 1. 先建立可信的基准时间

```text
固定输入和 dtype
→ warmup
→ 多次测量
→ 每次使用 CUDA event
→ 必要时固定频率
→ 报告 min/median/分位数
```

最低要求：

- warmup 后再计时；
- 每个配置运行多次；
- 计时区间只包含目标工作；
- 比较前确认结果正确；
- 不在 Debug Mode 或 IKET instrumentation 下报告最终性能；
- 明确问题 Shape、dtype、layout、GPU 和软件版本。

理论 GEMM 工作量：

```text
FLOPs ≈ 2 × M × N × K × batch
TFLOP/s = FLOPs / time_seconds / 1e12
```

## 2. Nsight Compute：从症状到原因

基础命令：

```bash
ncu --set basic --target-processes all \
  python your_kernel.py
```

需要完整报告时：

```bash
ncu --set full --target-processes all \
  -o report \
  python your_kernel.py
```

不要一开始收集所有 section。完整采集可能多次 replay kernel，时间长，
还可能改变缓存状态。先从问题选择指标。

### 判断顺序

#### 1. Kernel 是否真的被 Tensor Core 加速

查看：

- 生成 PTX/SASS 是否包含预期 MMA 指令；
- Tensor Core 相关 pipe 是否活跃；
- 实际吞吐是否与问题规模匹配。

如果没有生成预期指令，先回到 Debugging，不要调整 tile。

#### 2. 计算受限还是内存受限

观察：

- SM/Tensor Core 吞吐；
- DRAM、L2、SMEM 吞吐；
- arithmetic intensity；
- 各 pipeline 的利用率。

```text
Tensor Core 高、DRAM 不高
  → 更像 compute-bound

DRAM 高、Tensor Core 等数据
  → 更像 memory-bound

两者都低
  → 检查 occupancy、stall、launch 和 tile 数量
```

#### 3. Occupancy 为什么低

依次检查：

- 每线程寄存器；
- 每 CTA shared memory；
- block/cluster 大小；
- active warps/CTAs；
- register spill 到 local memory。

Occupancy 不是越高越好。只要延迟已被有效隐藏，提高 occupancy 未必提升
性能。

#### 4. Warp 在等什么

查看 scheduler 和 warp-state 指标：

```text
长时间等待 memory dependency
  → 检查 TMA/copy pipeline 和 tile 复用

长时间等待 barrier
  → 检查 producer/consumer 不平衡

eligible warp 很少
  → 检查 occupancy、依赖链和 warp specialization
```

## 3. IKET：观察 kernel 内时间线

IKET 是 CuTe DSL 的实验性 In-Kernel Event Tracing。它让 device kernel
发出 marker/range，由 `run-iket` 收集并生成 Perfetto/JSON trace。

先确认工具存在：

```bash
run-iket --help
```

### 最小插桩

```python
@cute.kernel
def kernel(...):
    cute.experimental.iket.range_push("mainloop")
    # mainloop
    cute.experimental.iket.range_pop()
```

常用 API：

| API | 用途 |
|---|---|
| `mark(name, payload?)` | 一个时间点 |
| `range_push(name)` / `range_pop()` | 结构化、嵌套区间 |
| `range_start(name)` / `range_end(token)` | 跨作用域或跨迭代区间 |
| `sentinel_token(name)` | 初始化跨迭代 token，不产生真实事件 |

只在 `@cute.kernel` 内插桩。Host 侧 `@cute.jit` 中调用不会产生
in-kernel event。

### 运行

```bash
run-iket profile --postprocess perfetto -- \
  python examples/python/CuTeDSL/dsl_tutorials/fp16_gemm_4_iket.py \
  --mnk 512,1024,64
```

然后在 Perfetto 中打开生成的 `.pftrace`。

## 4. 异步操作应该测 issue 还是 wait

这是 IKET 最重要的判断。

```python
issue = cute.experimental.iket.range_start("tma_issue", k_tile)
cute.copy(tma_atom, src, dst, tma_bar_ptr=barrier)
cute.experimental.iket.range_end(issue, k_tile)
```

这个 range 测量的是：

```text
CPU/GPU 指令发射附近的时间
```

它不代表 TMA 数据已经到达。

若要观察等待：

```python
cute.experimental.iket.range_push("ab_wait")
full_stage = ab_consumer.wait_and_advance()
cute.experimental.iket.range_pop()
```

这个 range 才表示 consumer 因数据未就绪而阻塞多久。

同理：

```text
围住 cute.gemm
  通常测 issue 端代码

围住 pipeline/mbarrier wait
  测等待完成的可观察边界
```

## 5. Warp-specialized kernel 的插桩

按角色命名：

```text
tma_main
tma_acquire
tma_issue
mma_main
mma_wait
mma_issue
epilogue
```

range 的开始和结束必须位于同一 warp role 和兼容控制流中：

```python
if warp_idx == tma_warp_id:
    iket.range_push("tma_main")
    # producer work
    iket.range_pop()

if warp_idx == mma_warp_id:
    iket.range_push("mma_main")
    # consumer work
    iket.range_pop()
```

不要在一个发散分支中开始 range，在另一个分支中结束。

## 6. IKET 使用边界

- 事件以 warp 为粒度；
- event name 最长 32 个字符；
- unique name 超过约 30 个时编码和开销可能增加；
- 不要在最内层 unrolled loop 中高频插桩；
- `cutlass.range(..., prefetch_stages=...)` 内当前不支持 IKET range；
- profiled kernel 必须在 `run-iket` 进程中重新 JIT；
- IKET 与 Nsight Compute、Nsight Systems 等 CUPTI profiler 不能同时运行；
- IKET 适合 kernel 内时间线，不适合测 host launch latency。

## 7. 一个实用分析闭环

```text
1. CUDA event
   确认性能回归真实存在

2. Nsight Compute
   判断 compute、memory、occupancy 或 stall

3. IKET
   若怀疑 pipeline/warp-role 不平衡，定位等待发生在哪一段

4. 修改一个变量
   tile、stage、cluster、角色分配或 epilogue

5. 重新做 correctness + benchmark
```

不要根据单个指标直接下结论。例如“occupancy 低”只是现象，需要继续判断
是否真的导致 Tensor Core 缺少可执行工作。

## 最短检查表

```text
[ ] 结果正确吗？
[ ] benchmark 是否 warmup、多次运行并使用设备计时？
[ ] 是否生成预期 MMA 指令？
[ ] 瓶颈是 compute、DRAM、SMEM、occupancy 还是 wait？
[ ] IKET 测的是 issue 还是 completion boundary？
[ ] 插桩是否改变了需要报告的最终性能？
[ ] 每次实验是否只改变一个主要变量？
```
