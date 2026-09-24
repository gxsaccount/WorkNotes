# Elementwise Algorithms

> 官方对应：`axpby.hpp`、`fill.hpp`、`clear.hpp`
>
> 更新：2026-09-16

这一节学习三个简单但常用的 Tensor 算法：

```text
axpby: y = alpha * x + beta * y
fill:  tensor[:] = value
clear: tensor[:] = value_type{}
```

它们也是理解 CuTe 通用算法设计的最小样本：按逻辑一维坐标遍历，并允许 Engine
提供更专门的实现。

## 1. axpby

名称来自：

```text
Alpha times X Plus Beta times Y
```

接口：

```cpp
axpby(alpha, x, beta, y);
```

逐元素语义：

```cpp
y(i) = alpha * x(i) + beta * y(i);
```

### predicate

当前官方接口还接受可选 predicate：

```cpp
axpby(alpha, x, beta, y, pred);
```

语义：

```cpp
if (pred(i)) {
  y(i) = alpha * x(i) + beta * y(i);
}
```

默认 predicate 恒为 true。

### `beta == 0` 优化

当前实现会先判断 `beta` 是否为零。若为零：

```cpp
y(i) = alpha * x(i);
```

而不会先读取旧的 `y(i)`。

这不仅减少一次读取，也避免在数学上不需要旧值时传播其中可能存在的无效值。
对复数 `beta`，实部和虚部都为零才视为零。

### Shape 前提

通用循环以 `size(x)` 为边界，并访问相同逻辑编号的 `y(i)` 与 `pred(i)`。
调用者必须保证这些 Tensor 的逻辑元素可正确配对，不能依赖算法替你修正不兼容
Shape。

## 2. fill

接口：

```cpp
fill(tensor, value);
```

默认语义：

```cpp
for (int i = 0; i < size(tensor); ++i) {
  tensor(i) = value;
}
```

与 `copy` 一样，遍历的是逻辑一维坐标，再由 Tensor Layout 完成实际寻址。

### Engine 专用分派

当前实现优先尝试：

```cpp
fill(tensor.data(), value);
```

若底层 data/engine 存在更专门的 `fill`，就使用它；否则回退到逐逻辑元素赋值。

这说明 CuTe 算法常见的设计方式：

```text
优先选择可用的专门实现
       ↓ 不可用
回退到通用 Tensor 循环
```

## 3. clear

接口：

```cpp
clear(tensor);
```

当前实现本质上是：

```cpp
using T = typename Tensor<Engine, Layout>::value_type;
fill(tensor, T{});
```

因此 `clear` 的准确含义是：

```text
把每个逻辑元素赋值为该 value_type 的值初始化结果
```

对常见数值类型，这就是数值零。

它不表示：

- 释放 Tensor；
- 清空底层内存分配；
- 对任意字节对象执行 `memset(..., 0, ...)`；
- 自动处理线程间同步。

## 4. 常用组合

### 4.1 初始化 accumulator

```cpp
clear(accum);
gemm(A, B, accum);
```

得到纯乘积：

```text
accum = A * B
```

### 4.2 predicated load 前补零

```cpp
clear(tile);
copy_if(pred, src, tile);
```

false predicate 对应的位置保留 clear 写入的零。

### 4.3 epilogue 线性组合

```cpp
axpby(alpha, accum, beta, output);
```

对应常见 GEMM epilogue：

```text
output = alpha * accum + beta * output
```

实际高性能 CUTLASS epilogue 会有更完整的线程映射、类型转换和向量化机制，但
数学关系相同。

## 5. 并行与同步注意事项

这些 API 本身不意味着“所有线程共同处理整个 Tensor”。

在典型 kernel 中，每个线程传入的是自己已经 partition 后的 Tensor：

```text
完整 Tensor
   ↓ thread partition
每线程 Tensor
   ↓
fill / clear / axpby
```

若多个线程会读取彼此写入的 shared-memory 结果，调用者仍需在正确位置同步。

## 6. 常见错误

### 错误 1：把 clear 当作内存释放

`clear` 只写逻辑元素。

### 错误 2：假设 clear 一定等于按字节清零

准确语义是 `value_type{}`，实现通过 `fill` 完成。

### 错误 3：忽略 predicate false 时 y 保持不变

predicated `axpby` 只更新 predicate 为真的元素。

### 错误 4：不同线程重复写同一元素

先保证 partition 无冲突，再调用逐元素算法。

### 错误 5：把 API 循环当成性能结论

源码中的通用循环可能被静态展开，也可能由更专门的实现替代；应结合模板实例和
生成代码判断真实性能。

## 7. 自测

1. `axpby` 的数学语义是什么？
2. `beta == 0` 时为什么不必读取旧 `y`？
3. predicated `axpby` 遇到 false 时会怎样？
4. `fill` 为什么可能不走通用元素循环？
5. `clear(tensor)` 精确地填入什么值？
6. 怎样用 `clear + copy_if` 实现越界位置补零？

## 官方资料

- [CuTe Tensor Algorithms：axpby / fill / clear](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/04_algorithms.html#axpby)
- [axpby.hpp](https://github.com/NVIDIA/cutlass/blob/main/include/cute/algorithm/axpby.hpp)
- [fill.hpp](https://github.com/NVIDIA/cutlass/blob/main/include/cute/algorithm/fill.hpp)
- [clear.hpp](https://github.com/NVIDIA/cutlass/blob/main/include/cute/algorithm/clear.hpp)
