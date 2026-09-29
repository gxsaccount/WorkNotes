# Flash Attention v2 相比 v1 的优化总结

> 基于论文：FlashAttention-2: Faster Attention with Better Parallelism and Work Partitioning (arXiv:2307.08691, 2023)

## 0. 背景：FA1 的瓶颈在哪里

FA1 在 A100 上 forward 仅达到理论最大 FLOPs/s 的 **30-50%**，backward 更低（**25-35%**）。而优化过的 GEMM 可以达到 **80-90%**。

通过 profiling 发现两个主要原因：

| 瓶颈 | 说明 |
|------|------|
| **非 matmul FLOPs 占比过高** | A100 上 matmul 吞吐量为 312 TFLOPs/s（FP16/BF16），非 matmul 仅 19.5 TFLOPs/s（FP32），差距 **16×**。每个非 matmul FLOP 的代价等于 16 个 matmul FLOP |
| **线程块/Warp 间的 work partitioning 不佳** | 导致 GPU 占用率（occupancy）低，或 shared memory 读写开销大 |

FA2 的三大优化方向与此一一对应：(1) 减少非 matmul FLOPs，(2) 提高并行度/occupancy，(3) 优化 warp 间的 work partitioning。

## 1. 优化一：减少非 matmul FLOPs（算法调整）

### 1.1 Forward：延迟归一化（Delayed Rescaling）

**FA1 的做法：** 每处理一个 K/V 块，都要把 O 除以最新的归一化因子 `diag(ℓ)^{-1}`，即每步都维护一个 **已归一化** 的 O：

```
O^(j) = diag(ℓ^(j))^{-1} · ( diag(ℓ^(j-1)) · e^{m^(j-1) - m^(j)} · O^(j-1)  +  e^{S^(j) - m^(j)} · V_j )
                ↑ 每步都除                      ↑ 先乘回来再缩放
```

这意味着每步循环有 **两次** 向量级别的 rescaling 运算（先乘 `ℓ^(j-1)` 恢复，再除 `ℓ^(j)` 归一化）。

**FA2 的做法：** 保持 **未归一化** 的 Õ，只在循环结束后做一次归一化：

```
Õ^(j) = diag(e^{m^(j-1) - m^(j)}) · Õ^(j-1)  +  e^{S^(j) - m^(j)} · V_j
                   ↑ 只做 max 修正缩放，不除 ℓ

最终: O = diag(ℓ^(T_c))^{-1} · Õ^(T_c)    ← 全部循环结束后一次性归一化
```

**节省：** 每个内层循环迭代少了一次 `diag(ℓ)^{-1}` 的逐元素除法（B_r × d 个 FLOPs），共 T_c 次迭代，总计省去 T_c × B_r × d 个非 matmul FLOPs。

### 1.2 Forward & Backward：只存 logsumexp

**FA1 的做法：** 为反向传播保存两个统计量 —— 行最大值 m ∈ R^N 和指数和 ℓ ∈ R^N。

**FA2 的做法：** 只存一个 **logsumexp** L = m + log(ℓ) ∈ R^N。

反向传播中恢复 softmax：`P = exp(S - L)` 而非 FA1 的 `P̃ = exp(S - m)`，后者还需要额外除 ℓ。

**好处：**
- 存储量减半（N 而非 2N 个标量）
- 反向传播中少一步除法操作

### 1.3 两步改动的完整公式对比

以两个块 S^(1), S^(2) 的情况为例：

```
┌─────────────────────────────────────────────────────────────────────┐
│ FA1 (Algorithm 1 from v1 paper):                                    │
│   Õ^(1) = P̃^(1) V^(1)                      ← 局部 softmax 乘 V    │
│   O^(1) = diag(ℓ^(1))^{-1} · Õ^(1)         ← 归一化              │
│   O^(2) = diag(ℓ^(1)/ℓ^(2)) · O^(1)        ← 反归一化再重新归一化 │
│           + diag(ℓ^(2))^{-1} · e^{S^(2)-m^(2)} · V^(2)            │
│   保存: m, ℓ (分别保存)                                             │
├─────────────────────────────────────────────────────────────────────┤
│ FA2 (Algorithm 1 from v2 paper):                                    │
│   Õ^(1) = e^{S^(1) - m^(1)} · V^(1)        ← 不归一化             │
│   Õ^(2) = diag(e^{m^(1)-m^(2)}) · Õ^(1)    ← 只做 max 修正       │
│           + e^{S^(2) - m^(2)} · V^(2)                              │
│   O = diag(ℓ^(2))^{-1} · Õ^(2)              ← 循环结束后一次性归一化│
│   保存: L = m + log(ℓ) (合并为一个值)                               │
└─────────────────────────────────────────────────────────────────────┘
```

