# 01 基础类型与概念

> 官方对应：`01_layout.md` 的 Fundamental Types and Concepts
>
> 更新：2026-09-11

## 1. Layout 的位置

CuTe 将“数据在哪里”和“如何组织数据”拆成两个部分：

```text
Layout：坐标 -> 整数 index
Engine：保存或引用数据
Tensor：Engine + Layout
```

因此 Layout 本身不拥有数据，也不限定数据一定在 global memory、shared memory 或寄存器中。

先把 Layout 当成纯函数：

```text
L : coordinate -> index
```

等到 Tensor 章节，再把这个 index 用于访问真正的数据。

---

## 2. Integer：静态整数与动态整数

CuTe 同时使用两类整数。

### 2.1 动态整数

动态整数的值在运行时确定，例如：

```cpp
int m = 128;
size_t n = 64;
```

这类值可以随每次程序运行而变化。

### 2.2 静态整数

静态整数的值编码在类型中，在编译期已经确定：

```cpp
Int<8>{}
_8{}
```

其中 `_8` 是常用简写。静态整数的主要价值是：

- 编译器可以在编译期做计算和化简；
- 某些合法性条件可以通过 `static_assert` 检查；
- 模板实例可以针对固定 Shape、Stride 生成专门代码；
- 更容易消除运行时除法、取模和分支。

静态与动态只影响“值何时已知”，不改变 Layout 的数学语义：

```text
8:1
_8:_1
```

作为坐标映射可以表示相同的函数，但二者的 C++ 类型不同。

### 2.3 常见类型判断

官方文档列出的常用 traits 包括：

```cpp
cute::is_integral<T>
cute::is_std_integral<T>
cute::is_static<T>
cute::is_constant<N, T>
```

学习初期不必记住全部名字，但要能够判断一个 Shape 或 Stride 的组成部分是静态还是动态。

---

## 3. Tuple 与 IntTuple

### 3.1 Tuple

`cute::tuple` 是适合 host 和 device 使用的轻量 tuple。它与 `std::tuple` 的定位相似，但实现和约束面向 CUDA/CuTe。

### 3.2 IntTuple

IntTuple 是递归概念：

```text
IntTuple := Integer
          | Tuple<IntTuple...>
```

因此下面都属于 IntTuple：

```text
2
_3
(2,_3)
(42,(1,3),17)
```

CuTe 使用 IntTuple 表示很多对象：

- Shape
- Stride
- Coord
- Step

层级不是装饰。括号决定了对象拥有怎样的 mode 结构，以及可以接受哪些形状的坐标。

---

## 4. rank、depth 与 size

### 4.1 rank

`rank(x)` 表示当前层直接包含多少个元素。

官方定义中，单个整数的 rank 是 1：

```text
rank(6)         = 1
rank((4,3))     = 2
rank((3,(6,2))) = 2
```

最后一个例子的顶层只有两个元素：`3` 和 `(6,2)`。

### 4.2 depth

`depth(x)` 表示 tuple 的层级深度：

```text
depth(6)         = 0
depth((4,3))     = 1
depth((3,(6,2))) = 2
```

rank 只观察当前层，depth 观察最深嵌套。

### 4.3 size

`size(x)` 是所有叶子整数的乘积：

```text
size(6)         = 6
size((4,3))     = 12
size((3,(6,2))) = 36
```

层级改变逻辑结构，但不会改变乘积规则。

---

## 5. Shape 与 Stride

Shape 和 Stride 都是 IntTuple。

```text
Shape：定义坐标空间
Stride：把自然坐标映射到整数 index
```

例如：

```text
Shape  = (4,3)
Stride = (1,4)
Coord  = (i,j)

index = i*1 + j*4
```

### 5.1 congruent

一个 Layout 的 Shape 和 Stride 必须具有相同的 tuple profile，即层级结构一一对应：

```text
Shape  = (2,(2,2))
Stride = (4,(2,1))     # congruent
```

下面的结构不匹配：

```text
Shape  = (2,(2,2))
Stride = (4,2,1)       # 顶层结构不同
```

在 C++ 中可以检查：

```cpp
static_assert(congruent(shape, stride));
```

对应关系意味着 Shape 中每一个叶子 mode 都有一个 Stride 叶子。

---

## 6. Layout

Layout 是 Shape 与 Stride 的组合：

```text
Layout = Shape : Stride
```

例如：

```text
(4,3):(1,4)
```

可以展开成：

```cpp
for (int j = 0; j < 3; ++j) {
  for (int i = 0; i < 4; ++i) {
    int index = i * 1 + j * 4;
  }
}
```

自然遍历时 mode-0 最先变化，因此 mode-0 对应最内层计数器。

但要注意：

```text
mode-0 最先变化
```

不等于：

```text
mode-0 在内存中一定连续
```

是否连续由 mode-0 的 stride 决定。

---

## 7. Tensor

Layout 与数据引擎结合后构成 Tensor：

```text
Tensor = Engine + Layout
```

概念上可以写成：

```text
tensor(coord)
  = engine[layout(coord)]
```

同一个 Layout 可以用于不同存储空间；同一块数据也可以通过不同 Layout 进行解释。

本章只讨论 Layout。Tensor 的 owning/nonowning、地址空间以及 slicing 会在 `04-Tensor` 继续展开。

---

## 8. 本节自测

1. 静态整数 `_8` 与动态整数 `8` 的映射语义是否不同？
2. `rank((3,(2,4)))`、`depth((3,(2,4)))` 和 `size((3,(2,4)))` 分别是什么？
3. 为什么 Shape 与 Stride 必须 congruent？
4. mode-0 最先变化是否意味着 mode-0 的地址一定连续？
5. Layout 为什么能够脱离 Tensor 单独存在？

完成后参阅：[自测参考答案](自测参考答案.md)。
