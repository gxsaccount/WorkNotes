# Flash Attention v3 相比 v2 的优化总结

> 基于论文：FlashAttention-3: Fast and Accurate Attention with Asynchrony and Low-precision (arXiv:2407.08608v2, July 2024)

## 0. 核心动机

FlashAttention-2 在 H100 GPU 上仅达到 **35% 利用率**，而优化后的 GEMM 可达 80-90%。根本原因是 FA2 遵循同步执行模型，没有利用 Hopper 架构的两个关键新特性：

| 硬件特性 | 说明 | FA2 是否利用 |
|----------|------|-------------|
| **异步执行** | Tensor Core (WGMMA) 和 TMA 可异步执行，独立于 CUDA Core | ❌ |
| **低精度 FP8** | FP8 Tensor Core 吞吐量是 FP16 的 2× | ❌ |

## 1. Hopper GPU 硬件特性回顾

### 1.1 内存层次

```
┌─────────────────────────────────┐
│  RMEM（寄存器文件）             │  256 KiB/SM
├─────────────────────────────────┤
│  SMEM（共享内存）               │  228 KiB/SM, 31 TB/s 全芯片
├─────────────────────────────────┤
│  L2 Cache                       │  50 MiB, 12 TB/s
├─────────────────────────────────┤
│  GMEM / HBM                     │  80 GiB, 3.35 TB/s
└─────────────────────────────────┘
```

### 1.2 线程层次

```
Thread → Warp (32 threads) → Warpgroup (4 warps) → CTA (threadblock) → Cluster → Grid
```

### 1.3 关键硬件单元

| 单元 | 功能 | 特性 |
|------|------|------|
| **TMA** (Tensor Memory Accelerator) | GMEM ↔ SMEM 异步拷贝 | 专用硬件，不占 CUDA Core |
| **WGMMA** | Warpgroup 级矩阵乘法 | 异步执行，可直接读 SMEM，Tensor Core 执行 |
| **Multi-function Unit** | exp2 等特殊函数 | 每 SM 每周期 16 次操作 |

### 1.4 吞吐量不对称问题

```
H100 SXM5:
  FP16 matmul:       989 TFLOPS  (Tensor Core)
  特殊函数 (exp2):   3.9 TFLOPS  (Multi-function Unit)
  比值:              ~256×

对于 hdim=128 的 FP16 attention forward:
  matmul FLOPs / exp FLOPs = 512×
  但 exp 吞吐量比 matmul 低 256×
  → exp 可能占用 matmul ~50% 的周期！
```

这个不对称是 FA3 进行 GEMM-softmax 重叠优化的核心动机。

## 2. FA3 三大优化技术

### 2.1 优化一：Producer-Consumer 异步 — Warp Specialization

**核心思想：** 将 CTA 内的 warp 划分为 **Producer（数据搬运）** 和 **Consumer（计算）** 两种角色，利用 TMA 和 WGMMA 的异步特性实现数据搬运与计算的重叠。

```
┌──────────────────────────────────────────────────────────┐
│                    CTA 内部                               │
│                                                          │
│  Producer Warpgroup          Consumer Warpgroup(s)       │
│  ┌────────────────┐          ┌────────────────────┐      │
│  │ setmaxnreg ↓   │          │ setmaxnreg ↑       │      │
│  │ (释放寄存器)    │          │ (获取更多寄存器)    │      │
│  │                │          │                    │      │
│  │ TMA load Q_i   │─commit──→│ wait Q_i           │      │
│  │                │          │                    │      │
│  │ for j in K/V:  │          │ for j in K/V:      │      │
│  │   wait buffer  │          │   wait K_j         │      │
│  │   TMA load K_j │─commit──→│   S = Q_i @ K_j^T  │      │
│  │   TMA load V_j │─commit──→│   softmax(S)       │      │
│  │                │          │   wait V_j         │      │
│  │                │←release──│   O += P̃ @ V_j     │      │
│  └────────────────┘          └────────────────────┘      │
└──────────────────────────────────────────────────────────┘
```

**关键实现细节：**

