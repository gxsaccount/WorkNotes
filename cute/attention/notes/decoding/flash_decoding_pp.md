# FlashDecoding++: Faster Large Language Model Inference on GPUs

> 论文: arXiv:2311.01282v4, 2024年1月  
> 作者: Ke Hong (清华), Guohao Dai (上海交大/Infinigence-AI), Yu Wang (清华) 等  
> 机构: 清华大学、上海交通大学、北京大学、Infinigence-AI

## 1. 问题背景

LLM 推理由两个阶段组成：

- **Prefill 阶段**：处理输入 prompt，生成第一个 token，主要是标准 GEMM 运算。
- **Decode 阶段**：自回归逐 token 生成，每次仅处理 1 个（或少量 batch）token，运算退化为 GEMV 或"扁平 GEMM"（M 很小）。

论文识别出 LLM 推理中的三大瓶颈：

| 挑战 | 描述 | 开销 |
|------|------|------|
| 同步 partial softmax 更新 | 分块计算 softmax 后需要同步更新所有分块结果 | Attention 计算约 18.8% 的开销 (Llama2-7B, A100) |
| 扁平 GEMM 计算利用率低 | Decode 阶段 M 维很小，cuBLAS/CUTLASS 将 M 补零到 64 | 超过 50% 的计算浪费 |
| 静态 dataflow 性能损失 | 不同形状的 GEMM 需要不同优化策略，单一方案无法兼顾 | 可达 50.25% 的性能损失 |

## 2. 核心技术

### 2.1 异步 Softmax —— 统一最大值 (Asynchronized Softmax with Unified Max Value)

**动机**：FlashAttention / FlashDecoding 中的 partial softmax 需要同步更新——每个分块计算完局部 max 后，必须用全局 max 去回溯修正之前的分块结果。

**核心洞察**：softmax 公式中的缩放因子（通常取 max）在数学上可以是任意常数 φ：

$$\text{softmax}(x) = \frac{[e^{x_1 - \phi}, \dots, e^{x_d - \phi}]}{\sum_i e^{x_i - \phi}}, \quad \forall \phi \in \mathbb{R}$$

**方法**：
1. **统计先验**：对主流 LLM (Llama2-7B, ChatGLM2-6B 等) 统计 softmax 输入分布，发现 >99.99% 的值落在一个有限范围 [a, b] 内。例如 Llama2-7B 中 99.99% 的值在 [-16.8, 6.5]。
2. **预设统一 φ**：所有分块共享同一个预设的 φ 值，各分块可以完全独立、异步地计算 partial softmax，无需同步。
3. **溢出回退**：极少数情况下（<0.01%）出现 x_i - φ 超出安全范围时，回退到传统的同步 partial softmax 方案重新计算。

**效果**：消除了约 20% 的 attention 同步开销，且回退的概率极低，几乎无额外代价。

> **注意**：对于值域过大的模型（如 OPT-6.7B 的范围达 [-496.8, 363.5]），此技术不适用。

#### 代码示例：三种 Softmax 实现对比

