# TMA Multicast：一次源读取，为多个 CTA 填充 SMEM

> 官方资料：
> [CUDA Hopper Tuning Guide](https://docs.nvidia.com/cuda/hopper-tuning-guide/index.html)、
> [CuTe TMA Tensors](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0z_tma_tensors.html)
>
> 更新：2026-09-28

## 1. 它解决什么问题

**TMA multicast 主要适用于同一 cluster 内多个 CTA 在相近时间需要
同一个全局内存 tile 的场景。**

例如，两个 CTA 沿 GEMM 的 M 方向排列：

```text
CTA 0:
C[M0,N0] = A[M0,K0] × B[N0,K0]

CTA 1:
C[M1,N0] = A[M1,K0] × B[N0,K0]
```

它们需要不同的 A tile：

```text
CTA 0 使用 A[M0,K0]
CTA 1 使用 A[M1,K0]
```

但需要完全相同的 B tile：

```text
CTA 0 使用 B[N0,K0]
CTA 1 使用 B[N0,K0]
```

不使用 multicast 时，两个 CTA 分别加载一次 `B[N0,K0]`；使用
multicast 时，一次 TMA 操作把它分发到两个 CTA 各自的 SMEM：

```text
                         ┌→ CTA 0 的 sB
B[N0,K0] ─ TMA multicast┤
                         └→ CTA 1 的 sB
```

## 2. 不使用 Multicast

每个 CTA 都发起独立的 TMA load：

```text
                         ┌─ TMA load 0 ─→ CTA 0 的 sB
B[N0,K0] [GMEM，经 L2] ──┤
                         └─ TMA load 1 ─→ CTA 1 的 sB
```

虽然第二次读取可能命中 L2，但仍然存在：

- 两个独立的 TMA 请求；
- 两次源侧读取处理；
- 两份从 L2/片上互连送往 CTA 的数据传输。

假设 B tile 为 32 KiB：

```text
源侧向 CTA 0 提供 32 KiB
源侧向 CTA 1 再提供 32 KiB

合计约 64 KiB 的重复源侧传输
```

这里不应简单说“读取了两次 HBM”，因为第二次请求是否访问 HBM 取决于
L2 cache 是否命中。

## 3. 使用 TMA Multicast

软件构造 multicast TMA 操作，并指定哪些 CTA 是目标：

```text
                          ┌→ CTA 0 的 sB
B[N0,K0] ─ TMA multicast ┤
                          └→ CTA 1 的 sB
```

执行结果是：

```text
CTA 0 的 SMEM 中有一份 B tile
CTA 1 的 SMEM 中也有一份 B tile
```

两个 CTA 并没有共用同一块 shared memory。它们仍有各自的 SMEM
destination，只是由一次 multicast 操作同时填充。

## 4. Multicast 到底节省什么

**TMA multicast 的本质是复用 cluster 内多个 CTA 共同需要的输入
tile，减少冗余的 GMEM/L2 读取请求；当这些请求原本需要访问显存时，
也会相应降低 HBM 流量。**

仍以 32 KiB B tile、两个 CTA 为例：

```text
普通 TMA:        两个 CTA 各自请求 32 KiB
TMA multicast:   一次源 tile 请求，分发到两个 SMEM destination
```

它减少：

- 重复的 GMEM/L2 读取请求；
- L2 向 cluster 输送相同 tile 的重复流量；
- 多个 CTA 重复执行的 TMA load；
- producer 侧的指令和地址准备。

它不减少：

- tile 本身包含的逻辑数据；
- 每个 CTA 为该 tile 预留的 SMEM；
- 向各 CTA 的 SMEM 写入副本所需的目标侧工作。

因此更准确的性能术语是：

```text
减少冗余的 GMEM/L2 读取请求
降低源侧 L2 read traffic
```

而不是笼统地说“减少重复流量”或“保证 HBM 只读一次”。

## 5. 为什么 GEMM 中容易共享输入 tile

### Cluster 沿 M 方向排列

```text
CTA 0: C[M0,N0]
CTA 1: C[M1,N0]
```

两者共享：

```text
B[N0,K]
```

因此 B 适合沿 cluster-M multicast。

### Cluster 沿 N 方向排列

```text
CTA 0: C[M0,N0]
CTA 1: C[M0,N1]
```

两者共享：

```text
A[M0,K]
```

因此 A 适合沿 cluster-N multicast。

### 二维 cluster

```text
CTA(m,n)
```

一般规律：

```text
相同 m、不同 n 的 CTA 共享 A
相同 n、不同 m 的 CTA 共享 B
```

具体 multicast mask 由 cluster layout 和当前 CTA 坐标计算。

## 6. 谁负责决定，谁负责执行

Multicast 不是 GPU cache 自动推断出来的。

### 软件负责

- 选择 cluster shape；
- 判断哪些 CTA 共享 A/B tile；
- 选择 multicast TMA copy op；
- 构造目标 CTA mask；
- 建立 cluster-aware pipeline 和 barrier；
- 保证所有目标 CTA 的 SMEM destination 有效。

在 CuTe DSL 中会看到类似：

```text
CopyBulkTensorTileG2SMulticastOp
```

而不是普通：

```text
CopyBulkTensorTileG2SOp
```

### 硬件负责

软件提交 multicast 请求后，TMA 硬件负责：

```text
读取源 tensor tile
→ 在 cluster 数据通路中分发
→ 写入 mask 指定的各 CTA SMEM
→ 更新完成同步状态
```

因此：

> 是否使用 multicast 是软件策略；具体的一对多数据分发由硬件完成。

高层库可能在内部选择带 multicast 的 kernel，所以 cuBLAS 用户未必看到
这些配置；编写 CuTe/CUTLASS kernel 时则需要明确选择。

## 7. 与普通 Broadcast 的区别

TMA multicast 不是让所有线程读取一个寄存器值：

```text
warp broadcast:
一个 lane 的值 → 同一 warp 的其他 lane
```

也不是让 CTA 共享同一块 SMEM：

```text
错误理解：
CTA 0 和 CTA 1 指向同一物理 SMEM tile
```

它是一次数据搬运产生多个目标副本：

```text
同一个 GMEM tile
→ CTA 0 的 SMEM 副本
→ CTA 1 的 SMEM 副本
→ ...
```

## 8. 同步与生命周期

目标 CTA 不能因为“multicast 已发射”就立即读取 SMEM。

```text
发射 TMA multicast
→ TMA 正在读取和分发
→ cluster-aware mbarrier/pipeline 报告完成
→ 各目标 CTA 才能消费自己的 SMEM tile
```

同样，在 WGMMA/TCGen05 仍读取该 stage 时，不能提前覆盖：

```text
EMPTY
→ TMA_MULTICAST_LOADING
→ FULL
→ MMA_READING
→ EMPTY
```

Multicast 解决的是“一份输入如何送到多个 CTA”，不替代 producer/
consumer 同步。

## 9. 什么时候值得使用

适合：

- cluster 中多个 CTA 确实共享同一个 A 或 B tile；
- 共享 tile 较大；
- L2/GMEM 带宽是重要瓶颈；
- cluster shape 能与问题 Shape 良好匹配。

不一定适合：

- 每个 CTA 使用完全不同的数据；
- tile 很小；
- cluster 导致明显的 SM 空闲或 occupancy 损失；
- multicast 的同步和调度成本超过节省的读取成本；
- 问题边界产生大量不完整 cluster。

所以 multicast 不是“打开就一定更快”，需要结合 profiling 和 autotuning
选择 cluster shape。

## 检查理解

1. 两个沿 M 方向排列的 GEMM CTA 通常共享 A 还是 B？

   > Hint：比较 `C[M0,N0]` 与 `C[M1,N0]`。

2. Multicast 后，两个 CTA 是否访问同一块物理 SMEM？

   > Hint：每个 CTA 最终仍然需要自己的目标副本。

3. 为什么不能保证 multicast 让 HBM 流量严格减半？

   > Hint：普通第二次读取可能已经命中 L2。

4. 谁决定 multicast mask：硬件自动推断，还是 kernel/library？

   > Hint：区分策略选择和硬件执行。
