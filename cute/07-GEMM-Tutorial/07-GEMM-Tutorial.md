# 07 GEMM Tutorial

> 官方对应：`media/docs/cpp/cute/0x_gemm_tutorial.md`
>
> 官方基线：NVIDIA CUTLASS `main`，核对日期 2026-09-21
>
> 前置章节：[Tensor Algorithms](../05-Tensor-Algorithms/05-Tensor-Algorithms.md) 与
> [MMA Atom](../06-MMA-Atom/06-MMA-Atom.md)

这一章不再单独学习抽象，而是把前面的概念串成一条完整数据流：

```text
global memory
   │ CTA tile
   ▼
gA / gB / gC
   │ copy partition
   ▼
shared memory sA / sB
   │ MMA partition
   ▼
register fragments
   │ K-loop
   ▼
register accumulator
   │ epilogue
   ▼
global memory C
```

## 推荐学习顺序

1. [Full Tensors 与 CTA Partitioning](01-Full-Tensors与CTA/01-Full-Tensors与CTA.md)
   - `(M,K) × (N,K) → (M,N)`
   - M-major、N-major、K-major
   - `CtaTiler`
   - `local_tile`
2. [SMEM 与 Copy Partitioning](02-SMEM与Copy/02-SMEM与Copy.md)
   - shared-memory Tensor
   - `local_partition`
   - `TiledCopy`
   - global → register → shared
3. [Math Partitioning 与 Mainloop](03-Math与Mainloop/03-Math与Mainloop.md)
   - C tile 的线程分工
   - A/B 投影
   - accumulator fragment
   - K-loop、同步和 epilogue
4. [SM70 与 SM80 演进](04-SM70与SM80/04-SM70与SM80.md)
   - shared/register pipeline
   - `cp.async`
   - multistage shared memory
   - Tensor Core MMA

## 一句话理解每个层次

```text
ProblemShape：完整问题有多大
CtaTiler：一个 CTA 算多大
Copy partition：每个线程搬哪些数据
MMA partition：每个线程算哪些结果
Mainloop：沿 K 反复搬运并累加
Epilogue：把 accumulator 合并到 C
```

## 官方示例之间的关系

| 示例 | 重点 |
|---|---|
| `sgemm_1.cu` | 用普通 Thread Layout 解释最基本的 CTA、copy 和 math partition |
| `sgemm_2.cu` | 用 `TiledCopy`、`TiledMMA` 替换手工 Thread Layout |
| `sgemm_sm70.cu` | 增加 global→register→shared 与 shared→register 流水 |
| `sgemm_sm80.cu` | 使用 `cp.async`、多级 shared-memory pipeline 和 Tensor Core |

本地可运行副本及 CPU reference 检查见：

- [代码实验：官方 GEMM 示例与结果检查](代码实验/代码实验.md)
- [四个教程版本的优化演进与实测效果](四版本优化演进.md)

本章把 Layout、Tensor、Copy 和 MMA 组合成完整 GEMM kernel。

## 本章统一命名

CuTe 示例常使用三字符 Tensor 名：

```text
tAgA
││└─ A：矩阵 A
│└── g：global memory
└─── tA：copy partition pattern
```

常见前缀：

| 名称 | 含义 |
|---|---|
| `mA/mB/mC` | 完整矩阵 Tensor |
| `gA/gB/gC` | 当前 CTA 对应的 global-memory tile |
| `sA/sB` | shared-memory tile |
| `tAgA/tAsA` | copy partition 后的每线程 source/destination view |
| `tCsA/tCsB/tCgC` | math partition 后的每线程 view |
| `tArA/tBrB` | copy pipeline 使用的 register fragment |
| `tCrA/tCrB/tCrC` | MMA 使用的 register fragment/accumulator |

## 最重要的区分

```text
local_tile / partition_*：
  只创建 Tensor view，不搬运、不计算

copy：
  真正搬运数据

gemm：
  真正执行乘加

barrier / wait：
  保证被搬运的数据已经可以安全消费
```

## 本章边界

官方这些基础示例假设 CTA tile 能整除问题尺寸。也就是说，示例中的 global
load 没有完整处理越界。非整除问题将在下一章
[Predication](../08-Predication/08-Predication.md) 处理。

## 学完后应能追踪

给定一个 C 元素，应能依次回答：

1. 它属于哪个 CTA tile？
2. 哪个线程负责对应 accumulator？
3. 该线程从 sA、sB 读取哪些 fragment？
4. sA、sB 中的数据由哪些线程从 global memory 搬入？
5. K-loop 的哪一轮会消费这些数据？
6. 哪次同步防止读取未完成或覆盖仍在使用的 shared memory？

## 官方资料

- [CuTe GEMM Tutorial](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0x_gemm_tutorial.html)
- [官方 Markdown](https://github.com/NVIDIA/cutlass/blob/main/media/docs/cpp/cute/0x_gemm_tutorial.md)
- [CuTe tutorial examples](https://github.com/NVIDIA/cutlass/tree/main/examples/cute/tutorial)
