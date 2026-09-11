# 第 5 章：Divide 与 Product

> 建议时间：第 7 周

## 学习目标

- 掌握 `Divide = A ∘ (B,B*)`
- 掌握 `Product = (A,A*∘B)`
- 区分 tile mode 与 rest mode
- 理解 logical、zipped、tiled、flat divide
- 判断 divide 是 permutation、gather 还是 reindex

## 当前笔记

- [CuTe Division 与 Product](Division与Product.md)

## 建议练习

给定：

```text
A = (4,2,3):(2,1,8)
B = 4:2
```

依次计算 `B*`、`(B,B*)` 和 `A ∘ (B,B*)`，然后展开每一个 tile。

## 完成标准

能够从 concatenation、composition 和 complement 推导 Divide/Product，而不是单独背诵 API。

