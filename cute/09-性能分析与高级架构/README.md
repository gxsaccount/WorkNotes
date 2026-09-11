# 第 9 章：性能分析与高级架构

> 建议时间：第 12 周及以后

## 学习目标

- 使用 Nsight Compute 分析 kernel
- 理解吞吐、occupancy 和 register pressure
- 掌握 multistage pipeline 与 warp specialization
- 继续学习 TMA、mbarrier、warpgroup MMA 和 cluster

## 待补笔记

- Nsight Compute 指标
- Roofline 分析
- Register Pressure 与 Occupancy
- Multistage Pipeline
- Hopper TMA 与 WGMMA
- Persistent Kernel
- Split-K 与 Stream-K
- Epilogue Fusion
- Blackwell 架构能力

## 本章项目

选择第 8 章的 GEMM，建立性能基线，逐项分析访存、计算、同步、occupancy 和寄存器瓶颈。

## 完成标准

面对一个性能不理想的 kernel，能够根据测量结果提出并验证优化假设。

