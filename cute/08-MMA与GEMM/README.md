# 第 8 章：MMA 与 GEMM

> 建议时间：第 10～11 周

## 学习目标

- 理解 MMA Atom 与 TiledMMA
- 掌握 `partition_A/B/C`
- 理解 accumulator fragment
- 掌握 GEMM mainloop、K-loop、流水线和 epilogue
- 从 SIMT GEMM 过渡到 Tensor Core GEMM

## 待补笔记

- MMA Atom
- TiledMMA
- SIMT GEMM
- Tensor Core GEMM
- Mainloop 与 Epilogue
- Double Buffering

## 本章项目

依次完成 CPU reference、naive CUDA、shared-memory tiled、CuTe SIMT 和 CuTe Tensor Core GEMM，并为每个版本编写正确性测试。

## 完成标准

能够阅读基础 CuTe GEMM kernel，并解释 A、B、C 的线程划分和一次 MMA 中的数据所有权。

