# SM70 与 SM80 演进

> 官方示例：`sgemm_sm70.cu`、`sgemm_sm80.cu`
>
> 更新：2026-09-23

四个版本的完整横向对比见：

- [CuTe GEMM 四个教程版本的优化演进](../四版本优化演进.md)

这一节不要求逐行记住流水线，而是观察同一 GEMM 数据流如何逐步优化：

```text
正确但串行的阶段
      ↓
global/register/shared 重叠
      ↓
shared/register/compute 重叠
      ↓
cp.async 多级 shared pipeline
      ↓
Tensor Core MMA
```

## 1. 四个官方示例的层次

| 示例 | Copy | Compute | Pipeline |
|---|---|---|---|
| `sgemm_1.cu` | 简单 `local_partition` | Thread Layout + `gemm` | 每轮完整同步 |
| `sgemm_2.cu` | `TiledCopy`，global→register→shared | `TiledMMA<UniversalFMA>` | 预取下一 global tile |
| `sgemm_sm70.cu` | register staging | register fragment FMA | shared 与 register 双层流水 |
| `sgemm_sm80.cu` | `cp.async` global→shared | SM80 MMA / UniversalFMA | 多级 shared pipeline |

前两个示例主要教学抽象，后两个示例开始展示架构相关流水线。

## 2. `sgemm_1`：阶段完全串开

```text
global → shared
wait
shared → compute
wait
下一轮
```

伪代码：

```cpp
for (k_tile) {
  copy(gmem, smem);
  wait_copy();
  __syncthreads();

  gemm(smem, accum);
  __syncthreads();
}
```

优点：

- 最容易验证；
- 数据生命周期清楚；
- 适合理解 partition。

缺点：

- global load、shared load 和 compute 几乎不重叠；
- 大量时间可能等待访存。

## 3. `sgemm_2`：global → register → shared

增加：

```text
tArA / tBrB：global load 的 register staging
```

预先加载第一个 tile：

```cpp
copy(copy_a, gmem_tile_0, tArA);
copy(copy_b, gmem_tile_0, tBrB);
```

循环中：

```text
1. 当前 register tile → shared
2. 下一 global tile → register
3. 使用 shared tile 计算
```

这让下一轮 global load 有机会与当前轮计算重叠。

## 4. `sgemm_sm70`：再增加 shared → register pipeline

SM70 示例同时维护三类数据：

```text
tArA/tBrB：global → register staging
sA/sB：   CTA shared-memory tile
tCrA/tCrB：shared → register MMA fragment
tCrC：    register accumulator
```

数据路径：

```text
global
  ↓
copy staging registers
  ↓
shared memory
  ↓
MMA operand registers
  ↓
FMA / MMA
  ↓
accumulator registers
```

K tile 内还会拆出更小的 `k_block`：

```cpp
auto K_TILE_MAX  = size<3>(tAgA);
auto K_BLOCK_MAX = size<2>(tCrA);
```

循环概念：

```text
计算当前 k_block
同时准备下一个 shared→register k_block
在适当位置准备下一 global K tile
```

简化时序：

```text
时间 →

G→R tile 1
R→S tile 0 | G→R tile 2
S→R block1 | GEMM block0
S→R block2 | GEMM block1
...
```

这里使用普通同步 copy，但通过手工安排操作顺序隐藏部分延迟。

## 5. `sgemm_sm80`：`cp.async`

SM80 示例的 global→shared Copy Atom：

```cpp
Copy_Atom<
    SM80_CP_ASYNC_CACHEALWAYS<uint128_t>,
    half_t>
```

数据可以直接：

```text
global → shared
```

而不需要经过普通 register staging。

copy 发起后：

```cpp
copy(copy_a, gmem_tile, smem_pipe);
cp_async_fence();
```

计算真正消费该 shared stage 前：

```cpp
cp_async_wait<N>();
__syncthreads();
```

两种同步职责不同：

```text
cp_async_wait：等待异步事务完成
__syncthreads：等待 CTA 内所有线程到达并安全共享 smem
```

## 6. 多级 Shared-memory Pipeline

SM80 示例的 shared Tensor 带 PIPE mode：