1. **寄存器动态重分配 (`setmaxnreg`)：** Producer 只需发 TMA 指令（单线程即可），释放寄存器给 Consumer；Consumer 做 MMA 需要大量寄存器
2. **环形 SMEM Buffer (s-stage)：** Producer 持续填充 buffer，Consumer 持续消费，通过 barrier 同步。前 s 次迭代 Producer 无需等待（buffer 从空到满的填充阶段，不可能追上自己的尾巴）；第 s 次起必须等 Consumer 释放槽位才能继续写。s 越大 Producer 提前量越大，越能"藏住" TMA 搬运延迟，但每多一个 stage 多一份 K/V tile 的 SMEM 空间，是个 trade-off。FA3 典型用 **s=2**
3. **TMA 异步性：** 发出 TMA load 后 Producer 不等待完成，立即发下一条

### 2.2 优化二：GEMM-Softmax 流水线重叠（Intra-warpgroup Pipelining）

**问题：** 在单个 warpgroup 内，softmax 依赖第一个 GEMM (QK^T) 的输出，第二个 GEMM (PV) 依赖 softmax 的输出 → 串行依赖链。

#### 关键前提：这不是 warp 分化，而是硬件级并行

与优化一（不同 warpgroup 干不同活）不同，GEMM-Softmax 重叠由**同一个 warpgroup** 完成，利用的是 SM 内部不同执行单元的并行性：

```
SM 内部执行单元（简化）:

┌───────────────────────────────────┐
│  Tensor Core (MMA 单元)           │  ← 执行 WGMMA（矩阵乘）
│  异步流水线，发出指令后后台执行     │
├───────────────────────────────────┤
│  CUDA Core (FP32/INT32 单元)      │  ← 执行 fmul, fadd, fmax
├───────────────────────────────────┤
│  MFU / SFU (特殊函数单元)         │  ← 执行 exp2f
└───────────────────────────────────┘
   ↑ 三组硬件可以同时工作 ↑
```

WGMMA 是异步指令：warpgroup 发出 `wgmma.mma_async` 后，Tensor Core 在后台执行矩阵乘，线程可以立即转去跑 softmax 代码（`fmax`、`fmul`、`exp2f`）。**不需要专门分出一组 warp 做 softmax**——同一批线程先"下单"给 Tensor Core，然后自己动手做 softmax，两边互不阻塞。

| | 优化一：Warp Specialization | 优化二：GEMM-Softmax 重叠 |
|---|---|---|
| **谁和谁并行** | Producer WG vs Consumer WG | Tensor Core vs CUDA Core/MFU |
| **是否分了不同的 warp** | 是 | **否，同一个 warpgroup** |
| **并行原理** | 不同线程做不同事 | 同一线程发出异步指令后做别的 |
| **关键机制** | `if (wg_idx == 0) ... else ...` | `commit` 后不 `wait`，立刻做 softmax |

**补充：CUDA Core 和 MFU 之间也能并行吗？** 能，但这是 Warp Scheduler 自动完成的，不需要显式优化。一个 warpgroup 有 4 个 warp，SM 有 4 个 Warp Scheduler，softmax 的 `FMNMX/FMUL/FADD` 发给 CUDA Core、`MUFU.EX2`(exp2f) 发给 MFU，Scheduler 自然交错调度。FA3 作者的精力花在**第二层**（Tensor Core vs CUDA Core+MFU 的重叠），第三层（CUDA Core vs MFU）是"免费附赠"的硬件行为。

**解法：2-stage 跨迭代流水线** — 把 PV_GEMM 往后推一轮，让本轮 softmax 和上轮 PV_GEMM 重叠（两者无数据依赖）。

**对比：无流水线 vs 有流水线**

```
无流水线 (FA2 风格，朴素串行):
  每次 softmax 时 Tensor Core 闲着，每次 GEMM 时 CUDA Core 闲着

  Tensor Core: ▓QK(j-1)▓░░░░░░░░░░░▓PV(j-1)▓░░░░░░▓QK(j)▓░░░░░░░░░░░▓PV(j)▓
  CUDA Core:   ░░░░░░░░░▓softmax(j-1)▓░░░░░░░░░░░░░░░░░░░▓softmax(j)▓░░░░░░░
                                                            ↑
                                             Tensor Core 闲着等 softmax

有流水线 (FA3，PV 推迟一轮):
  本轮 softmax(j) 和上轮 PV(j-1) 重叠，两者无数据依赖

  Tensor Core: ▓▓QK(j)▓▓▓PV(j-1)▓▓▓▓▓▓▓░░░░▓▓QK(j+1)▓▓▓PV(j)▓▓▓▓▓▓▓
  CUDA Core:   ░░░░░░░░░░░░░░▓▓softmax(j)▓▓░░░░░░░░░░░░░░▓▓softmax(j+1)▓▓
                               ↑                            ↑
                          PV(j-1) 还在跑              Tensor Core 没闲着！
```

