# 第 4 章：Complement

> 建议时间：第 6 周

## 学习目标

- 理解 `B* = complement(B, M)`
- 理解 complement 表示 tile 副本的基址布局
- 掌握 cotarget、ordered 和 disjoint codomain
- 理解 cotarget 不整除时的向上覆盖
- 理解 `(B,B*)` 如何同时表达 tile 内与 tile 间

## 当前笔记

- [CuTe Complement（补集）概念总结](Complement补集概念.md)

## 建议练习

```text
complement(4:1, 24)
complement(4:2, 24)
complement(4:1, 10)
```

对每个结果展开 `(B,B*)(i,j) = B(i) + B*(j)`，检查覆盖范围和地址重叠。

## 完成标准

能够解释 complement 为什么不是“遗漏元素列表”，以及 `B*` 为什么代表 tile 间的移动方式。