```text
sA: (BLK_M,BLK_K,PIPE)
sB: (BLK_N,BLK_K,PIPE)
```

例如：

```cpp
auto bP = Int<3>{};
```

表示三份 shared-memory stage。

预取阶段：

```cpp
for (int k_pipe = 0;
     k_pipe < K_PIPE_MAX-1;
     ++k_pipe)
{
  copy(gmem_tile, smem_stage[k_pipe]);
  cp_async_fence();
}
```

mainloop 同时进行：

```text
global → smem_pipe_write
smem_pipe_read → register
register → MMA
```

读写 stage 通过：

```cpp
smem_pipe_read
smem_pipe_write
```

循环轮换。

## 7. SM80 Tile 参数的选择依据

官方 Tensor Core TN 路径使用：

```cpp
auto bM = Int<128>{};
auto bN = Int<128>{};
auto bK = Int< 64>{};
auto bP = Int<  3>{};
```

这是一组教学和性能配置，不是 CuTe 根据 MMA Atom 唯一推导出的答案。

### `BLK_M=BLK_N=128`

一个 CTA 负责：

```text
C tile = 128×128
```

当前 TiledMMA 的逻辑 tile 是 `32×32×16`，所以 CTA tile 在 M/N 方向分别
重复：

```text
128/32 = 4 次
```

增大 M/N 可以提高 A/B 的 CTA 内复用，但也会增加每线程 accumulator、
寄存器压力和单个 CTA 的资源占用。

### `BLK_K=64`

基础 Tensor Core Atom 是：

```text
16×8×16
```

当前 TiledMMA 的 K tile 也是 16，因此：

```text
BLK_K / TiledMMA_K
= 64 / 16
= 4 个 k_blocks
```

较大的 K tile 可以减少完整 K 维上的 `k_tile` 循环次数，并摊薄 barrier 和
pipeline stage 轮换开销，但每级 shared-memory 占用会增大。

### `PIPE=3`

三份 shared-memory stage 表示：

```text
stage 0：当前正在计算
stage 1：下一 tile 已经加载完成
stage 2：再下一 tile 正在通过 cp.async 加载
```

更多 stage 更有机会隐藏 global-memory latency，但会消耗更多 shared memory。

### Shared-memory 容量

FP16 每个元素 2 bytes，A/B 的逻辑容量约为：

```text
2 matrices
× 128
× 64
× 3 stages
× 2 bytes
= 98304 bytes
= 96 KiB
```

因此源码使用动态 shared memory，并通过
`cudaFuncAttributeMaxDynamicSharedMemorySize` 请求对应容量。换 GPU 或修改
tile 后，必须重新检查每 block 的 shared-memory 上限。

### `TiledMMA=32×32×16` 的来源

```cpp
make_tiled_mma(
    SM80_16x8x16_F16F16F16F16_TN{},
    Layout<Shape<_2,_2>>{},
    Tile<_32,_32,_16>{});
```

拆解：

```text
基础 Atom：16×8×16，一个 warp=32 threads

Atom Layout 2×2：
  M：16×2 = 32
  N： 8×2 = 16
  线程：4 warps = 128 threads

自然线程覆盖：32×16×16

目标 Tile：32×32×16
  N 再扩大 2 倍
  由已有线程持有更多 value 覆盖
  线程数仍为 128
```

最终：

```text
CTA tile：      128×128×64
TiledMMA tile：  32× 32×16
重复次数：        4×  4× 4
```

### 实际调优时需要平衡

```text
M/N tile 大小
  ↔ A/B 复用
  ↔ accumulator 寄存器数量

K tile 大小
  ↔ K-loop 次数
  ↔ 每级 shared-memory 容量

Pipeline stage 数
  ↔ 延迟隐藏能力
  ↔ shared-memory 占用
```

因此这些参数是资源与流水的共同调优结果，不是只根据 Atom Shape 做一次乘法就能
唯一确定。

## 8. 为什么需要多个 stage

两级流水已经可以正确运行：

```text
stage 0：正在计算 tile k
stage 1：正在加载 tile k+1
```

但 tile k 计算结束后，必须保证 tile k+1 已完成。对于：