**为什么能重叠：**
- `softmax(j)` 需要 `S_cur = QK(j)` 的结果 → wait QK 之后有了
- `PV(j-1)` 需要 `P̃_prev` = 上轮 softmax 的结果 → 上轮已经算好了
- 两者之间**没有数据依赖** → 可以分别跑在 CUDA Core 和 Tensor Core 上

```
迭代 j 的执行流 (计算视角命名):

  ┌─ WGMMA: S_cur = Q_i @ K_j^T ────────┐  ← 提交但不等待
  │                                       │
  │  WGMMA: O_i += P̃_prev @ V_{j-1} ──┐│  ← 提交但不等待 (P̃_prev 是上轮算好的)
  │                                     ││
  │  等待 S_cur 完成                      ││
  │  softmax(S_cur) → P̃_cur             ││  ← 与 PV GEMM 重叠！两者无数据依赖
  │                                     ││
  │  等待 O_i 的 WGMMA 完成              ││
  │  rescale O_i                        ││
  └─────────────────────────────────────┘│
                                         │
  P̃_cur → 下一轮的 P̃_prev              │
```

**Algorithm 2 伪代码逻辑（Consumer Mainloop，计算视角命名）：**

```
// Prologue: 第 0 次迭代完整执行
S_cur = Q_i @ K_0^T         (WGMMA, commit+wait)
softmax(S_cur) → P̃_cur

// Mainloop: 第 1 到 T_c-2 次迭代
for j = 1 to T_c-2:
    P̃_prev ← P̃_cur                                          ← 保存上轮结果
    S_cur = Q_i @ K_j^T         (WGMMA, commit 但不 wait)    ← 异步发出
    O_i += P̃_prev @ V_{j-1}    (WGMMA, commit 但不 wait)    ← 异步发出，用上轮的 P̃
    wait S_cur                                                ← 等本轮 QK 完成
    softmax(S_cur) → P̃_cur                                   ← 与 PV GEMM 重叠！
    wait O_i 的 WGMMA
    rescale O_i

// Epilogue: 最后一次 PV GEMM
O_i += P̃_cur @ V_{T_c-1}   (WGMMA, commit+wait)
```

**实际效果（SASS 验证）：**

编译器生成的 SASS 代码确认了预期的重叠：
- Softmax 操作（FMNMX, MUFU.EX2, FADD 等）被重排到 mainloop 开头
- 第一个 WGMMA (HGMMA) 与 softmax/FP32→FP16 转换交错执行
- 第二个 WGMMA 独立执行，不与其他指令重叠

**寄存器代价：** 需要额外存储 S_next ∈ R^(B_r × B_c)，增加 B_r × B_c × sizeof(float) 的寄存器用量，需要在 tile 大小和流水线深度之间权衡。

#### Pingpong 调度（跨 Warpgroup 重叠）

除了 warpgroup 内部的流水线，FA3 还在 **两个 Consumer Warpgroup 之间** 实现 pingpong 调度。

**问题：** 一个 SM 的 Tensor Core 是共享资源。如果两个 Consumer WG 同时发 WGMMA，它们会争抢 Tensor Core，导致两边都变慢。

**解法：** 用 Named Barrier 让两个 WG **交替**使用 Tensor Core——一个做 GEMM 时另一个做 softmax。

```
时间线:

          Tensor Core 使用权
              ↓
WG1:  [QK+PV GEMM] → barrier_arrive(WG2) → [softmax] → barrier_sync(WG1) → [QK+PV GEMM] → ...
WG2:  barrier_sync(WG2) → [QK+PV GEMM] → barrier_arrive(WG1) → [softmax] → barrier_sync(WG2) → ...

展开:
  WG1:  ▓▓▓GEMM▓▓▓  softmax   ▓▓▓GEMM▓▓▓  softmax
  WG2:   softmax   ▓▓▓GEMM▓▓▓  softmax   ▓▓▓GEMM▓▓▓
               Tensor Core ↑         ↑ 永远只有一个 WG 在用
```