## 2. 优化二：序列长度维度的并行化

### 2.1 FA1 的并行策略及瓶颈

**FA1：** 只在 batch × num_heads 维度并行，每个 attention head 分配一个 thread block。

```
并行度 = batch_size × num_heads
```

当序列很长时，batch 通常很小（受显存限制），导致 thread block 总数 < SM 数量 → **GPU 占用率低**。

### 2.2 FA2 Forward：交换循环顺序 + 沿序列长度并行

**关键改变：** 将 FA1 的循环顺序 **反转**：

```
FA1:  外层遍历 K/V 块（列方向），内层遍历 Q 块（行方向）
FA2:  外层遍历 Q 块（行方向），内层遍历 K/V 块（列方向）
```

**为什么要反转？** 因为 FA2 外层循环的每次迭代是 **独立** 的：

- 每个 Q 块 i 的输出 O_i 只依赖于 Q_i 和所有 K/V 块，不依赖于其他 Q 块
- 外层循环可以完全并行 → 每个 Q 块分配一个独立的 thread block

```
FA2 forward 并行度 = batch_size × num_heads × T_r
                                                ↑ 新增的序列维度并行
                                                  T_r = ⌈N / B_r⌉
```

**注意：** FA1 的外层遍历 K/V 时，所有 Q 块共享同一个 K/V 块的加载，但内层各 Q 块的 O_i 更新之间互相独立，无法直接并行。FA2 通过反转循环，把这种独立性暴露到外层。

### 2.3 FA2 Backward：列方向并行 + 原子加

反向传播中各个矩阵梯度的依赖关系更复杂：

```
dV_j = Σ_i P_ij^T · dO_i       ← 各 Q 块的贡献需要累加到同一个 dV_j
dK_j = Σ_i dS_ij^T · Q_i       ← 同上
dQ_i = Σ_j dS_ij · K_j         ← 各 K 块的贡献需要累加到同一个 dQ_i
```

**FA2 的策略：** 外层按列（K/V 块）并行，每个 thread block 处理一列：

- dK_j、dV_j 在一个 thread block 内完成累加 → 无需跨 block 通信
- dQ_i 需要多个 thread block 的贡献 → 使用 **原子加（atomic adds）** 通过 HBM 通信

```
FA2 backward 并行度 = batch_size × num_heads × T_c
                                                 ↑ T_c = ⌈N / B_c⌉
```

### 2.4 对比图示

```
┌────────────────────────────────────────────────────────────────┐
│ Forward:  每个 worker (thread block) 负责一个 Q 行块           │
│                                                                │
│           K/V 块 1    K/V 块 2    K/V 块 3    K/V 块 4         │
│  Q 块 1:  ████████ → ████████ → ████████ → ████████  → O_1   │  ← Worker 1
│  Q 块 2:  ████████ → ████████ → ████████ → ████████  → O_2   │  ← Worker 2
│  Q 块 3:  ████████ → ████████ → ████████ → ████████  → O_3   │  ← Worker 3
│                    各 worker 完全独立，无需通信                  │
├────────────────────────────────────────────────────────────────┤
│ Backward: 每个 worker (thread block) 负责一个 K/V 列块         │
│                                                                │
│            Q 块 1    Q 块 2    Q 块 3                           │
│  KV 块 1:  ██████ → ██████ → ██████  → dK_1, dV_1            │  ← Worker 1
│  KV 块 2:  ██████ → ██████ → ██████  → dK_2, dV_2            │  ← Worker 2
│                    dQ 通过 atomic adds 跨 worker 累加           │
└────────────────────────────────────────────────────────────────┘
```

## 3. 优化三：Warp 间的 Work Partitioning

一个 thread block 通常包含 4 或 8 个 warp（每个 warp 32 线程）。warp 间如何分配工作对 shared memory 读写量有直接影响。

### 3.1 FA1 Forward：Split-K（低效）

```
FA1 Forward (4 warps):
┌──────────────────────────────────────────────────┐
│  Q (所有 warp 共享，驻留 shared memory)           │
│                                                   │
│  K 分成 4 片:  K₁   K₂   K₃   K₄                │
│  V 分成 4 片:  V₁   V₂   V₃   V₄                │
│                                                   │
│  Warp 1: Q @ K₁^T → slice of S → × V₁ → O₁     │
│  Warp 2: Q @ K₂^T → slice of S → × V₂ → O₂     │  ← "Split-K"
│  Warp 3: Q @ K₃^T → slice of S → × V₃ → O₃     │
│  Warp 4: Q @ K₄^T → slice of S → × V₄ → O₄     │
│                                                   │
│  然后: O = O₁ + O₂ + O₃ + O₄                     │
│         ↑ 需要写 shared memory → sync → 读回相加  │
│         ↑ 这是 split-K 的通信开销！               │
└──────────────────────────────────────────────────┘
```