```cpp
K_PIPE_MAX = 2;
```

等待参数为：

```cpp
cp_async_wait<K_PIPE_MAX-2>(); // wait<0>：全部 group 完成
```

一个 global tile 的 load 只有“计算一个 tile”的时间用于隐藏延迟。如果 Tensor
Core 很快而 global load 尚未完成，就会产生 stall。

三级流水：

```text
stage 0：正在计算 tile k
stage 1：tile k+1 已提交，准备成为下一计算 tile
stage 2：正在异步加载 tile k+2
```

对于：

```cpp
K_PIPE_MAX = 3;
cp_async_wait<K_PIPE_MAX-2>(); // wait<1>
```

`wait<1>` 允许最新一个 group 继续 pending，只要求更老、即将被消费的 stage
完成。因此 tile k+2 从发起加载到真正消费，中间可以经过更多计算：

```text
加载 tile k+2
    ↓
计算 tile k
    ↓
计算 tile k+1
    ↓
消费 tile k+2
```

对比：

| Pipeline | 当前计算 | 下一 tile | 再下一 tile |
|---|---|---|---|
| 2 stages | 计算中 | 加载中 | 无空闲 stage |
| 3 stages | 计算中 | 已预取/等待 | 加载中 |

当前 FP16 配置中，每个 A+B stage 的逻辑容量约为：

```text
2 matrices × 128 × 64 × 2 bytes = 32 KiB
```

所以：

```text
2 stages：64 KiB
3 stages：96 KiB
4 stages：128 KiB
```

增加 stage 可以扩大 global-load 延迟的隐藏窗口，但代价是：

- 更多 shared memory；
- 更复杂的 stage 生命周期；
- 更多 barrier/wait 状态；
- 可能降低 occupancy。

因此三级不是正确性要求，也不是唯一答案，而是：

```text
延迟隐藏能力
    与
shared-memory 占用 / occupancy
```

之间的一种调优选择。

## 9. Shared → Register Copy

SM80 Tensor Core 路径使用：

```cpp
make_tiled_copy_A(s2r_atom_a, mma);
make_tiled_copy_B(s2r_atom_b, mma);
```

### `ldmatrix` 是什么

SM80 示例选择：

```cpp
Copy_Atom<SM75_U32x4_LDSM_N, half_t>
```

它包装的是 `ldmatrix` 类 shared-memory load。`ldmatrix` 本身不执行矩阵乘法，
只负责：

```text
一个 warp 协作读取 shared-memory matrix fragment
        ↓
按照 Tensor Core 规定的 lane/register 分布
写入每线程 A/B operand registers
```

`SM75_U32x4_LDSM_N` 中：

```text
SM75：Turing 开始支持的 ldmatrix 指令族
U32： 每个目标寄存器为 32 bit
x4：  每个 lane 得到 4 个 32-bit registers
N：   non-transposed 形式
```

因为一个 32-bit register 可以打包两个 FP16，所以每个 lane 最终得到：

```text
4 registers × 2 FP16/register = 8 个 FP16 values
```

`ldmatrix.x4` 是 warp cooperative 指令，不能理解为 32 个互不相关的普通
`ld.shared`。

### 为什么使用 `make_tiled_copy_A/B`

```cpp
make_tiled_copy_A(s2r_atom_a, mma);
make_tiled_copy_B(s2r_atom_b, mma);
```

它会读取 TiledMMA 的：

```text
LayoutA_TV
LayoutB_TV
```

并构造对应的 shared→register TiledCopy。

### `retile_D` 的重点

```cpp
Tensor tXsA = s2r_thr_copy_a.partition_S(sA);
Tensor tXrA = s2r_thr_copy_a.retile_D(tCrA);
```

`tCrA` 已经是当前 lane 私有的 MMA register fragment，所以不需要再次按线程
切分。真正需要解决的是：

```text
ldmatrix 输出的第 0、1、2、3... 个 value
分别应该写入 tCrA 的哪个 MMA fragment register slot？
```

`retile_D` 建立的就是：

```text
Copy Atom 的 CPY value 编号
        ↓
MMA 的 A/B fragment register 编号
```

