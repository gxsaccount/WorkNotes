# Efficient Memory Management for Large Language Model Serving with PagedAttention

> 论文: arXiv:2309.06180v1, SOSP 2023  
> 作者: Woosuk Kwon, Zhuohan Li, Siyuan Zhuang, Ying Sheng 等  
> 机构: UC Berkeley, Stanford University, UC San Diego

## 1. 问题背景

LLM 推理的 GPU 显存分布（以 OPT-13B / A100 40GB 为例）：

| 用途 | 占比 | 特点 |
|------|------|------|
| 模型参数 | ~65%（26GB） | 静态，serving 期间不变 |
| KV Cache | >30% | 动态，随请求增长/缩小，生命周期不确定 |
| 激活值 | <5% | 临时，推理过程中短暂使用 |

**核心矛盾**：KV Cache 的管理效率直接决定了最大 batch size，进而决定了吞吐量。但现有系统的 KV Cache 管理极度浪费。

### 1.1 KV Cache 的规模

以 OPT-13B 为例：
- 单个 token 的 KV Cache = 2 × 5120 × 40 × 2 bytes = **800 KB**
- 单个请求最长 2048 tokens → 最多 **1.6 GB**
- 40GB 显存中能存放的并发请求数极其有限

### 1.2 现有系统的三大内存浪费

现有系统（FasterTransformer、Orca）将每个请求的 KV Cache 存储在**连续内存空间**中，按最大可能长度预分配：

```
请求 A（最大 2048 tokens）：
┌─────────────────────────────────────────────────────────────────┐
│ 7 tokens │  2 slots  │          2038 slots 永不使用              │
│ 实际 KV  │ 已预留将用│        （internal fragmentation）         │
└─────────────────────────────────────────────────────────────────┘

请求 B（最大 512 tokens）：
┌───────────────────────────────┐
│ 3 tokens │ 1 slot │ 507 never│    ← external fragmentation
│ 实际 KV  │ 预留   │   used   │      （与 A 之间的碎片）
└───────────────────────────────┘
```

| 浪费类型 | 说明 |
|---------|------|
| **预留空间 (Reservation)** | 为未来 token 预留的空间，在请求生命周期内被独占 |
| **内部碎片 (Internal fragmentation)** | 实际输出长度远小于预分配的最大长度，剩余空间永不使用 |
| **外部碎片 (External fragmentation)** | 不同大小的预分配块之间的间隙，类似 buddy allocator 的碎片 |

**实测数据**：现有系统中仅 **20.4% - 38.2%** 的 KV Cache 内存被实际使用（Figure 2）。

### 1.3 缺乏共享能力

复杂解码算法（parallel sampling、beam search）中，多个输出序列可以共享 prompt 部分的 KV Cache，但连续内存分配方案无法实现这种共享。

## 2. 核心思路：类比操作系统的虚拟内存

| 操作系统概念 | PagedAttention 对应 |
|-------------|-------------------|
| 虚拟页 (Virtual page) | 逻辑 KV 块 (Logical KV block) |
| 物理页帧 (Physical page frame) | 物理 KV 块 (Physical KV block) |
| 页表 (Page table) | 块表 (Block table) |
| 字节 (Byte) | Token |
| 进程 (Process) | 请求 (Request) |
| 按需分配 (Demand paging) | 按需分配新物理块 |
| 写时复制 (Copy-on-write) | KV 块级别的 Copy-on-write |
| 换出/换入 (Swap out/in) | GPU→CPU / CPU→GPU 的 KV Cache 迁移 |

## 3. PagedAttention 算法

### 3.1 分块存储

将每个序列的 KV Cache 划分为固定大小的 **KV 块**，每个块存储 B 个 token 的 key 和 value 向量。块不需要在物理内存中连续。

标准 attention：

$$o_i = \sum_{j=1}^{i} a_{ij} v_j, \quad a_{ij} = \frac{\exp(q_i^\top k_j / \sqrt{d})}{\sum_{t=1}^{i} \exp(q_i^\top k_t / \sqrt{d})}$$