**问题：** 每个 warp 得到的是 QK^T 的 **不同列**，乘 V 后得到的是 O 的 **部分和**（partial sum）。必须通过 shared memory 做跨 warp 的归约（reduce），带来额外的 shared memory 读写和同步开销。

### 3.2 FA2 Forward：Split-Q（高效）

```
FA2 Forward (4 warps):
┌──────────────────────────────────────────────────┐
│  K, V (所有 warp 共享，驻留 shared memory)        │
│                                                   │
│  Q 分成 4 片:  Q₁   Q₂   Q₃   Q₄                │
│                                                   │
│  Warp 1: Q₁ @ K^T → S₁ → × V → O₁              │
│  Warp 2: Q₂ @ K^T → S₂ → × V → O₂              │  ← "Split-Q"
│  Warp 3: Q₃ @ K^T → S₃ → × V → O₃              │
│  Warp 4: Q₄ @ K^T → S₄ → × V → O₄              │
│                                                   │
│  输出: O = [O₁; O₂; O₃; O₄] (直接拼接)          │
│         ↑ 各 warp 的输出是 O 的不同行，无需归约！  │
│         ↑ 零通信开销 ✓                             │
└──────────────────────────────────────────────────┘
```

**关键洞察：** 将 Q 而非 K/V 分片给不同 warp 后，每个 warp 独立计算出 O 的一部分行（而非部分和）。这些行之间 **完全独立**，不需要 shared memory 通信。

### 3.3 Backward 的 Warp Partitioning

反向传播同样避免了 split-K 方案。虽然由于 dQ/dK/dV 之间更复杂的依赖关系，仍需要一些同步，但相比 FA1 的方案减少了 shared memory 读写量。

### 3.4 Block Size 调优

FA2 的 block size 通常选择 {64, 128} × {64, 128}：

| 因素 | 影响 |
|------|------|
| 增大 block size | ✅ 减少 shared memory load/store 次数；❌ 增加寄存器压力（spilling → 变慢） |
| 减小 block size | ✅ 减少寄存器使用；❌ 更多 shared memory 访问 |
| shared memory 容量上限 | block size 过大时 kernel 无法运行 |

FA2 按 head dimension 手动调优了 block size（实际只有 4 种组合），论文提到未来可通过 auto-tuning 自动化。

## 4. 附加优化：Causal Mask 的高效处理

### 4.1 块级跳过（Block Skipping）

对于 causal attention（S_ij = -∞ when j > i），约 **一半的块** 全部被 mask 掉：

```
注意力矩阵 (causal):
  ████░░░░
  ████████░░░░
  ████████████░░░░
  ████████████████

█ = 有效计算区域
░ = 全部 mask（S = -∞），可跳过整个 block
```

当 block 的所有列索引 > 所有行索引时，直接跳过该 block 的计算。这带来约 **1.7-1.8×** 的加速。

### 4.2 减少逐元素 Mask 操作

对于 **行索引严格小于列索引** 的块，所有元素都不需要 mask → 跳过逐元素的 mask 操作。每行只有 **1 个块**（假设方阵块）需要实际应用 causal mask。

## 5. MQA / GQA 支持

Multi-Query Attention (MQA) 和 Grouped-Query Attention (GQA) 中，多个 Q head 共享同一个 KV head。

**FA2 的做法：** 不复制 KV head，而是通过 **隐式索引操作** 让不同 Q head 指向同一个 KV head。反向传播中，对共享同一个 KV head 的多个 Q head 的梯度 dK、dV 做求和。

## 6. 性能结果

### 6.1 Attention Benchmark（A100 80GB SXM4）

| 设置 | FA1 | FA2 | 加速比 |
|------|-----|-----|--------|
| Forward, hdim=128, 无 causal, seqlen=16k | ~73 TFLOPs/s | ~223 TFLOPs/s | **3.1×** |
| Forward, hdim=64, causal, seqlen=16k | ~94 TFLOPs/s | ~183 TFLOPs/s | **1.9×** |
| Backward, hdim=128, 无 causal, seqlen=16k | ~88 TFLOPs/s | ~196 TFLOPs/s | **2.2×** |
| Backward, hdim=64, causal, seqlen=16k | ~98 TFLOPs/s | ~166 TFLOPs/s | **1.7×** |
| Forward+Backward, hdim=128, 无 causal, seqlen=16k | ~83 TFLOPs/s | ~203 TFLOPs/s | **2.4×** |

