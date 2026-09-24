# SMEM 与 Copy Partitioning

> 官方示例：`sgemm_1.cu` 与 `sgemm_2.cu`
>
> 更新：2026-09-23

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

### 普通 direct copy 其实也会经过寄存器

对普通 load/store 路径（不是 `cp.async`），源码中的：

```cpp
copy(global_view, shared_view);
```

在机器指令层通常仍然需要：

```text
LDG：global memory → 临时寄存器
STS：临时寄存器 → shared memory
```

区别在于临时寄存器的生命周期：

```text
普通 direct copy：
  LDG 后立即 STS
  寄存器只用于连接相邻的 load/store

显式 tArA/tBrB staging：
  LDG 下一 tile → tArA/tBrB
  中间执行不依赖这些寄存器的当前 GEMM
  下一轮才 STS → shared memory
```

所以显式 register staging 的目的不是“global 不能直接写 shared”，而是：

- 为下一 K tile 提供与当前 shared tile 分离的缓冲区；
- 延长预取数据的生命周期；
- 为 global load 与当前计算的重叠创造机会；
- 允许 global 和 shared 两侧采用不同分区或 Layout。

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

### 普通 load 为什么也能称为“预取”

这里不要把“普通 load”理解成阻塞式函数调用。简单记忆：

> **后续计算必须与 load 的目标寄存器没有数据依赖，才可能与 load 重叠。**

```text
发出 LDG：
  内存请求开始，结果未来写入 tArA/tBrB

执行当前 GEMM：
  只读取 sA/sB 并更新 tCrC
  不读取 tArA/tBrB，所以没有数据依赖，可能继续执行

下一轮使用 tArA/tBrB：
  若 load 尚未完成，scoreboard 才在这里等待
```

如果紧接着执行依赖预取结果的指令：

```cpp
copy(copy_a, next_gA, tArA);
consume(tArA); // 立即读取 tArA
```

那么 `consume` 会因 RAW（Read After Write）数据依赖等待 LDG 完成，无法用中间
计算隐藏这次 load 延迟。

因此：

```text
普通 LDG：
  没有显式 commit/wait
  依赖由硬件 scoreboard 自动跟踪

cp.async：
  有独立异步 transaction group
  需要显式 commit/wait
```

`sgemm_2` 把下一 tile 提前读入寄存器，只是为 global-load 延迟与当前 GEMM
重叠创造机会；实际重叠程度仍取决于编译器调度和硬件执行。

### 寄存器不够时会发生什么

寄存器压力升高时，常见结果按影响理解：

1. **Occupancy 下降**
   每线程寄存器越多，一个 SM 同时容纳的 blocks/warps 越少。
2. **Spill 到 local memory**
   编译器可能将部分本应位于寄存器的值存入每线程 local-memory 地址空间。
3. **极端情况下 kernel 无法启动**
   若一个 block 的资源需求超过硬件上限，会出现
   `too many resources requested for launch`。

CUDA 的 local memory 名称虽然带有 “local”，但它不是片上寄存器：

```text
逻辑上：每线程私有
物理上：位于 device memory，通常经过 L1/L2 cache
```

spill 会新增：

```text
register → local memory 的 store
local memory → register 的 load
```

因此可能显著增加延迟和显存流量，抵消 register staging 的收益。

检查方式：

```bash
nvcc ... -Xptxas=-v
```

关注：

```text
Used N registers
spill stores
spill loads
```

也可以：

```bash
cuobjdump --dump-resource-usage binary
```

当前在 A100 SM80 上编译的 `sgemm_sm70` 实例使用约 `102～106`
registers/thread，`LOCAL:0`，表示当前构建没有发生 spill。重新编译到其他 GPU
架构后，寄存器数量和 spill 情况可能变化。

### 为什么 `sgemm_2` 没有 `cp_async_fence/wait`

`sgemm_2` 的两级搬运是：

```text
global → register：UniversalCopy，普通 load（非 cp.async）
register → shared：普通 store（非 cp.async）
```

它们都没有创建 `cp.async` transaction group，因此不需要：

```cpp
cp_async_fence();
cp_async_wait<0>();
```

但 shared memory 仍由整个 CTA 共享，所以必须使用：

```cpp
__syncthreads(); // 所有线程读完上一轮 smem，才能覆盖
copy(rmem, smem);
__syncthreads(); // 所有线程写完新 smem，才能开始 GEMM
```

真正使用 `cp.async` 的是后续 `sgemm_sm80.cu`，那里才需要对应的
commit/wait 协议。

## 9. 为什么 NT 使用 128-bit，TN 使用标量 Copy

`gemm_device` 是泛型 kernel，`copy_a/copy_b` 的实际类型由 Host 端传入。
因此 NT 与 TN 会实例化出不同的 kernel，而不是在同一个 kernel 中运行时切换
copy 宽度。

### NT

```text
A(M,K):(1,ldA) → M 连续
B(N,K):(1,ldB) → N 连续
```

其 Value Layout 为：

```text
4×1
```

同一线程取得的四个 M/N values 在内存中连续：

```text
4 float × 32 bit = 128 bit
```

所以可以使用：

```cpp
Copy_Atom<UniversalCopy<uint128_t>, T>
```

### TN

```text
A(M,K):(ldA,1) → K 连续
B(N,K):(ldB,1) → K 连续
```

但当前 `32×8` K-major Thread Layout 已将相邻 K 坐标分配给不同线程。单个线程
沿 M/N 重复负责的四个元素相隔 `ldA/ldB`：

```text
A(m,k), A(m+32,k), A(m+64,k), A(m+96,k)
```

这些地址不连续，不能直接复用 NT 的 `4×1 uint128_t` load。因此当前示例选择：

```cpp
Copy_Atom<UniversalCopy<T>, T>
Value Layout = 1×1
```

TN 并非天然不能使用 128-bit copy。若改成同一线程沿 K 持有连续的 `1×4`
values，并同步调整 Thread Layout、shared-memory destination Layout 和对齐
条件，也可以设计向量化 copy。

## 10. Copy 数据流不要混淆

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

## 11. 同步责任

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
