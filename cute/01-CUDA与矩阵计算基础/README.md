# 第 1 章：CUDA 与矩阵计算基础

> 建议时间：第 1～2 周

## 学习目标

- 理解 thread、warp、block、grid
- 区分 global、shared、register memory
- 理解合并访存和 shared memory bank conflict
- 掌握 row-major、column-major、shape 和 stride
- 理解 GEMM 的 `M/N/K` 以及 CTA、warp、thread 分块

## 本章任务

1. 用二维循环表示矩阵访问。
2. 手算 `(4,3):(1,4)` 和 `(4,3):(3,1)` 的 offset。
3. 画出 block、warp、thread 的层级关系。
4. 写一个 naive CUDA GEMM，并与 CPU 结果比较。

## 完成标准

能够解释一个矩阵元素由哪个线程处理、地址如何计算，以及为什么矩阵乘法需要分块和数据复用。

