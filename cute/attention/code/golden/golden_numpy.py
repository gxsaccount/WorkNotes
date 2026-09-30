"""标准 Attention 的 numpy golden reference。

这是整条链路的「真值」：后续所有 FA 变体（v0 两遍 softmax、v1 online、
v2 causal ...）都以此对拍。故意写成最直白的标准实现——不分块、不 online，
只保证数值正确，作为正确性基线。

算法（对齐 flash_att_v1.md 符号）：
    S = Q @ K^T * scale      ∈ R^(N×N)
    (可选 causal mask)
    P = softmax(S, axis=-1)  行方向，数值稳定（减 row max）
    O = P @ V                ∈ R^(N×d)

scale = 1/sqrt(d)，标准缩放点积注意力。
"""
import numpy as np
import os

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "artifacts")

# 是否启用 causal mask。v0/v1 阶段关闭；v2 再打开对拍。
CAUSAL = False


def load_inputs():
    with open(os.path.join(OUT_DIR, "dims.txt")) as f:
        N, d = map(int, f.read().split())
    Q = np.fromfile(os.path.join(OUT_DIR, "Q.bin"), dtype=np.float32).reshape(N, d)
    K = np.fromfile(os.path.join(OUT_DIR, "K.bin"), dtype=np.float32).reshape(N, d)
    V = np.fromfile(os.path.join(OUT_DIR, "V.bin"), dtype=np.float32).reshape(N, d)
    return Q, K, V, N, d


def stable_softmax(S):
    """行方向数值稳定 softmax：减去每行最大值后再 exp。"""
    m = np.max(S, axis=-1, keepdims=True)          # 行最大值 m_i
    P = np.exp(S - m)                               # 稳定的 exp
    ell = np.sum(P, axis=-1, keepdims=True)         # 归一化因子 ℓ_i
    return P / ell


def attention(Q, K, V, causal=False):
    d = Q.shape[-1]
    scale = 1.0 / np.sqrt(d)
    # 全程用 float32 计算，与 GPU 端对齐（先不引入 fp16 精度问题）
    S = (Q @ K.T).astype(np.float32) * np.float32(scale)   # S = QK^T * scale
    if causal:
        N = S.shape[0]
        # 上三角（j > i）置 -inf，query i 只能看到 key j<=i
        mask = np.triu(np.ones((N, N), dtype=bool), k=1)
        S = np.where(mask, np.float32(-np.inf), S)
    P = stable_softmax(S)
    O = (P @ V).astype(np.float32)
    return O


def main():
    Q, K, V, N, d = load_inputs()
    O = attention(Q, K, V, causal=CAUSAL)
    O.astype(np.float32).tofile(os.path.join(OUT_DIR, "O_numpy.bin"))
    print(f"[golden_numpy] N={N} d={d} causal={CAUSAL} "
          f"O[0,:4]={O[0,:4]}  O.sum={O.sum():.6f}")


if __name__ == "__main__":
    main()
