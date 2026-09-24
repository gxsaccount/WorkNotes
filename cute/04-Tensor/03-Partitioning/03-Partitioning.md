# 03 Tensor Partitioning

> 官方对应：`03_tensor.md` 的 Partitioning a Tensor
>
> 更新：2026-09-15

## 1. 本节目标

学完本节后，应当能够：

1. 用“tiling/composition + slicing”解释 partitioning；
2. 区分 inner partition 与 outer partition；
3. 解释 `local_tile`、`outer_partition` 和 `local_partition`；
4. 读懂 Thread-Value Layout；
5. 判断 partition 结果表示 tile、rest，还是某线程持有的 values。

## 2. Partitioning 的统一定义

Tensor partitioning 不是一种独立的底层机制，而是：

```text
partitioning
  = composition 或 tiling
  + slicing
```

第一步重组坐标：

```text
完整 Tensor 坐标
    ↓
(tile 内坐标, tile/rest 坐标)
```

第二步固定某一组坐标：

```text
选择某个 tile
或
选择某个线程在所有 tile 中负责的位置
```

partitioning 只产生 view 和数据归属关系，本身不执行 copy。

## 3. 基础示例

```cpp
auto A = make_tensor(
    ptr,
    make_shape(8, 24));

auto tiler = Shape<_4,_8>{};

auto tiled_a =
    zipped_divide(A, tiler);
```

Shape 变化：

```text
A       : (8,24)
tiler   : (_4,_8)
tiled_a : ((_4,_8),(2,3))
```

可以把结果读成：

```text
第 0 顶层 mode：一个 4×8 tile 内的坐标
第 1 顶层 mode：tile 在完整 Tensor 中的位置
```

即：

```text
tiled_a((tile_m,tile_n), (rest_m,rest_n))
```

## 4. Inner Partition：保留 tile 内坐标

假设每个 CTA 负责一个 4×8 tile：

```cpp
auto cta_a = tiled_a(
    make_coord(_, _),
    make_coord(blockIdx.x, blockIdx.y));
```

这里：

- tile 坐标使用 `_` 保留；
- rest 坐标由 `blockIdx` 固定。

结果：

```text
cta_a Shape = (_4,_8)
```

它表示：

> 某个 CTA 负责的完整 tile。

之所以称为 inner partition，是因为它保留 division 结果中的内部 tile mode。

通用封装：

```cpp
inner_partition(tensor, tiler, coord);
```

常见别名：

```cpp
local_tile(tensor, tiler, coord);
```

所以：

```text
local_tile = inner_partition
```

`local_tile` 最常见的用法是在 CTA 级别，按 block coordinate 从完整 Tensor 中取得本 CTA 的 tile。

## 5. Outer Partition：固定 tile 内位置

另一种需求是：一个 4×8 tile 有 32 个位置，恰好交给 32 个线程，每个线程负责每个 tile 中的一个位置。

```cpp
auto thr_a = tiled_a(
    threadIdx.x,
    make_coord(_, _));
```

这里：

- `threadIdx.x` 固定 tile 内的一个逻辑位置；
- rest mode 使用 `_` 保留。

结果：

```text
thr_a Shape = (2,3)
```

它表示：

> 某个线程在所有 2×3 个 tile 中负责的元素。

之所以称为 outer partition，是因为它保留 division 结果中的外部 rest mode。

通用封装：

```cpp
outer_partition(tensor, tiler, coord);
```

## 6. Inner 与 Outer 对照

对：

```text
tiled_a = (tile, rest)
```

两类 partition 可以直接记成：

| 类型 | 固定 | 保留 | 典型含义 |
|---|---|---|---|
| inner partition | rest 坐标 | tile 坐标 | 某 CTA 的完整 tile |
| outer partition | tile 内坐标 | rest 坐标 | 某线程在所有 tile 中的位置 |

伪代码：

```cpp
inner = tiled_a(_, rest_coord);
outer = tiled_a(tile_coord, _);
```

“inner/outer”说的是保留 division 结果的哪一部分，不是 global/shared/register memory 的层级。

## 7. `local_partition`

官方还介绍了：

```cpp
local_partition(tensor, layout, idx);
```

它是一个 rank-sensitive 的 outer-partition 包装。

大致过程是：

```text
1. 接收线程 Layout
2. 用 Layout 的逆映射把线性 idx 转成线程坐标
3. 用该 Layout 的顶层 Shape 构造 tiler
4. 执行 outer partition
```

它允许用户用一个 Layout 明确描述线程如何排布：

```text
row-major threads
column-major threads
任意合法的线程坐标 Layout
```

然后用线性的 `threadIdx.x` 选择当前线程。

### `local_tile` 与 `local_partition`

| API | 常见输入坐标 | 保留内容 | 常见使用层级 |
|---|---|---|---|
| `local_tile` | block/CTA coordinate | 一个完整 tile | CTA |
| `local_partition` | thread index | 当前线程负责的部分 | thread |

二者名称相近，但问题不同：

