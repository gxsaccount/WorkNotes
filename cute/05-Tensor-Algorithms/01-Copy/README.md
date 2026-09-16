# copy

> 官方对应：`include/cute/algorithm/copy.hpp`
>
> 更新：2026-09-16

`copy` 把源 Tensor 的逻辑元素复制到目标 Tensor。最重要的不是记住函数名，
而是理解它的行为由参数类型决定。

## 1. 两类主要接口

### 默认分派

```cpp
template <class SrcEngine, class SrcLayout,
          class DstEngine, class DstLayout>
CUTE_HOST_DEVICE
void
copy(Tensor<SrcEngine, SrcLayout> const& src,
     Tensor<DstEngine, DstLayout>      & dst);
```

调用：

```cpp
copy(src, dst);
```

CuTe 根据源、目标 Tensor 类型选择默认实现。

### 显式指定 Copy Atom

```cpp
template <class... CopyArgs,
          class SrcEngine, class SrcLayout,
          class DstEngine, class DstLayout>
CUTE_HOST_DEVICE
void
copy(Copy_Atom<CopyArgs...>       const& copy_atom,
     Tensor<SrcEngine, SrcLayout> const& src,
     Tensor<DstEngine, DstLayout>      & dst);
```

调用：

```cpp
copy(copy_atom, src, dst);
```

`Copy_Atom` 用来覆盖默认策略，显式指定基础搬运操作。它可能代表普通 load/store，
也可能对应架构相关的 copy 指令。

## 2. 通用实现揭示了什么

官方文档用下面的简化实现说明基本语义：

```cpp
for (int i = 0; i < size(dst); ++i) {
  dst(i) = src(i);
}
```

### 2.1 按逻辑坐标遍历

`i` 是一维逻辑坐标，不是直接拿来当裸指针 offset：

```text
src(i) = src.engine[src.layout(i)]
dst(i) = dst.engine[dst.layout(i)]
```

因此：

```text
copy = 保持逻辑元素编号，分别使用两侧 Layout 寻址
```

### 2.2 一维坐标采用逻辑 column-major 顺序

对于层级化 Tensor，`tensor(i)` 会把自然数逻辑坐标转换为该 Tensor 的坐标，
按 CuTe 的逻辑 column-major 顺序遍历。它不等于沿物理地址连续递增。

### 2.3 Layout 可以不同

例如：

```text
src layout = (2,3):(1,2)
dst layout = (2,3):(3,1)
```

两者具有相同逻辑 shape，但一个按第一维连续，另一个按第二维连续。
`copy` 会把逻辑元素 `src(i)` 写到 `dst(i)`，从而完成布局转换。

## 3. 类型为什么能选择实现

Tensor 的静态类型可能包含：

- 源、目标元素类型；
- Engine 类型与 memory space；
- 静态 Shape 和 Stride；
- 对齐与可向量化信息；
- Copy Atom 的操作类型。

因此编译器可以在编译期判断：

1. 是否能使用架构专用指令；
2. 是否能把多个标量访问合并为向量访问；
3. 指令宽度是否与 Tensor 的元素组织兼容；
4. 源、目标 memory space 是否满足指令要求。

例如，global → shared 的 copy 在满足架构、大小和类型条件时，可能使用
`cp.async`；否则可以退回通用 copy。具体选择仍应以当前头文件实现和生成代码
为准。

## 4. Copy Atom 的 mode 约定

带 `Copy_Atom` 的 Tensor 通常写成：

```text
src: (V, Rest...)
dst: (V, Rest...)
```

- 最左侧 `V` 表示一次 atom 操作消费的 value mode；
- `Rest...` 表示需要重复执行 atom 的其余逻辑空间。

实现可以把 `Rest...` 分组为一维循环，对每个位置调用：

```cpp
copy_atom.call(src_v(_, i), dst_v(_, i));
```

所以可以把它理解为：

```text
外层算法：遍历 Rest...
内层 Atom：一次搬运 V 个逻辑 value
```

## 5. 并行性和同步语义

官方特别强调：`copy` 的并行范围与同步语义取决于参数类型。

### 可能的执行方式

