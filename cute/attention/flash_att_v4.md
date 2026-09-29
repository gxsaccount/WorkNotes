# Flash Attention v4 相比 v3 的优化总结

> 基于论文：FlashAttention-4: Algorithm and Kernel Pipelining Co-Design for Asymmetric Hardware Scaling (arXiv:2603.05451v1, Mar 2026)

## 0. 核心动机

FA3 在 Hopper H100 上做到了 ~75% 利用率，但行业已快速切换到 Blackwell（B200/GB200），新的架构表现出**非对称硬件缩放（asymmetric hardware scaling）**：

| 资源 (per SM, per cycle) | Hopper H100 | Blackwell B200 | 变化 |
|---|---|---|---|
| BF16 Tensor Core | 4096 ops | **8192 ops** | **2×** |
| 指数单元 MUFU | 16 ops | 16 ops | 不变 |
| SMEM 读带宽 | 128 B | 128 B | 不变 |

**核心问题：Tensor Core 吞吐翻倍，但 SMEM 带宽和指数单元没变。** 对于典型 attention 工作负载，瓶颈从 matmul 转移到 SMEM 流量和 softmax 的 `exp`，前者在反向中超 MMA 约 25-60%。直接把 FA3 移植过来要么性能低下，要么因为 Hopper WGMMA 在 Blackwell 上没有前向兼容而根本跑不起来。

FA4 的设计原则：**算法与 Kernel 协同设计**，针对转移后的瓶颈做优化，而不是把硬件当作均匀资源。

## 1. Blackwell GPU 硬件特性回顾

### 1.1 新增内存层级：Tensor Memory (TMEM)

```
┌─────────────────────────────────┐
│  RMEM（寄存器）                  │  256 regs/thread
├─────────────────────────────────┤
│  TMEM（张量内存）【新】           │  256 KB/SM, 与 Tensor Core 紧耦合
│  - warp-synchronous              │  MMA 直接异步写入，不过寄存器
│  - 32 列 (16 KB) 粒度分配         │
├─────────────────────────────────┤
│  SMEM（共享内存）                │  ~228 KB/SM, 128 B/cycle 读
├─────────────────────────────────┤
│  L2 / HBM                       │
└─────────────────────────────────┘
```

TMEM 解决了 Hopper 上累加器把寄存器"吃光"的问题，允许更大的 tile 和更多并发累加。

### 1.2 第五代 Tensor Core：更大、更异步

| | Hopper WGMMA | **Blackwell UMMA** |
|---|---|---|
| 指令粒度 | 64 × N | **128 × N**（面积翻倍）|
| 累加器写到哪 | 寄存器 | **TMEM**（完全异步）|
| 启动/等待 | 线程同步 | 异步，MMA 单元不再阻塞寄存器回写 |

Tile 变大意味着：一次 MMA 指令覆盖更多元素 → 发射频率降低 → 但单次读的 operand 必须喂饱更大的 tile，**SMEM 读被重复使用的次数变多**（见 §2）。

### 1.3 2-CTA MMA 模式【新】

Blackwell 允许同一 cluster 内的一对 CTA **协同执行单个 MMA**：

```
┌──────────────── Cluster (2 CTAs) ────────────────┐
│                                                   │
│   CTA0                           CTA1             │
│  ┌────────┐                    ┌────────┐         │
│  │ SMEM:  │                    │ SMEM:  │         │
│  │ B_left │                    │ B_right│         │
│  │ (N/2)  │                    │ (N/2)  │         │
│  └───┬────┘                    └───┬────┘         │
│      │      ┌─────────────────┐    │              │
│      └──→   │  Tensor Core    │  ←─┘              │
│             │  消费完整 B tile │                    │
│             └────────┬────────┘                    │
│                      ↓                             │
│         TMEM (CTA0 一半) / TMEM (CTA1 一半)         │
└───────────────────────────────────────────────────┘
```

关键性质：
- 一个线程发起 MMA，对端 CTA 必须存活并 hold 住它那一半 B。
- M 维支持 128 或 256；**B 沿 N 切半**，A 和累加器沿 M 切半。
- 每个 CTA **只 stage 一半的 B 到自己的 SMEM**，总 SMEM 流量减半（这是 BWD 优化的核心杠杆）。

