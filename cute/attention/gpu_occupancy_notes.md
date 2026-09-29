# GPU Occupancy 与调度机制笔记

> 基于 FlashAttention v1→v2 优化背景下的 GPU 架构理解

## 1. 什么是 Occupancy

Occupancy = SM 上实际活跃的 warp 数 / SM 最大能容纳的 warp 数

A100 有 **108 个 SM**，每个 SM 最多能同时驻留 **64 个 warp**（2048 个线程）。

## 2. 什么是"活跃 Warp"

活跃（active/resident）warp 是已经被分配到 SM 上、**拥有自己的寄存器和执行上下文**、随时可以被 warp scheduler 调度执行的 warp。

活跃 warp 有三种子状态：

```
活跃 (Active/Resident):  已分配寄存器，驻留在 SM 上
├── 正在执行 (Executing):  当前时钟周期被 scheduler 选中发射指令
├── 就绪 (Eligible):      下一条指令已准备好，等待被 scheduler 选中
└── 阻塞 (Stalled):       在等数据（内存读取、同步等）
```

**活跃 ≠ 正在执行。** SM 上可能有 48 个活跃 warp，但每个时钟周期只有若干个（A100 上最多 4 个）在执行。其余的要么在等数据，要么排队等调度。

活跃 warp 之间的切换是 **零开销** 的——因为每个 warp 的寄存器一直驻留在 SM 上，不需要保存/恢复上下文。这是 GPU 隐藏延迟的核心机制。

## 3. 为什么 Occupancy 重要：延迟隐藏

GPU 的核心策略是 **用大量线程的并行来隐藏内存访问延迟**。当一个 warp 在等内存数据（几百个时钟周期）时，scheduler 切换到另一个就绪的 warp 继续执行：

```
活跃 warp 多（比如 48 个）:
  Warp 1: [计算][等内存~~~~~~~~~~~~~~~~~~~~]
  Warp 2:       [计算][等内存~~~~~~~~~~~~~~]
  Warp 3:              [计算][等内存~~~~~~~]
  ...
  → 总有 warp 准备好了，scheduler 不空转

活跃 warp 少（比如 2 个）:
  Warp 1: [计算][等内存~~~~~~~~~~~~~~~~~~~~~][计算]
  Warp 2:       [计算][等内存~~~~~~~~~~~~~~]
                             ↑ 两个都在等内存，SM 执行单元空转！
```

## 4. 影响 Occupancy 的两个层级

### 层级 1：SM 间 —— Thread Block 数量够不够

SM 只有被分配到 thread block 才会工作。如果总 block 数 < SM 数，部分 SM 直接空闲：

```
FA1: batch=1, heads=16 → 16 个 block → 108 个 SM 中 92 个闲着
FA2: batch=1, heads=16, ⌈N/128⌉=256 → 4096 个 block → 所有 SM 满载
```

**FA2 的优化重点就在这一层：** 通过在序列长度维度增加并行，把 block 总数提上去。

### 层级 2：SM 内 —— 每个 SM 能驻留多少 Warp

假设 block 数量够了，每个 SM 能驻留多少 warp 取决于三个资源的 **最小瓶颈**：

```
实际活跃 warp 数 = min(
    硬件上限 (64),
    寄存器文件总量 / 每个 warp 的寄存器用量,
    shared memory 总量 / 每个 block 的 shared memory 用量 × 每 block 的 warp 数,
    最大 block 数限制 × 每 block 的 warp 数
)
```

以 A100 为例：

```
kernel 每线程用 128 个寄存器
→ 每 warp 用 128 × 32 = 4096 个寄存器
→ 65536 / 4096 = 16 个 warp 能驻留
→ occupancy = 16 / 64 = 25%

kernel 每线程用 32 个寄存器
→ 每 warp 用 32 × 32 = 1024 个寄存器
→ 65536 / 1024 = 64 个 warp（达到上限）
→ occupancy = 64 / 64 = 100%
```

### 高 Occupancy 不是万能的