- 单线程顺序 copy；
- 多线程协作 copy；
- thread block 或 cluster 范围的 copy；
- 同步 load/store；
- `cp.async` 等异步 copy；
- 更高层的流水化搬运。

### 两种同步不要混淆

#### 线程协作同步

若多个线程共同写 shared memory，在读取结果前通常要保证所有参与线程完成：

```cpp
copy(...);
__syncthreads();
// consume shared-memory data
```

#### 异步事务完成

若底层使用异步 copy，仅有线程 barrier 未必足够，还要执行与该指令或 pipeline
匹配的 commit/wait 操作。

正确顺序应由具体 Copy Atom、pipeline 和架构决定，不能机械地认为
“调用 `copy` 后加一个 `__syncthreads()` 就一定正确”。

#### 官方 GEMM 教程中的 `cp.async` 例子

下面是官方简单 mainloop 的核心顺序：

```cpp
for (int k_tile = 0; k_tile < K_TILE_MAX; ++k_tile)
{
  // 每个线程发起自己负责的 global -> shared copy。
  // 根据 Tensor 和 Copy 类型，它们可能被实现成 cp.async。
  copy(tAgA(_,_,k_tile), tAsA);
  copy(tBgB(_,_,k_tile), tBsB);

  cp_async_fence();    // 结束并提交当前这一组潜在的 cp.async
  cp_async_wait<0>();  // 等待此前提交的异步 copy 全部完成
  __syncthreads();     // 等待整个 block，确保所有线程写入的 smem 都可使用

  gemm(tCsA, tCsB, tCrC);

  // 所有线程读取完当前 smem tile 后，才允许下一轮覆盖它。
  __syncthreads();
}
```

三个同步操作解决的问题不同：

| 操作 | 解决的问题 |
|---|---|
| `cp_async_fence()` | 把当前线程此前发起的 `cp.async` 标记为一个完成组 |
| `cp_async_wait<0>()` | 等待当前线程此前提交的异步 copy 组完成 |
| `__syncthreads()` | 等待 block 内所有线程到达，并协调共享内存的跨线程使用 |

只写：

```cpp
copy(src, dst);
__syncthreads();
```

对于普通同步 load/store 可能足够；但当 `copy` 分派成 `cp.async` 时，
`__syncthreads()` 本身不负责等待该线程尚未完成的异步 copy 组。因此需要先
执行与 `cp.async` 对应的 fence/wait，再执行 block barrier。

循环末尾的第二个 `__syncthreads()` 也不能省略：否则某些跑得快的线程可能已经
开始下一轮 copy 并覆盖 shared-memory tile，而其他线程还在用它执行 `gemm`。

#### 怎么判断一次 `copy` 是同步还是异步

不能只看 `src`、`dst` 是 global/shared memory，也不能只看函数名 `copy`。
应沿着实际选中的 **copy policy / Copy Atom 类型** 判断。

| 调用或底层 Atom | 当前官方实现中的性质 | 完成方式 |
|---|---|---|
| `copy(src, dst)` | 默认走自动向量化的普通赋值，属于同步 copy | 当前线程返回时，它负责的 load/store 已按同步指令执行 |
| `copy(AutoCopyAsync{}, src, dst)` | 满足 SM80+、gmem → smem、类型及宽度条件时选 `cp.async`，否则回退到 `UniversalCopy` | 按 `cp.async` 路径配套 fence/wait；回退时这些操作为空或无待处理事务 |
| `Copy_Atom<UniversalCopy<...>>` | 同步 | 不需要 `cp_async_wait` |
| `Copy_Atom<SM80_CP_ASYNC_...>` | 异步 `cp.async` | `cp_async_fence()` + `cp_async_wait<N>()`，跨线程消费时再加 barrier |
| SM90 TMA / bulk-copy Atom | 异步，但不是 SM80 `cp.async` 协议 | 使用该 TMA/pipeline 的 mbarrier、transaction barrier 或 wait API |

例如，下面两个 TiledCopy 都叫 `copy`，但同步语义不同：

