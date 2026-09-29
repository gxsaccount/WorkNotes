# Flash Attention v1 相比原始 Attention 的优化总结

> 基于论文：FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness (arXiv:2205.14135, NeurIPS 2022)

## 1. 原始 Attention 的问题

### 1.1 标准 Attention 算法 (Algorithm 0)

```
输入: Q, K, V ∈ R^(N×d)，存储在 HBM 中

Step 1: 从 HBM 分块加载 Q, K，计算 S = QK^T ∈ R^(N×N)，将 S 写回 HBM
        S 是注意力得分矩阵，S[i,j] 表示第 i 个 query 和第 j 个 key 的点积相似度
Step 2: 从 HBM 读取 S，计算 P = softmax(S) ∈ R^(N×N)，将 P 写回 HBM
        P 是注意力权重矩阵，对 S 的每一行做 softmax 归一化，P[i,j] 表示位置 i "关注"位置 j 的权重
Step 3: 从 HBM 分块加载 P, V，计算 O = PV ∈ R^(N×d)，将 O 写回 HBM
        O 是最终输出，用权重 P 对 V 做加权求和
返回 O
```

### 1.2 存在的问题

| 问题 | 说明 |
|------|------|
| **显存 O(N²)** | 必须在 HBM 中为完整的 N×N 中间矩阵 S 和 P 分配空间并完整写入 |
| **HBM 访问量大** | 标准实现需要 **Θ(Nd + N²)** 次 HBM 访问（论文 Theorem 2） |
| **memory-bound** | 大部分操作（softmax、masking、dropout）是内存带宽受限的，GPU 算力利用率低 |
| **多次 kernel launch** | PyTorch 中实际执行为多个独立 CUDA kernel：matmul → mask → softmax → dropout → matmul，每次 kernel 之间中间结果必须经 HBM "落盘" |

论文关键论点：**近似注意力方法关注 FLOPs 缩减，但 FLOPs 并不直接对应 wall-clock 速度；真正的瓶颈是 HBM 访问（IO）。**

### 1.3 GPU 内存层次结构

论文以 A100 为例说明两级存储的带宽差距：

```
┌────────────────────────────────────┐
│  SRAM（片上共享内存）               │  ~19 TB/s 带宽,  ~20 MB（108 个 SM 各 192 KB）
├────────────────────────────────────┤
│  HBM（高带宽显存）                 │  ~1.5-2.0 TB/s 带宽,  40-80 GB
└────────────────────────────────────┘
         约 10× 带宽差距
```

> 论文原文 (Section 2.1): "As compute has gotten faster relative to memory speed, operations are increasingly bottlenecked by memory (HBM) accesses. Thus exploiting fast SRAM becomes more important."

## 2. Flash Attention 的核心优化

论文提出两个已有技术的组合 + 一个实现层面的关键决策：

### 2.1 分块计算 — Tiling

将 Q、K、V 分成小块，在 SRAM 中逐块完成注意力计算，**避免在 HBM 中生成完整的 N×N 矩阵**。

**分块大小的选取（Algorithm 1 line 1）：**

```
B_c = ⌈M / (4d)⌉        — K/V 分块的行数
B_r = min(⌈M / (4d)⌉, d) — Q 分块的行数
```

其中 M 为 SRAM 大小。分块大小由 SRAM 容量决定，需要同时容纳 Q_i (B_r × d)、K_j (B_c × d)、V_j (B_c × d)、以及中间结果 S_ij (B_r × B_c)。

**FA1 的循环结构（Algorithm 1）：**

```
外层循环: for j = 1 to T_c          ← 遍历 K/V 分块
  将 K_j, V_j 从 HBM 加载到 SRAM
  内层循环: for i = 1 to T_r        ← 遍历 Q 分块
    将 Q_i, O_i, ℓ_i, m_i 从 HBM 加载到 SRAM
    在 SRAM 中计算 S_ij = Q_i @ K_j^T             ← GEMM
    在 SRAM 中计算局部 softmax 统计量并更新 O_i    ← 见 2.2
    将更新后的 O_i, ℓ_i, m_i 写回 HBM
  end for
end for
```

**注意 FA1 的循环顺序：外层遍历 K/V 块，内层遍历 Q 块。** 即 K_j/V_j 驻留 SRAM，所有 Q 块轮流进来更新各自的输出 O_i。这意味着每个 Q 块的中间输出 O_i 和统计量 (ℓ_i, m_i) 要随外层循环反复读写 HBM（共 T_c 次）。

