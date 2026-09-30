// Attention 对拍脚手架（harness）—— 读输入、调用你的 attention()、写结果、对拍。
//
// 本文件不含任何 attention 实现，只提供 main 与 I/O。实现在 impl_*.cpp 里，
// 编译时二选一链接进来，见 build.sh。I/O 风格对齐 golden/golden.cpp。
//
// 一般用 build.sh 编译，不必手敲。手动编译示例（搭配某个实现）：
//   g++ -O2 -std=c++17 harness.cpp impl_template.cpp -o attention_template
//
// 运行（需先跑 golden 流水线生成 artifacts/ 里的输入与真值）：
//   ./attention_template ../artifacts        # 传 artifacts 目录
//   (cd ../artifacts && ../learn/attention_template)   # 或缺省读当前目录

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

#include "attention.h"

// causal 开关，需与 golden 保持一致（golden 默认 false）
static constexpr bool kCausal = false;
// 对拍容差，与 golden/check.py 的 TOL 对齐
static constexpr float kTol = 1e-4f;

static std::vector<float> read_bin(const std::string& path, size_t count) {
    std::ifstream f(path, std::ios::binary);
    if (!f) {
        std::fprintf(stderr, "cannot open %s (先跑 golden 流水线生成 artifacts/)\n",
                     path.c_str());
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

static void write_bin(const std::string& path, const std::vector<float>& buf) {
    std::ofstream f(path, std::ios::binary);
    if (!f) {
        std::fprintf(stderr, "cannot write %s\n", path.c_str());
        std::exit(1);
    }
    f.write(reinterpret_cast<const char*>(buf.data()),
            static_cast<std::streamsize>(buf.size() * sizeof(float)));
}

int main(int argc, char** argv) {
    // artifacts 目录：优先命令行参数，否则读当前目录
    const std::string dir = (argc > 1) ? argv[1] : ".";
    const std::string sep = "/";

    // ---- 读维度 ----
    std::ifstream df(dir + sep + "dims.txt");
    if (!df) {
        std::fprintf(stderr, "cannot open %s/dims.txt (先跑 gen_inputs.py)\n",
                     dir.c_str());
        return 1;
    }
    int N = 0, d = 0;
    df >> N >> d;

    const size_t nd = static_cast<size_t>(N) * d;
    std::vector<float> Q = read_bin(dir + sep + "Q.bin", nd);
    std::vector<float> K = read_bin(dir + sep + "K.bin", nd);
    std::vector<float> V = read_bin(dir + sep + "V.bin", nd);

    const float scale = 1.0f / std::sqrt(static_cast<float>(d));

    // ---- 调用你的实现（链接自某个 impl_*.cpp）----
    std::vector<float> O(nd, 0.0f);
    attention(Q.data(), K.data(), V.data(), N, d, scale, kCausal, O.data());

    // ---- 写出结果，供 golden/check.py 复用对拍 ----
    write_bin(dir + sep + "O_cute.bin", O);

    // ---- 内置对拍：与 numpy 真值逐元素比较 ----
    std::vector<float> ref = read_bin(dir + sep + "O_numpy.bin", nd);
    float max_abs = 0.0f;
    size_t arg = 0;
    for (size_t i = 0; i < nd; ++i) {
        const float diff = std::fabs(O[i] - ref[i]);
        if (diff > max_abs) {
            max_abs = diff;
            arg = i;
        }
    }
    const bool ok = max_abs < kTol;
    std::printf("[harness] N=%d d=%d causal=%d\n", N, d,
                static_cast<int>(kCausal));
    std::printf("        vs O_numpy.bin: max_abs_diff=%.3e @ (%zu,%zu)\n",
                max_abs, arg / d, arg % d);
    std::printf("        %s (tol=%.0e)\n", ok ? "PASS" : "FAIL",
                static_cast<double>(kTol));
    return ok ? 0 : 1;
}
