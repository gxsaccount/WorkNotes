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

void attention(const float* Q, const float* K, const float* V,
               int N, int d, float scale, bool causal, float* O) {
    // ---- TODO: 你的实现 ----
    // 当前占位：全零输出，编译可过、对拍会 FAIL（提示尚未实现）。
    (void)Q;
    (void)K;
    (void)V;
    (void)scale;
    (void)causal;
    for (int i = 0; i < N * d; ++i) {
        O[i] = 0.0f;
    }
}