### 1.4 Roofline 数字

```
Feeds & Speeds (B200, per SM, per cycle):
  Tensor Core BF16:  8192 ops
  MUFU (exp2):         16 ops   ← 比 TC 慢 512×
  SMEM 读:            128 B
```

## 2. Roofline 分析（识别瓶颈）

### 2.1 前向

两次 MMA（QK^T 和 PV），`S = SMEM-SMEM`、`PV = TMEM-SMEM`：

| Tile | MMA | SMEM | Exp |
|---|---|---|---|
| M=N=d=128 | 1024 | 768 | 1024 |
| **M=256, N=d=128** | 2048 | 1536 | 2048 |

→ **MMA 与 Exp 并列瓶颈**，motivate: 用更大 tile 摊薄 SMEM、用 FMA 模拟 exp、跳掉不必要的 rescale。

### 2.2 反向

五次 MMA（S, dP, dV, dQ, dK）：

| 资源 (M=N=d=128) | 1-CTA | **2-CTA (M=256)** |
|---|---|---|
| MMA compute | 2560 | 2560 |
| SMEM (MMA operands) | 2048 | **1536** |
| SMEM (dS write) | 256 | 256 |
| SMEM (dS DSMEM) | 0 | 384 |
| SMEM (dQ write+read) | 1024 | **512** |
| **Total SMEM** | **3328** | **2688** |
| Exp | 1024 | 1024 |

→ 1-CTA 下 SMEM 超过 MMA 约 30%，是主瓶颈；**2-CTA 把 SMEM 流量压到比 MMA 仅高 5%**，非常接近 roofline。

## 3. 前向（Forward）三大优化

### 3.1 优化一：围绕 TMEM 重构 ping-pong 流水线

沿用 FA3 每个 thread block 计算两个输出 tile 的 ping-pong 思路，但 Blackwell 有几个根本变化：

| | FA3 (Hopper) | **FA4 (Blackwell)** |
|---|---|---|
| 累加器位置 | 寄存器（4 线程/行交织）| **TMEM** |
| 单 tile 形状 | 64×128 | **128×128** |
| P 如何传递 | 寄存器文件 | **TMEM** |

**Warpgroup 角色（4 个 WG / CTA）：**

```
CTA 内部 (4 warpgroups):
┌──────────────────────────────────────────────────────────────┐
│  WG-A: MMA / TMA 驱动 (发 MMA 指令、发 TMA)                    │
│  WG-B1, WG-B2: Softmax（每个 WG 128 线程，每线程处理整行）       │
│  WG-C: Correction（Output rescale）                            │
└──────────────────────────────────────────────────────────────┘
```

关键设计点：
1. **每线程处理整行**：一行 128 个元素，由一个线程全拿到 RMEM。好处是求 rowmax/rowsum 不需要 warp 内 shuffle。代价是要 128 个寄存器装输入 + 可能 64 个装输出。
2. **两个 Softmax WG 显式同步**，不让两边同时进入"exp 关键区"。
3. **Correction 解耦**：因为 P 经 TMEM 而不是寄存器传给下游 MMA，可以把"用 \(e^{m_{j-1}-m_j}\) 去 rescale O" 的工作从 softmax WG 搬到独立的 Correction WG，移出关键路径。

**TMEM 分区策略（hdim=128）：**

```
TMEM (256 KB/SM):
 ┌─────────────┐  ┌─────────────┐
 │  O tile 0   │  │  O tile 1   │    ← 两份输出累加器
 └─────────────┘  └─────────────┘
 ┌─────────────┐  ┌─────────────┐
 │ S tile 0    │  │ S tile 1    │    ← 与 P 复用同一块区域
 │ / P tile 0  │  │ / P tile 1  │
 └─────────────┘  └─────────────┘
 ┌──────────────────────────────┐
 │  rescale statistics          │    ← 给 Correction WG 传 scale
 └──────────────────────────────┘
```