```python
import torch
import torch.nn.functional as F

# ============================================================
# (a) 标准 partial softmax —— FlashAttention / FlashDecoding 的方式
#     每个分块需要同步更新之前分块的结果
# ============================================================
def partial_softmax_synchronized(Q, K, V, block_size):
    """
    模拟 FlashAttention 的 online softmax：
    每处理一个 K/V 块后，都要用全局 max 修正之前的累加结果。
    """
    N, d = Q.shape
    num_blocks = (N + block_size - 1) // block_size
    O = torch.zeros(N, d)
    row_max = torch.full((N,), float('-inf'))  # m_i
    row_sum = torch.zeros(N)                   # ℓ_i

    for j in range(num_blocks):
        kv_start = j * block_size
        kv_end = min(kv_start + block_size, N)
        K_j = K[kv_start:kv_end]   # (block_size, d)
        V_j = V[kv_start:kv_end]

        S_j = Q @ K_j.T            # (N, block_size)

        # --- 同步点：必须用当前块的 max 去修正之前所有块的累积结果 ---
        m_new = torch.max(S_j, dim=1).values            # 当前块的行最大值
        m_combined = torch.max(row_max, m_new)           # 全局最大值

        # 缩放修正：之前的 exp 值要乘上 exp(旧max - 新max)
        scale_old = torch.exp(row_max - m_combined)      # ← 这就是"同步更新"
        scale_new = torch.exp(m_new - m_combined)

        P_j = torch.exp(S_j - m_combined.unsqueeze(1))   # 当前块的 softmax 分子

        # 更新累积：O 和 row_sum 都要被 scale_old 修正
        O = O * scale_old.unsqueeze(1) + P_j @ V_j       # ← 修正旧 O
        row_sum = row_sum * scale_old + P_j.sum(dim=1)    # ← 修正旧 sum
        row_max = m_combined

    return O / row_sum.unsqueeze(1)


# ============================================================
# (b) FlashDecoding++ 的异步 softmax —— 统一最大值 φ
#     所有分块共享预设 φ，无需同步修正
# ============================================================
def partial_softmax_async_unified_phi(Q, K, V, block_size, phi=0.0,
                                       safe_lo=-16.0, safe_hi=16.0):
    """
    FlashDecoding++ 核心创新：
    用预设的统一常数 φ 替代动态 max，各分块完全独立计算。
    """
    N, d = Q.shape
    num_blocks = (N + block_size - 1) // block_size
    numerator = torch.zeros(N, d)   # Σ exp(x_i - φ) * v_i
    denominator = torch.zeros(N)    # Σ exp(x_i - φ)

    for j in range(num_blocks):
        kv_start = j * block_size
        kv_end = min(kv_start + block_size, N)
        K_j = K[kv_start:kv_end]
        V_j = V[kv_start:kv_end]

        S_j = Q @ K_j.T            # (N, block_size)

        # --- 溢出检查：如果 S_j - φ 超出安全范围，回退到同步方案 ---
        if (S_j - phi).max() > safe_hi or (S_j - phi).min() < safe_lo:
            print("Overflow detected! Falling back to synchronized softmax.")
            return partial_softmax_synchronized(Q, K, V, block_size)

        # --- 异步计算：各分块独立，无需修正之前的结果 ---
        P_j = torch.exp(S_j - phi)                      # 直接用固定 φ
        numerator += P_j @ V_j                           # ← 无同步，直接累加
        denominator += P_j.sum(dim=1)                    # ← 无同步，直接累加

    return numerator / denominator.unsqueeze(1)


# ============================================================
# 验证两种方法产生相同结果
# ============================================================
torch.manual_seed(42)
N, d, block_size = 128, 64, 32
Q = torch.randn(N, d) * 0.1    # 模拟 LLM 中 softmax 输入的典型范围
K = torch.randn(N, d) * 0.1
V = torch.randn(N, d)

# 统计 QK^T 的范围，选取合适的 φ
S_full = Q @ K.T
print(f"QK^T range: [{S_full.min():.2f}, {S_full.max():.2f}]")

# 论文建议 φ 取在 99.99% 分位数范围内
phi = S_full.median().item()    # 简单起见取中位数

O_sync = partial_softmax_synchronized(Q, K, V, block_size)
O_async = partial_softmax_async_unified_phi(Q, K, V, block_size, phi=phi)
O_ref = F.softmax(Q @ K.T, dim=1) @ V

print(f"Sync  vs Reference max error: {(O_sync - O_ref).abs().max():.2e}")
print(f"Async vs Reference max error: {(O_async - O_ref).abs().max():.2e}")
```

对比核心差异：

