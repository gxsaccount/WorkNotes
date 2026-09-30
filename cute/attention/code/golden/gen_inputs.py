"""生成 Flash Attention 对拍用的固定输入 Q/K/V。

三方（numpy golden / C++ golden / 后续 CuTe 实现）都读这里生成的同一份
二进制文件，确保输入完全一致，对拍才有意义。

数据格式：裸 float32，row-major，无 header。
形状约定：Q,K,V 均为 (N, d)，单头单 batch（v0 先不引入 batch/head）。
维度信息写入 dims.txt，供 C++ 读取。
"""
import numpy as np
import os

# ---- 可调参数 ----
N = 128   # 序列长度 (seq_len)
d = 64    # head_dim
SEED = 1234

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "artifacts")


def main():
    rng = np.random.default_rng(SEED)
    # 用较小的尺度，避免 exp 溢出掩盖 softmax 稳定性问题；float32 全程
    Q = rng.standard_normal((N, d)).astype(np.float32)
    K = rng.standard_normal((N, d)).astype(np.float32)
    V = rng.standard_normal((N, d)).astype(np.float32)

    Q.tofile(os.path.join(OUT_DIR, "Q.bin"))
    K.tofile(os.path.join(OUT_DIR, "K.bin"))
    V.tofile(os.path.join(OUT_DIR, "V.bin"))

    with open(os.path.join(OUT_DIR, "dims.txt"), "w") as f:
        f.write(f"{N} {d}\n")

    print(f"[gen_inputs] wrote Q/K/V as ({N},{d}) float32, seed={SEED}")


if __name__ == "__main__":
    main()