PagedAttention 将其改写为**分块计算**：

$$o_i = \sum_{j=1}^{\lceil i/B \rceil} V_j A_{ij}^\top$$

其中 $K_j, V_j$ 分别是第 j 个块中的 key/value 矩阵，$A_{ij}$ 是 query $q_i$ 对第 j 个块的 attention score 向量。

### 3.2 动态地址查找

Attention kernel 在计算时通过 **block table** 查找每个逻辑块对应的物理块地址，然后从非连续的物理块中读取 KV Cache 数据。

```
逻辑块:    Block 0 → Block 1 → Block 2
                ↓          ↓          ↓       （通过 block table 映射）
物理块:   Phys 7    Phys 1    Phys 3
           (在 GPU DRAM 中可以不连续)
```

## 4. vLLM 系统设计

### 4.1 系统架构

```
┌─────────────────────────────────┐
│       Centralized Scheduler     │
│  ┌────────────┐ ┌────────────┐  │
│  │ KV Cache   │ │  CPU Block │  │
│  │ Manager    │ │  Allocator │  │
│  │            │ ├────────────┤  │
│  │ Block      │ │  GPU Block │  │
│  │ Tables     │ │  Allocator │  │
│  └────────────┘ └────────────┘  │
└──────────┬──────────────────────┘
           │ broadcast control messages
    ┌──────┴──────┬──────────────┐
    ▼             ▼              ▼
┌────────┐  ┌────────┐    ┌────────┐
│Worker 0│  │Worker 1│ .. │Worker N│
│Model   │  │Model   │    │Model   │
│Shard 0 │  │Shard 1 │    │Shard N │
│Cache   │  │Cache   │    │Cache   │
│Engine  │  │Engine  │    │Engine  │
└────────┘  └────────┘    └────────┘
```

- **集中式调度器**：管理所有请求的调度和 KV Cache 的逻辑→物理块映射
- **GPU Block Engine**：在 GPU DRAM 上预分配一段连续内存，切分为等大小的物理 KV 块
- **CPU Block Allocator**：管理 CPU 端的物理块（用于 swap）

### 4.2 解码过程的内存管理

以 prompt "Four score and seven years ago our"（7 tokens）、block size=4 为例：

**Step 1（Prefill）：**
- 分配 2 个物理块：Block 7（存前 4 token）、Block 1（存后 3 token + 1 空位）
- 生成第一个 output token 的 KV Cache

**Step 2（第 1 步 decode）：**
- Block 1 还有 1 个空位 → 直接写入新 token 的 KV Cache
- 更新 block table 中的 #filled 计数

**Step 3（第 2 步 decode）：**
- Block 1 已满 → 分配新物理块 Block 3
- 将新 token 的 KV Cache 写入 Block 3

**关键优势**：
- 无需预留最大长度空间，按需逐块分配
- 内存浪费仅限于最后一个块的未填满部分（≤ B-1 个 token）
- 请求完成后立即释放所有物理块

### 4.3 多请求内存管理

不同请求的逻辑块映射到不同的物理块，相邻逻辑块无需对应连续物理内存，物理块在所有请求间高效复用。

## 5. 高级解码场景的内存共享

### 5.1 Parallel Sampling（并行采样）

多个输出共享同一个 prompt 的 KV Cache：

```
Sample A1: [Prompt Block 0] → [Prompt Block 1] → [Output Block ...]
                  ↕ 共享 (ref count = 2)   ↕ 共享
Sample A2: [Prompt Block 0] → [Prompt Block 1] → [Output Block ...]
```

- 物理块通过 **引用计数 (reference count)** 管理共享
- 当某个 sample 需要写入共享块时，触发 **Copy-on-Write**：
  1. 检查物理块的 ref count > 1
  2. 分配新物理块，复制原块内容
  3. 原块 ref count 减 1
  4. 在新块上执行写入

**节省**：prompt 部分（实验中占 12% KV Cache）仅存一份。

### 5.2 Beam Search

