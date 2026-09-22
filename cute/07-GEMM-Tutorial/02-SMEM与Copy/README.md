# SMEM 与 Copy Partitioning

> 官方示例：`sgemm_1.cu` 与 `sgemm_2.cu`
>
> 更新：2026-09-21

CTA 已经通过 `local_tile` 得到：

```text
gA: (BLK_M,BLK_K,k)  // A 的 tile 内坐标 + K tile 编号
gB: (BLK_N,BLK_K,k)  // B 的 tile 内坐标 + K tile 编号
gC: (BLK_M,BLK_N)    // 当前 CTA 的输出 tile
```

其中小写 `k` 是完整 K 维除以 `BLK_K` 后留下的 Rest mode。mainloop 使用
`k_tile` 对它进行切片：

```cpp
gA(_,_,k_tile);
gB(_,_,k_tile);
```

本节继续解决：

```text
一个 CTA 内的线程怎样协作，
把一轮 K tile 从 global memory 搬到 shared memory？
```

## 1. Shared-memory Tensor

基础示例定义：

```cpp
auto sA_layout = make_layout(make_shape(bM, bK));
auto sB_layout = make_layout(make_shape(bN, bK));
```

然后分配 shared memory：

```cpp
__shared__ TA smemA[cosize_v<ASmemLayout>];
__shared__ TB smemB[cosize_v<BSmemLayout>];

Tensor sA =
    make_tensor(make_smem_ptr(smemA), sA_layout); // (BLK_M,BLK_K)

Tensor sB =
    make_tensor(make_smem_ptr(smemB), sB_layout); // (BLK_N,BLK_K)
```

为什么使用 `cosize`：

```text
size   = Layout 的逻辑元素数
cosize = 覆盖 Layout 所有输出 offset 所需的存储范围
```

带 padding 或 swizzle 的 Layout 可能存在：

```text
cosize(layout) > size(layout)
```

因此底层数组容量应按 `cosize` 准备。

## 2. Shared Layout 的要求

官方基础 kernel 检查：

```text
sA shape = (BLK_M,BLK_K)
sB shape = (BLK_N,BLK_K)
```

Layout 可以是：

- M/N-major；
- K-major；
- 带 padding；
- swizzled。

只要满足逻辑 Shape，并能让 global store 和 MMA load 高效即可。

例如 TN 版本将简单 K-major 改为：

```cpp
auto sA =
    make_layout(
        make_shape(bM,bK),
        make_stride(Int<1>{}, bM+Int<1>{}));
```

`+1` padding 的目的是改变相邻 K 列的 shared-memory 起点，降低某些访问模式中的
bank conflict。

## 3. 最简单的 copy Thread Layout

`sgemm_1.cu` 使用：

```cpp
auto tA =
    make_layout(make_shape(Int<32>{}, Int<8>{}));

auto tB =
    make_layout(make_shape(Int<32>{}, Int<8>{}));
```

以 A 为例：

```text
A tile        = 128×8
thread layout =  32×8
```

Thread Layout 在 A 的 `(M,K)` 坐标上重复：

```text
M：128 / 32 = 4 values/thread
K：  8 /  8 = 1 value/thread
```

所以每个线程得到：

```text
(THR_M,THR_K) = (4,1)
```

线程总数：

```text
32 * 8 = 256 threads
```

## 4. 对 global 与 shared 使用相同 partition

```cpp
Tensor tAgA =
    local_partition(gA, tA, threadIdx.x);

Tensor tAsA =
    local_partition(sA, tA, threadIdx.x);
```

结果：

```text
tAgA: (THR_M,THR_K,k)
tAsA: (THR_M,THR_K)
```

同一个 `tA` 同时作用于 gA 和 sA，因此逻辑位置一一对应：

```cpp
copy(tAgA(_,_,k_tile), tAsA);
```

对每个线程来说，就是把自己负责的 global values 写到 shared-memory 中相同的
逻辑位置。

### 命名法

```text
tAgA
││└─ A matrix
│└── global memory
└─── partition pattern tA

tAsA
  └─ tA pattern applied to shared-memory A
```

看到：

```cpp
copy(tAgA, tAsA);
```

可以通过名称快速确认两侧使用相同 partition pattern。

## 5. `local_partition` 做了什么

