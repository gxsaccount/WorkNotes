# 04 Tensor

> 官方对应：`media/docs/cpp/cute/03_tensor.md`
>
> 官方基线：NVIDIA CUTLASS `main`，核对日期 2026-09-15
>
> 前置章节：[Layout](../02-Layout/02-Layout.md) 与 [Layout Algebra](../03-Layout-Algebra/03-Layout-Algebra.md)

Tensor 把前两章的整数映射真正应用到数据上：

```text
Tensor = Engine + Layout

tensor(coord)
  = engine[layout(coord)]
```

- `Layout` 定义逻辑坐标空间，并把坐标映射为 offset；
- `Engine` 保存或引用可随机访问的数据；
- `Tensor` 用 Layout 算出的 offset 访问 Engine。

因此，Tensor 不等于“连续显存数组”。它既可以引用 global memory、shared memory，也可以拥有寄存器数组；其迭代器甚至可以在访问时生成或变换数据。

## 推荐学习顺序

1. [Engine 与创建](01-Engine与创建/01-Engine与创建.md)
   - Tensor 的基本接口
   - Engine 与 tagged iterator
   - owning / nonowning Tensor
   - 元素访问和参数传递
2. [Tiling 与 Slicing](02-Tiling与Slicing/02-Tiling与Slicing.md)
   - Tensor 上的 Layout Algebra
   - `_` 切片语义
   - 新指针与新 Layout 如何组成 subtensor
   - 将任意 subtile 搬到寄存器
3. [Partitioning](03-Partitioning/03-Partitioning.md)
   - inner partition 与 `local_tile`
   - outer partition 与 `local_partition`
   - Thread-Value Layout

## 核心心智模型

### 1. Layout 只算 offset

```text
coord --Layout--> offset
```

### 2. Engine 决定 offset 作用于什么

```text
offset --Engine--> element/reference
```

### 3. Tensor 把二者组合

```text
coord --Tensor--> element/reference
```

这解释了为什么同一个算法可以面向不同存储空间和不同 Layout 编写。

## 三类操作不要混淆

| 操作 | 输入 | 结果 |
|---|---|---|
| 元素访问 | 完整坐标 | 一个元素或引用 |
| slicing | 坐标中含 `_` | 一个 subtensor |
| partitioning | tiling/composition，再 slicing | 某个并行实体负责的 subtensor |

其中：

```text
partitioning = 坐标重组 + slicing
```

它描述数据归属，不会自动执行 copy。

## 本章完成标准

学完后应能回答：

1. 为什么 Tensor 的输入参数通常应按引用传递？
2. tagged pointer 提供了什么额外信息？
3. owning Tensor 为什么要求静态 Shape 和静态 Stride？
4. `A(2,_)` 为什么返回 Tensor，而 `A(2,5)` 返回元素？
5. slicing 如何同时改变数据指针和 Layout？
6. `local_tile` 与 `local_partition` 分别保留哪部分坐标？
7. TV Layout 如何表达“线程 × 每线程 value → 数据坐标”？

## 官方资料

- [NVIDIA CuTe Tensors 文档](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/03_tensor.html)
- [NVIDIA/CUTLASS 官方 Markdown](https://github.com/NVIDIA/cutlass/blob/main/media/docs/cpp/cute/03_tensor.md)
- 主要头文件：`include/cute/tensor.hpp`
