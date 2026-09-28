# 第 11 章代码实验

> 来源：NVIDIA CUTLASS `main`，固定 commit
> `098de2a652cf8f00fd70b2df54051c7eccbb855a`
>
> 同步日期：2026-09-28

本章不再只保留导读，同时收录三份基于官方源码制作的中文注释版：

| 架构 | 本地源码 | 官方路径 | 上游原文件 SHA-256 |
|---|---|---|---|
| Ampere Warp MMA | [`../01-WMMA/代码实验/tensorop_gemm.py`](../01-WMMA/代码实验/tensorop_gemm.py) | [英文原版](https://github.com/NVIDIA/cutlass/blob/098de2a652cf8f00fd70b2df54051c7eccbb855a/examples/python/CuTeDSL/cute/ampere/kernel/dense_gemm/tensorop_gemm.py) | `ed7eca473c66a3a3ded741eb4ee30757b4b944d5d360e4023ad6be7ba225b21c` |
| Hopper WGMMA | [`../02-WGMMA/代码实验/dense_gemm.py`](../02-WGMMA/代码实验/dense_gemm.py) | [英文原版](https://github.com/NVIDIA/cutlass/blob/098de2a652cf8f00fd70b2df54051c7eccbb855a/examples/python/CuTeDSL/cute/hopper/kernel/dense_gemm/dense_gemm.py) | `bb7b76d893219757e2f3701abf1a7c8c819b9966e38aaed30a768596a55aca9f` |
| Blackwell TCGen05 | [`../03-TCGen05/代码实验/fp16_gemm_0.py`](../03-TCGen05/代码实验/fp16_gemm_0.py) | [英文原版](https://github.com/NVIDIA/cutlass/blob/098de2a652cf8f00fd70b2df54051c7eccbb855a/examples/python/CuTeDSL/cute/blackwell/tutorial/tutorial_gemm/fp16_gemm_0.py) | `a15471df9a2a9c80a6a772416210ea256a58b142aa4b6358ca01851f6f02362a` |

源码保留 NVIDIA BSD-3-Clause 英文许可证原文，并在每个文件头部标明固定
commit 的英文原版链接。许可证文字、代码标识符、公开 API、命令行参数和
数据类型名称不能翻译；其余英文注释、文档字符串、帮助文本、报错与运行提示
均已翻译为中文。kernel 逻辑和默认配置未修改，小规模冒烟测试参数由独立
运行脚本提供。

## 1. 环境要求

- Linux x86-64；
- Python 3；
- PyTorch CUDA 版本；
- `cuda-python`；
- `nvidia-cutlass-dsl==4.8.0`，或上述固定 commit 的 editable build；
- Warp MMA：Ampere SM80 GPU；
- WGMMA：Hopper SM90/SM90a GPU；
- TCGen05：Blackwell SM100 GPU。

从固定 CUTLASS checkout 安装对应 wheel：

```bash
git clone https://github.com/NVIDIA/cutlass.git
cd cutlass
git checkout 098de2a652cf8f00fd70b2df54051c7eccbb855a

# CUDA 12
bash python/CuTeDSL/setup.sh

# CUDA 13 则使用：
# bash python/CuTeDSL/setup.sh --cu13
```

还需要安装与机器 CUDA 环境匹配的 PyTorch。不要在同一个 Python 环境中混用
不同 CUDA major 的 PyTorch、`cuda-python` 和 CuTe DSL wheel。

## 2. 静态校验

不需要 GPU，用于检查源码没有损坏：

```bash
python3 11-Architecture-MMA/代码实验/tests/validate_sources.py
```

该测试会检查：

- 三份源码的计算代码结构与关键架构 API；
- 每份源码中的固定 commit 英文原版链接；
- Python 语法；
- WGMMA/TCGen05 核心 API 标记；
- 运行脚本的 Bash 语法。

## 3. Ampere Warp MMA

在 A100 等 SM80 机器上：

```bash
bash 11-Architecture-MMA/代码实验/run_wmma.sh
```

默认运行官方的 `256×256×512` FP16 GEMM，保留 PyTorch reference check，
关闭性能 benchmark 以缩短 smoke test 时间。只有源码最终打印 `PASS` 才算
运行成功。

## 4. Hopper WGMMA

在 H100/H200 等 SM90 机器上：

```bash
bash 11-Architecture-MMA/代码实验/run_wgmma.sh
```

默认 smoke shape 为：

```text
M=N=K=256, L=1
tile=128×128
cluster=1×1
FP16 input/output, FP32 accumulator
```

自定义参数会原样传给官方程序：

```bash
bash 11-Architecture-MMA/代码实验/run_wgmma.sh \
  --mnkl 8192,8192,8192,1 \
  --tile_shape_mn 128,256 \
  --cluster_shape_mn 1,1 \
  --warmup_iterations 5 \
  --iterations 20
```

脚本保留参考结果检查，只有源码最终打印“运行通过”才算运行成功。

## 5. Blackwell TCGen05

在 B100/B200 等 SM100 机器上：

```bash
bash 11-Architecture-MMA/代码实验/run_tcgen05.sh
```

默认 smoke shape 为：

```text
M=256, N=256, K=64
FP16 input/output, FP32 accumulator
```

正式尺寸：

```bash
bash 11-Architecture-MMA/代码实验/run_tcgen05.sh \
  --mnk 8192,8192,8192
```

脚本保留 PyTorch 参考结果检查，只有源码最终打印“运行通过”才算运行成功。

## 6. 验证状态

当前工作机是 macOS ARM64，没有 NVIDIA GPU、CUDA 和 CuTe DSL。已配置的
远程 GPU 是 A100（SM80），可用于 Warp MMA，但不能执行 WGMMA 或 TCGen05。

要把状态推进到“GPU 编译并运行通过”，必须在 SM90 和 SM100 机器上分别执行
上述脚本，并把完整日志保存到本目录。不能用 A100 上的 Python
`py_compile` 冒充架构 kernel 编译。
