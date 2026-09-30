"""对拍脚本：比较两份 attention 输出的逐元素误差。

用法：
    python3 check.py                      # 默认比 O_numpy.bin vs O_cpp.bin
    python3 check.py O_numpy.bin X.bin    # 比任意两份输出（后续 CuTe 结果也用它）

判定：max abs diff < TOL 视为通过。float32 标准 attention 之间应 < 1e-4。
"""
import numpy as np
import os
import sys

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "artifacts")
TOL = 1e-4


def load_dims():
    with open(os.path.join(OUT_DIR, "dims.txt")) as f:
        N, d = map(int, f.read().split())
    return N, d


def main():
    a_name = sys.argv[1] if len(sys.argv) > 1 else "O_numpy.bin"
    b_name = sys.argv[2] if len(sys.argv) > 2 else "O_cpp.bin"
    N, d = load_dims()
    a = np.fromfile(os.path.join(OUT_DIR, a_name), dtype=np.float32).reshape(N, d)
    b = np.fromfile(os.path.join(OUT_DIR, b_name), dtype=np.float32).reshape(N, d)

    diff = np.abs(a - b)
    max_diff = float(diff.max())
    # 相对误差（避免大值处的绝对误差误导），加 eps 防除零
    rel = float((diff / (np.abs(a) + 1e-8)).max())
    idx = np.unravel_index(int(diff.argmax()), diff.shape)

    ok = max_diff < TOL
    print(f"[check] {a_name} vs {b_name}: N={N} d={d}")
    print(f"        max_abs_diff={max_diff:.3e} @ {idx}  max_rel_diff={rel:.3e}")
    print(f"        {'PASS' if ok else 'FAIL'} (tol={TOL:.0e})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
