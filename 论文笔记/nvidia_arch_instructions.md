# NVIDIA GPU 架构指令演进（FlashAttention 视角）

> 聚焦 FlashAttention 用到的关键指令，梳理各代架构的变化。

## 1. 架构总览

| 架构 | SM 版本 | 代表 GPU | 年份 | FlashAttention 版本 |
|------|--------|----------|------|-------------------|
| Pascal | SM60/61 | P100, GTX 1080 | 2016 | — |
| Volta | SM70 | V100 | 2017 | — |
| Turing | SM75 | T4, RTX 2080 | 2018 | — |
| **Ampere** | **SM80/86** | **A100, RTX 3090** | **2020** | **FA1, FA2** |
| **Hopper** | **SM90** | **H100, H200** | **2022** | **FA3** |
| **Blackwell** | **SM100/110** | **B100, B200, GB200** | **2024** | **FA4** |

## 2. 矩阵乘指令（MMA）演进

这是每代变化最大的指令，直接影响 Tensor Core 的使用方式。

### 2.1 演进路线

```
Volta (2017)     →  Ampere (2020)    →  Hopper (2022)      →  Blackwell (2024)
hmma / mma           mma                  wgmma                  umma (tcgen05)
1 warp (32 线程)     1 warp (32 线程)     1 warpgroup (128线程)  1 warpgroup (128线程)
                                                                  + 可选 2CTA 模式
```

### 2.2 详细对比

| | Volta/Turing | Ampere | Hopper | Blackwell |
|---|---|---|---|---|
| **指令名** | `hmma` / `mma` | `mma` | `wgmma` | `umma` (tcgen05.mma) |
| **执行粒度** | 1 warp (32 线程) | 1 warp (32 线程) | 1 warpgroup (128 线程) | 1 warpgroup (128 线程) |
| **异步执行** | ❌ 同步 | ❌ 同步 | ✅ 异步 | ✅ 异步 |
| **操作数 A 来源** | 寄存器 | 寄存器 | SMEM 或 寄存器 | TMEM 或 寄存器 |
| **操作数 B 来源** | 寄存器 | 寄存器 | SMEM (描述符) | SMEM (描述符) |
| **累加器** | 寄存器 (FP32) | 寄存器 (FP32) | 寄存器 (FP32) | TMEM (FP32) |
| **最大 tile** | 16×16×16 | 16×16×16 | 64×256×16 | 更大 |
| **FP8 支持** | ❌ | ❌ | ✅ (e4m3/e5m2) | ✅ + FP4 |
| **特殊模式** | — | — | — | 2CTA (两个 CTA 协同) |
| **commit/wait** | — | — | `wgmma.commit_group` / `wgmma.wait_group` | 类似机制 |

### 2.3 Warpgroup 概念

```
Ampere 及之前：
  mma 执行单元 = 1 warp = 32 线程
  没有 "warpgroup" 概念

Hopper 起：
  wgmma 执行单元 = 1 warpgroup = 4 warp = 128 线程
  4 个 warp 捆绑在一起喂更大的 Tensor Core
```

### 2.4 异步 MMA 的意义

```
Ampere (同步 mma):
  发出 mma → 等待完成 → 才能执行下一条指令
  CUDA Core 在等 Tensor Core 期间空闲

Hopper (异步 wgmma):
  发出 wgmma → 立刻返回 → CUDA Core 继续执行其他指令（如 softmax）
  Tensor Core 在后台计算

  控制接口:
    wgmma.commit_group   — 提交一组 wgmma
    wgmma.wait_group N   — 等到最多 N 个组还在执行
      N=0: 全部完成
      N=1: 允许 1 个还在飞（FA3 用来让 softmax 和 PV GEMM 重叠）
```

这个异步能力是 FA3 能做 GEMM-softmax 重叠的基础。

### 2.5 Blackwell 的 2CTA 模式

```
普通模式:
  1 条 umma = 1 个 warpgroup (128 线程), 在 1 个 CTA 内

2CTA 模式:
  1 条 umma = 2 个 CTA 各出 1 个 warpgroup, 共 256 线程
  两个 CTA 在同一个 cluster 中，调度到相邻 SM

  ┌──── CTA 0 (SM_a) ────┐  ┌──── CTA 1 (SM_b) ────┐
  │  warpgroup → 提供数据  │  │  warpgroup → 提供数据  │
  └───────────────────────┘  └───────────────────────┘
              ↘                      ↙
            两个 CTA 合力完成更大的矩阵乘

好处: 更大的 tile, 更高的吞吐
FA4 在 hdim=128 的 Blackwell 路径使用了 2CTA
```