> 论文 Figure 1 caption: "In the outer loop (red arrows), FlashAttention loops through blocks of the K and V matrices and loads them to fast on-chip SRAM. In each block, FlashAttention loops over blocks of Q matrix (blue arrows), loading them to SRAM, and writing the output of the attention computation back to HBM."

### 2.2 在线 Softmax (Online / Tiling-Safe Softmax)

标准 softmax 需要完整的一行数据才能计算（先求全局 max，再求全局 sum）。Flash Attention 使用分块可递推的 softmax 分解。

**数学基础：** 对向量 x^(1), x^(2) ∈ R^B 的拼接 x = [x^(1), x^(2)] ∈ R^(2B)，softmax 可以分解为：

```
m(x) = max(m(x^(1)), m(x^(2)))                          — 合并 max

f(x) = [e^{m(x^(1)) - m(x)} · f(x^(1)),  e^{m(x^(2)) - m(x)} · f(x^(2))]   — 缩放 exp

ℓ(x) = e^{m(x^(1)) - m(x)} · ℓ(x^(1)) + e^{m(x^(2)) - m(x)} · ℓ(x^(2))    — 合并 sum

softmax(x) = f(x) / ℓ(x)
```

**在算法中的具体操作（Algorithm 1 line 9-13）：** 对每个块 (i, j)：

```
1. 计算当前块得分:  S_ij = Q_i @ K_j^T                          ∈ R^(B_r × B_c)
2. 当前块局部统计:  m̃_ij = rowmax(S_ij)                          ∈ R^B_r
                    P̃_ij = exp(S_ij - m̃_ij)                      ∈ R^(B_r × B_c)
                    ℓ̃_ij = rowsum(P̃_ij)                          ∈ R^B_r
3. 合并全局统计:    m_i^new = max(m_i, m̃_ij)
                    ℓ_i^new = e^{m_i - m_i^new} · ℓ_i + e^{m̃_ij - m_i^new} · ℓ̃_ij
4. 更新输出:        O_i = diag(ℓ_i^new)^{-1} · (diag(ℓ_i) · e^{m_i - m_i^new} · O_i
                                                  + e^{m̃_ij - m_i^new} · P̃_ij @ V_j)
5. 更新统计量:      m_i ← m_i^new,  ℓ_i ← ℓ_i^new
```

关键点：
- 通过维护每行的 **m_i**（行最大值）和 **ℓ_i**（归一化因子），可以逐块增量计算 softmax
- 每接入一个新的 K 块，用 max 差值的指数对历史累加结果进行 **缩放修正**
- **完整的 N×N 的 S 和 P 矩阵从未在 HBM 中出现过**，每个 B_r × B_c 的小块 S_ij 仅临时存在于 SRAM 中，用完即丢弃

### 2.3 反向传播中的重计算 (Recomputation)

标准反向传播需要保存前向的 S, P ∈ R^(N×N) 来计算梯度，占用 O(N²) 显存。

**Flash Attention 的策略：**
- 前向只保存 **O**（输出）和 **softmax 归一化统计量 (m, ℓ)**，共 O(N) 额外存储
- 反向传播时，从 HBM 中的 Q, K, V 重新分块计算 S 和 P（利用保存的 m, ℓ 恢复正确的 softmax 值）

> 论文原文 (Section 3.1): "by storing the output O and the softmax normalization statistics (m, ℓ), we can recompute the attention matrix S and P easily in the backward pass from blocks of Q, K, V in SRAM. This can be seen as a form of selective gradient checkpointing."

**与传统 gradient checkpointing 的区别：** 传统做法用速度换内存（重算导致变慢）。Flash Attention 的重算反而 **更快**，因为减少了 HBM 访问量——attention 是 memory-bound 的，额外的 FLOPs 被 IO 节省所覆盖。

> 论文原文: "even with more FLOPs, our recomputation speeds up the backward pass due to reduced HBM accesses (Fig. 2)."

### 2.4 Kernel 融合 (Kernel Fusion)

> 论文原文 (Section 3.1 "Implementation details: Kernel fusion"): "Tiling enables us to implement our algorithm in one CUDA kernel, loading input from HBM, performing all the computation steps (matrix multiply, softmax, optionally masking and dropout, matrix multiply), then write the result back to HBM. This avoids repeatedly reading and writing of inputs and outputs from and to HBM."

标准实现中的多步操作（matmul → scale → mask → softmax → dropout → matmul）被融合为 **单个 CUDA kernel**：