`tXrA` 与 `tCrA` 使用同一批底层寄存器：

```text
tXrA：ldmatrix 写寄存器时使用的编号
tCrA：Tensor Core 读取寄存器时使用的编号
```

所以：

```cpp
copy(s2r_atom_a, tXsA, tXrA); // 按 ldmatrix 输出顺序写寄存器
gemm(mma, tCrA, tCrB, tCrC);  // 按 MMA fragment 顺序读同一批寄存器
```

`retile_D` 不分配存储，也不搬数据，只负责保证 `ldmatrix` 输出的 N 个寄存器值
落入 MMA 期望的 fragment 槽位。

### `tXsA_p / tXsB_p` 的 Shape

完整 shared source view：

```cpp
Tensor tXsA = s2r_thr_copy_a.partition_S(sA);
Tensor tXsB = s2r_thr_copy_b.partition_S(sB);
```

当前配置实际打印：

```text
tXsA: ((_8,_1),_4,_4,(_1,_3))
tXsB: ((_8,_1),_4,_4,(_1,_3))
```

按各 mode 的 size 简化：

```text
tXsA/tXsB = (CPY=8, MMA_M/N=4, MMA_K=4, PIPE=3)
```

来源：

```text
CPY=8：
  ldmatrix.x4 每个 lane 输出 4 个 32-bit registers
  每个 register 打包 2 个 FP16
  所以共有 8 个 FP16 values

MMA_M/N=4：
  CTA M/N=128，TiledMMA M/N=32
  128/32=4

MMA_K=4：
  BLK_K=64，TiledMMA K=16
  64/16=4

PIPE=3：
  三个 shared-memory pipeline stages
```

固定当前读取 stage：

```cpp
Tensor tXsA_p = tXsA(_,_,_,smem_pipe_read);
Tensor tXsB_p = tXsB(_,_,_,smem_pipe_read);
```

最后的 PIPE mode 被切掉：

```text
tXsA_p: ((_8,_1),_4,_4)
tXsB_p: ((_8,_1),_4,_4)
```

简化为：

```text
(CPY=8, MMA_M/N=4, MMA_K=4)
```

所以 `tXsA_p/tXsB_p` 就是当前 `smem_pipe_read` stage 中，当前 lane 后续通过
`ldmatrix` 要读取的 shared-memory view。这个切片不复制或移动数据。

## 10. SM80 Tensor Core TiledMMA

官方 half TN 示例：

```cpp
TiledMMA mma =
    make_tiled_mma(
        SM80_16x8x16_F16F16F16F16_TN{},
        Layout<Shape<_2,_2>>{},
        Tile<_32,_32,_16>{});
```

### Tensor Core MMA Atom 是什么

```cpp
SM80_16x8x16_F16F16F16F16_TN
```

描述一条 warp-level Tensor Core MMA：

```text
协作范围：1 warp = 32 lanes
逻辑 Shape：M=16, N=8, K=16
数据类型：D/A/B/C 都是 FP16
```

数学语义：

```text
D(16×8) =
    A(16×16) × B(8×16)
  + C(16×8)
```

CuTe 仍采用 B 的 `(N,K)` 约定，所以 B 写成 `8×16`；传统矩阵视角相当于
`16×8`。

底层：

```text
PTX： mma.sync
SASS：HMMA
执行：Tensor Core
```

它与 `UniversalFMA` 的区别：

```text
UniversalFMA：
  一个线程处理一个标量乘加

SM80 MMA Atom：
  32 个 lanes 协作完成一个 16×8×16 矩阵乘加
```

### 每次 `gemm` 的实际入参 Shape

当前配置实际打印：

```text
tCrA: ((_2,_2,_2),_4,_4)
tCrB: ((_2,_2),   _8,_4)
tCrC: ((_2,_2),   _4,_8)
```

最后一维是 `MMA_K=4`。每轮：

```cpp
gemm(
    mma,
    tCrA(_,_,k_block),
    tCrB(_,_,k_block),
    tCrC);
```

固定 `k_block` 后：