---

## 3. 数据搬运指令演进

### 3.1 演进路线

```
Volta (2017)     →  Ampere (2020)    →  Hopper (2022)     →  Blackwell (2024)
全局 load/store      cp.async             TMA                   TMA (增强)
线程级，同步         线程级，异步          硬件级，异步            硬件级，异步
```

### 3.2 详细对比

| | Volta/Turing | Ampere | Hopper | Blackwell |
|---|---|---|---|---|
| **GMEM→SMEM** | `ld.global` + `st.shared` | `cp.async` | `cp.async.bulk.tensor` (TMA) | TMA (增强) |
| **执行方式** | 每线程搬几字节 | 每线程搬 4/8/16 字节 | **1 个线程 1 条指令搬整个 tile** | 同 Hopper |
| **异步** | ❌ | ✅ (有限) | ✅ (完全异步) | ✅ |
| **张量感知** | ❌ 手动算地址 | ❌ 手动算地址 | ✅ tensor map 描述符 | ✅ |
| **自动边界处理** | ❌ 手写 if | ❌ 手写 if | ✅ 硬件 clamp/zero-fill | ✅ |
| **所需线程数** | 全 block 协作 | 全 block 协作 | **1 个线程** | 1 个线程 |
| **通知机制** | `__syncthreads()` | `cp.async.commit/wait` | mbarrier | mbarrier |
| **专用硬件** | ❌ (用 Load/Store Unit) | ❌ (用 Load/Store Unit) | ✅ TMA Engine | ✅ TMA Engine |

### 3.3 三代搬运方式对比

```
Ampere (cp.async):
  每个线程搬 16 字节，需要很多线程协作搬一个 tile
  ──────────────────────────────
  Thread 0:  cp.async.ca.shared.global [smem+0],  [gmem+0],  16;
  Thread 1:  cp.async.ca.shared.global [smem+16], [gmem+16], 16;
  Thread 2:  cp.async.ca.shared.global [smem+32], [gmem+32], 16;
  ...
  Thread 31: cp.async.ca.shared.global [smem+496],[gmem+496],16;
  cp.async.commit_group;
  cp.async.wait_group 0;
  ──────────────────────────────
  32 个线程才搬了 512 字节

Hopper (TMA):
  1 个线程发 1 条指令，搬整个 tile (比如 128×128×2 = 32KB)
  ──────────────────────────────
  Thread 0:  cp.async.bulk.tensor.2d [smem], [tensor_map, {x,y}], [mbarrier];
  ──────────────────────────────
  1 条指令，TMA Engine 自动完成全部搬运
  其他 127 个线程完全空闲，可以去做别的事
```

### 3.4 TMA 的 Tensor Map 描述符

```
TMA 的关键创新：张量描述符 (Tensor Map)

在 CPU 端创建，包含张量的全部元数据:
  - 基地址 (GMEM 中的指针)
  - 数据类型 (fp16, bf16, fp8, ...)
  - 维度数 (1D, 2D, 3D, 4D, 5D)
  - 全局 shape 和 stride
  - tile shape (每次搬多大)
  - swizzle 模式 (避免 SMEM bank conflict)

GPU 端只需传坐标 {x, y}，硬件自动:
  1. 计算 GMEM 地址 = base + y*stride_y + x*stride_x
  2. 检查边界，越界部分 zero-fill
  3. DMA 搬运 GMEM → SMEM
  4. 完成后通知 mbarrier
```

---

## 4. 同步原语演进

### 4.1 演进路线

```
Volta (2017)     →  Ampere (2020)    →  Hopper (2022)      →  Blackwell (2024)
__syncthreads()     __syncthreads()     __syncthreads()       __syncthreads()
bar.sync             bar.sync            bar.sync              bar.sync
                     mbarrier (基础)     mbarrier (完整)       mbarrier (增强)
                                         Named Barrier         Named Barrier
```

