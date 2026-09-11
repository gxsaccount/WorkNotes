# 第 1 章：CUDA 与矩阵计算基础

> 建议时间：第 1～2 周<br>
> 更新：2026-09-11

这一章不直接学习复杂的 CuTe API，而是先建立后续 Layout Algebra 所依赖的三个基础模型：

1. **执行模型**：哪个 thread 负责哪个矩阵元素。
2. **地址模型**：矩阵坐标怎样通过 shape 和 stride 变成内存 offset。
3. **分块模型**：为什么 GEMM 要按 CTA、warp、thread 分块并复用数据。

## 学习材料

1. [CUDA 与矩阵计算基础](CUDA与矩阵计算基础.md)
2. [练习与自测](练习与自测.md)

## 学习目标

- 理解 thread、warp、block/CTA、grid 的层级关系
- 能把 `blockIdx`、`blockDim`、`threadIdx` 转换成矩阵坐标
- 区分 register、shared memory、global memory
- 区分合并访存、数据复用和 shared memory bank conflict
- 掌握 row-major、column-major、shape、stride、coordinate、offset
- 理解 GEMM 的 `M/N/K` 和 K 维归约
- 理解 CTA tile、warp tile、thread tile
- 能解释 naive GEMM 的主要性能问题和 tiled GEMM 的基本思路

## 推荐学习顺序

```text
CUDA 执行层级
  ↓
二维线程坐标
  ↓
矩阵坐标与线性地址
  ↓
global/shared/register memory
  ↓
合并访存与 bank conflict
  ↓
naive GEMM
  ↓
shared-memory tiled GEMM
  ↓
CTA / warp / thread 分块
  ↓
进入 CuTe Layout
```

## 本章任务

1. 用二维循环表示矩阵访问。
2. 手算 `(4,3):(1,4)` 和 `(4,3):(3,1)` 的 offset。
3. 画出 grid、block、warp、thread 的层级关系。
4. 解释合并访存和数据复用的区别。
5. 写一个带边界检查的 naive CUDA GEMM，并与 CPU 结果比较。
6. 解释 shared-memory tiled GEMM 为什么能减少 global memory 读取。

## 完成标准

能够独立回答以下问题：

- 一个矩阵元素由哪个线程负责？
- 坐标 `(i,j)` 的线性地址如何计算？
- 哪个方向在内存中连续？
- 为什么合并访存不等于数据复用？
- naive GEMM 为什么存在重复读取？
- tiled GEMM 如何利用 shared memory？
- CTA、warp、thread tile 分别描述什么？
