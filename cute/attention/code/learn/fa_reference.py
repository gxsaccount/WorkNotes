"""Flash Attention 分块算法的 numpy 参考骨架（v0 / v1）。

这不是性能实现，而是 **DSL/C++ kernel 的翻译蓝本**：用 numpy 把「分块调度 +
online softmax + P→V 衔接」的逻辑跑对，后续 CuTe 实现照此结构翻译，并用
check.py 与 golden 对拍。

对齐 flash_att_v2.md 的 FA2 结构：
    外层循环遍历 Q 块（行方向，块间独立 → 未来映射到 thread block）
    内层循环遍历 K/V 块（列方向，在线累加）

提供两个函数，对应计划里的 v0 / v1：
    fa_v0_blocked_twopass : 分块，但每个 Q 块内先扫完所有 K 求全局 m/ℓ，
                            再第二遍算 O。逻辑最简单，用来先跑通「分块 + 衔接」。
    fa_v1_online          : 分块 + online softmax（FA2 delayed rescaling），
                            单遍扫 K，维护 running m/ℓ，循环末一次性归一化。

两者都应与 golden_numpy 的标准 attention 数值一致。
"""
import numpy as np
import os
import sys

# golden 真值代码在同级 golden/ 目录，加入模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "golden"))
from golden_numpy import load_inputs, attention

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "artifacts")

# 分块大小（v0 先取整除 N 的值；非整除留到 v2 predication）
BLK_M = 32   # B_r，Q 块行数
BLK_N = 32   # B_c，K/V 块行数


def fa_v0_blocked_twopass(Q, K, V):
    """v0：分块，每个 Q 块内两遍扫 K（先求全局 m/ℓ，再算 O）。"""
    N, d = Q.shape
    scale = np.float32(1.0 / np.sqrt(d))
    O = np.zeros((N, d), dtype=np.float32)

    for i0 in range(0, N, BLK_M):
        i1 = min(i0 + BLK_M, N)
        Qi = Q[i0:i1]                                  # (bm, d)
        bm = i1 - i0

        # ---- 第一遍：扫所有 K 块，求每行全局 m 和 ℓ ----
        m = np.full((bm, 1), -np.inf, dtype=np.float32)
        ell = np.zeros((bm, 1), dtype=np.float32)
        for j0 in range(0, N, BLK_N):
            j1 = min(j0 + BLK_N, N)
            Sij = (Qi @ K[j0:j1].T).astype(np.float32) * scale   # (bm, bn)
            m_blk = Sij.max(axis=1, keepdims=True)
            m_new = np.maximum(m, m_blk)
            # 历史 ell 按 max 变化缩放，再加本块贡献
            ell = ell * np.exp(m - m_new) + np.exp(Sij - m_new).sum(axis=1, keepdims=True)
            m = m_new

        # ---- 第二遍：用已知全局 m/ℓ 算 O ----
        acc = np.zeros((bm, d), dtype=np.float32)
        for j0 in range(0, N, BLK_N):
            j1 = min(j0 + BLK_N, N)
            Sij = (Qi @ K[j0:j1].T).astype(np.float32) * scale
            Pij = np.exp(Sij - m)                        # 用全局 m，已可直接归一化
            acc += Pij @ V[j0:j1]
        O[i0:i1] = acc / ell
    return O


def fa_v1_online(Q, K, V):
    """v1：分块 + online softmax（FA2 delayed rescaling），单遍扫 K。"""
    N, d = Q.shape
    scale = np.float32(1.0 / np.sqrt(d))
    O = np.zeros((N, d), dtype=np.float32)

    for i0 in range(0, N, BLK_M):
        i1 = min(i0 + BLK_M, N)
        Qi = Q[i0:i1]
        bm = i1 - i0

        m = np.full((bm, 1), -np.inf, dtype=np.float32)   # running row max
        ell = np.zeros((bm, 1), dtype=np.float32)         # running row sum
        acc = np.zeros((bm, d), dtype=np.float32)         # 未归一化的 Õ

        for j0 in range(0, N, BLK_N):
            j1 = min(j0 + BLK_N, N)
            Sij = (Qi @ K[j0:j1].T).astype(np.float32) * scale   # (bm, bn)
            m_blk = Sij.max(axis=1, keepdims=True)
            m_new = np.maximum(m, m_blk)
            corr = np.exp(m - m_new)                       # 历史修正因子 e^{m_old-m_new}
            Pij = np.exp(Sij - m_new)                      # 本块未归一化权重
            # FA2：先修正历史 acc/ell，再加本块贡献，全程不除 ℓ
            acc = acc * corr + Pij @ V[j0:j1]
            ell = ell * corr + Pij.sum(axis=1, keepdims=True)
            m = m_new

        O[i0:i1] = acc / ell                              # 循环末一次性归一化
    return O


def main():
    Q, K, V, N, d = load_inputs()
    ref = attention(Q, K, V, causal=False)                # golden
    assert N % BLK_M == 0 and N % BLK_N == 0, "v0 先要求整除分块"

    for name, fn in [("v0_twopass", fa_v0_blocked_twopass),
                     ("v1_online", fa_v1_online)]:
        O = fn(Q, K, V)
        max_diff = float(np.abs(O - ref).max())
        status = "PASS" if max_diff < 1e-4 else "FAIL"
        print(f"[fa_reference] {name:12s} vs golden: max_abs_diff={max_diff:.3e}  {status}")
        O.tofile(os.path.join(OUT_DIR, f"O_{name}.bin"))


if __name__ == "__main__":
    main()