### 4.2 三种同步机制对比

| 机制 | 粒度 | 同步方式 | 典型用途 |
|------|------|---------|---------|
| **`__syncthreads()`** | 整个 CTA | 全部线程到齐才继续 | 通用同步 |
| **Named Barrier (`bar.sync/arrive`)** | CTA 内任意线程子集 | 指定数量的线程到齐 | Pingpong 调度 |
| **mbarrier** | CTA 内 + 可跨 cluster | 按"到达计数"或"字节数"通知 | TMA 完成通知，Producer-Consumer |

### 4.3 mbarrier 详解

```
mbarrier 是 Hopper 最核心的同步原语
本质：一个硬件计数器，支持按字节追踪异步数据搬运

传统 __syncthreads():
  所有线程 → 到齐 → 继续
  问题：强制等所有线程，粒度太粗

mbarrier (Ampere 基础版):
  init(count)         — 设置期望到达次数
  arrive()            — "我到了" (计数 -1)
  wait()              — 等计数归零
  配合 cp.async 使用

mbarrier (Hopper 完整版):
  init(expected_bytes) — 设置期望的数据字节数
  TMA 搬完后自动 arrive (tx_count -= bytes)
  try_wait(phase)      — 非阻塞检查 phase 是否翻转
  支持 phase bit 区分奇偶轮次（环形 buffer 关键）
  支持跨 cluster 的 arrive（多 CTA 协作）
```

### 4.4 Named Barrier 在 FA3 Pingpong 中的用法

```
Named Barrier: 比 __syncthreads 更细粒度

__syncthreads():  整个 CTA (256线程) 全部等待 — 太重了
Named Barrier:    只同步指定的线程子集

FA3 Pingpong 用法:
  barrier 0 → WG1 专用 (128 线程参与)
  barrier 1 → WG2 专用 (128 线程参与)

  WG1: barrier_sync(0)  → 做 GEMM → barrier_arrive(1)  → 做 softmax
  WG2: 做 softmax       → barrier_sync(1)  → 做 GEMM → barrier_arrive(0)

  两个 WG 交替使用 Tensor Core，互不阻塞
```

---

## 5. 寄存器管理演进

| | Ampere 及之前 | Hopper | Blackwell |
|---|---|---|---|
| **寄存器分配** | 编译时固定 | **运行时动态调整** | 运行时动态调整 |
| **指令** | — | `setmaxnreg` | `setmaxnreg` |
| **粒度** | — | per-warpgroup | per-warpgroup |

```
Ampere:
  编译器决定每个线程用多少寄存器，运行时不能改

Hopper:
  setmaxnreg.dec.sync.aligned.u32 40;    — "我只需要 40 个寄存器"
  setmaxnreg.inc.sync.aligned.u32 232;   — "我需要 232 个寄存器"

  FA3 用法:
    Producer warpgroup:  decrease → 释放寄存器 (只发 TMA, 不需要多少)
    Consumer warpgroup:  increase → 获取寄存器 (WGMMA 累加器需要大量寄存器)
    总寄存器量不变，只是在 warpgroup 间重新分配
```

---

## 6. 存储层次演进

### 6.1 存储类型

| 存储 | 引入架构 | 访问者 | 作用 |
|------|---------|--------|------|
| **RMEM** (寄存器) | 所有 | 线程私有 | 计算操作数、累加器 |
| **SMEM** (共享内存) | 所有 | CTA 内共享 | tile 缓存、线程间通信 |
| **L2 Cache** | 所有 | 全芯片 | 透明缓存 |
| **GMEM / HBM** | 所有 | 全芯片 | 主存 |
| **TMEM** (张量内存) | **Blackwell** | Tensor Core 专用 | MMA 操作数和累加器 |

### 6.2 Blackwell 新增的 TMEM

```
Hopper 的数据路径:
  HBM →(TMA)→ SMEM →(load)→ RMEM →(wgmma)→ Tensor Core
                     ↘(wgmma 可直接读 SMEM)↗

Blackwell 的数据路径:
  HBM →(TMA)→ SMEM →(copy)→ TMEM →(umma)→ Tensor Core
                               ↑
                    Tensor Core 专用存储
                    比 SMEM→RMEM→Tensor Core 路径更短更快
                    累加器也直接放在 TMEM 中

TMEM 的好处:
  - 释放了 RMEM 的压力（累加器不再占用通用寄存器）
  - 数据路径更短（TMEM 紧贴 Tensor Core）
  - 容量比 RMEM 更大（可以做更大的 tile）
```

