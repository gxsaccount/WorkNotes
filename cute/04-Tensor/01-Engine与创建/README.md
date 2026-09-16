# 01 Engine 与 Tensor 创建

> 官方对应：`03_tensor.md` 的 Fundamental operations、Tensor Engines、Tensor Creation 与 Accessing a Tensor
>
> 更新：2026-09-15

## 1. 本节目标

学完本节后，应当能够：

1. 用 `Engine + Layout` 解释一次 Tensor 访问；
2. 区分 tagged 与 untagged iterator；
3. 区分 owning 与 nonowning Tensor；
4. 根据数据所在位置选择 `make_tensor` 的构造方式；
5. 解释为什么泛型函数不应随意按值接收 Tensor。

---

## 2. Tensor 的基本接口

CuTe Tensor 提供与容器相似的访问接口：

```cpp
t.data();          // Engine 持有的 iterator
t.size();          // Tensor 的逻辑元素总数
t[coord];          // 按逻辑坐标访问
t(coord);          // 按逻辑坐标访问
t(c0, c1, ...);    // 等价于 t(make_coord(c0, c1, ...))
```

它也继承了 Layout 的层级查询方式：

```cpp
rank<I...>(t);
depth<I...>(t);
shape<I...>(t);
size<I...>(t);
layout<I...>(t);
tensor<I...>(t);
```

其中：

- `layout<I...>(t)` 取得对应 mode 的 Layout；
- `tensor<I...>(t)` 取得对应 mode 的 subtensor；
- `size(t)` 统计逻辑位置数，不等于底层分配跨度。

## 3. Engine 是什么

官方把 Engine 定义为 iterator 或数据数组的轻量包装。其核心接口近似：

```cpp
using iterator   = ...;
using value_type = ...;
using reference  = ...;

iterator begin();
```

通常不需要手写 Engine。调用 `make_tensor` 时，CuTe 会根据实参选择适当实现，例如：

```text
ArrayEngine<T,N>       owning，内部拥有 N 个元素
ViewEngine<Iter>       nonowning，可写 view
ConstViewEngine<Iter>  nonowning，只读 view
```

最重要的抽象不是这些具体类型名，而是：

> Engine 提供可以被 offset、解引用的随机访问对象。

所以 Engine 不一定只是裸指针。只要符合所需接口，它也可以表示经过包装、变换或按需生成的数据源。

## 4. Tensor 如何访问元素

Tensor 的访问逻辑可以简化为：

```cpp
template <class Coord>
decltype(auto) operator[](Coord const& coord) {
  return data()[layout()(coord)];
}
```

完整链路是：

```text
逻辑坐标 coord
    ↓
layout()(coord)
    ↓
相对 iterator 的 offset
    ↓
data()[offset]
    ↓
元素或元素引用
```

例如：

```text
Layout = (4,2):(2,1)
coord  = (3,1)

offset = 3*2 + 1*1 = 7
```

若 `data()` 指向 `float`，则 Tensor 最终访问的是：

```cpp
data()[7]
```

不要把 Layout 的输出直接说成字节地址。它通常是相对于 iterator 的元素 offset；具体地址运算由 iterator 的类型负责。

## 5. Tagged Iterator：给指针标记存储空间

任意满足要求的随机访问 iterator 都可以构造 Tensor。对于 CUDA 内存，CuTe 还允许为指针附加地址空间标签：

```cpp
make_gmem_ptr(ptr);     // global memory
make_gmem_ptr<T>(ptr);

make_smem_ptr(ptr);     // shared memory
make_smem_ptr<T>(ptr);
```

### 5.1 标签不做什么

tag 不会：

- 分配 global/shared memory；
- 把数据从一种存储空间搬到另一种；
- 改变裸指针所指向的地址；
- 自动执行同步。

### 5.2 标签提供什么

tag 把“这个 iterator 指向哪类存储空间”编码进类型，使算法可以：

1. 根据源和目的地址空间选择专用实现；
2. 在编译期检查某个操作的地址空间前提；
3. 区分普通 pointer、`gmem_ptr` 和 `smem_ptr`。

例如某些优化 copy 路径要求：

```text
source      = global memory
destination = shared memory
```

如果 Tensor 保留了地址空间标签，算法就有机会验证并分派到正确路径。

## 6. Nonowning Tensor

nonowning Tensor 是已有数据的 view，常用二参数形式构造：

```cpp
make_tensor(iterator, layout)
```

也可以直接给出用于构造 Layout 的 Shape 或 Shape + Stride：

```cpp
float* A = ...;

auto t0 = make_tensor(A, make_layout(Int<8>{}));
auto t1 = make_tensor(A, Int<8>{});
auto t2 = make_tensor(A, 8, 2);
```

对应 Layout 可理解为：

```text
t0: _8:_1
t1: _8:_1
t2:  8: 2
```

### 6.1 Global memory view

```cpp
auto g0 = make_tensor(make_gmem_ptr(A), Int<8>{});
auto g1 = make_tensor(make_gmem_ptr(A), 8);

auto g2 = make_tensor(
    make_gmem_ptr(A),
    make_shape(Int<8>{}, 16));

auto g3 = make_tensor(
    make_gmem_ptr(A),
    make_shape(8, Int<16>{}),
    make_stride(Int<16>{}, Int<1>{}));
```

nonowning Tensor 的 Layout 可以是静态、动态或混合的，因为它不负责分配数据，只负责解释已有地址。

### 6.2 Shared memory view

