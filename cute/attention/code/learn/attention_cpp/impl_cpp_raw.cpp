// Attention 实现模板 —— 复制本文件为 impl_<你的方案>.cpp，补齐 attention() 即可。
//
// 只需实现这一个函数，其余（读输入/写结果/对拍）由 harness.cpp 负责。
// 参考算法（对齐 golden/golden_numpy.py）：
//     S = Q K^T * scale ; (可选 causal mask) ; P = softmax(S) 行方向稳定 ; O = P V
// 提示：先跑通标准三重循环拿到 PASS，再逐步替换为分块 / online softmax / CuTe 实现。
//
// 编译：bash build.sh impl_template.cpp   ->  生成可执行 attention_template



#include <cmath>
#include "attention.h"

void attention_decode(const float* Q, const float* K, const float* V,
               int N, int d, float* O) {

    // Q [1,d] 
    // K , V [N,d]
    // O [1,d]
    if (scale == 0.0f) scale = 1.0f / std::sqrtf((float)d);

    float* s = new float[N];

    // 1) s_j = q · K_j * scale
    float m = -INFINITY;
    for (int j = 0; j < N; ++j) {
        float acc = 0.0f;
        for (int k = 0; k < d; ++k)
            acc += Q[k] * K[j * d + k];
        s[j] = acc * scale;
        m = std::fmaxf(m, s[j]);
    }

    // 2) 稳定 softmax（单查询，只有 N 个分数）
    float sum = 0.0f;
    for (int j = 0; j < N; ++j) {
        s[j] = expf(s[j] - m);
        sum += s[j];
    }
    for (int j = 0; j < N; ++j) s[j] /= sum;

    // 3) 只写输出最后一行 o = s · V
    for (int c = 0; c < d; ++c) {
        float acc = 0.0f;
        for (int j = 0; j < N; ++j)
            acc += s[j] * V[j * d + c];
        O[(N - 1) * d + c] = acc;
    }

    delete[] s;
}