```text
local_tile：
  “这个 CTA 拿哪一块？”

local_partition：
  “这一块或这个 Tensor 中，本线程拿哪些元素？”
```

## 8. Thread-Value Partitioning

更一般的线程分工不一定是“一线程一个值”。每个线程可能负责多个 values，且这些 values 在目标 Tensor 中可以有复杂排列。

CuTe 使用 TV Layout 表达：

```text
(Thread, Value) -> 目标数据坐标
```

官方示例：

```cpp
auto tv_layout =
    Layout<
        Shape<
            Shape<_2,_4>,
            Shape<_2,_2>>,
        Stride<
            Stride<_8,_1>,
            Stride<_4,_16>>>{};
```

按顶层 mode 配对后：

```text
Thread = (2,4):(8,1)
Value  = (2,2):(4,16)

tv_layout = (Thread, Value)
```

其逻辑 Shape 可概括为：

```text
(T8, V4)
```

含义是：

- 一共有 8 个线程逻辑位置；
- 每个线程获得 4 个 value 逻辑位置；
- Layout 输出 0 到 31 中的坐标，用于覆盖 4×8 数据。

## 9. 手算 TV Layout

将坐标写成：

```text
thread = (t0,t1), Shape = (2,4), Stride = (8,1)
value  = (v0,v1), Shape = (2,2), Stride = (4,16)
```

TV Layout 的输出为：

```text
logical_index
  = 8*t0 + 1*t1 + 4*v0 + 16*v1
```

线程的标量 id 会按 `(2,4)` 的自然序展开：

```text
tid -> (tid % 2, tid / 2)
```

value id 同理：

```text
vid -> (vid % 2, vid / 2)
```

例如线程 3：

```text
thread coord = (1,1)
thread base  = 8*1 + 1*1 = 9
```

四个 value 的贡献为：

```text
vid 0 -> 0
vid 1 -> 4
vid 2 -> 16
vid 3 -> 20
```

所以线程 3 负责的四个逻辑位置是：

```text
9, 13, 25, 29
```

这些是传给目标 Tensor Layout 的逻辑坐标，不应未经目标 Layout 映射就直接理解成最终物理地址。

## 10. TV Layout 应用于目标 Tensor

先构造任意 Layout 的 4×8 Tensor：

```cpp
auto A = make_tensor<float>(
    Shape<_4,_8>{},
    LayoutRight{});
```

再进行 composition：

```cpp
auto tv = composition(A, tv_layout);
```

概念链路：

```text
(thread,value)
    ↓ tv_layout
A 的逻辑坐标
    ↓ A.layout()
A 的最终 offset
```

因此：

```text
tv(thread,value)
```

直接表示指定线程的指定 value 对应的实际元素。

最后固定 thread mode：

```cpp
auto v = tv(threadIdx.x, _);
```

这里的 `threadIdx.x` 被当作整个 Thread mode `(2,4)` 的一维自然逻辑
index，而不是只对应其中的 `t0`：

```text
tid = threadIdx.x
(t0,t1) = (tid % 2, tid / 2)
```

第二个参数 `_` 保留的是完整 Value mode `(2,2)`，不是省略的
`threadIdx.y`。

如果 CUDA block 本身就是二维的 `blockDim=(2,4)`，也可以直接传入：

```cpp
auto v = tv(
    make_coord(threadIdx.x, threadIdx.y),
    _);
```

此时它与传入线性编号
`threadIdx.x + 2*threadIdx.y` 表示相同的 Thread 坐标。

结果：

```text
v Shape = (4)
```

它是当前线程持有的 4 个 values 的 Tensor view。

## 11. TV Layout 的价值

TV Layout 将两件事分离：

```text
目标 Tensor Layout：
  数据本身如何排布

TV Layout：
  线程和值如何映射到数据逻辑坐标
```

通过 composition，它们重新组合：

```text
(thread,value)
  -> 数据坐标
  -> 数据 offset
```

这种表达方式特别适合：

- MMA fragment 的线程分工；
- tiled copy 的线程和值分配；
- 一个线程持有多个非连续元素；
- 将硬件指令规定的数据归属编码成类型。

## 12. 用检查清单读懂 Partitioning

以本文两个例子直接作答。

### 例 1：`local_tile` 选择当前 CTA

```cpp
auto A = make_tensor(ptr, make_shape(8, 24));
auto tiled_a = zipped_divide(A, Shape<_4,_8>{});  // ((TileM,TileN),(RestM,RestN))

auto cta_a = tiled_a(
    make_coord(_, _),
    make_coord(blockIdx.x, blockIdx.y));
```

| 问题 | 本例答案 |
|---|---|
| 原 Tensor 的逻辑 Shape | `(8,24)` |
| tiler 的输入坐标 | FULL 的二维逻辑坐标 `(m,n)` |
| division 后的 mode | `mode-0=(4,8)` 是 tile 内坐标；`mode-1=(2,3)` 是 tile 位置 |
| slicing 固定什么 | 用 `(blockIdx.x,blockIdx.y)` 固定 rest mode |
| `_` 保留什么 | 完整的 `(4,8)` tile mode |
| 结果是什么 | 当前 CTA 对应的完整 tile |
| 是否已经 copy | 否，`cta_a` 只是 Tensor view |

