# 02 Tensor Tiling 与 Slicing

> 官方对应：`03_tensor.md` 的 Tiling a Tensor、Slicing a Tensor 与 Examples
>
> 更新：2026-09-15

## 1. 本节目标

学完本节后，应当能够：

1. 将 Layout Algebra 的 division/composition 应用于 Tensor；
2. 解释为什么 Tensor 没有对应的 `_product` 操作；
3. 手算 slicing 后的新数据起点和新 Layout；
4. 根据 `_` 的数量判断结果 Tensor 的 rank；
5. 构造静态 tile 对应的 register Tensor。

## 2. Tensor 上的 Layout Algebra

许多 Layout 变换也可以直接应用于 Tensor：

```cpp
composition(tensor, tiler);
logical_divide(tensor, tiler);
zipped_divide(tensor, tiler);
tiled_divide(tensor, tiler);
flat_divide(tensor, tiler);
```

其核心思想是：

```text
原 Tensor
  = 原 Engine + 原 Layout

变换后的 Tensor
  = 仍然引用相关数据 + 变换后的 Layout
```

这些操作重组 Tensor 的逻辑坐标，不自动搬运元素。

常见用途包括：

- 为 CTA 划分 tile；
- 为 warp 或线程划分数据；
- 按 MMA 要求重排坐标；
- 将 tile 内坐标与 tile 编号显式分离。

### 2.1 为什么 Tensor 没有 product

官方没有为 Tensor 实现 Layout Algebra 的 `_product` 系列。

原因是 product 往往扩大 Layout 的 codomain：

```text
旧 Tensor 可访问范围
  ↓ product
新 Layout 可能要求访问更远的 offset
```

对于纯 Layout，这只是整数函数的变化；对于 Tensor，它可能让新 view 越过原有数据边界。CuTe 无法一般性地保证这种访问安全，因此：

```text
Layout 可以 product
Tensor 不提供 product
```

## 3. 元素访问与 slicing 的分界

完整坐标会选择一个元素：

```cpp
A(2, 5);       // element/reference
```

坐标中出现 `_` 时，会保留对应 mode 并返回 subtensor：

```cpp
A(2, _);       // subtensor
A(_, 5);       // subtensor
```

`_` 是 `cute::Underscore` 的实例，语义类似 Fortran、Matlab 或 Python 中的完整切片：

```text
这个 mode 不固定，保留在结果中
```

## 4. Slicing 的两个步骤

给定：

```text
Tensor = Engine(base) + Layout
partial_coord = 固定坐标与 `_` 的组合
```

slicing 同时执行两件事。

### 4.1 固定坐标贡献到新 iterator

将 partial coordinate 中的固定部分代入 Layout，计算基址偏移：

```text
new_base = old_base + fixed_offset
```

### 4.2 `_` 对应的 mode 组成新 Layout

所有 `_` 所保留的 mode，按照切片坐标中的结构组成结果 Layout：

```text
new_tensor = Engine(new_base) + retained_layout
```

因此 slicing 不是单纯“删掉 Shape 中的维度”。它既改变：

- view 的起始 iterator；
- view 的 Shape；
- view 的 Stride；
- 可能还改变结果的 rank 与层级。

## 5. 官方切片示例

原 Tensor：

```cpp
auto A = make_tensor(
    ptr,
    make_shape(
        make_shape(Int<3>{}, 2),
        make_shape(2, Int<5>{}, Int<2>{})),
    make_stride(
        make_stride(4, 1),
        make_stride(Int<2>{}, 13, 100)));
```

打印形式：

```text
A = ((_3,2),(2,_5,_2)):((4,1),(_2,13,100))
```

自然坐标写作：

```text
((m0,m1),(n0,n1,n2))
```

offset 为：

```text
4*m0 + 1*m1 + 2*n0 + 13*n1 + 100*n2
```

### 5.1 `A(2, _)`

第 0 个顶层 mode 被标量 `2` 固定，第 1 个顶层 mode 保留：

```cpp
auto B = A(2, _);
```

结果：

```text
B Layout = ((2,_5,_2)):((_2,13,100))
base += layout<0>(2)
```

注意最外层仍带有单 mode tuple 层级，因为 `_` 保留的是一个顶层 mode。

### 5.2 `A(_, 5)`

```cpp
auto C = A(_, 5);
```

结果：

```text
C Layout = ((_3,_2)):((4,1))
```

标量 `5` 会作为第 1 个顶层 mode 的 compatible 坐标，先转换到该层级 Shape 的自然坐标，再计算固定 offset。

### 5.3 `A(make_coord(_,_), 5)`

```cpp
auto D = A(make_coord(_, _), 5);
```

结果：

```text
D Layout = (_3,2):(4,1)
```

`C` 与 `D` 选择相同元素，但 Shape 不同：

```text
C: ((_3,_2))   顶层 rank = 1
D: (_3,2)      顶层 rank = 2
```

原因是：

- `A(_,5)` 用一个 `_` 保留整个第 0 顶层 mode；
- `A(make_coord(_,_),5)` 用两个 `_` 分别保留该 mode 的两个子 mode。