Beam search 中的共享更加复杂和动态：

```
迭代前:                              迭代后:
Beam 0: [B0][B1][B3][B6]           Beam 0 (来自旧 Beam 1): [B0][B1][B3][B6][B9]
Beam 1: [B0][B1][B3][B7]           Beam 1 (来自旧 Beam 2): [B0][B1][B3][B6][B10]
Beam 2: [B0][B1][B3][B7]           Beam 2 (来自旧 Beam 1): [B0][B1][B3][B7][B11]
Beam 3: [B0][B2][B4][B8]           Beam 3 (来自旧 Beam 2): [B0][B1][B3][B7][B12]
         ↑ 全部共享                           ↑ 旧 Beam 0,3 被淘汰，B2,B4,B5,B8 被释放
```

- 多个 beam 候选可共享大量历史物理块（不仅是 prompt）
- 共享模式随解码推进动态变化（类似 OS 的 fork 进程树）
- 传统系统需要频繁复制 KV Cache；vLLM 通过物理块共享，仅在 copy-on-write 时复制单个块

**节省**：beam search 可节省高达 **55%** 的内存。

### 5.3 Shared Prefix（共享前缀）

多个请求共享相同的 system prompt / few-shot 示例：

- LLM 服务商预先缓存共享前缀的物理块
- 新请求的逻辑块直接映射到缓存的物理块（最后一个块标记为 copy-on-write）
- Prefill 阶段仅需计算用户特定的 task input 部分

### 5.4 统一接口

vLLM 通过三个原语支持所有解码算法：
- **fork**：从现有序列创建新序列（共享物理块）
- **append**：向序列追加新 token
- **free**：释放序列的所有块

## 6. 调度与抢占

### 6.1 调度策略

- **FCFS（先来先服务）**：保证公平性，防止饥饿
- 当 GPU 物理块耗尽时，需要抢占（evict）部分请求

### 6.2 抢占策略

**All-or-nothing 驱逐**：要么驱逐一个序列的全部块，要么不驱逐（因为处理一个请求需要其所有 KV Cache）。

**Gang scheduling**：同一请求的多个序列（如 beam search 的多个候选）作为一组统一调度。

两种恢复方式：

| 方式 | 机制 | 优势 | 劣势 |
|------|------|------|------|
| **Swapping** | 将 KV 块复制到 CPU 内存，需要时再复制回来 | 大 block size 时高效 | 小 block size 时大量小数据传输，PCIe 利用率低 |
| **Recomputation** | 丢弃 KV 块，需要时将已生成 token 拼接为新 prompt 重新计算 | 与 block size 无关，开销恒定 | 需要重新执行 prefill（但比原始推理快，因为所有 token 已知） |

实测中 block size 16-64 时两种方式端到端性能相当。

## 7. GPU Kernel 优化

| 优化 | 说明 |
|------|------|
| **Fused reshape & block write** | 每层 Transformer 的 KV Cache 分块、reshape、按 block table 存储融合为单个 kernel |
| **Fused block read & attention** | 将按 block table 读取 KV Cache 和 attention 计算融合，一个 GPU warp 处理一个块 |
| **Fused block copy** | 将 copy-on-write 触发的多个不连续块复制操作合并为单次 kernel launch |

**开销**：PagedAttention kernel 比 FasterTransformer 的 attention kernel 慢 20-26%（额外的 block table 查找和分支），但端到端性能远超 FasterTransformer。

## 8. 分布式执行

- 使用 Megatron-LM 风格的 tensor model parallelism（SPMD）
- Attention 按 head 维度切分，每个 GPU 处理一部分 heads
- **关键设计**：所有 GPU worker 共享同一套逻辑→物理块映射（因为所有 shard 处理相同的 token 集合）
- 调度器在每步广播 control message（token IDs + block tables）给所有 worker
- Worker 间通过 all-reduce 同步中间结果，无需为内存管理做额外同步

## 9. 实验结果

### 9.1 实验配置

