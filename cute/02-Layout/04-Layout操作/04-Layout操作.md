# 04 Layout 操作

> 官方对应：`01_layout.md` 的 Layout Manipulation
>
> 更新：2026-09-11

本节讨论 Layout 的结构操作。这些操作主要改变：

- 选择哪些 mode；
- mode 如何组合；
- tuple 层级如何组织。

它们与下一章的 Layout Algebra 不同。本节重点是结构重组，而不是 composition、complement 或 divide。

## 先区分三种相似写法

```cpp
a(i);                    // 应用映射：坐标 i -> index
cute::layout<1,0>(a);    // 沿层级路径取得一个 sublayout
cute::select<1,0>(a);    // 从当前层选择两个兄弟 mode
```

这里的 `a(i)` 与函数 `cute::layout<I...>(a)` 不是同一种操作。

---

## 1. Sublayout

`layout<I...>` 沿 Shape/Stride 的嵌套路径逐层访问，并返回路径末端对应的一个子 Layout。

考虑：

```cpp
Layout a = Layout<Shape<_4,Shape<_3,_6>>>{};
```

默认 `LayoutLeft` 生成：

```text
(4,(3,6)):(1,(4,12))
```

可以使用 `layout<I...>` 取得子 Layout：

```cpp
layout<0>(a);     // 4:1
layout<1>(a);     // (3,6):(4,12)
layout<1,0>(a);   // 3:4
layout<1,1>(a);   // 6:12
```

每次索引沿 tuple 层级向内走一层。

适合的思考方式是：

```text
layout<I...>(a)
```

同时从 Shape 和 Stride 的相同位置取出一棵 congruent 子树。

---

## 2. select

`select<I...>` 从同一层选择指定 mode，并保留给出的顺序：

```cpp
Layout a = Layout<Shape<_2,_3,_5,_7>>{};
// a = (2,3,5,7):(1,2,6,30)

auto a13  = select<1,3>(a);    // (3,7):(2,30)
auto a013 = select<0,1,3>(a);  // (2,3,7):(1,2,30)
auto a2   = select<2>(a);      // (5):(6)
```

`select` 同时选择对应的 Shape 和 Stride，不会重新计算 Stride。

同一个 Layout、相同参数的结果对比：

```cpp
Layout h = Layout<Shape<_2,Shape<_3,_5>,_7>>{};
// h = (2,(3,5),7):(1,(2,6),30)

layout<1,0>(h);  // 3:2
select<1,0>(h);  // ((3,5),2):((2,6),1)
```

```text
layout<1,0>：把 1、0 当成嵌套路径
select<1,0>：把 1、0 当成当前层的选择列表
```

可以辅助记成“`layout` 纵向深入，`select` 横向选择”，但它们不是严格意义上的深度优先搜索和广度优先搜索，因为二者都不会遍历整棵树。

---

## 3. take

`take<Begin,End>` 选择半开区间：

```text
[Begin, End)
```

例如：

```cpp
Layout a = Layout<Shape<_2,_3,_5,_7>>{};

take<1,3>(a);   // 选择 mode 1、2
take<1,4>(a);   // 选择 mode 1、2、3
```

与 `select` 的区别：

```text
select：按索引列表选取，可以是不连续的
take：按连续半开区间选取
```

官方接口不允许通过 `take<1,1>` 构造空 Layout。

---

## 4. Concatenation

多个 Layout 可以组合为一个更高 rank 的 Layout。

例如：

```cpp
Layout a = Layout<_3,_1>{};  // 3:1
Layout b = Layout<_4,_3>{};  // 4:3

auto row = make_layout(a, b);       // (3,4):(1,3)
auto col = make_layout(b, a);       // (4,3):(3,1)
auto q   = make_layout(row, col);   // ((3,4),(4,3)):((1,3),(3,1))
```

这里做的是拼接：

```text
(A, B)
```

不是函数复合：

```text
A o B
```

二者必须严格区分。

### 4.1 包装会增加层级

```cpp
auto aa  = make_layout(a);   // (3):(1)
auto aaa = make_layout(aa);  // ((3)):((1))
```

这些对象可能拥有相同的整数映射，但 rank、depth 和可接受的坐标结构不同。

---

## 5. append、prepend 与 replace

除 `make_layout` 外，CuTe 还提供结构编辑接口：

```cpp
append(a, b)
prepend(a, b)
replace<I>(a, b)
```

### append

把新 Layout 放到现有 Layout 的末尾。

