# FlashAttention-3 三大优化 — CUTLASS / CuTe 官方 API 代码示例

> 只使用 NVIDIA 官方 CUTLASS 3.x / CuTe API，不使用 FA3 的自定义封装（如 `flash::gemm`）。
> 展示如何用官方积木从零搭建 FA3 的三个优化。

---

## 1. CuTe 核心概念

```cpp
#include "cute/tensor.hpp"
#include "cutlass/pipeline/pipeline.hpp"
#include "cutlass/arch/barrier.h"
#include "cutlass/arch/reg_reconfig.h"
using namespace cute;

// ── Tensor = 指针 + Layout(形状×步长) ──
Tensor gK = make_tensor(
    make_gmem_ptr(ptr_K),                              // GMEM 指针
    make_shape(seqlen, hdim), make_stride(hdim, 1)     // [seqlen, hdim], 行主序
);
Tensor sK = make_tensor(
    make_smem_ptr(smem_k_ptr),                         // SMEM 指针
    SmemLayoutK{}                                       // 带 swizzle 的布局
);

// ── TiledMma: WGMMA 的 tile 配置 ──
// atom 名字格式: SM90_{M}x{N}x{K}_{AccType}{AType}{BType}_{SS/RS}
// SS = 两个操作数都在 SMEM, RS = A 在寄存器 B 在 SMEM
using MmaQK = decltype(make_tiled_mma(SM90_64x128x16_F32F16F16_SS{}));
using MmaPV = decltype(make_tiled_mma(SM90_64x128x16_F32F16F16_RS{}));

// ── 为当前线程分配累加器 ──
auto tiled_mma = make_tiled_mma(SM90_64x128x16_F32F16F16_SS{});
Tensor acc = partition_fragment_C(tiled_mma, make_shape(Int<64>{}, Int<128>{}));
// acc 是当前线程持有的 FP32 寄存器片段

// ── TMA copy: 创建 tensor map + copy atom ──
auto tma_load = make_tma_copy(SM90_TMA_LOAD{}, gK, sK);
// host 端自动创建 CUtensorMap 描述符

// ── Pipeline: mbarrier + 环形 buffer ──
using Pipeline = cutlass::PipelineTmaAsync</*Stages=*/2>;
using PipelineState = cutlass::PipelineState<2>;
```

---

## 2. 优化一：Warp Specialization

```cpp
__global__ void kernel(/* params */) {
    extern __shared__ char smem[];
    int wg_idx = cyclic_warpgroup_idx();

    // ━━━ PRODUCER (warpgroup 0) ━━━
    if (wg_idx == 0) {
        cutlass::arch::warpgroup_reg_dealloc<40>();   // 官方: 释放寄存器

        PipelineState write_state = cutlass::make_producer_start_state<Pipeline>();

        for (int j = 0; j < Tc; j++) {
            // 官方: 等 consumer 释放 buffer
            pipeline_k.producer_acquire(write_state);

            // 官方: TMA copy — cute::copy 根据 atom 类型自动选择指令
            copy(tma_load_K.with(*pipeline_k.producer_get_barrier(write_state)),
                 tKgK(_, j),                          // GMEM 源: 第 j 个 K 块
                 tKsK(_, write_state.index()));        // SMEM 目标: 第 stage 个槽

            ++write_state;
        }
        pipeline_k.producer_tail(write_state);         // 官方: 发送结束信号
    }
    // ━━━ CONSUMER (warpgroup 1) ━━━
    else {
        cutlass::arch::warpgroup_reg_alloc<232>();    // 官方: 获取寄存器

        Tensor acc_O = partition_fragment_C(mma_pv, make_shape(Int<Br>{}, Int<Hd>{}));
        clear(acc_O);
        PipelineState read_state;

        for (int j = 0; j < Tc; j++) {
            pipeline_k.consumer_wait(read_state);     // 官方: 等数据到达
            /* ... MMA + softmax ... */
            pipeline_k.consumer_release(read_state);  // 官方: 释放 buffer
            ++read_state;
        }
    }
}
```

---

## 3. 优化二：GEMM-Softmax 重叠

### 3.1 异步 WGMMA 的 6 步流程

关键：完全展开为官方原语，不用任何自定义封装。