```cpp
using SyncAtom =
    Copy_Atom<UniversalCopy<uint128_t>, Element>;

using AsyncAtom =
    Copy_Atom<SM80_CP_ASYNC_CACHEALWAYS<uint128_t>, Element>;

auto sync_copy  = make_tiled_copy(SyncAtom{},  thr_layout, val_layout);
auto async_copy = make_tiled_copy(AsyncAtom{}, thr_layout, val_layout);

copy(sync_copy,  src, dst);  // 同步 load/store
copy(async_copy, src, dst);  // 发起 cp.async
```

`TiledCopy` 本身只是线程和值的铺排；真正决定指令性质的是它内部包装的
`CopyAtom`。

实际工程中按下面三层确认：

1. **先看构造代码**：是否显式使用 `AutoCopyAsync`、`SM80_CP_ASYNC_*`、
   TMA 或 pipeline copy；
2. **再看 Atom/Traits 定义**：其 `copy` 最终调用普通赋值、`UniversalCopy`、
   `cp.async`，还是 TMA 指令；
3. **最后检查生成代码**：用编译器输出或反汇编确认是否出现
   `CPASYNC`、`cp.async`、`cp.async.bulk` 等目标指令。

不要编写“运行时判断它是不是异步，再决定要不要 wait”的逻辑。同步协议应当与
所选 Copy Atom/pipeline 一起在代码结构中确定。若使用 `AutoCopyAsync` 这种
允许回退的 policy，则按异步路径写 fence/wait；同步回退路径不会产生待等待的
异步事务。

官方 GEMM 示例在普通 `copy` 后仍写 `cp_async_fence/wait`，注释中称其为
“potential `cp.async`”。这是为了让示例的同步结构兼容潜在异步实现；判断自己
的 kernel 时，仍应以实际 Copy Atom 和当前版本头文件为准。

## 6. 自动向量化的直觉

若源、目标 Layout 和对齐信息能证明相邻元素可安全合并，CuTe 可以把多个窄访问
重解释为更宽的向量访问：

```text
4 × 32-bit load/store
        ↓
1 × 128-bit load/store
```

向量化必须同时满足：

- 源和目标都存在足够长的共同连续向量；
- 对齐满足宽访问要求；
- 总 bit 数合法；
- 不跨越 Tensor 的逻辑边界；
- 不因 stride、broadcast 或 alias 破坏语义。

静态 Layout 的价值之一，就是让这些条件能够在编译期证明。

## 7. 常见错误

### 错误 1：只比较 `size`

`size(src) == size(dst)` 是必要的逻辑条件，但显式 Copy Atom 还可能要求 rank、
value mode、memory space、对齐和指令宽度兼容。

### 错误 2：认为 copy 后一定可见

多线程协作或异步 copy 需要调用方完成相应同步。

### 错误 3：把逻辑连续当成物理连续

`tensor(i)` 按逻辑顺序遍历；只有 Layout 证明物理连续时才能安全向量化。

### 错误 4：忽略目标别名

若目标 Layout 让多个逻辑坐标映射到同一地址，copy 会产生 scatter 歧义或重复
写。调用者不应依赖未定义的写入顺序。

## 8. 从普通 copy 到 TiledCopy

```text
copy(src, dst)
  ↓ 理解默认逻辑语义
copy(copy_atom, src, dst)
  ↓ 理解单条基础 copy 操作
TiledCopy
  ↓ 把 copy 分配给 thread × value
thr_copy.partition_S / partition_D
  ↓ 得到每线程源、目标 Tensor
copy(thr_copy, thread_src, thread_dst)
```

本节重点是前两层。线程分配与 tiled copy 应结合后续 GEMM 实例学习。

## 9. 自测

1. `copy(src, dst)` 为什么能在两个不同 stride 的 Tensor 之间搬运？
2. `src(i)` 中的 `i` 是物理 offset 吗？
3. `Copy_Atom` 的 `V` mode 表示什么？
4. 为什么 `copy` 返回不代表异步事务已经完成？
5. 自动向量化至少需要证明哪些条件？

## 官方资料

- [CuTe Tensor Algorithms：copy](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/04_algorithms.html#copy)
- [copy.hpp](https://github.com/NVIDIA/cutlass/blob/main/include/cute/algorithm/copy.hpp)