### 5.4 混合层级 slicing

```cpp
auto E = A(
    make_coord(_, 1),
    make_coord(0, _, 1));
```

固定贡献：

```text
m1 = 1  -> 1
n0 = 0  -> 0
n2 = 1  -> 100

new_base = old_base + 101
```

保留 `m0` 与 `n1`：

```text
E Layout = (_3,_5):(4,13)
```

另一个例子：

```cpp
auto F = A(
    make_coord(2, _),
    make_coord(_, 3, _));
```

固定贡献：

```text
m0 = 2  -> 8
n1 = 3  -> 39

new_base = old_base + 47
```

保留的 mode 及 stride：

```text
m1 -> 2:1
n0 -> 2:2
n2 -> _2:100

F Layout = (2,2,_2):(1,_2,100)
```

## 6. 结果 rank 如何判断

官方示例给出的实用规则是：

> 结果 rank 等于 slicing coordinate 中 `Underscore` 的数量。

但要按传入坐标的层级理解：

```cpp
A(_, 5);                  // 1 个 `_`，保留整个复合 mode
A(make_coord(_,_), 5);    // 2 个 `_`，分别保留两个子 mode
```

所以 slicing 中的 tuple 结构会决定结果 Tensor 的层级，不只是决定保留哪些元素。

## 7. 从 global memory 复制一行到寄存器

官方示例先展示不需要知道具体 Layout 的泛型写法：

```cpp
auto gmem = make_tensor(
    ptr,
    make_shape(Int<8>{}, 16));

auto rmem = make_tensor_like(gmem(_, 0));

for (int j = 0; j < size<1>(gmem); ++j) {
  copy(gmem(_, j), rmem);
  do_something(rmem);
}
```

这里的关键点是：

```text
gmem(_,j)        -> 第 j 个一维 subtensor
make_tensor_like -> 创建 Shape compatible 的 owning register Tensor
copy             -> 真正执行数据搬运
```

Tensor slicing 本身只创建 view，`copy` 才会传输元素。

该算法依赖两个可在编译期表达的条件：

```cpp
CUTE_STATIC_ASSERT_V(rank(gmem) == Int<2>{});
CUTE_STATIC_ASSERT_V(
    is_static<decltype(shape<0>(gmem))>{});
```

- 输入必须是 rank-2；
- 第 0 个 mode 的 Shape 必须静态，才能创建对应的 owning register Tensor。

## 8. 从 global memory 复制任意 subtile

把 slicing 与 division 结合：

```cpp
auto gmem = make_tensor(
    ptr,
    make_shape(24, 16));

auto tiler = Shape<_8,_4>{};

auto gmem_tiled =
    zipped_divide(gmem, tiler);

auto rmem =
    make_tensor_like(gmem_tiled(_, 0));

for (int j = 0; j < size<1>(gmem_tiled); ++j) {
  copy(gmem_tiled(_, j), rmem);
  do_something(rmem);
}
```

逻辑过程是：

```text
1. zipped_divide
   将完整 Tensor 重组为 (tile, rest)

2. gmem_tiled(_, j)
   选择第 j 个 tile，保留 tile 内坐标

3. make_tensor_like
   为一个 tile 创建静态 owning Tensor

4. copy
   把该 tile 的值搬到寄存器
```

tiler 也可以是带非平凡 stride 的 Layout：

```cpp
using Tiler =
    Tile<Layout<_8,_3>, Layout<_4,_2>>;
```

这说明 tile 不必只表示连续矩形；它可以描述任意可组合的坐标采样模式。

## 9. 常见误区

### 误区 1：slicing 会复制数据

错误。slicing 创建 subtensor view；`copy` 才搬运元素。

### 误区 2：`_` 只是保留 Shape 大小

不完整。它还保留对应 stride 和层级，并影响新 iterator 的计算方式。

### 误区 3：选择相同元素一定得到相同 Tensor 类型

错误。`A(_,5)` 与 `A(make_coord(_,_),5)` 可以选择相同元素，但 rank 和 Shape 不同。

### 误区 4：可以安全地对 Tensor 做任意 Layout product

错误。product 可能扩大可访问 codomain，使 view 越过原始数据范围。

### 误区 5：`zipped_divide` 已经完成了分块 copy

错误。它只重组坐标，数据仍在原 Engine 中。

## 10. 本节自测

1. Tensor tiling 会不会移动数据？
2. 为什么 Tensor 不提供 `_product` 操作？
3. slicing 时固定坐标和 `_` 分别产生什么作用？
4. 为什么 `A(_,5)` 与 `A(make_coord(_,_),5)` 的元素相同但 Shape 不同？
5. 对官方 Tensor `A`，手算 `E` 与 `F` 的新 base offset。
6. 为什么 `make_tensor_like(gmem(_,0))` 要求对应 Shape 静态？
7. `zipped_divide`、slicing 和 `copy` 在 subtile 示例中分别负责什么？

完成后参阅：[自测参考答案](自测参考答案.md)。