```
┌──────────────────────────────────────────────────────────────────────┐
│ 同步方案 (FlashAttention):                                          │
│                                                                      │
│  Block 0: m₀ = max(S₀)                                              │
│  Block 1: m₁ = max(m₀, max(S₁))                                     │
│           O₀ *= exp(m₀ - m₁)     ← 回溯修正之前的结果（同步开销）   │
│           ℓ₀ *= exp(m₀ - m₁)                                        │
│  Block 2: m₂ = max(m₁, max(S₂))                                     │
│           O₁ *= exp(m₁ - m₂)     ← 再次修正（同步开销）             │
│           ℓ₁ *= exp(m₁ - m₂)                                        │
│  ...                                                                 │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│ 异步方案 (FlashDecoding++):                                          │
│                                                                      │
│  预设 φ（统一常数，所有分块共享）                                      │
│                                                                      │
│  Block 0: num₀ = exp(S₀ - φ) @ V₀    den₀ = Σexp(S₀ - φ)          │
│  Block 1: num₁ = exp(S₁ - φ) @ V₁    den₁ = Σexp(S₁ - φ)          │  ← 完全独立！
│  Block 2: num₂ = exp(S₂ - φ) @ V₂    den₂ = Σexp(S₂ - φ)          │  ← 无需修正！
│  ...                                                                 │
│  最终: O = (num₀ + num₁ + ...) / (den₀ + den₁ + ...)               │
└──────────────────────────────────────────────────────────────────────┘
```

作为参考，本仓库 FA4 的 online softmax 实现在 `flash_attn/cute/softmax.py` 中，使用的是动态 max 的同步方案（`Softmax.online_softmax` 方法），每行迭代中都会 `fmax_reduce` 取新 max 并用 `exp2(old_max - new_max)` 修正历史 `row_sum`。

### 2.2 扁平 GEMM 优化 —— 双缓冲 (Flat GEMM Optimization with Double Buffering)

**动机**：Decode 阶段的矩阵乘法 M 维很小（batch_size=1 时为 GEMV），cuBLAS/CUTLASS 将 M 补零到 64，造成严重的计算浪费。

**方法**：
1. **减少填充**：仅将 M 维补到 8（匹配现代 Tensor Core 最小粒度），而非 64，大幅提高计算利用率。
2. **瓶颈分析**：通过分析 N 维 tile 大小 B_N 与性能的关系：
   - N 较小时 → 并行度受限（parallelism-bounded），需要较小的 B_N
   - N 较大时 → 访存受限（memory-bounded），需要隐藏访存延迟
3. **双缓冲技术**：在 shared memory 中分配两个缓冲区，一个执行 GEMM 计算，另一个同时加载下一个 tile，实现计算和访存的流水线重叠。

#### 代码示例：Padding 对比 + 双缓冲 CUDA 伪代码

```python
import torch
import time

# ============================================================
# 问题演示：M 维 padding 到 64 vs padding 到 8 的浪费对比
# ============================================================
def flat_gemm_padding_comparison():
    """
    Decode 阶段典型参数：M=batch_size (1~8), K=4096, N=4096
    对比不同 padding 策略的有效计算占比。
    """
    K_dim, N_dim = 4096, 4096

    for batch_size in [1, 2, 4, 8]:
        M = batch_size

        # cuBLAS 默认策略: pad M 到 64
        M_padded_64 = ((M + 63) // 64) * 64
        util_64 = M / M_padded_64

        # FlashDecoding++ 策略: pad M 到 8 (Tensor Core 最小粒度)
        M_padded_8 = ((M + 7) // 8) * 8
        util_8 = M / M_padded_8

        print(f"batch_size={batch_size}: "
              f"pad-to-64 → M={M_padded_64}, util={util_64*100:.1f}% | "
              f"pad-to-8  → M={M_padded_8},  util={util_8*100:.1f}%")
        # batch_size=1: pad-to-64 → M=64, util=1.6%  | pad-to-8 → M=8, util=12.5%
        # batch_size=4: pad-to-64 → M=64, util=6.2%  | pad-to-8 → M=8, util=50.0%
        # batch_size=8: pad-to-64 → M=64, util=12.5% | pad-to-8 → M=8, util=100.0%

flat_gemm_padding_comparison()
```

