# TMA 相比 `cp.async` 的优化

> 官方资料：
> [CUDA Hopper Tuning Guide](https://docs.nvidia.com/cuda/hopper-tuning-guide/index.html)、
> [CuTe TMA Tensors](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0z_tma_tensors.html)
>
> 更新：2026-09-28

## 1. 一句话结论

`cp.async` 已经实现了不经过通用寄存器的数据异步搬运；TMA 的进一步改进
是：

> **只需少量线程发出大粒度的多维 tile 搬运请求，再由专用硬件负责地址
> 生成、布局适配、异步传输和可选 multicast。**

所以 TMA 的优势不能只概括为“异步”或“不使用寄存器”，因为
`cp.async` 也具备这两个特征。

## 2. 三种搬运方式

### 普通 load/store

```text
GMEM
  │ load
  ▼
RMEM
  │ store
  ▼
SMEM
```

线程既负责计算地址，也用自己的寄存器中转 payload。

### `cp.async`

```text
GMEM
  │ 每个线程发出若干小粒度异步 copy
  ▼
SMEM
```

Payload 可以绕过 RMEM，但仍然需要：

```text
多个线程参与
→ 每个线程计算自己的源地址和目标地址
→ 每个线程发出多条 copy
→ 所有线程共同覆盖完整 tile
```

### TMA

```text
一个线程提交：
TMA descriptor
+ tile coordinate
+ SMEM 地址
+ completion barrier
        │
        ▼
TMA 硬件完成整个多维 tile 搬运
```

这里的“一个线程”是指发射请求。整个 CTA 或 cluster 仍然需要通过
pipeline/barrier 等待并消费结果。

## 3. 优化一：减少搬运指令

假设需要搬运一个较大的 A tile。

`cp.async` 的组织方式：

```text
线程 0 负责若干小块
线程 1 负责若干小块
...
线程 127 负责若干小块
```

每个线程需要生成地址并发射 copy 指令。

TMA 的组织方式：

```text
一个 elected thread
→ 提交整个 tensor tile 的搬运
→ TMA 硬件遍历 tile
```

因此减少的是：

- 动态 copy 指令数量；
- producer warp 的指令发射压力；
- 每线程地址计算；
- 保存地址和循环状态所需的寄存器。

TMA 不会减少实际需要经过内存系统的数据字节数。

## 4. 优化二：硬件完成多维地址生成

使用 `cp.async` 时，线程通常显式计算：

```text
global_offset(thread, iteration)
shared_offset(thread, iteration)
边界 predicate
```

TMA descriptor 则描述：

- GMEM base pointer；
- tensor rank、Shape 和 Stride；
- tile box；
- element stride；
- interleave；
- SMEM swizzle；
- 越界行为。

运行时只需提供 tile coordinate，TMA 硬件就能生成 tile 内的地址。

## 5. 优化三：搬运时完成受支持的布局适配

TMA 可以从一种 GMEM 物理布局读取，并写入适合 Tensor Core 的
SMEM swizzled layout。

```text
逻辑坐标保持不变：
A(m,k) → A(m,k)

物理地址发生变化：
gmem_layout(m,k)
→ smem_swizzled_layout(m,k)
```

例如：

```text
GMEM：普通 strided row-major tile
              │ TMA
              ▼
SMEM：适合 WGMMA/TCGen05 descriptor 的 swizzled tile
```

这不是任意 Layout Algebra 引擎。TMA 只能执行 tensor map 和具体
TMA 指令支持的布局转换。

`cp.async` 也能实现布局重排，但地址对应关系需要由线程布局和每线程
copy 显式表达；TMA 把常见的规则多维映射交给 descriptor 和硬件。

## 6. 优化四：支持 Cluster Multicast

多个 CTA 需要相同输入 tile 时，软件可以显式选择 TMA multicast，让一次
源 tile 读取填充多个 CTA 各自的 SMEM，从而减少冗余的 GMEM/L2
读取请求。它不会让 CTA 共用同一块 SMEM。

原理、GEMM 中 A/B 的共享方向和软件职责见
[TMA Multicast：一次源读取，为多个 CTA 填充 SMEM](TMA-Multicast.md)。

## 7. 优化五：更适合 Warp Specialization

`cp.async` 通常由一组线程共同发出许多 copy：

```text
producer threads:
  地址计算 + copy issue
```

TMA 可以让一个 elected thread 发起整个 tile：

```text
TMA producer warp:
  一个线程发起 TMA

MMA consumer warpgroup:
  执行 WGMMA/TCGen05
```

这样 producer 侧的其他线程不需要各自承担 tile 搬运指令，更适合把 CTA
划分成 TMA、MMA 和 epilogue 等角色。

## 8. 优化六：与 MMA 形成深流水

TMA 和 MMA 是两套不同的异步操作：

```text
TMA:
  GMEM → SMEM

WGMMA/TCGen05:
  消费 SMEM/TMEM operand
  → 更新 accumulator
```

它们可以同时推进：

```text
时间 ─────────────────────────────────►

TMA:       load K1     load K2     load K3
MMA:       compute K0  compute K1  compute K2
```

SMEM stage 的生命周期通常是：

```text
EMPTY
→ TMA_LOADING
→ FULL
→ MMA_READING
→ EMPTY
```

对应同步职责：

```text
TMA pipeline/mbarrier:
  当前输入是否已经到达 SMEM？

WGMMA group 或 UMMA pipeline:
  MMA 是否还在读取该 SMEM stage？
```

只有两个条件都满足，producer 才能覆盖该 stage。

## 9. TMA Store

TMA 不只支持输入路径：

```text
GMEM → SMEM
```

也支持输出路径：

```text
SMEM → GMEM
```

典型 epilogue：

```text
accumulator
→ RMEM output fragment
→ SMEM epilogue tile
→ TMA store
→ GMEM
```

TMA store 可以减少线程逐元素执行 GMEM store 的指令和地址计算。

## 10. TMA 与 WGMMA/TCGen05 的位置

```text
Ampere Warp MMA:
GMEM ─cp.async→ SMEM ─ldmatrix→ RMEM ─mma.sync→ RMEM

Hopper WGMMA:
GMEM ───TMA──→ SMEM ─descriptor→ WGMMA ─→ RMEM

Blackwell TCGen05:
GMEM ───TMA──→ SMEM ─descriptor→ TCGen05 ─→ TMEM
                                                   │
                                                  T2R
                                                   ▼
                                                  RMEM
```

TMA 是 MMA 的输入生产者，不是 MMA 指令的一部分：

```text
TMA 负责搬运
WGMMA/TCGen05 负责计算
```

## 11. TMA 没有优化什么

TMA 不会自动：

- 减少必须传输的数据量；
- 提高 DRAM 的物理带宽上限；
- 修复缺乏数据复用的算法；
- 执行任意 transpose、gather 或 scatter；
- 保证 consumer 读取时数据已经完成；
- 替代 WGMMA、TCGen05 或 epilogue。

对于很小、不规则或难以表示成规则 tensor tile 的搬运，`cp.async`
可能更容易控制，TMA descriptor 的准备成本也未必值得。

## 12. 最终对照

| 项目 | 普通 load/store | `cp.async` | TMA |
|---|---|---|---|
| Payload 经过 RMEM | 是 | 否 | 否 |
| 执行方式 | 同步指令流 | 异步 | 异步 |
| 发起粒度 | 每线程元素/向量 | 每线程小块 | 单线程大块 tile |
| 地址生成 | 每线程 | 每线程 | descriptor + 硬件 |
| 多维 tensor | 手工展开 | 手工展开 | 原生描述 |
| SMEM swizzle 写入 | 线程显式映射 | 线程显式映射 | descriptor 支持 |
| Cluster multicast | 否 | 否 | 支持 |
| 异步 SMEM→GMEM | 普通 store | 不属于经典 `cp.async` 路径 | 支持 |

## 检查理解

1. 为什么不能把 TMA 的优势简单写成“不经过寄存器”？

   > Hint：`cp.async` 的 payload 是否经过 RMEM？

2. TMA 减少的是内存流量，还是地址计算和指令发射？

   > Hint：同一个 tile 的字节数并没有改变。

3. TMA 把 row-major GMEM tile 写成 swizzled SMEM tile 时，元素的逻辑
   坐标是否改变？

   > Hint：区分逻辑坐标和物理 offset。

4. TMA load 完成后，是否就能证明 WGMMA 已经读完该 SMEM stage？

   > Hint：输入生产和 MMA 消费是两套异步协议。