```
标准实现 (PyTorch):
  Kernel 1: S = Q @ K^T       → S 写 HBM
  Kernel 2: S = mask(S)       → 从 HBM 读 S，写 HBM
  Kernel 3: P = softmax(S)    → 从 HBM 读 S，P 写 HBM
  Kernel 4: P = dropout(P)    → 从 HBM 读 P，写 HBM
  Kernel 5: O = P @ V         → 从 HBM 读 P, V，O 写 HBM

Flash Attention:
  单一 Kernel: 从 HBM 加载 Q/K/V 分块 → SRAM 内完成全部计算 → 只将 O 写回 HBM
```

Kernel 融合是 tiling 的 **实现前提**——只有在同一个 kernel 内，分块的中间结果才能留在 SRAM 中而不必写回 HBM。

论文也指出，传统的 kernel fusion（如编译器自动融合 elementwise 操作）在训练中效果有限，因为中间值仍需保存用于反向传播。Flash Attention 的 recomputation 策略解决了这个问题。

## 3. IO 复杂度分析

论文给出了严格的 IO 复杂度证明（Theorem 2 + Proposition 3）：

### 3.1 HBM 访问量对比

| 算法 | HBM 访问量 | 条件 |
|------|-----------|------|
| 标准 Attention (Algorithm 0) | **Θ(Nd + N²)** | — |
| FlashAttention (Algorithm 1) | **Θ(N²d² / M)** | d ≤ M ≤ Nd |

其中 N 为序列长度，d 为头维度，M 为 SRAM 大小。

**为什么 Flash Attention 更少？** 证明思路（Section 3.2）：
- 每个 K/V 块大小 Θ(M)，共 Θ(Nd/M) 个块
- 对每个 K/V 块，需遍历所有 Q 块，每次加载 Θ(Nd) 数据
- 总 HBM 访问 = Θ(Nd/M) × Θ(Nd) = **Θ(N²d²/M)**

**数值示例（论文 Figure 2）：**

| | 标准 Attention | FlashAttention |
|---|---|---|
| GFLOPs | 66.6 | 75.2（更多，因为 recomputation） |
| HBM R/W (GB) | 40.3 | **4.4**（减少 ~9×） |
| Runtime (ms) | 41.7 | **7.3**（加速 ~5.7×） |

> 关键发现：**Flash Attention 的 FLOPs 更多，但因为 HBM 访问大幅减少，实际运行反而更快。** 这验证了论文的核心论点——对于 memory-bound 操作，IO 而非 FLOPs 才是性能的决定因素。

### 3.2 最优性证明：为什么 FA1 的 IO 已经无法再优化

> 论文 Proposition 3: "There does not exist an algorithm to compute exact attention with o(N²d²/M) HBM accesses for all M in the range [d, Nd]."

Flash Attention 的 HBM 访问量 Θ(N²d²/M) 已经是所有精确注意力算法的 **渐近下界**，即在 IO 层面无法进一步优化。

#### 下界证明的核心思路

证明基于矩阵乘法的 IO 下界（Hong & Kung, 1981 红蓝卵石博弈）：

```
经典结论: 在 SRAM 大小为 M 的两级存储模型下，
计算矩阵乘法 C = A × B（维度 n×n）至少需要 Ω(n³/√M) 次 HBM 访问。

直觉: SRAM 每次能容纳 √M × √M 的子矩阵块，
      要完成 n×n 的乘法，需要 (n/√M)³ = n³/M^{3/2} 个块组合，
      每个组合需要搬 O(M) 数据 → 总 IO = Ω(n³/√M)。
```

将此结论应用到 attention：

```
Attention 包含 S = Q @ K^T，其中 Q, K ∈ R^{N×d}:
  输出 S ∈ R^{N×N}，但 FA1 不需要把 S 完整写出来。

关键约束 —— softmax 需要全局信息:
  softmax 要求每行的 max 和 sum → 每个 Q 行块必须和所有 K 块至少交互一次。

推导:
  SRAM 大小为 M，一次最多容纳:
    一个 Q 块: B_r × d ≈ M/(4d) × d = M/4
    一个 K 块: B_c × d ≈ M/(4d) × d = M/4
    （还要放 V 块 + 中间结果 S_ij）

  Q 共有 N/B_r ≈ 4Nd/M 个块
  K 共有 N/B_c ≈ 4Nd/M 个块

  每对 (Q_i, K_j) 至少交互一次 → 至少 (4Nd/M)² 次块级操作
  每次操作至少搬运一个块 ≈ O(M/4) 数据

  但更紧的分析是: 每次外层迭代加载一个 K/V 块后，
  内层要遍历所有 Q 块 → 每次外层迭代 IO = O(Nd)
  外层共 O(Nd/M) 次
  → 总 IO = O(Nd/M) × O(Nd) = O(N²d²/M)

  论文证明这也是下界: 不可能比 Ω(N²d²/M) 更少。
```