**伪代码（两个 Consumer WG 各自执行，以 WG1 为例）：**

```
// 每个 Consumer WG 都有自己的 barrier_id
my_barrier    = WG1_BARRIER   // WG1 等这个
other_barrier = WG2_BARRIER   // WG1 通知这个

// Prologue: WG1 先跑，WG2 等
if is_WG1:
    S_cur = Q @ K_0^T   (commit+wait)
    softmax(S_cur) → P̃_cur
    // WG1 先完成 prologue，WG2 此时被 barrier 挡住

// Mainloop
for j = 1 to T_c-2:
    P̃_prev ← P̃_cur

    // ── 等轮到我 ──
    NamedBarrier::sync(my_barrier)        // 等对方 arrive 后才继续
    //  ↑ WG1 第一轮跳过（prologue 已保证 WG1 先跑）
    //    WG2 第一轮阻塞，等 WG1 做完 GEMM 后 arrive

    // ── GEMM 阶段（独占 Tensor Core）──
    S_cur = Q @ K_j^T       (commit, 不 wait)
    O_i += P̃_prev @ V_{j-1} (commit, 不 wait)

    // ── 通知对方：我的 GEMM 发完了，你可以用 Tensor Core 了 ──
    NamedBarrier::arrive(other_barrier)

    // ── softmax 阶段（用 CUDA Core，不占 Tensor Core）──
    wait S_cur
    softmax(S_cur) → P̃_cur   // 此时对方 WG 在跑 GEMM
    wait O_i
    rescale O_i
```

**关键：`arrive` 在 GEMM 发出后、softmax 之前。** 这样对方 WG 收到信号就开始发 GEMM，自己则去做 softmax，两边错开：

| 时刻 | WG1 | WG2 | Tensor Core 被谁用 |
|------|-----|-----|------------------|
| T1 | GEMM (发指令) | barrier_sync 等待 | WG1 |
| T2 | arrive → softmax | 收到 arrive → GEMM | WG2 |
| T3 | barrier_sync 等待 | arrive → softmax | — |
| T4 | 收到 arrive → GEMM | softmax | WG1 |

**效果：** hdim=128, seqlen=8192 时从 570 TFLOPS → 620-640 TFLOPS。

#### 3-stage 流水线（实验性）

进一步尝试将 softmax 与 **两个 GEMM 都重叠**：第 j+2 次的 QK^T GEMM + 第 j 次的 PV GEMM + 第 j+1 次的 softmax 同时执行。

**实际结果不如 2-stage：**
1. 编译器没有按预期重排指令 — 只有第一个 WGMMA 与 softmax 重叠
2. 寄存器压力更大 — 需要额外存储 P̃_next 和 scale_o，迫使使用更小的 tile

### 2.3 优化三：FP8 低精度加速

#### 2.3.1 效率：布局变换

FP8 WGMMA 相比 FP16 有更严格的布局约束：

| | FP16 WGMMA | FP8 WGMMA |
|---|---|---|
| 操作数格式 | mn-major 或 k-major | **仅 k-major** |

**问题 1: V 的转置**

输入 V 通常沿 head dimension 连续（mn-major），但 FP8 要求 k-major（沿 sequence length 连续）。

三种方案：
- (1a) 融合到前序操作（如 rotary embedding）的 epilogue — 难以集成到标准库
- (1b) 独立的预处理转置 kernel — 推理时 memory-bound 太浪费
- **(2) Kernel 内转置** ✅ — FA3 的选择

实现方式：利用 **LDSM/STSM** (ldmatrix/stmatrix) 指令，一个 warp 集体执行 SMEM↔RMEM 的 128 字节拷贝，支持转置。在 Producer warpgroup 中执行，可被两个 WGMMA "遮盖"。

**问题 2: 累加器与操作数的布局不匹配**

FP8 WGMMA 的 FP32 累加器布局与操作数 A 的寄存器布局不同：

```
FP32 累加器 (行 0, 线程 0):  {d0, d1, d2, d3, d4, d5, d6, d7}
FP8 操作数A (行 0, 线程 0):  {a0, a1, a2, a3, a4, a5, a6, a7}
                              ↑ 不同的排列方式
```

