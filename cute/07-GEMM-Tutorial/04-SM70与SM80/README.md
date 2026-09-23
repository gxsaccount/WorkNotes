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

## 7. 为什么需要多个 stage

单 stage：

```text
加载完成后才能计算
计算完成后才能重新加载
```

多 stage：

```text
stage 0 正在计算
stage 1 已经准备好
stage 2 正在异步加载
```

目标是让：

```text
计算单元忙碌时，内存系统也在工作
```

代价是：

- 更多 shared memory；
- 更复杂的 stage 生命周期；
- 更多 barrier/wait 状态；
- 可能降低 occupancy。

## 8. Shared → Register Copy

SM80 Tensor Core 路径使用：

```cpp
make_tiled_copy_A(s2r_atom_a, mma);
make_tiled_copy_B(s2r_atom_b, mma);
```

它让 shared→register copy 的目标布局与 TiledMMA fragment 对齐。

```cpp
Tensor tXsA = s2r_thr_copy_a.partition_S(sA);
Tensor tXrA = s2r_thr_copy_a.retile_D(tCrA);
```

含义：

```text
tXsA：按 S2R Copy Atom 分区的 shared source
tXrA：同一 copy 的 register destination，
      但底层存储就是 MMA fragment tCrA
```

`retile_D` 不创建第二份 fragment，而是用 Copy Atom 的目标视角重新解释已有
MMA fragment。

## 9. SM80 Tensor Core TiledMMA

官方 half TN 示例：

```cpp
TiledMMA mma =
    make_tiled_mma(
        SM80_16x8x16_F16F16F16F16_TN{},
        Layout<Shape<_2,_2>>{},
        Tile<_32,_32,_16>{});
```

理解：

```text
基础 Atom Shape：16×8×16
基础 Atom 线程：一个 warp，32 threads
AtomLayout：M/N 各 2 份
目标 TiledMMA：32×32×16
```

这里必须以打印出的 `TiledMMA` 和 `tile_shape(mma)` 为准，不要仅靠整数相乘
猜每线程 fragment。

## 10. Swizzled Shared Layout

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

## 11. 同一时刻的数据

在成熟 mainloop 的某个时刻，可能同时存在：

```text
K tile k+1：global → shared，异步加载
K tile k：  shared → register
K block k-1：register MMA compute
```

这就是流水线的核心，而不是简单地“多申请几块 shared memory”。

## 12. 演进中不变的部分

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

## 13. 不要忽略边界

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