```cpp
// 计算 S = Q @ K^T (SS-GEMM, 两个操作数都在 SMEM)

auto tiled_mma_qk = make_tiled_mma(SM90_64x128x16_F32F16F16_SS{});
auto thr_mma = tiled_mma_qk.get_thread_slice(tidx);   // 当前线程的 MMA 视图

Tensor tSrQ = thr_mma.partition_fragment_A(sQ);         // Q 的 SMEM → 寄存器分片
Tensor tSrK = thr_mma.partition_fragment_B(sK);         // K 的 SMEM 分片
Tensor acc_S = partition_fragment_C(tiled_mma_qk,       // S 的累加器
                                     make_shape(Int<Br>{}, Int<Bc>{}));

// ── 异步 WGMMA 的 6 步流程 ──

// ① fence: 告诉编译器这些寄存器要交给 WGMMA
warpgroup_fence_operand(acc_S);

// ② arrive: 标记一个 WGMMA group 开始
warpgroup_arrive();

// ③ 设置累加器模式
tiled_mma_qk.accumulate_ = GMMA::ScaleOut::Zero;  // 第一个 k_block 清零

// ④ 发出 WGMMA 指令 (按 K 维度循环)
constexpr int K_TILES = size<2>(tSrQ);  // K 维度的 tile 数
CUTLASS_PRAGMA_UNROLL
for (int k = 0; k < K_TILES; k++) {
    cute::gemm(tiled_mma_qk, tSrQ(_, _, k), tSrK(_, _, k), acc_S);
    //  ↑ CuTe 官方 gemm: 对 SM90 atom 自动生成 wgmma.mma_async PTX
    tiled_mma_qk.accumulate_ = GMMA::ScaleOut::One;  // 后续 k_block 改为累加
}

// ⑤ commit: 提交这组 WGMMA
warpgroup_commit_batch();

// ⑥ wait: 控制异步程度
// 选项 A: warpgroup_wait<0>() — 等所有完成（同步模式）
// 选项 B: 不调用 wait      — WGMMA 在后台飞（异步模式）

warpgroup_fence_operand(acc_S);  // fence: 标记寄存器重新可用
```

### 3.2 完整 2-stage 重叠 mainloop

```cpp
for (int j = 1; j < Tc - 1; j++) {
    PipelineState pipe_v = read_state;
    ++read_state;

    pipeline_k.consumer_wait(read_state);

    // ── Pingpong barrier: 等轮到我 ──
    cutlass::arch::NamedBarrier::sync(
        2 * NumThreadsPerWarpGroup, my_barrier_id);

    // ── ① QK^T GEMM: 提交，不等待 ──
    Tensor acc_S = partition_fragment_C(mma_qk, Shape<Int<Br>, Int<Bc>>{});
    warpgroup_fence_operand(acc_S);
    warpgroup_arrive();
    mma_qk.accumulate_ = GMMA::ScaleOut::Zero;
    for (int k = 0; k < K_TILES; k++) {
        cute::gemm(mma_qk, tQ(_, _, k), tK(read_state.index())(_, _, k), acc_S);
        mma_qk.accumulate_ = GMMA::ScaleOut::One;
    }
    warpgroup_commit_batch();
    // ★ 不 wait ★

    // ── ② PV GEMM: 也不等待 ──
    pipeline_v.consumer_wait(pipe_v);
    warpgroup_fence_operand(acc_O);
    warpgroup_arrive();
    mma_pv.accumulate_ = GMMA::ScaleOut::One;
    for (int k = 0; k < K_TILES_V; k++) {
        cute::gemm(mma_pv, P_regs(_, _, k), tV(pipe_v.index())(_, _, k), acc_O);
    }
    warpgroup_commit_batch();
    // ★ 也不 wait，两个 WGMMA 都在飞 ★

    // ── Pingpong barrier: 通知对方 WG ──
    cutlass::arch::NamedBarrier::arrive(
        2 * NumThreadsPerWarpGroup, next_wg_barrier_id);

    // ── ③ 只等 QK^T 完成 ──
    warpgroup_wait<1>();     // 允许 1 个(PV)还在飞
    warpgroup_fence_operand(acc_S);
    pipeline_k.consumer_release(read_state);

    // ── ④ Softmax: 与 PV GEMM 并行执行！ ──
    // softmax 用 CUDA Core/MFU, Tensor Core 还在跑 PV GEMM
    online_softmax(acc_S, ...);

    // ── ⑤ 等 PV 也完成 ──
    warpgroup_wait<0>();
    warpgroup_fence_operand(acc_O);
    pipeline_v.consumer_release(pipe_v);

    // rescale, convert, 准备下一轮 ...
}
```