**解法：** 使用 **byte permute** 指令将第一个 WGMMA 的累加器重排为：
```
{d0, d1, d4, d5, d2, d3, d6, d7}
```
对应 P tile 的列置换。然后让 kernel 内转置输出匹配的 V tile 行置换，确保第二个 WGMMA 计算正确。

#### 2.3.2 精度：Block Quantization + Incoherent Processing

FP8 (e4m3) 仅 3 bit 尾数 + 4 bit 指数，数值误差大。LLM 中还存在 outlier 值问题。

**技术 1: Block Quantization（分块量化）**

```
标准方案: per-tensor scaling — 每个张量一个缩放因子
FA3 方案: per-block scaling — 每个 B_r×d 或 B_c×d 块一个缩放因子

优势:
  - 每个块独立量化，outlier 影响局部化
  - 量化可融合到前序操作（如 rotary embedding）中，零额外开销
  - FA3 算法天然按块操作，缩放 S 块来补偿不同块的 scale 无额外计算开销
```

**技术 2: Incoherent Processing（不相干处理）**

```
核心思想: 用随机正交矩阵 M "打散" outlier

数学保证: (QM)(KM)^T = QMM^TK^T = QK^T  (M 正交 → MM^T = I)

实现: M = 随机 ±1 对角矩阵 × Hadamard 矩阵
  - Hadamard 乘法复杂度 O(d log d) 而非 O(d²)
  - 可融合到 rotary embedding 中，零额外开销

效果: QM 和 KM 的每个元素是 Q/K 元素的随机加权和
      → outlier 被"摊平"到所有维度 → 量化误差降低
```

## 3. 消融实验

固定参数 {batch=4, seqlen=8448, nheads=16, hdim=128}，non-causal FP16：

| 配置 | 耗时 | TFLOPs/s |
|------|------|----------|
| FA3 完整版（Warp-Spec + GEMM-Softmax Pipeline） | 3.538 ms | **661** |
| 仅 Warp-Specialization，无 GEMM-Softmax 重叠 | 4.021 ms | 582 |
| 仅 GEMM-Softmax 重叠，无 Warp-Specialization | 4.105 ms | 570 |

两个技术都有显著贡献，组合效果最佳。

## 4. 性能对比

### 4.1 FP16 Forward

| Head Dim | 对比 FA2 | 对比 cuDNN | 峰值 TFLOPs/s |
|----------|---------|-----------|--------------|
| 64 | 1.5-1.6× | 中长序列超越 | ~497 |
| 128 | 1.7-1.8× | 中长序列超越 | ~648 |
| 256 | 2.0-2.2× | 中长序列超越 | **~756** |

FP16 峰值达 **740+ TFLOPs/s**，约 H100 理论峰值的 **75%**（vs FA2 的 35%）。

### 4.2 FP16 Backward

| Head Dim | 对比 FA2 | 对比 cuDNN |
|----------|---------|-----------|
| 64 | 1.5-1.6× | 超越 |
| 128 | 1.5-1.75× | 超越 |

反向传播中新增 **dQ-writer warp** 角色（3 种角色：Producer / Consumer / dQ-writer），专门处理 dQ 的全局累加写入，避免阻塞 Consumer。

### 4.3 FP8 Forward

| Head Dim | 峰值 TFLOPs/s | 说明 |
|----------|--------------|------|
| 64 | ~613 | 超越 cuDNN |
| 128 | ~1008 | 与 cuDNN 持平 |
| 256 | **~1171** | 接近 **1.2 PFLOPs/s** |

### 4.4 数值精度

以 FP64 参考实现为基准，测试包含 outlier 的分布 N(0,1) + N(0,100)·Bernoulli(0.001)：

| 方法 | RMSE |
|------|------|
| 标准 Attention FP16 | 3.2e-4 |
| FlashAttention-2 FP16 | 1.9e-4 |
| **FlashAttention-3 FP16** | **1.9e-4** |
| 标准 Attention FP8 (per-tensor scaling) | 2.4e-2 |
| FA3 FP8 无 block quant | 9.3e-3 |
| FA3 FP8 无 incoherent processing | 2.4e-2 |
| **FA3 FP8 完整版** | **9.1e-3** (↓2.6×) |

FP16 下 FA3 与 FA2 精度相同（中间结果保持 FP32）。FP8 下 block quantization + incoherent processing 将误差降低 **2.6×**。