```cpp
auto smem_layout =
    make_layout(make_shape(Int<4>{}, Int<8>{}));

__shared__ float smem[
    decltype(cosize(smem_layout))::value];

auto col = make_tensor(make_smem_ptr(smem), smem_layout);

auto row = make_tensor(
    make_smem_ptr(smem),
    shape(smem_layout),
    LayoutRight{});
```

这里数组长度使用 `cosize(layout)`，因为底层存储必须覆盖 Layout 可能访问到的 offset 范围，而不仅仅是逻辑元素数量。

### 6.3 生命周期

nonowning Tensor 不拥有数据：

```text
复制 Tensor        -> 复制 view，不复制元素
销毁 Tensor        -> 不释放底层数据
底层数据先失效     -> Tensor 变成悬空 view
```

其生命周期安全规则与普通指针、span 或 view 类似。

## 7. Owning Tensor

owning Tensor 内部拥有一个类似 `std::array<T,N>` 的静态数组：

```cpp
auto r0 = make_tensor<float>(Shape<_4,_8>{});

auto r1 = make_tensor<float>(
    Shape<_4,_8>{},
    LayoutRight{});

auto r2 = make_tensor<float>(
    Shape<_4,_8>{},
    Stride<_32,_2>{});
```

这类 Tensor 常用于寄存器片段，因此也常简称 register-memory Tensor。

### 7.1 为什么必须全静态

owning Tensor 的容量是其 C++ 对象类型的一部分，类似：

```cpp
std::array<float, 32>
```

CuTe 不在 Tensor 内部做动态内存分配。因此，要在编译期确定所需数组容量，Layout 的 Shape 和 Stride 都必须是静态的。

特别注意，所需容量可能由 `cosize(layout)` 决定。即使：

```text
size(layout) = 32
```

一个带 padding 或空洞的 Layout 也可能要求更大的底层数组。

### 7.2 `make_tensor_like`

```cpp
auto r3 = make_tensor_like(r2);
```

它创建一个 owning Tensor：

- value type 与输入相同；
- Shape 与输入相同；
- 尝试保留输入的 stride 顺序；
- 结果不保证保留原 Layout 的 padding 数值。

官方示例中：

```text
input:  (_4,_8):(_32,_2)
like:   (_4,_8):(_8,_1)
```

二者 Shape 相同、连续方向的相对次序一致，但 `make_tensor_like` 为新寄存器数组生成了紧凑 Layout。

### 7.3 拷贝语义

owning Tensor 类似 `std::array`：

```text
复制 Tensor -> 深拷贝内部元素
销毁 Tensor -> 内部数组随对象一起销毁
```

这与 nonowning view 的浅拷贝语义完全不同。

## 8. 为什么函数参数通常按引用传递

泛型代码只看到 `Tensor` 类型时，不能先假定它一定是 view。

下面的写法可能很昂贵：

```cpp
template <class Tensor>
void foo(Tensor t);
```

因为：

- 若 `t` 是 nonowning Tensor，只复制了 view；
- 若 `t` 是 owning Tensor，可能深拷贝所有元素。

更稳妥的输入参数形式是：

```cpp
template <class Tensor>
void read_only(Tensor const& t);

template <class Tensor>
void mutate(Tensor& t);
```

具体算法若有意按值接收 view，应明确其类型约束，而不是依赖“所有 Tensor 都只是指针”的错误假设。

## 9. 三种坐标访问

构造一个层级 Tensor：

```cpp
auto A = make_tensor<float>(
    Shape<Shape<_4,_5>, _13>{},
    Stride<Stride<_12,_1>, _64>{});
```

可以使用自然坐标：

```cpp
A[make_coord(make_coord(m0, m1), n)] = value;
```

也可以使用 variadic `operator()`：

```cpp
A(m, n);
```

此时 `m` 可以是与第 0 个顶层 mode compatible 的标量坐标。Tensor 会沿用 Layout 的坐标归一化规则。

还可以使用标量自然序号：

```cpp
A[i];
```

但必须记住：

```text
A[i] = A.data()[A.layout()(i)]
```

不保证访问底层连续的第 `i` 个物理位置。只有当 Layout 的标量映射恰好为 `i -> i` 时，两者才相同。

## 10. 常见误区

### 误区 1：Tensor 的 `.size()` 就是底层数组长度

错误。`.size()` 是逻辑定义域大小；带空洞的 Layout 可能需要更大的 `cosize`。

### 误区 2：`make_gmem_ptr` 会把数据搬到显存

错误。它只给现有 iterator 添加类型标签。

### 误区 3：所有 Tensor 复制都很便宜

错误。owning Tensor 的复制可能深拷贝元素。

### 误区 4：register Tensor 可以用动态 Shape

错误。owning Tensor 需要编译期可确定的静态存储大小。

### 误区 5：`A[i]` 一定是地址连续遍历

错误。它按 Layout 的标量自然序进行映射。

## 11. 本节自测

1. Engine 与 Layout 各自负责什么？
2. `make_gmem_ptr` 会不会分配或搬运数据？
3. 为什么 nonowning Tensor 可以使用动态 Layout？
4. 为什么 owning Tensor 要求静态 Shape 和 Stride？
5. `size(layout)` 与 `cosize(layout)` 在分配存储时分别意味着什么？
6. 为什么泛型函数按值接收 Tensor 有潜在风险？
7. `make_tensor_like` 是否保证完全复制输入 Tensor 的 Stride？

完成后参阅：[自测参考答案](自测参考答案.md)。