---

## 4. 优化三：FP8 V 转置

```cpp
// 在 SMEM 内做 V 转置，用两条 pipeline: pipeline_vt(原始) → pipeline_v(转置后)

auto copy_Vt_to_V = [&](PipelineState const& smem_pipe_write) {
    PipelineState smem_pipe_read{
        smem_pipe_write.index(),
        smem_pipe_write.phase() ^ 1,  // phase 翻转
        smem_pipe_write.count()
    };

    // 等 TMA 搬完原始 V
    pipeline_vt.consumer_wait(smem_pipe_read);

    // 获取转置后 V 的 buffer
    pipeline_v.producer_acquire(smem_pipe_write);

    // 执行转置 (内部用 ldmatrix + stmatrix.trans)
    transpose_V(smem_pipe_write.index());

    // 官方: SMEM fence，确保写入对 WGMMA 可见
    cutlass::arch::fence_view_async_shared();

    // 通知 consumer
    pipeline_v.producer_commit(smem_pipe_write);

    // 官方: warp 内同步
    cutlass::arch::NamedBarrier::sync(
        NumThreadsPerWarpGroup,
        cutlass::arch::ReservedNamedBarriers::TransposeBarrier);

    // 释放原始 V buffer
    pipeline_vt.consumer_release(smem_pipe_read);
};
```

---

## 5. 官方 API 完整速查表

| 类别 | CuTe / CUTLASS 官方 API | 对应 PTX | 作用 |
|------|------------------------|---------|------|
| **张量** | `make_tensor(ptr, layout)` | — | 创建 tensor |
| **张量** | `make_gmem_ptr(p)` / `make_smem_ptr(p)` | — | 标注指针的地址空间 |
| **布局** | `make_layout(shape, stride)` | — | 创建 layout |
| **TMA** | `make_tma_copy(SM90_TMA_LOAD{}, g, s)` | 创建 CUtensorMap | 创建 TMA 描述符 |
| **TMA** | `copy(tma.with(*barrier), src, dst)` | `cp.async.bulk.tensor` | TMA 搬运 |
| **MMA** | `make_tiled_mma(SM90_64x128x16_...)` | — | 创建 MMA atom 配置 |
| **MMA** | `partition_fragment_C(mma, shape)` | — | 分配线程私有累加器 |
| **MMA** | `cute::gemm(mma, A, B, C)` | `wgmma.mma_async` | **执行 WGMMA** |
| **MMA** | `mma.accumulate_ = Zero/One` | 设置 scale_d | 清零/累加 模式 |
| **异步** | `warpgroup_fence_operand(t)` | fence | 标记寄存器给 WGMMA |
| **异步** | `warpgroup_arrive()` | `warpgroup.arrive` | WGMMA group 开始 |
| **异步** | `warpgroup_commit_batch()` | `wgmma.commit_group` | 提交 group |
| **异步** | `warpgroup_wait<N>()` | `wgmma.wait_group N` | 等到最多 N 个在飞 |
| **Pipeline** | `pipeline.producer_acquire(s)` | `mbarrier.try_wait` | 等 buffer 可写 |
| **Pipeline** | `pipeline.producer_get_barrier(s)` | — | 获取 mbarrier 指针 |
| **Pipeline** | `pipeline.producer_tail(s)` | — | 发送结束信号 |
| **Pipeline** | `pipeline.consumer_wait(s)` | `mbarrier.try_wait` | 等数据到达 |
| **Pipeline** | `pipeline.consumer_release(s)` | `mbarrier.arrive` | 释放 buffer |
| **Barrier** | `NamedBarrier::sync(n, id)` | `bar.sync` | 同步线程子集 |
| **Barrier** | `NamedBarrier::arrive(n, id)` | `bar.arrive` | 通知到达 |
| **寄存器** | `warpgroup_reg_dealloc<N>()` | `setmaxnreg.dec` | 释放寄存器 |
| **寄存器** | `warpgroup_reg_alloc<N>()` | `setmaxnreg.inc` | 获取寄存器 |
| **Fence** | `fence_view_async_shared()` | `fence.proxy.async.shared` | SMEM 写入可见性 |