| 模型 | GPU | 总显存 | 参数大小 | KV Cache 空间 |
|------|-----|--------|---------|--------------|
| OPT-13B | 1×A100 40GB | 40 GB | 26 GB | 12 GB |
| OPT-66B | 4×A100 40GB | 160 GB | 132 GB | 21 GB |
| OPT-175B | 8×A100 80GB | 640 GB | 346 GB | 264 GB |

### 9.2 基础采样（单输出）

| 数据集 | vLLM vs Orca (Oracle) | vLLM vs Orca (Max) | vLLM vs FasterTransformer |
|--------|----------------------|--------------------|-----------------------|
| ShareGPT（长序列） | **1.7×-2.7×** 更高请求率 | **2.7×-8×** 更高请求率 | 高达 **22×** |
| Alpaca（短序列） | 类似趋势，OPT-175B 上优势较小 | 显著优势 | 显著优势 |

vLLM 在 OPT-13B + ShareGPT 下同时处理的请求数（batch size）：

| 系统 | 平均 batch size |
|------|----------------|
| Orca (Max) | 7.00 |
| Orca (Pow2) | 9.81 |
| Orca (Oracle) | 13.62 |
| **vLLM** | **30.42** |

### 9.3 Parallel Sampling & Beam Search

| 解码方式 | 相比 Orca (Oracle) 的加速 |
|---------|-------------------------|
| 基础采样 | 1.3× |
| Parallel sampling (size=6) | 更显著提升 |
| Beam search (width=6) | **2.3×** |

内存节省：

| 解码方式 | 内存节省（Alpaca） | 内存节省（ShareGPT） |
|---------|-------------------|---------------------|
| Parallel sampling (2-6 outputs) | 6.1% - 9.8% | 16.2% - 30.5% |
| Beam search (width 2-6) | 37.6% - 55.2% | 44.3% - 66.3% |

### 9.4 Block Size 选择

| Block Size | 表现 |
|-----------|------|
| 太小 (1-8) | GPU 并行度不足，读取 KV Cache 低效 |
| **16**（默认） | 兼顾 GPU 利用率和低碎片 |
| 16-128 | ShareGPT 上均表现良好 |
| 太大 (>128) | 短序列上碎片严重，Alpaca 性能下降 |

## 10. 与本项目（FlashAttention）的关系

| 维度 | FlashAttention | PagedAttention (vLLM) |
|------|---------------|----------------------|
| **优化目标** | Attention 计算的速度和峰值内存 | KV Cache 的存储管理效率 |
| **适用阶段** | Training + Inference（prefill 为主） | Inference serving（尤其是 decode） |
| **核心技术** | Tiling + online softmax，减少 HBM IO | 分页内存管理，消除碎片和浪费 |
| **内存视角** | 减少 attention 计算过程中的临时内存 | 减少 KV Cache 存储的浪费 |
| **关系** | vLLM 的 prefill 阶段可使用 FlashAttention | FlashAttention 的 paged KV cache 支持即来源于此思想 |

两者**互补**：FlashAttention 让单次 attention 计算更快、更省内存；PagedAttention 让多请求并发时 KV Cache 管理更高效。

## 11. 关键要点总结

1. **虚拟内存类比**是论文最核心的洞察——将 OS 的分页、按需分配、copy-on-write 等经典技术移植到 KV Cache 管理中。
2. **消除三类浪费**（预留、内部碎片、外部碎片），将 KV Cache 有效利用率从 20-38% 提升到 **96.3%**。
3. **Block 级共享**通过引用计数和 copy-on-write，天然支持 parallel sampling、beam search、shared prefix 等复杂解码场景。
4. **Kernel 融合**将 block table 查找开销（20-26%）通过与 attention 计算融合来摊销，端到端性能反而大幅领先。
5. **All-or-nothing eviction + gang scheduling** 是针对 LLM 特性的应用级优化，OS 的通用策略无法直接适用。
6. vLLM 的设计后来成为 LLM serving 的事实标准，PagedAttention 的思想也被 FlashAttention 等计算库所采纳（paged KV cache 支持）。