双缓冲的 CUDA 伪代码（对应论文 Figure 8）：

```cpp
// ============================================================
// Flat GEMM with Double Buffering — CUDA Kernel 伪代码
// C[M×N] = A[M×K] × B[K×N], M ≤ 8
// ============================================================
// 每个 GPU Block 处理 C 的一个 N 维 tile: C[:, n:n+BN]
// K 维在 block 内串行处理，使用双缓冲隐藏访存

__global__ void flat_gemm_double_buffer(
    float *A, float *B, float *C,
    int M, int K, int N, int BK, int BN
) {
    int block_n = blockIdx.x * BN;   // N 维并行

    // 双缓冲: 两块 shared memory 交替使用
    __shared__ float smem_A[2][8 * BK];      // M padded to 8
    __shared__ float smem_B[2][BK * BN];
    int buf = 0;

    // ---- Prologue: 预加载第一个 tile 到 buffer 0 ----
    load_tile(A, smem_A[0], M, BK, /*k_offset=*/0);
    load_tile(B, smem_B[0], BK, BN, /*k_offset=*/0, block_n);
    __syncthreads();

    float acc[8 * BN] = {0};

    for (int k = 0; k < K; k += BK) {
        int next_k = k + BK;
        int next_buf = 1 - buf;

        // ---- 双缓冲核心: 计算 buffer[buf], 同时加载下一个 tile 到 buffer[next_buf] ----

        // 启动异步加载 (如果还有下一个 tile)
        if (next_k < K) {
            async_load_tile(A, smem_A[next_buf], M, BK, next_k);
            async_load_tile(B, smem_B[next_buf], BK, BN, next_k, block_n);
        }

        // 用当前 buffer 做 GEMM (Tensor Core, M=8)
        // 计算与上面的加载 **同时进行**
        tensor_core_mma(smem_A[buf], smem_B[buf], acc, /*M=*/8, BN, BK);

        __syncthreads();  // 等待加载完成
        buf = next_buf;   // 切换 buffer
    }

    // 将累加结果写回 global memory
    store_tile(C, acc, M, BN, block_n);
}
```

时间线可视化：

```
传统方案（无双缓冲）:
  Time: |-- load A₁B₁ --|-- compute A₁B₁ --|-- load A₂B₂ --|-- compute A₂B₂ --|
                          ↑ 计算空闲等加载     ↑ 加载空闲等计算

双缓冲方案:
  Time: |-- load A₁B₁ --|-- load A₂B₂ -----|-- load A₃B₃ -----|
                         |-- compute A₁B₁ --|-- compute A₂B₂ --|-- compute A₃B₃ --|
                          ↑ 计算与加载重叠！    ↑ 持续重叠
```

### 2.3 启发式 Dataflow —— 硬件资源自适应 (Heuristic Dataflow with Hardware Resource Adaptation)

**动机**：LLM 推理中不同操作（K/Q/V 投影、O 投影、FFN1、FFN2）的 GEMM 形状各异，batch size 和序列长度也动态变化。单一实现方案无法最优覆盖所有情况。

**核心洞察**：对于给定的 LLM，[K, N] 形状只有 4 种（对应 4 类线性运算），仅 M 维随 batch size 和序列长度变化。

**方法**：三种实现方案按 M 值区间切换：
- **ImplA (FastGEMV)**：使用 CUDA Core，适合 M 极小（GEMV/极小 flat GEMM）
- **ImplB (本文的 flat GEMM 优化)**：使用 Tensor Core + 双缓冲，适合中等 M
- **ImplC (CUTLASS)**：使用 Tensor Core 标准 GEMM，适合大 M