对于 FlashAttention 这类计算密集型 kernel，**盲目追求高 occupancy 反而可能变慢**：

```
方案 A: 每线程 128 寄存器，occupancy 25%
        → 所有数据留在寄存器，计算飞快

方案 B: 每线程 32 寄存器，occupancy 100%
        → 寄存器不够 → 溢出到 local memory（走 HBM，很慢）
        → 虽然 warp 多，但每个都在等 HBM → 反而更慢
```

最优点在寄存器使用（效率）和 occupancy（延迟隐藏）之间的平衡处。

## 5. CUDA 线程层次结构

```
Grid (一次 kernel launch 的全部线程)
 ├── Block 0  (blockIdx = 0)
 │    ├── Warp 0  (thread 0-31)
 │    ├── Warp 1  (thread 32-63)
 │    ├── Warp 2  (thread 64-95)
 │    └── Warp 3  (thread 96-127)
 ├── Block 1  (blockIdx = 1)
 │    ├── Warp 0-3
 ├── Block 2  (blockIdx = 2)
 │    └── ...
 └── ...
```

- **Thread block**（简称 block）= 一组线程，用 `blockIdx` 标识，共享同一块 shared memory
- 每个 block 被调度器 **整体分配到某个 SM** 上执行，从头到尾不会迁移
- 一个 SM 可以 **同时驻留多个 block**（只要资源够）

### FlashAttention 中的 Block 映射

```
FA2 Forward kernel launch:

grid 维度 = (T_r, batch, heads)

blockIdx.x = 第几个 Q 行块 (0, 1, ..., T_r-1)   ← FA2 新增的并行维度
blockIdx.y = batch 中第几个样本
blockIdx.z = 第几个 attention head
```

## 6. Block 数与 SM 数的关系

### Block 数最好是 SM 数的倍数

这涉及 **wave 效率**——GPU 调度器把 block 一批一批（wave）分配给 SM：

```
A100: 108 个 SM，假设每个 SM 同时驻留 1 个 block

Block 数 = 108  → 1 wave, 满载, 利用率 100%
Block 数 = 216  → 2 waves, 每 wave 满载, 利用率 100%
Block 数 = 150  → wave 1: 108 block 满载
                  wave 2: 42 block → 66 个 SM 空闲
                  → 第 2 wave 利用率 39%
                  → 整体 ≈ 69%
```

实际上一个 SM 往往能同时驻留多个 block，所以精确倍数是"SM 数 × 每 SM 并发 block 数"。实践中只要 block 数远大于 SM 数，尾部浪费的比例就很小。

### Block 与 SM 的绑定关系

```
Block 0 → SM 17   (绑定，直到执行完毕)
Block 1 → SM 42
Block 2 → SM 3
...
Block 0 执行完 → SM 17 空出 → 调度新 block 给 SM 17

同一个 SM 上可以同时有多个 Block:
SM 17:  Block 0 (Warp 0-3) + Block 5 (Warp 4-7) + Block 10 (Warp 8-11)
```

## 7. SM 的并发执行能力

一个 SM **每个时钟周期可以从多个 warp 发射指令**，不是只能运行一个 warp。

A100 每个 SM 的结构（简化）：

```
┌──────────────────────────────────────────────────────┐
│  SM                                                   │
│                                                       │
│  4 个 Warp Scheduler（每周期各选 1 个就绪 warp）       │
│  ├── Scheduler 0 → Warp A → 发射指令到执行单元        │
│  ├── Scheduler 1 → Warp B → 发射指令                  │
│  ├── Scheduler 2 → Warp C → 发射指令                  │
│  └── Scheduler 3 → Warp D → 发射指令                  │
│                                                       │
│  执行单元:                                             │
│  ├── 4 组 FP32 单元 (各 16 个)                        │
│  ├── 4 组 INT32 单元                                  │
│  ├── 4 组 Load/Store 单元                             │
│  └── Tensor Core 阵列                                 │
└──────────────────────────────────────────────────────┘
```

加上执行单元的流水线效应（一条指令要几十个周期才完成），实际上数十个 warp 的指令在同时"飞行"中：

