# CuTe 官方 GEMM 示例与结果检查

> 来源：NVIDIA CUTLASS `main`，commit `147295a3`
>
> 同步日期：2026-09-21

本目录保存官方教程源码的本地副本：

```text
sgemm_1.cu
sgemm_2.cu
sgemm_sm70.cu
sgemm_sm80.cu
```

相对官方版本只增加：

```text
reference_check.hpp
CPU reference GEMM
最大绝对/相对误差统计
PASS/FAIL 与非零失败退出码
```

## 本地检查器测试

```bash
c++ -std=c++17 -O2 \
  tests/reference_check_test.cpp \
  -o /tmp/reference_check_test

/tmp/reference_check_test
```

## 编译

在 CUTLASS 仓库根目录执行：

```bash
SRC=/path/to/WorkNotes/cute/07-GEMM-Tutorial/代码实验
BUILD=build-cute-tutorial-checked
NVCC=/usr/local/cuda-12.2/bin/nvcc

mkdir -p "$BUILD"

for name in sgemm_1 sgemm_2 sgemm_sm70 sgemm_sm80; do
  "$NVCC" -std=c++17 -O3 -lineinfo -arch=sm_80 \
    -Iinclude \
    -Itools/util/include \
    -I"$SRC" \
    "$SRC/$name.cu" \
    -o "$BUILD/$name"
done
```

## 运行

测试尺寸需满足示例的 tile 整除假设：

```bash
./build-cute-tutorial-checked/sgemm_1    512 512 512 N T
./build-cute-tutorial-checked/sgemm_2    512 512 512 N T
./build-cute-tutorial-checked/sgemm_sm70 512 512 512 N T
./build-cute-tutorial-checked/sgemm_sm80 512 512 512 T N
```

`sgemm_sm80` 的 half Tensor Core 实现只提供 TN 路径，因此最后一个示例使用
`T N`。

## 容差

```text
FP32 output：atol=5e-3，rtol=5e-3
FP16 output：atol=1.0， rtol=0.10
```

FP16 示例使用 FP16 accumulator，CPU reference 使用 double 累加，因此需要比
FP32 更宽的容差。检查器会报告最大误差所在的 `(m,n)`。

## 运行记录

日期：2026-09-21

环境：

```text
Host：10.10.16.112
GPU：NVIDIA A100-SXM4-80GB MIG 1g.20gb
Compute Capability：8.0
可用 SM：14
CUDA：12.2
CUTLASS commit：147295a3
测试 Shape：M=N=K=512
```

结果：

| 示例 | 路径 | 最大绝对误差 | 性能 |
|---|---|---:|---:|
| `sgemm_1` | NT / FP32 | `2.88766e-05` | `1165.0 GFlop/s` |
| `sgemm_2` | NT / FP32 | `2.88766e-05` | `1298.9 GFlop/s` |
| `sgemm_sm70` | NT / FP32 | `2.88766e-05` | `1319.5 GFlop/s` |
| `sgemm_sm80` | TN / FP16 Tensor Core | `0.089232` | `11632.7 GFlop/s` |

四个示例均输出：

```text
RESULT_CHECK: PASS
```

远端产物：

```text
源码：/root/workspace/cutlass/build-cute-tutorial-checked-src
二进制：/root/workspace/cutlass/build-cute-tutorial-checked
日志：/root/workspace/cutlass/build-cute-tutorial-checked/build_run.log
```
