# Attention 学习与实操

CuTe 学习配套：左边是**理论笔记**（`notes/`），右边是**动手对拍流水线**（`code/`）。
笔记讲清 Flash Attention 各版本「为什么这么优化」，代码用最直白的 numpy/C++ 参考实现
把「分块调度 + online softmax」跑对，作为后续 CuTe kernel 的翻译蓝本与对拍真值。

## 目录结构

```
attention/
├── notes/                       理论笔记（按主题分）
│   ├── flash-attention/         FA v1→v4 逐版本优化 + v3 的 CUTLASS/CuTe API 示例
│   ├── decoding/                FlashDecoding++ / PagedAttention（推理侧）
│   └── gpu-arch/                GPU occupancy / NVIDIA 架构指令演进
└── code/                        对拍流水线（CPU，无需 GPU）
    ├── run.sh                   一键跑通全流程
    ├── golden/                  对拍基线：固定输入 + 真值 + 校验工具（搭一次，很少动）
    ├── learn/                   学习/实操：FA 算法参考 + CuTe 入口（主要在这写）
    └── artifacts/               生成产物（.bin / dims.txt / 可执行，已 gitignore）
```

## 建议学习路径

1. `notes/flash-attention/flash_att_v1.md` → `v2` → `v3` → `v4`：主线，逐版本理解优化动机。
2. `notes/gpu-arch/`：补 GPU occupancy 与架构指令背景，理解 FA 优化为何依赖硬件特性。
3. `notes/flash-attention/flash_att_v3_cuda_examples.md`：把 v3 优化对应到 CUTLASS/CuTe 官方 API。
4. `notes/decoding/`：推理侧的 FlashDecoding++ 与 PagedAttention。
5. 动手：跑 `code/`，从标准 attention 到 FA 分块参考，理解算法后再用 CuTe 翻译。

## 跑对拍流水线

```bash
bash code/run.sh
```

依赖：`python3` + `numpy`、`g++`（C++17）。全程 CPU，几秒完成，全 PASS 即环境与算法就绪。

流程（产物统一写到 `code/artifacts/`）：

| 步骤 | 源码 | 作用 |
|---|---|---|
| 1 | `golden/gen_inputs.py` | 生成固定 Q/K/V（seed 固定）+ `dims.txt`，三方共用同一份输入 |
| 2 | `golden/golden_numpy.py` | numpy 标准 attention 真值 → `O_numpy.bin` |
| 3 | `golden/golden.cpp` | 独立 C++ 真值 → `O_cpp.bin`，排除「golden 写错」风险 |
| 4 | `learn/fa_reference.py` | FA 分块参考 v0(两遍)/v1(online) 自对拍 golden → `O_v0/v1.bin` |
| 5 | `golden/check.py` | 逐元素对拍 `O_numpy` vs `O_cpp`，max abs diff < 1e-4 判定 PASS |

`code/learn/smoke_dsl.py` 是独立的 GPU 冒烟测试：验证 nvidia-cutlass-dsl 能在本机
JIT 编译并在 GPU 上执行 kernel（需 GPU + DSL 环境，不属于上面的 CPU 对拍流程）。

其中 `golden/` 是**对拍基线**——生成 `artifacts/` 里的真值，搭一次基本不动；
`learn/` 是**你动手的地方**——FA 算法参考与后续 CuTe 实现都写这里。

## 下一步（CuTe 实操）

用 CuTe 实现 FA kernel 后（放 `code/learn/`），输出写成 `artifacts/O_cute.bin`，
直接复用对拍脚本验证：

```bash
python3 code/golden/check.py O_numpy.bin O_cute.bin
```