**决策流程**（离线 profiling）：
1. 对每种 [K, N] 形状，从 M=1 开始递增
2. 找到拐点 M₁：ImplB 性能超过 ImplA 的位置
3. 找到拐点 M₂：ImplC 性能超过 ImplB 的位置
4. 生成查找表，运行时 O(1) 查表选择最优实现

#### 代码示例：离线 Profiling + 运行时查表

```python
import time
from dataclasses import dataclass

# ============================================================
# 离线阶段：为每种 [K, N] 形状找到两个拐点 M1, M2
# ============================================================

def impl_a_fastgemv(A, B):
    """ImplA: CUDA Core GEMV, 适合 M ≤ ~2"""
    return A @ B  # 实际用 FastGEMV kernel

def impl_b_flat_gemm(A, B):
    """ImplB: Tensor Core + pad-to-8 + 双缓冲, 适合小 M"""
    return A @ B  # 实际用 Section 4 的自定义 kernel

def impl_c_cutlass(A, B):
    """ImplC: CUTLASS 标准 GEMM, 适合大 M"""
    return A @ B  # 实际用 cuBLAS/CUTLASS

def benchmark(fn, A, B, warmup=10, repeat=100):
    """简易 benchmark，实际应使用 CUDA events"""
    for _ in range(warmup):
        fn(A, B)
    t0 = time.perf_counter()
    for _ in range(repeat):
        fn(A, B)
    return (time.perf_counter() - t0) / repeat


@dataclass
class InflectionPoints:
    K: int
    N: int
    M1: int   # ImplA → ImplB 切换点
    M2: int   # ImplB → ImplC 切换点


def find_inflection_points(K, N, max_M=64):
    """
    对给定的 [K, N]，逐步增大 M，找到两个拐点：
    M1: ImplB 首次超过 ImplA 的位置
    M2: ImplC 首次超过 ImplB 的位置
    """
    M1, M2 = max_M, max_M  # 默认值

    for M in range(1, max_M + 1):
        A = torch.randn(M, K, device='cuda', dtype=torch.float16)
        B = torch.randn(K, N, device='cuda', dtype=torch.float16)

        t_a = benchmark(impl_a_fastgemv, A, B)
        t_b = benchmark(impl_b_flat_gemm, A, B)
        t_c = benchmark(impl_c_cutlass, A, B)

        if M1 == max_M and t_b < t_a:
            M1 = M
        if M2 == max_M and M >= M1 and t_c < t_b:
            M2 = M
            break

    return InflectionPoints(K=K, N=N, M1=M1, M2=M2)


def build_lookup_table(model_config):
    """
    对 LLM 的 4 种 [K, N] 形状，各找一组拐点。
    以 Llama2-7B 为例：HD=4096, FD=11008
    """
    shapes = [
        (model_config['HD'], model_config['HD'] * 3),  # K,Q,V projection
        (model_config['HD'], model_config['HD']),       # O projection
        (model_config['HD'], model_config['FD']),       # FFN1
        (model_config['FD'], model_config['HD']),       # FFN2
    ]
    table = {}
    for K, N in shapes:
        pts = find_inflection_points(K, N)
        table[(K, N)] = pts
        print(f"  [K={K}, N={N}]: M1={pts.M1}, M2={pts.M2}")
    return table


# ============================================================
# 运行时阶段：O(1) 查表选择最优实现
# ============================================================

class HeuristicGEMM:
    def __init__(self, lookup_table):
        self.table = lookup_table

    def __call__(self, A, B):
        """
        根据矩阵形状自动选择最优 GEMM 实现。
        运行时开销仅为一次字典查找 + 两次整数比较。
        """
        M, K = A.shape
        _, N = B.shape
        pts = self.table[(K, N)]

        if M < pts.M1:
            return impl_a_fastgemv(A, B)    # CUDA Core
        elif M < pts.M2:
            return impl_b_flat_gemm(A, B)   # Tensor Core + 双缓冲
        else:
            return impl_c_cutlass(A, B)     # CUTLASS 标准 GEMM


# 使用示例
llama2_7b = {'HD': 4096, 'FD': 11008}
# table = build_lookup_table(llama2_7b)   # 离线执行一次
# gemm = HeuristicGEMM(table)

# 推理时根据 batch_size 自动选择：
# batch_size=1  → FastGEMV (CUDA Core)
# batch_size=4  → Flat GEMM (Tensor Core + 双缓冲)
# batch_size=32 → CUTLASS (标准 Tensor Core GEMM)
```

