# 第 2 章：CuTe Layout 基础

> 建议时间：第 3 周

## 学习目标

- 建立 `Layout = Shape : Stride` 的核心模型
- 掌握 mode、rank、depth、size、cosize
- 理解 `idx2crd`、`crd2idx` 和 CuTe 自然序
- 判断单射、紧凑、空洞、广播和地址别名
- 掌握 `flatten` 与 `coalesce`

## 当前材料

- [Composition 笔记第 0 节：Layout 与 Coalesce](../03-Composition/用循环理解Composition.md#0-预备layout-就是一段循环)
- [Python Layout 模型](../03-Composition/代码实验/sim.py)
- [Coalesce 练习](../03-Composition/代码实验/quiz.py)

当前基础材料暂时包含在 Composition 笔记中。后续可将 Shape、Stride、坐标系统和 Coalesce 扩写为本章独立笔记。

## 本章任务

对以下 Layout 展开 offset，并判断其性质：

```text
(4,3):(1,4)
(4,3):(3,1)
(2,2):(1,1)
(2,2,2):(2,1,4)
```

## 完成标准

看到一个 Layout 后，能够把它解释为坐标映射、嵌套循环、混合进制计数器和地址生成器。