因此：

```text
local_tile：不使用 threadIdx，先由 blockIdx 取得整个 CTA tile
```

### 例 2：TV Layout 选择当前线程的 values

```cpp
auto A = make_tensor<float>(
    Shape<_4,_8>{},
    LayoutRight{});

auto tv_layout =
    Layout<
        Shape<
            Shape<_2,_4>,
            Shape<_2,_2>>,
        Stride<
            Stride<_8,_1>,
            Stride<_4,_16>>>{};

auto tv = composition(A, tv_layout); // tv.layout = ((2,4),(2,2)):((2,8),(1,4))
auto v  = tv(threadIdx.x, _);
```

先把输入全部写成具体 Layout：

```text
A.layout  = (4,8):(8,1)

Thread    = (2,4):(8,1)
Value     = (2,2):(4,16)
tv_layout = (Thread,Value)
```

`tv_layout` 先产生 A 的逻辑 index：

```text
q = 8*t0 + t1 + 4*v0 + 16*v1
```

再由 `A.layout` 将 q 映射为最终 offset：

```text
(m,n) = (q % 4, q / 4)
offset = 8*m + n
```

所以这个 composition 的映射可写成：

```text
tv((t0,t1),(v0,v1))
  = A(8*t0 + t1 + 4*v0 + 16*v1)
```

进一步代入 `A.layout=(4,8):(8,1)`：

```text
q      = t1 + 4*(2*t0 + v0 + 4*v1)
(m,n)  = (t1, 2*t0 + v0 + 4*v1)
offset = 8*t1 + 2*t0 + v0 + 4*v1
```

因此 composition 后的 Layout 可写成：

```text
tv.layout = ((2,4),(2,2)):((2,8),(1,4))

Thread Layout = (2,4):(2,8)
Value Layout  = (2,2):(1,4)
```

这里：

- Thread Shape `(2,4)`：共有 8 个线程逻辑位置；
- Thread Stride `(2,8)`：改变 `t0/t1` 时，最终 offset 分别增加 `2/8`；
- Value Shape `(2,2)`：每个线程持有 4 个 value；
- Value Stride `(1,4)`：改变 `v0/v1` 时，最终 offset 分别增加 `1/4`。

| 问题 | 本例答案 |
|---|---|
| 原 Tensor 的 Shape / Layout | `(4,8)` / `(4,8):(8,1)` |
| TV Layout | `((2,4),(2,2)):((8,1),(4,16))` |
| TV Layout 的输入坐标 | `((t0,t1),(v0,v1)) = (thread,value)` |
| composition 后的 mode | Thread=`(2,4):(2,8)`；Value=`(2,2):(1,4)` |
| slicing 固定什么 | 用 `threadIdx.x` 固定 thread mode |
| `_` 保留什么 | `value Shape=(2,2)`，容量为 4 |
| 结果是什么 | 当前线程负责的 4 个 values 的 Tensor view |
| 是否已经 copy | 否，仍需后续 copy 或计算操作读取数据 |

例如 `threadIdx.x=3`：

```text
thread coord          = (1,1)
tv_layout 逻辑 index = [9,13,25,29]
A.layout 最终 offset  = [10,11,14,15]
```

以后遇到新的 partitioning 代码，也按这七项检查，但答案必须根据具体
Tensor、tiler、TV Layout 和 slicing 表达式重新计算。

## 13. 常见误区

### 误区 1：inner partition 是取“内存内部”

错误。inner 指保留 tiling 结果中的 tile mode。

### 误区 2：outer partition 返回 tile 外的数据

错误。它固定 tile 内坐标，并保留 rest mode，表示同一 tile 内位置在各 tile 中的集合。

### 误区 3：`local_partition` 只能表示一维线程顺序

错误。线性 thread id 可通过线程 Layout 的逆映射转成多维、row-major、column-major 或其他线程坐标。

### 误区 4：TV Layout 的输出就是字节地址

错误。它先产生目标 Tensor 的逻辑坐标，再由目标 Layout 映射到最终 offset。

### 误区 5：partitioning 自动把数据放进每个线程的寄存器

错误。它首先产生 view；是否加载到寄存器取决于后续 copy 或计算操作。

## 14. 本节自测

1. 为什么说 partitioning 是 tiling/composition 加 slicing？
2. 对 `tiled_a = (tile,rest)`，inner partition 固定和保留什么？
3. outer partition 固定和保留什么？
4. `local_tile` 与 `local_partition` 分别回答什么问题？
5. TV Layout 的两个输入 mode 各表示什么？
6. 官方 TV Layout 中，线程 3 的四个 value 逻辑位置是什么？
7. `composition(A, tv_layout)` 建立了哪两层映射？
8. `tv(threadIdx.x,_)` 是否已经把数据复制进寄存器？

完成后参阅：[自测参考答案](自测参考答案.md)。