## 5. 反向传播算法

FA3 反向传播在 FA2 基础上引入 **三角色 Warp Specialization**：

```
┌──────────────────────────────────────────────────────────────┐
│                         CTA 内部                              │
│                                                              │
│  Producer Warp        Consumer Warpgroup(s)    dQ-writer Warp│
│  ┌──────────┐         ┌──────────────────┐    ┌────────────┐│
│  │ TMA load │         │ S = Q_i @ K_j^T  │    │ wait dQ_i  ││
│  │ K_j, V_j │─commit→ │ dP = dO @ V_j^T  │    │ atomic add ││
│  │ Q_i, dO_i│─commit→ │ P = exp(S - L)   │    │ dQ_i → HBM ││
│  │          │         │ dS = P ⊙ (dP - D)│    │            ││
│  │          │         │ dV += P^T @ dO    │    │            ││
│  │          │         │ dK += dS^T @ Q    │    │            ││
│  │          │         │ dQ_local = dS @ K │→→→ │            ││
│  └──────────┘         └──────────────────┘    └────────────┘│
└──────────────────────────────────────────────────────────────┘
```

dQ 需要多个 CTA 的贡献累加到同一全局位置 → 使用信号量（semaphore）原子累加 → 独立的 dQ-writer warp 异步执行，避免阻塞 Consumer 的下一轮计算。

## 6. 优化全景图

```
FA2 (Ampere, 同步模型):
  ┌─────────────────────────────────────────────────┐
  │ 所有 warp 统一执行:                              │
  │  load K/V → GEMM(QK^T) → softmax → GEMM(PV)    │
  │       ↑         ↑          ↑          ↑          │
  │     串行       串行       串行       串行         │
  │                                                  │
  │  H100 利用率: ~35%                               │
  └─────────────────────────────────────────────────┘

FA3 (Hopper, 异步模型):
  ┌─────────────────────────────────────────────────┐
  │ Producer Warp:                                   │
  │   TMA load K_j ─→ TMA load V_j ─→ TMA load K_{j+1} ...  │
  │        ↓ (async)      ↓ (async)                  │
  │ Consumer WG1:                                    │
  │   [WGMMA: QK^T₁] [softmax₁] [WGMMA: QK^T₃] [softmax₃] │
  │   [WGMMA: PV₀  ]             [WGMMA: PV₂  ]             │
  │ Consumer WG2 (pingpong):                         │
  │   [softmax₀    ] [WGMMA: QK^T₂] [softmax₂]             │
  │                  [WGMMA: PV₁  ]                          │
  │                                                  │
  │  三层重叠: TMA ∥ WGMMA ∥ softmax                 │
  │  H100 利用率: ~75%                               │
  └─────────────────────────────────────────────────┘
```

## 7. 量化效果总结

| 指标 | FlashAttention-2 | FlashAttention-3 |
|------|-----------------|-----------------|
| 目标架构 | Ampere (SM80) | **Hopper (SM90)** |
| 编程模型 | 同步 | **异步 (Warp-Specialized)** |
| 精度支持 | FP16/BF16 | **FP16/BF16 + FP8** |
| FP16 前向峰值 | ~370 TFLOPs/s | **~740 TFLOPs/s (2×)** |
| FP8 前向峰值 | — | **~1.2 PFLOPs/s** |
| H100 利用率 | ~35% | **~75%** |
| FP16 前向加速 (vs FA2) | — | **1.5-2.0×** |
| FP16 反向加速 (vs FA2) | — | **1.5-1.75×** |
| FP8 精度 (vs per-tensor) | — | **2.6× 更准确** |

## 8. 局限性

1. **FP8 缺少 persistent kernel** — FP16 版本有 persistent kernel 和负载均衡，FP8 没有；这导致 FP8 在短序列和 causal masking 场景下弱于 cuDNN
2. **FP8 训练稳定性未验证** — 论文未在大规模训练中验证 FP8 attention 的效果
3. **推理场景未优化** — 推理（特别是 decode 阶段）需要不同的优化策略

这些局限在 FA4 中被进一步解决：FA4 基于 CuTeDSL 实现，支持 Hopper + Blackwell (SM100/SM110)，加入了 SplitKV、Paged KV Cache、Persistent Kernel、2CTA 指令等完整特性。
