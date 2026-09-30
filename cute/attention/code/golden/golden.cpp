// 标准 Attention 的 C++ golden reference（纯 CPU，无 CUDA）。
//
// 目的：作为独立于 numpy 的第二份真值。三方对拍时，C++ 与 numpy 一致
// 可排除「golden 本身写错」的风险；后续 CuTe kernel 也与它对拍。
//
// 故意写成最直白的三重循环标准实现——不分块、不 online，只保证数值正确。
// 与 golden_numpy.py 逐行对应，符号对齐 flash_att_v1.md：
//     S = Q K^T * scale ; P = softmax(S) 行方向稳定 ; O = P V
//
// 输入：读同目录 dims.txt / Q.bin / K.bin / V.bin（float32 row-major）。
// 输出：O_cpp.bin（float32 row-major）。
//
// 编译：g++ -O2 -std=c++17 golden.cpp -o golden
// 运行：./golden      （需先跑 gen_inputs.py 生成输入）

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

// causal mask 开关，需与 golden_numpy.py 的 CAUSAL 保持一致
static constexpr bool kCausal = false;

static std::vector<float> read_bin(const std::string& path, size_t count) {
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        std::fprintf(stderr, "cannot open %s\n", path.c_str());
        std::exit(1);
    }
    std::vector<float> buf(count);
    f.read(reinterpret_cast<char*>(buf.data()),
           static_cast<std::streamsize>(count * sizeof(float)));
    if (!f) {
        std::fprintf(stderr, "short read on %s\n", path.c_str());
        std::exit(1);
    }
    return buf;
}

int main() {
    // ---- 读维度 ----
    std::ifstream df("dims.txt");
    if (!df) {
        std::fprintf(stderr, "cannot open dims.txt (run gen_inputs.py first)\n");
        return 1;
    }
    int N = 0, d = 0;
    df >> N >> d;

    const size_t nd = static_cast<size_t>(N) * d;
    std::vector<float> Q = read_bin("Q.bin", nd);
    std::vector<float> K = read_bin("K.bin", nd);
    std::vector<float> V = read_bin("V.bin", nd);

    const float scale = 1.0f / std::sqrt(static_cast<float>(d));
    std::vector<float> O(nd, 0.0f);

    // 每行独立做完整 attention，行间无耦合
    std::vector<float> S(static_cast<size_t>(N));  // 当前 query 行的 S_i[:]
    for (int i = 0; i < N; ++i) {
        // ---- S_i = Q_i · K_j^T * scale ----
        for (int j = 0; j < N; ++j) {
            float acc = 0.0f;
            for (int k = 0; k < d; ++k) {
                acc += Q[static_cast<size_t>(i) * d + k] *
                       K[static_cast<size_t>(j) * d + k];
            }
            acc *= scale;
            if (kCausal && j > i) {
                acc = -INFINITY;  // causal：query i 看不到 key j>i
            }
            S[static_cast<size_t>(j)] = acc;
        }

        // ---- 行方向稳定 softmax：先求 row max ----
        float m = -INFINITY;
        for (int j = 0; j < N; ++j) {
            if (S[static_cast<size_t>(j)] > m) {
                m = S[static_cast<size_t>(j)];
            }
        }
        float ell = 0.0f;
        for (int j = 0; j < N; ++j) {
            float e = std::exp(S[static_cast<size_t>(j)] - m);
            S[static_cast<size_t>(j)] = e;  // 原地存 P_i[j]（未归一化）
            ell += e;
        }
        const float inv_ell = 1.0f / ell;

        // ---- O_i = P_i · V ----
        for (int k = 0; k < d; ++k) {
            float acc = 0.0f;
            for (int j = 0; j < N; ++j) {
                acc += S[static_cast<size_t>(j)] * V[static_cast<size_t>(j) * d + k];
            }
            O[static_cast<size_t>(i) * d + k] = acc * inv_ell;
        }
    }

    // ---- 写出 ----
    std::ofstream of("O_cpp.bin", std::ios::binary);
    of.write(reinterpret_cast<const char*>(O.data()),
             static_cast<std::streamsize>(nd * sizeof(float)));
    std::printf("[golden_cpp] N=%d d=%d causal=%d O[0,:4]=%.6f %.6f %.6f %.6f\n",
                N, d, static_cast<int>(kCausal), O[0], O[1], O[2], O[3]);
    return 0;
}