```
周期 1: Scheduler 发射 Warp A, B, C, D 的指令
周期 2: 发射 Warp E, F, G, H，同时 A-D 还在流水线里
周期 3: 发射 Warp I, J, K, L，A-H 都在流水线里
...
```

## 8. nvidia-smi 的 GPU-Util 到底在统计什么

### 常见误解

很多人以为 `nvidia-smi` 的 GPU-Util 显示的是"多少个 SM 在工作"。**不是的**，它比这粗糙得多。

### GPU-Util 的真实含义

```
$ nvidia-smi
+---------------------------+
| GPU-Util:  87%            |
+---------------------------+
```

这个 87% 表示：**过去采样周期内（通常 1-2 秒），有 87% 的时间里 GPU 上至少有一个 kernel 在运行。**

```
采样周期（~1秒）:
|████████████████████░░░░░░░░░░████████████████████████████|
 ↑ 有 kernel 在跑      ↑ 空闲       ↑ 有 kernel 在跑

GPU-Util = 有 kernel 运行的时间 / 总时间 ≈ 87%
```

它完全不关心：
- 用了多少个 SM
- 每个 SM 的 occupancy 是多少
- 计算单元是否在做有效计算

**哪怕只有 1 个 SM 在跑一个很轻的 kernel，只要持续运行，GPU-Util 也会显示 100%。**

### 要看 SM 级别的利用率用什么工具

| 工具 | 指标 | 含义 | 精度 |
|------|------|------|------|
| `nvidia-smi` GPU-Util | GPU 忙/闲占比 | 有没有 kernel 在跑 | 最粗糙 |
| `nvidia-smi dmon -s u` | sm% | SM 忙碌时间占比 | 中等（仍是时间采样） |
| **Nsight Compute** (`ncu`) | Achieved Occupancy | 真正的 SM 级 occupancy | 精确，per kernel |
| **Nsight Systems** (`nsys`) | SM Warp Occupancy | 时间线级别 warp 活跃度 | 精确，全局时间线 |

### 实用命令

```bash
# 粗略看 SM 利用率（采样间隔 1 秒）
nvidia-smi dmon -s u -d 1
# 输出示例:
# gpu  sm  mem  enc  dec
#   0  45   23    0    0    ← sm 列：SM 忙碌时间百分比

# 精确看某个 kernel 的 achieved occupancy
ncu --metrics sm__warps_active.avg.pct_of_peak_sustained_active ./my_program

# profile 整个程序的时间线
nsys profile ./my_program
```

### 对 FlashAttention 优化的启示

在优化 FlashAttention 这种 kernel 时，`nvidia-smi` 基本没参考价值（大概率显示 100%）。真正的性能分析要靠 **Nsight Compute** 看每个 kernel 的：
- Achieved Occupancy（实际 SM 利用率）
- Memory Throughput（HBM 带宽利用率）
- Compute Throughput（计算单元利用率）
- Roofline 分析（判断 kernel 是 compute-bound 还是 memory-bound）

## 9. 速查表

| 问题 | 答案 |
|------|------|
| Occupancy 是什么 | 活跃 warp 数 / SM 最大 warp 数 |
| 活跃 warp 是什么 | 已分配寄存器、驻留在 SM 上、可被 scheduler 调度的 warp |
| 一个 Block 对应一个 SM？ | 是，绑定且不迁移；但一个 SM 可同时容纳多个 Block |
| SM 同一时间只跑一个 Warp？ | 不是，A100 每周期最多从 4 个 warp 发射指令 |
| Block 数最好是 SM 倍数？ | 理想情况是，能避免尾部 wave 的 SM 空闲；远大于 SM 数即可 |
| 高 Occupancy 一定好？ | 不一定，寄存器溢出的代价可能更大；关键是找平衡点 |
| FA1 Occupancy 为什么低 | 只在 batch × heads 并行，block 总数可能 < SM 数 |
| FA2 如何解决 | 增加序列维度并行，block 数 = batch × heads × seq_blocks |