选择"两份 S 与 P 复用"而不是"一份 S + 两份 P"，原因是**流水线启动时能立刻发出两个 S MMA**。

**P 分段写回**：前 3/4 写完一起触发后续 MMA，最后 1/4 单独写，以降低寄存器峰值。

### 3.2 优化二：指数函数软件模拟（突破 MUFU 瓶颈）

**问题：** MUFU 16 ops/cycle，Tensor Core 8192 ops/cycle，差 512×。Softmax 的 exp 数量与 S 元素数成正比，在 Blackwell 上已经是一级瓶颈。

**解法：** 在 FMA 单元上用多项式近似并行跑 `2^x`，和 MUFU 同时出货。

```
2^x = 2^⌊x⌋ · 2^{x-⌊x⌋}       (Cody-Waite 范围归约)

① 整数部分 2^⌊x⌋:
   直接操纵 IEEE-754 指数位 = 整数 ALU 的 shift + add

② 小数部分 2^{x_frac}，x_frac ∈ [0,1):
   Horner FMA 多项式   Σ p_i · x_frac^i
   系数由 Sollya 生成，最小化 [0,1) 上相对误差
```

**执行算法：**
1. Clamp `x ≥ -127` 防下溢
2. 用 magic-number (`x + 2^23 + 2^22` 再减回，round-down) 取出 `⌊x⌋`
3. `x_frac = x - ⌊x⌋`
4. Horner FMA 得到 `2^{x_frac}`
5. 将 `⌊x⌋` 拼到指数域，和 mantissa 合并

**精度（4M 随机样本，BF16 输出）：**

| 方法 | FP32 最大相对误差 | BF16 量化后最大相对误差 |
|---|---|---|
| 硬件 MUFU.EX2 | 1.41e-7 | 3.89e-3 |
| Degree-3 多项式 | 8.77e-5 | **3.90e-3** |
| Degree-5 多项式 | 1.44e-7 | 3.89e-3 |

**结论：** Degree-3 足够 —— BF16 量化误差（~3.9e-3）把多项式误差淹没掉了，99% 输入与硬件差 ≤ 1 BF16 ULP。

**部分模拟策略（10–25%）：** 不能全走 FMA，否则寄存器/指令带宽反而吃亏。按 MMA 与 Exp 的吞吐比动态选一小部分元素走 FMA 模拟，其余继续走 MUFU，让两条路径同时饱和。

### 3.3 优化三：条件 Softmax Rescaling（Skip online rescale）

**FA 原始在线 softmax：**

```
处理第 j 块:
  m_j = max(m_{j-1}, rowmax(S_j))
  ℓ_j = e^{m_{j-1} - m_j} · ℓ_{j-1} + rowsum(e^{S_j - m_j})
  O_j = e^{m_{j-1} - m_j} · O_{j-1} + e^{S_j - m_j} · V_j   ← 每块都要向量乘
```

`e^{m_{j-1}-m_j} · O_{j-1}` 这一步向量乘操作次数 ∝ d×M_tile，代价不小。

**两个观察：**

1. `m_j > m_{j-1}` 时才真需要 rescale（新的更大最大值出现）。
2. 允许一定"slack"：只有 `m_j - m_{j-1} > τ` 才 rescale；只要记录累计的 scale，最后一次性由真正的 `m_final, ℓ_final` 归一化，不影响正确性。

**FA4 公式：**

\[
O_j=\begin{cases} e^{m_{j-1}-m_j}\,O_{j-1}+e^{S_j-m_j}\,V_j,& m_j-m_{j-1}>\tau\\[4pt] O_{j-1}+e^{S_j-m_{j-1}}\,V_j,& \text{otherwise}\end{cases}
\]

默认 `τ = log2(256) = 8`，即只有 max 跃升超过 256× 才触发 rescale。最终：

\[
\text{Output} = \frac{1}{\ell_{\text{final}}} O_{\text{final}}
\]

**实现细节：** 为避免 warp 分歧，warp 内任一线程判定需要 rescale 则全员 rescale（整 warp 一起进入那条分支）。

## 4. 反向（Backward）三大优化

### 4.1 优化一：5-MMA 的新流水线（靠 TMEM 解串行）

