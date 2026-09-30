// Attention 实现的统一接口声明。
//
// harness.cpp（脚手架：读输入/写结果/对拍）与各 impl_*.cpp（具体实现）
// 都 include 本头文件，从而解耦：一份 harness 可搭配任意一份实现编译。
//
// 约定（对齐 golden/golden_numpy.py 与 golden.cpp）：
//   Q,K,V,O 均为 (N,d) row-major float32；scale = 1/sqrt(d)；全程 float32。

#pragma once

// 你要实现的函数：读 Q/K/V，算出 O。
//   Q,K,V : 输入，(N,d) row-major
//   N,d   : 序列长度 / head_dim
//   scale : 1/sqrt(d)
//   causal: 是否启用 causal mask（query i 只能看到 key j<=i）
//   O     : 输出，(N,d) row-major，须与 golden 数值一致（max abs diff < 1e-4）
void attention(const float* Q, const float* K, const float* V,
               int N, int d, float scale, bool causal, float* O);