与 `local_tile` 的区别：

```text
local_tile：
  固定 Rest mode，保留完整 tile

local_partition：
  固定 tile 内的 thread 位置，保留该线程反复负责的 values
```

它仍然只返回 view：

```text
不搬数据
不分配 shared memory
不执行同步
```

真正的数据搬运发生在 `copy`。

## 6. 从 Thread Layout 到 TiledCopy

`sgemm_2.cu` 使用：

```cpp
TiledCopy copyA =
    make_tiled_copy(
        Copy_Atom<UniversalCopy<uint128_t>, TA>{},
        Layout<Shape<_32,_8>>{},
        Layout<Shape< _4,_1>>{});
```

三个部分：

```text
Copy Atom：每次使用 128-bit copy
Thr Layout：32×8 个线程位置
Val Layout：每个线程一次处理 4×1 个 float
```

因为：

```text
4 float × 32 bit = 128 bit
```

若分区结果不能形成合法的 128-bit 向量，CuTe 可以在编译期报错。

## 7. `partition_S` 与 `partition_D`

```cpp
auto thr_copy_a = copyA.get_slice(threadIdx.x);

Tensor tAgA = thr_copy_a.partition_S(gA);
Tensor tAsA = thr_copy_a.partition_D(sA);
```

这里：

```text
partition_S：按 Copy Atom 的 source TV Layout 切源 Tensor
partition_D：按 Copy Atom 的 destination TV Layout 切目标 Tensor
```

不能总是假设 source 与 destination 的分区相同。某些硬件 copy 指令对两侧有不同
的 thread-value 映射。

结果第一维通常是：

```text
CPY = 一条 Copy Atom 消费的 value mode
```

例如 128-bit copy 四个 float：

```text
size<0>(tAgA) = size<0>(tAsA) = 4
```

## 8. `sgemm_2` 的 register staging

官方示例没有直接 global → shared，而是：

```text
global → register → shared
```

先创建每线程 register fragment：

```cpp
Tensor tArA = make_fragment_like(tAsA);
Tensor tBrB = make_fragment_like(tBsB);
```

预取第一个 K tile：

```cpp
copy(copy_a, tAgA(_,_,_,0), tArA);
copy(copy_b, tBgB(_,_,_,0), tBrB);
```

mainloop 中：

```cpp
copy(tArA, tAsA); // register → shared
copy(tBrB, tBsB);
```

同时预取下一轮：

```cpp
copy(copy_a, tAgA(_,_,_,k_tile_next), tArA);
copy(copy_b, tBgB(_,_,_,k_tile_next), tBrB);
```

于是形成最简单的重叠：

```text
shared 正在被 GEMM 消费当前 tile
register 预取下一 tile 的 global 数据
```

## 9. Copy 数据流不要混淆

```text
gA/tAgA：global-memory view
tArA：   当前线程 owning register fragment
sA/tAsA：shared-memory view
```

对应：

```text
copy(copy_a, tAgA, tArA)
  global → register

copy(tArA, tAsA)
  register → shared
```

`partition_S/D` 只决定访问位置，`copy` 才真正移动数据。

## 10. 同步责任

shared memory 是 CTA 内共享的：

```cpp
copy(..., tAsA);
copy(..., tBsB);
__syncthreads();
```

读取 sA/sB 前，需要保证所有线程写入完成。

下一轮覆盖 shared memory 前，也要保证上一轮计算已经读取完成：

```cpp
gemm(...);
__syncthreads();
```

若 copy 使用 `cp.async`，还需在 block barrier 前按异步协议 commit/wait。

## 本节完成标准

能够区分：

```text
gA：CTA 的 global tile
tAgA：当前线程的 global source view
tArA：当前线程的 register staging fragment
tAsA：当前线程的 shared destination view
sA：整个 CTA 的 shared tile
```

## 官方资料

- [CuTe GEMM Tutorial：SMEM 与 Copy Partitioning](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0x_gemm_tutorial.html)
- [sgemm_1.cu](https://github.com/NVIDIA/cutlass/blob/main/examples/cute/tutorial/sgemm_1.cu)
- [sgemm_2.cu](https://github.com/NVIDIA/cutlass/blob/main/examples/cute/tutorial/sgemm_2.cu)