### prepend

把新 Layout 放到现有 Layout 的开头。

### replace

用新 Layout 替换指定 mode。

分析这些操作时，同时画出：

```text
操作前 Shape 树
操作前 Stride 树
操作后 Shape 树
操作后 Stride 树
```

这样可以避免只修改 Shape、忘记 Stride 必须保持 congruent。

---

## 6. Grouping

`group<Begin,End>` 把一段相邻 mode 包装成一个 multi-mode。

例如：

```text
(2,3,5,7):(1,2,6,30)
```

执行：

```cpp
group<0,2>(a);
```

得到结构：

```text
((2,3),5,7):((1,2),6,30)
```

Grouping 的核心作用是改变逻辑解释：

```text
原来：四个顶层 mode
现在：三个顶层 mode，第一个是 multi-mode
```

它不会凭空改变每个叶子 shape 与 stride 的对应关系。

---

## 7. Flattening

`flatten` 删除 tuple 层级，将所有叶子 mode 放回同一层：

```text
((2,3),(5,7)):((1,2),(6,30))

flatten

(2,3,5,7):(1,2,6,30)
```

Flattening 改变的是：

- rank；
- depth；
- 坐标的层级表达。

它不负责：

- 合并相邻 mode；
- 改变 stride 数值；
- 消除地址空洞；
- 消除地址重叠；
- 改变叶子 mode 的先后顺序。

因此：

```text
flatten != coalesce
```

### 7.1 flatten 与 coalesce 对比

```text
flatten：
  ((2,3),4):((1,2),6)
  -> (2,3,4):(1,2,6)

coalesce：
  (2,3,4):(1,2,6)
  -> 在满足代数条件时进一步合并 mode
```

`coalesce` 位于下一章 `03-Layout-Algebra/01-Coalesce`。

---

## 8. Slicing

Layout 本身支持 slicing，但官方建议在 Tensor 语境中学习和使用 slicing，因为切片通常同时涉及：

- 哪些坐标被固定；
- 哪些 mode 被保留；
- Tensor 起始指针是否移动；
- 结果 Tensor 的 Engine 与 Layout。

因此本章只建立概念，具体语法和 `_` 占位符放在：

```text
04-Tensor
```

---

## 9. 结构相同不等于语义相同

操作 Layout 时需要分别检查三个层面：

### 9.1 叶子内容

Shape 和 Stride 的具体整数是否改变。

### 9.2 层级结构

rank、depth 和 tuple profile 是否改变。

### 9.3 映射函数

对于兼容坐标，最终产生的 index 是否保持不变。

两个 Layout 可能：

- 映射相同但层级不同；
- size 相同但映射不同；
- 叶子整数相同但分组不同；
- 一维映射相同，但接受的 rank-D / hierarchical coordinate 不同。

不能仅看打印出来的数字集合判断它们是否完全等价。

---

## 10. 本节自测

练习优先设计为可直接计算、展开或对比结果的题目；只有概念无法自然转化为计算题时，才保留少量简答题。

### 练习 1：沿层级取得 sublayout

给定：

```text
a = (4,(3,6)):(1,(4,12))
```

写出：

```cpp
layout<0>(a)
layout<1>(a)
layout<1,0>(a)
layout<1,1>(a)
```

### 练习 2：select 与 take

给定：

```text
a = (2,3,5,7):(1,2,6,30)
```

写出以下操作的结果 Layout：

```cpp
select<0,2>(a)
select<1,3>(a)
take<0,2>(a)
take<1,3>(a)
```

### 练习 3：concatenation

给定：

```text
A = 8:2
B = 4:1
```

写出：

```text
make_layout(A,B)
```

然后展开 `make_layout(A,B)` 的前 8 个自然序 index。

### 练习 4：单层包装

给定：

```text
a = 3:1
```

写出下列对象的 Layout、rank 和 depth：

```cpp
a
make_layout(a)
make_layout(make_layout(a))
```

### 练习 5：group 与 flatten

给定：

```text
a = (2,3,5,7):(1,2,6,30)
```

依次写出：

```cpp
b = group<1,3>(a)
c = flatten(b)
```

并列出 `a`、`b`、`c` 的叶子 mode 顺序。

### 练习 6：flatten 后的 rank

给定：

```text
a = ((2,3),(4,5)):((1,2),(6,24))
```

写出：

```cpp
flatten(a)
```

以及结果的 rank 和 depth。

完成后参阅：[自测参考答案](自测参考答案.md)。
