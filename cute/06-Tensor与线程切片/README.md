# 第 6 章：Tensor 与线程切片

> 建议时间：第 8 周

## 学习目标

- 理解 `Tensor = Engine + Layout`
- 掌握 global、shared、register Tensor
- 学习 Tensor slicing、`local_tile` 和 `local_partition`
- 学习 `partition_S`、`partition_D`
- 建立 block、warp、thread 的数据所有权模型

## 待补笔记

- Tensor、Engine 与 Layout
- Tensor slicing
- Identity/Coordinate Tensor
- CTA、warp 和 thread partition

## 本章项目

把一个 `128×128` 矩阵依次划分为 CTA tile、warp tile 和 thread tile，并验证所有元素没有遗漏或非预期重复。

## 完成标准

给定线程编号，能够准确说明该线程负责矩阵中的哪些逻辑坐标。