BWD 有 5 个 MMA：`S^T = KQ^T`、`dP^T = V dO^T`、`dV = P^T dO`、`dQ = dS K`、`dK = dS^T Q`。FA3 下累加器都挤在寄存器里，排程几乎是串行（S → dP → dV → dQ → dK），只有 TMA 能跑在外头。

**FA4 的改变：**
- **dV 和 dK 长期驻留 TMEM**（两者是累加，不能共享空间，各占一块）。
- **S/P 共用一块 TMEM 区域**（offset 0）。
- **dP/dS/dQ 共用另一块**（中间结果，轮着复用）。

这样 TMEM 恰好放得下 "≤ 4 个 128×128 tile" —— 正好是主流水线所需。

**关键重叠：** 用**上一迭代的 dQ/dK MMA** 来跟本迭代的 softmax/elementwise 重叠，保证任意时刻都有 ≥ 2 个 MMA 在飞。

### 4.2 优化二：2-CTA UMMA（砍一半 SMEM + 砍一半 atomicAdd）

#### SMEM 流量减半

- 采用 M=256, N=K=128 的 2-CTA UMMA。
- 每 CTA 只 stage 一半 operand B 到自己的 SMEM，硬件从两边拼起来喂 Tensor Core。
- 五个 MMA 里，操作数 B 的 SMEM 读量大致**减半**。

#### dQ 的冲突与 DSMEM 解法

dQ 的 reduction 轴是 `N`（K/V seqlen）—— 恰好是 2-CTA 切分 B 的维度！如果直接套 2-CTA，每个 CTA 只会看到 N 的一半，reduction 不完整。

**解法：** 用 **DSMEM（distributed shared memory）** 在 cluster 内的两个 CTA 间交换一半 dS，把 dS **沿非 reduction 轴重新打包**：

```
2-CTA BWD dQ step:

Before (dS layout from dP computation):
   CTA0: dS[0:M,   0:N/2]    CTA1: dS[0:M,   N/2:N]
                ↑  N 被切半，reduction 不完整

通过 DSMEM 对换一半:
   CTA0: dS[0:M/2, 0:N]      CTA1: dS[M/2:M, 0:N]
                ↑  M 被切半，每个 CTA 自己就能完成整个 N 的 reduction

每个 CTA 的 dQ MMA:
   (M/2, 2N) × (2N, d) → (M/2, d)   注意 reduction 轴变 2N
```

**整个 BWD MMA tile 形状：**

| MMA | Shape |
|---|---|
| S, dP, dV, dK | M=256, N=K=128 (2-CTA) |
| **dQ** | M=128, N=K=**256**（double reduction）|

**流水线重排：** 把"本 tile 的 dP 计算"提到"上 tile 的 dQ MMA"之前，让 DSMEM 交换延迟被 dP MMA 遮盖；同时 dQ tile 小到能和 P 一起塞进 TMEM（复用 S 的那块，不再和 dP 共用），进一步让本 tile 的 dS elementwise 和上 tile 的 dQ MMA 并发。

#### 全局 atomicAdd 减半

FA3 中 dQ 需要跨 K/V 维度累加到全局内存，每个内层循环都要一次 atomicAdd —— 非常贵且**引入非确定性**。

2-CTA 下每个 CTA 只持有 dQ tile 的一半（沿 M），**写出次数天然减半**。

### 4.3 优化三：确定性 BWD（Deterministic mode）

**非确定性来源：** dQ（GQA 下还有 dK/dV）跨 CTA 的全局 atomicAdd 顺序不定 → 每次运行结果有浮点误差级别的抖动，对 RL/debug 不友好。

**解法：** Semaphore lock 串行化全局 reduction。每个写共享 dQ tile 的 CTA：
1. 按预定顺序拿锁；
2. 做 reduction；
3. 通过递增计数器释放锁。

**性能代价两项：**
- Memory fence 成本（acquire-release 语义需要 device-wide 可见性）。
- 后到的 CTA 要在锁上 stall。