#### 为什么下界恰好等于 FA1 的上界

```
FA1 的 IO:      Θ(N²d²/M)   ← 上界（算法实际做到的）
理论下界:        Ω(N²d²/M)   ← 任何精确 attention 算法不可能更少

上界 = 下界 → FA1 的 IO 复杂度是渐近最优的！
```

#### 直觉理解

```
为什么不能更少:
  1. softmax 需要全局信息 → 每个 Q 行必须看完所有 K 列
  2. SRAM 一次只能放 O(M) 数据 → Q 和 K 的 N²d² 对交互必须分批搬运
  3. 每批搬运量受 M 限制 → 至少需要 N²d²/M 次搬运

为什么 FA1 恰好做到了:
  1. tiling 使得每次只搬一个 B_r×d 或 B_c×d 的小块
  2. online softmax 使得看完一个 K 块就可以丢弃 S_ij，不需要写回 HBM
  3. 没有任何冗余搬运 → 恰好触及下界
```

#### 对后续优化的启示

**FA1 之后，IO 这条路已经走到头了。** 这也是为什么 FA2 转向了完全不同的优化方向——不再减少 IO 量，而是提高 GPU 计算单元的利用率（SM 并行度 + warp 有效计算密度）。

## 4. Block-Sparse 扩展

Flash Attention 还扩展为 **block-sparse** 版本，在 Algorithm 1 基础上跳过稀疏掩码中的零块：

- IO 复杂度降为 **Θ(Nd + N²d²s/M)**，其中 s 为非零块比例
- 使用 butterfly 稀疏模式，可实现 Θ(N√N) 或 Θ(N log N) 的 IO 复杂度
- 比所有已知的近似注意力方法都快（论文 Table 3）

## 5. 量化效果总结

| 指标 | 标准 Attention | Flash Attention v1 |
|------|---------------|-------------------|
| 显存复杂度 | O(N²) | **O(N)** |
| HBM IO 复杂度 | Θ(Nd + N²) | **Θ(N²d²/M)** |
| 是否精确 | 是 | **是（数学等价，Theorem 1）** |
| Attention 加速 | — | **最高 7.6×**（GPT-2, Figure 1） |
| 显存效率 | — | **最高 20×**（Figure 3） |
| BERT-large 训练加速 | — | **15%**（vs MLPerf 1.1 纪录） |
| GPT-2 端到端加速 | — | **3×**（vs HuggingFace） |
| 长序列能力 | OOM @ 64K | **支持 64K**（block-sparse 版本） |

## 6. 优化全景图

```
标准 Attention（多个 Kernel，N×N 矩阵反复读写 HBM）:

  HBM:  Q,K → [S=QK^T] → mask(S) → [P=softmax(S)] → dropout(P) → [O=PV]
              ↕ 写+读      ↕ 写+读      ↕ 写+读          ↕ 写+读
        每一步的中间结果都要完整写入 HBM，共 Θ(Nd + N²) 次 HBM 访问


Flash Attention（单个 Kernel，分块在 SRAM 中完成）:

  HBM:  Q, K, V ──分块加载──→  SRAM 内完成全部计算  ──→  O, (m, ℓ)
        ↑                      ↑                        ↑
     Θ(Nd) 读            S_ij, P̃_ij 从不离开 SRAM    Θ(Nd) 写
                    总 HBM 访问: Θ(N²d²/M) ← 省去所有 N×N 矩阵的 HBM 读写
```

## 7. 局限性（论文 Section 5）

1. **需要手写 CUDA kernel** — 每种新的 attention 变体都要重新实现，工程成本高，且不易跨 GPU 架构移植
2. **单 GPU 最优，未考虑多 GPU** — 多 GPU 场景需额外考虑 GPU 间数据传输的 IO 分析
3. **IO-aware 思想可泛化** — 论文认为 attention 之外的其他层（LayerNorm, FFN 等）也可受益于 IO 感知优化

这些局限在后续工作中被逐步解决：FA2 通过反转循环顺序 + 更好的 work partitioning 获得 ~2× 加速；FA3/FA4 针对 Hopper/Blackwell 架构做了进一步硬件适配。