FA2 forward 达到理论最大吞吐的 **73%**（vs FA1 的 30-50%），backward 达到 **63%**（vs FA1 的 25-35%）。

### 6.2 端到端训练（8×A100 80GB）

| 模型 | 无 FA | FA1 | FA2 |
|------|-------|-----|-----|
| GPT3-1.3B, 2k ctx | 142 TFLOPs/s | 189 TFLOPs/s | **196 TFLOPs/s** |
| GPT3-1.3B, 8k ctx | 72 TFLOPs/s | 170 TFLOPs/s | **220 TFLOPs/s** |
| GPT3-2.7B, 2k ctx | 149 TFLOPs/s | 189 TFLOPs/s | **205 TFLOPs/s** |
| GPT3-2.7B, 8k ctx | 80 TFLOPs/s | 175 TFLOPs/s | **225 TFLOPs/s** |

FA2 达到 225 TFLOPs/s（**72% model FLOPs utilization**），相比 FA1 端到端加速 **1.3×**，相比无 FA 加速 **2.8×**。

### 6.3 H100 初步结果

直接运行 FA2（未使用 H100 特有的 TMA、4th-gen Tensor Cores），即达到 **335 TFLOPs/s**。预期利用新硬件指令可再获 1.5-2× 加速。

## 7. 优化全景图

```
FA1 → FA2 的三大优化：

┌─────────────────────────────────────────────────────────────────────┐
│ 1. 算法层: 减少非 matmul FLOPs                                      │
│    ┌───────────────────────────────────────────────────────────┐    │
│    │ • 延迟归一化: 循环中不除 ℓ，最后一次性归一化               │    │
│    │ • 合并统计量: 只存 L = m + log(ℓ)，不分别存 m 和 ℓ       │    │
│    │ • 效果: 让 GPU 把更多时间花在 Tensor Core matmul 上       │    │
│    └───────────────────────────────────────────────────────────┘    │
│                                                                     │
│ 2. 并行层: 沿序列长度维度并行化                                      │
│    ┌───────────────────────────────────────────────────────────┐    │
│    │ • 反转循环顺序: 外层 Q 块（行），内层 K/V 块（列）        │    │
│    │ • Forward: 各 Q 块完全独立，zero communication            │    │
│    │ • Backward: 列方向并行，dQ 用 atomic adds                 │    │
│    │ • 效果: 长序列+小 batch 时 GPU 占用率大幅提升             │    │
│    └───────────────────────────────────────────────────────────┘    │
│                                                                     │
│ 3. Warp 层: 消除 split-K 的通信开销                                  │
│    ┌───────────────────────────────────────────────────────────┐    │
│    │ • FA1: K/V 分片给各 warp → 输出是 partial sum → 需 reduce │    │
│    │ • FA2: Q 分片给各 warp → 输出是独立行 → 无需通信          │    │
│    │ • 效果: 减少 shared memory 读写，提升计算/IO 比           │    │
│    └───────────────────────────────────────────────────────────┘    │
│                                                                     │
│ 综合效果: FA1 的 25-50% GPU 利用率 → FA2 的 50-73%                  │
│          相比 FA1 约 2× 加速，逼近 GEMM 的效率上限                   │
└─────────────────────────────────────────────────────────────────────┘
```

## 8. FA1 vs FA2 关键差异速查表

| 维度 | FlashAttention (v1) | FlashAttention-2 |
|------|-------------------|-----------------|
| **循环顺序** | 外层 K/V 块，内层 Q 块 | **外层 Q 块，内层 K/V 块** |
| **并行维度** | batch × heads | **batch × heads × seq_blocks** |
| **O 的归一化时机** | 每个内层迭代都归一化 | **只在循环结束后归一化一次** |
| **保存的统计量** | m（行最大值）+ ℓ（指数和）分别存 | **L = m + log(ℓ)（合并为 logsumexp）** |
| **Forward warp 策略** | Split-K（K/V 分片）→ 需 reduce | **Split-Q（Q 分片）→ 零通信** |
| **Backward 并行** | 仅 batch × heads | **沿列方向并行 + atomic adds** |
| **Forward GPU 利用率** | 30-50% of max | **50-73% of max** |
| **Backward GPU 利用率** | 25-35% of max | **up to 63% of max** |
| **相比标准 Attention** | 2-4× 加速 | **3-10× 加速** |
| **MQA/GQA 支持** | 无 | **隐式索引，无需复制 KV** |