**缓解调度：**
- head/batch 维做 CTA swizzle，使活跃 tile 集合能塞进 L2。
- Causal 情况：**KV block 降序发射，Q block 从对角线升序遍历，dQ reduction 按 Q block 降序**（SPT，shortest-processing-time-first），让首次写入的 CTA 不被任何 stall 阻塞。

实测确定性 BWD 达到非确定 1-CTA 版本的 **~75% 速度**。

## 5. 调度（Scheduling，跨架构通用）

### 5.1 LPT (Longest-Processing-Time-First) for Causal

原始 grid 是 `(mblocks, heads, batches)`，按递增顺序处理，但 causal mask 下这正好是从短到长 —— 最糟的顺序。

**FA4 的两难：**
- 朴素 LPT（最长先跑）会让不同 batch 的 KV load 命不中 L2。
- 把所有 heads 一次全加载又会爆 L2。

**折中方案：**
```
for batch in batches:                       # 最外层
    for section in sections(heads):         # 切成不超 L2 容量的 section
        for h in heads_of(section):
            for m in mblocks_reverse:       # 反向走 m，配合 causal
                process(batch, h, m)
```

MQA/GQA 下总是先遍历同 KV head 的所有 Q head，再换 m。H200 实测：MHA BF16 hdim=128 **+4–8% FLOPS**，MQA **+7–14%**。

### 5.2 LPT for Varlen

变长场景下不同 batch 工作量差别大（混合 prefill/decode 时尤其明显）。FA4 跑一个**预处理 kernel** 按每 worktile 最大执行时间对 batch 排序，产出"虚拟→物理"索引映射，attention kernel 按排序顺序访问。metadata 可以缓存，无额外开销。

## 6. 工程：CuTe-DSL（Python）

FA4 **完全用 CuTe-DSL（嵌入 Python）** 写，不含 C++。路径：

```
Python (CuTe-DSL) ──JIT──→ PTX ──ptxas──→ SASS
```

**保留的能力：**
- 编程模型与 CUTLASS C++ 同构，所有底层 GPU 能力都可表达。
- `cute.jit` 可把 PTX 当 escape hatch，定制指令不受框架约束。

**拿到的收益：**

| 单 kernel 编译时间 | FA3 (C++ templates) | **FA4 (CuTe-DSL)** | 加速 |
|---|---|---|---|
| 前向 | 55s | **2.5s** | **22×** |
| 反向 | 45s | **1.4s** | **32×** |

考虑到 FA2/FA3 通常要预编译几百个变体 kernel（dtype × hdim × causal × mask_mod × ...），这一量级的加速是从"小时级" → "分钟级"的改写。社区已经在其上做出了 FlexAttention、block-sparse 等变体，无需改核心框架。

## 7. 性能对比（B200 BF16, hdim=128）

### 7.1 Forward

| | 对比 Triton | 对比 cuDNN 9.13 | 峰值 |
|---|---|---|---|
| Non-causal | 2.1× | 1.1× | — |
| Causal | **2.7×** | **1.3×** | **~1613 TFLOPS (71% 理论峰值)** |

Causal 下优势更大，主要得益于 LPT 调度。

### 7.2 Backward

长序列、causal 下持续领先；确定性版本通过 SPT + swizzle 达到非确定版 ~75% 速度。

### 7.3 DeepSeek-V3 异构 hdim (192, 128)

专门针对 `head_dim_q=192, head_dim_kv=128` 的 causal 场景也做了优化，相比 cuDNN 有稳定加速。

## 8. 优化全景图：FA3 → FA4