---

## 7. 精度支持演进

| 数据类型 | Pascal | Volta | Ampere | Hopper | Blackwell |
|---------|--------|-------|--------|--------|-----------|
| FP64 | ✅ | ✅ | ✅ | ✅ | ✅ |
| FP32 | ✅ | ✅ | ✅ | ✅ | ✅ |
| TF32 | — | — | ✅ | ✅ | ✅ |
| FP16 | ✅ | ✅ (Tensor Core) | ✅ | ✅ | ✅ |
| BF16 | — | — | ✅ | ✅ | ✅ |
| **FP8** (e4m3/e5m2) | — | — | — | **✅** | **✅** |
| **FP4** | — | — | — | — | **✅** |
| INT8 | — | ✅ | ✅ | ✅ | ✅ |

```
FP8 的 Tensor Core 吞吐 (每 SM):
  Hopper:    FP8 = 2× FP16 吞吐
  Blackwell: FP8 = 2× FP16, FP4 = 4× FP16

FA3 的 FP8 挑战:
  - FP8 WGMMA 只支持 k-major 操作数（FP16 支持 k-major 和 mn-major）
  - FP8 累加器布局和 FP8 操作数布局不一致（需要 permute）
  - 3 bit 尾数精度低，需要 block quantization + incoherent processing
```

---

## 8. Cluster — Hopper 引入的新线程层次

```
Ampere 及之前:
  Grid → Block(CTA) → Warp → Thread
  每个 CTA 独立，CTA 之间只能通过 GMEM 或 atomics 通信

Hopper 起:
  Grid → Cluster → Block(CTA) → Warpgroup → Warp → Thread
                ↑           ↑
              新增！      新增！

Cluster:
  - 最多 16 个 CTA 组成一个 cluster
  - 同一 cluster 的 CTA 保证调度到同一个 GPC（GPU Processing Cluster）
  - cluster 内的 CTA 可以直接访问彼此的 SMEM（Distributed Shared Memory）
  - mbarrier 可以跨 cluster 内的 CTA arrive
  - TMA 支持 multicast: 一次搬运同时写到 cluster 内多个 CTA 的 SMEM

FA3/FA4 中的用途:
  - multicast TMA: 同一个 K/V 块广播给 cluster 内处理不同 Q 块的 CTA
  - 减少 HBM 带宽消耗
```

---

## 9. 各代 FlashAttention 使用的关键指令

| 指令/特性 | FA1 (Ampere) | FA2 (Ampere) | FA3 (Hopper) | FA4 (Hopper+Blackwell) |
|-----------|-------------|-------------|-------------|----------------------|
| MMA 指令 | `mma` (sync) | `mma` (sync) | `wgmma` (async) | `wgmma` + `umma` |
| 数据搬运 | `cp.async` | `cp.async` | TMA | TMA |
| 同步 | `__syncthreads` | `__syncthreads` | mbarrier + Named Barrier | mbarrier + Named Barrier |
| 寄存器管理 | 编译时固定 | 编译时固定 | `setmaxnreg` 动态 | `setmaxnreg` 动态 |
| Warp Specialization | ❌ | ❌ | ✅ Producer/Consumer | ✅ |
| GEMM-Softmax 重叠 | ❌ | ❌ | ✅ (async wgmma) | ✅ |
| Pingpong 调度 | ❌ | ❌ | ✅ (Named Barrier) | ✅ |
| FP8 | ❌ | ❌ | ✅ | ✅ |
| FP4 | ❌ | ❌ | ❌ | ✅ (Blackwell) |
| 2CTA | ❌ | ❌ | ❌ | ✅ (Blackwell) |
| TMEM | ❌ | ❌ | ❌ | ✅ (Blackwell) |
| SplitKV | ❌ | ❌ | ❌ | ✅ |
| Paged KV Cache | ❌ | ❌ | ❌ | ✅ |
| Persistent Kernel | ❌ | ❌ | ✅ (FP16 only) | ✅ |