```text
A: ((_2,_2,_2),_4)
   A_MMA_VALUES=8，MMA_M=4

B: ((_2,_2),_8)
   B_MMA_VALUES=4，MMA_N=8

C: ((_2,_2),_4,_8)
   C_MMA_VALUES=4，MMA_M=4，MMA_N=8
```

第一维是硬件 MMA 对当前 lane 规定的 fragment values：

```text
A 每 lane 每 Atom 需要 8 个 FP16 values
B 每 lane 每 Atom 需要 4 个 FP16 values
C 每 lane 每 Atom 持有 4 个 FP16 accumulator values
```

因此 A/B/C 的第一维大小不需要相同；它们分别由 MMA Atom 的
`LayoutA_TV/LayoutB_TV/LayoutC_TV` 决定。

理解：

```text
基础 Atom Shape：16×8×16
基础 Atom 线程：一个 warp，32 threads
AtomLayout：M/N 各 2 份
目标 TiledMMA：32×32×16
```

这里必须以打印出的 `TiledMMA` 和 `tile_shape(mma)` 为准，不要仅靠整数相乘
猜每线程 fragment。

### `ldmatrix` 与 Tensor Core 的分工

二者是前后两个阶段：

```text
ldmatrix：
  shared memory → A/B operand registers

Tensor Core MMA：
  A/B operand registers + C accumulator registers
  → 更新 C accumulator registers
```

所以 SM80 Tensor Core 并不会直接读取普通 shared-memory 地址。完整路径为：

```text
global
  --cp.async-->
shared
  --ldmatrix-->
A/B register fragment
  --mma.sync / HMMA-->
C register accumulator
```

三类指令各自负责：

```text
cp.async：global → shared
ldmatrix：shared → MMA operand registers
mma.sync：Tensor Core 计算
```

## 11. Swizzled Shared Layout

SM80 示例使用：

```cpp
composition(
    Swizzle<3,3,3>{},
    Layout<Shape<_8,Shape<_8,_8>>,
           Stride<_8,Stride<_1,_64>>>{});
```

然后：

```cpp
tile_to_shape(swizzle_atom,
              make_shape(bM,bK,bP));
```

目的：

- 匹配 128-bit global→shared copy；
- 匹配 `ldmatrix` shared→register load；
- 降低 shared-memory bank conflict；
- 扩展出 PIPE stage。

现阶段不必手算完整 Swizzle，先理解它同时服务于 copy 和 MMA 两侧的访问要求。

## 12. 同一时刻的数据

在成熟 mainloop 的某个时刻，可能同时存在：

```text
K tile k+1：global → shared，异步加载
K tile k：  shared → register
K block k-1：register MMA compute
```

这就是流水线的核心，而不是简单地“多申请几块 shared memory”。

## 13. 演进中不变的部分

无论 SM70 还是 SM80，以下逻辑不变：

```text
完整 Tensor
  → CTA tile
  → copy partition
  → shared tile
  → MMA partition
  → register accumulator
  → epilogue
```

变化的是：

- Copy Atom；
- MMA Atom；
- shared Layout；
- pipeline stage 数；
- wait/barrier 协议；
- 每线程 fragment 布局。

这也是 CuTe 抽象的价值：数据流框架保持稳定，架构细节由类型和 Layout 替换。

## 14. 不要忽略边界

这些官方基础示例假设 tile 整除问题尺寸。实际 kernel 必须处理：

- M/N 边界；
- K 尾块；
- 越界 global load；
- 无效 shared value 的补零；
- epilogue 越界 store。

下一章 Predication 专门处理这些问题。

## 本节完成标准

不要求背流水线代码，但应能画出：

```text
SM70：
global → register → shared → register → compute

SM80：
global --cp.async--> multistage shared
       → register → Tensor Core
```

并能解释每一级存储的生命周期和同步责任。

## 官方资料

- [CuTe GEMM Tutorial](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0x_gemm_tutorial.html)
- [sgemm_sm70.cu](https://github.com/NVIDIA/cutlass/blob/main/examples/cute/tutorial/sgemm_sm70.cu)
- [sgemm_sm80.cu](https://github.com/NVIDIA/cutlass/blob/main/examples/cute/tutorial/sgemm_sm80.cu)