```
FA3 (Hopper, 异步模型, 围绕寄存器):
  ┌─────────────────────────────────────────────────────┐
  │ Producer WG:  TMA loads                              │
  │ Consumer WG1/WG2: pingpong (WGMMA + softmax)         │
  │   累加器 → 寄存器                                      │
  │   P → 寄存器 → 下游 WGMMA                              │
  │ 瓶颈:  TC / SMEM / Exp 相对均衡                        │
  │ H100 利用率: ~75%                                     │
  └─────────────────────────────────────────────────────┘

FA4 (Blackwell, 异步模型, 围绕 TMEM):
  ┌─────────────────────────────────────────────────────┐
  │ 4 个 WG / CTA:                                       │
  │   WG-A:  MMA + TMA                                   │
  │   WG-B1/B2: Softmax（每线程整行、MUFU+FMA 并行 exp）    │
  │   WG-C:  Correction (rescale 解耦出关键路径)           │
  │                                                      │
  │ 累加器 → TMEM；P → TMEM；O rescale 条件跳过            │
  │                                                      │
  │ 2-CTA UMMA:                                          │
  │   B 按 N 切半 → SMEM 流量 ↓                            │
  │   dQ 用 DSMEM 交换 dS → atomicAdd ↓ 50%               │
  │                                                      │
  │ 三层重叠: TMA ∥ UMMA ∥ (softmax: MUFU + FMA)         │
  │ B200 利用率: ~71% (1613 TFLOPS, BF16)                │
  └─────────────────────────────────────────────────────┘
```

## 9. 量化效果总结

| 指标 | FlashAttention-3 | **FlashAttention-4** |
|---|---|---|
| 目标架构 | Hopper (SM90) | **Blackwell (SM100/SM110)** |
| 累加器载体 | 寄存器 | **TMEM** |
| MMA tile | 64×N | **128×N** |
| 协同 MMA | 单 CTA | **2-CTA UMMA (可用)** |
| Exp 计算 | MUFU.EX2 | **MUFU + FMA 多项式（双路并发）** |
| Online softmax | 每块 rescale | **条件 rescale，跳过多数步** |
| dQ 原子加 | 每内循环一次 | **减半（2-CTA 分 M）** |
| 确定性 BWD | — | **SPT + swizzle, ~75% 非确定速度** |
| 实现语言 | C++ 模板 | **Python + CuTe-DSL** |
| 单 kernel 编译 | 前 55s / 反 45s | **前 2.5s / 反 1.4s (20-30×)** |
| B200 BF16 前向峰值 | — (不支持) | **~1613 TFLOPS (71%)** |
| 对比 cuDNN 9.13 | — | **+1.3×** |
| 对比 Triton | — | **+2.7×** |

## 10. 局限与未来

1. **B300 / GB300 上的 exp 模拟权衡**：B300 已把 MUFU 翻到 32 ops/cycle，FMA 模拟比例要重新调整。
2. **软 exp 的寄存器压力**：是论文中明确提到的成本，需要按 tile 配置经验调参（10–25%）。
3. **部分算法迁回 Hopper**：LPT 调度、条件 rescale 等与 Blackwell 无关的优化也能反哺 FA3，已经在 H200 上实测有 4-14% FLOPS 增益。
4. **FP8 在 Blackwell 上的形态**：FA3 已有 FP8 路径，FA4 论文主要讨论 BF16；低精度（FP4/FP8）与 2-CTA/TMEM 的组合还有空间。

## 11. 仓库对应实现（本仓库 `flash_attn/cute/`）

| 模块 | 内容 |
|---|---|
| `flash_fwd_sm100.py` | `FlashAttentionForwardSm100`：§3 全部前向优化 |
| `flash_bwd_sm100.py` | `FlashAttentionBackwardSm100`：§4 的 5-MMA 流水线 + 2-CTA |
| `softmax.py` | Online softmax + 条件 rescale（§3.3）|
| `fast_math.py` | `exp2` 多项式系数、softcap score_mod（§3.2）|
| `blackwell_helpers.py` | UMMA、2-CTA 支持、PTX 优化路径 |
| `pipeline.py` | Producer/Consumer 环形 buffer，PipelineStateSimple |
| `tile_scheduler.py` | LPT 调度（§5）、persistent kernel |
| `named_barrier.py` | WG 间同步（WG-A / B1 / B2 / C）|
| `paged_kv.py` | Paged KV cache + TMA（FA4 新增）|

对照阅读：先看 `flash_fwd_sm100.py` 主循环理解 4 个 WG 怎么分工，再看 `softmax.py` 的条件 rescale 触发点，最后 `flash_bwd_sm100.py` 里搜 `dsmem` / `cluster` 关键字定位 2-CTA dQ 重排。
