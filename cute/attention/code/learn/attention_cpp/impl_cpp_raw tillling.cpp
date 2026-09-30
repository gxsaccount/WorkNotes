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


int BLK_K = 64;  // key/value block 行数

void attention_decode(const float* Q, const float* K, const float* V,
               int N, int d, float* O) {

    // Q [1,d] 
    // K , V [N,d]
    // O [1,d]
    // Q * K^T * scale -> [1,N] 
    // P = softmax = exp(Sij * scale - m) /  sum(exp(Sij * scale - m))  -> [1,N]  
    // P * V  -> [1,d] 

    for (int k = 0; k < d; ++k) O[k] = 0.0f;//reset O 


    auto scale = 1.0f / std::sqrtf((float)d);
    int blkNum = (N + BLK_K - 1) / BLK_K;
    float m_old = -INFINITY;
    float l_old = 0.0f; // softmax sum
    std::vector<float> s(BLK_K, 0.0f); // block score

    for(int kb =0; kb < blkNum;++kb){ // kb : key block index
        int i = kb* BLK_K;
        int blkSize = std::min(BLK_K, N - i);
        float m_new = -INFINITY;
        // 算局部 score: s_i = Q·K_iᵀ * scale   (1×Bk) 与统计局部max
        for(int j = 0; j < blkSize; ++j){
            float acc = 0.0f;
            for (int k = 0; k < d; ++k)
                acc += Q[k] * K[(i+j) * d + k];
            s[j] = acc * scale;
            m_new = std::fmaxf(m_new, s[j]);
        }
        // 算局部 softmax 权重 
        float corr = std::exp(m_old - m_new);
        l_old *= corr;
        for(int j = 0; j < blkSize; ++j){
            s[j] = std::exp(s[j] - m_new);
            l_old += s[j];
        }
        for (int k=0;k<d;++k) O[k]*=corr;
        // 算输出 O = P·V
        for(int j =0 ; j< blkSize; ++j){
            float p = s[j] / l_old;
            for(int k = 0; k < d; ++k){
                O[k] += p * V[(kb*BLK_K + j) * d + k];
            }
        }
        m_old = m_new;


    } 
    
}
