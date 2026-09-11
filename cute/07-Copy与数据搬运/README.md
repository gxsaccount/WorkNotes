# 第 7 章：Copy 与数据搬运

> 建议时间：第 9 周

## 学习目标

- 理解 Copy Atom 与 TiledCopy
- 掌握 thread layout 和 value layout
- 实现 global → shared → register 数据通路
- 理解向量化访问、predication 和 shared-memory swizzle

## 待补笔记

- Copy Atom
- TiledCopy
- Global/Shared/Register partition
- Vectorized Copy
- Predication
- Shared Memory Swizzle

## 本章项目

依次实现向量复制、矩阵转置、tiled copy 和非整除尺寸下的 predicated copy。

## 完成标准

能够说明每个线程搬运哪些元素，并判断访问是否合并、是否存在 bank conflict。