决策流程可视化（以 Llama2-7B 为例）：

```
                   M（batch_size × seq_len 或 batch_size）
                   1    2    4    8    16   32   64   128  ...
K,Q,V projection ──┤ ImplA ├──┤  ImplB  ├────┤    ImplC     ├──→
  [K=4096,N=12288]       M1=3         M2=17

O projection ──────┤ ImplA ├──┤  ImplB  ├──┤      ImplC       ├──→
  [K=4096,N=4096]       M1=2        M2=12

FFN1 ──────────────┤ ImplA ├──────┤  ImplB  ├──┤   ImplC      ├──→
  [K=4096,N=11008]       M1=2            M2=20

FFN2 ──────────────┤   ImplA    ├─┤  ImplB  ├──┤   ImplC      ├──→
  [K=11008,N=4096]           M1=5       M2=14

拐点 M1, M2 因 [K,N] 不同而不同 → 每种操作有自己的切换策略
```

## 3. 实验结果

### 硬件平台
- NVIDIA: Tesla A100 (80GB), RTX 3090 (24GB)
- AMD: MI210 (64GB), RX7900XTX (24GB)

### 测试模型
- Llama2-7B, Llama2-13B, OPT-6.7B, ChatGLM2-6B

### 性能对比

**Decode 阶段**：
| 对比基线 | 平均加速比 |
|---------|-----------|
| vs Hugging Face | 最高 4.86× (NVIDIA), 3.93× (AMD) |
| vs vLLM | 1.24× |
| vs DeepSpeed | 1.44× |
| vs TensorRT-LLM | 1.13× |
| vs OpenPPL | 1.24× |
| vs FlashDecoding | 1.21× (A100 上 1.37×) |

**Prefill 阶段**：
| 对比基线 | 平均加速比 |
|---------|-----------|
| vs Hugging Face | 最高 1.40× |
| vs FlashAttention2 | 1.09× |
| vs FlashDecoding | 1.08× |
| vs TensorRT-LLM | 1.06× |

## 4. 与 FlashAttention/FlashDecoding 的关系

| 方法 | 关注阶段 | 核心思路 |
|------|---------|---------|
| FlashAttention (v1/v2) | Prefill | 分块计算 attention，减少 HBM 访问，online softmax |
| FlashDecoding | Decode | 沿 KV 序列维度并行拆分，提升 decode 阶段并行度 |
| **FlashDecoding++** | **两者兼顾** | **异步 softmax 消除同步开销 + 扁平 GEMM 优化 + 启发式 dataflow** |

## 5. 关键要点总结

1. **统一最大值的异步 softmax** 是论文最核心的创新——利用统计先验将同步操作变为异步，思路简洁但有效。
2. **扁平 GEMM 优化**针对 decode 阶段的典型瓶颈（M 维极小），通过减少填充 + 双缓冲实现访存/计算重叠。
3. **启发式 dataflow** 通过离线 profiling 建立查找表，运行时零开销地在 CUDA Core / Tensor Core 方案间切换。
4. 三项优化相互正交，共同覆盖了 LLM 推理从 attention 到线性层的主要瓶颈。
5. 跨平台支持（NVIDIA + AMD）验证了优化的通用性。
