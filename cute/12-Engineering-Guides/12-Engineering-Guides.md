# 12 Engineering Guides

> 官方对应：`media/docs/pythonDSL/guides/`
>
> 更新：2026-09-28

## 本章定位

前 11 章回答“kernel 怎样写”。本章只回答工程问题：

```text
出错了怎样定位？
性能差在哪里？
参数怎样搜索？
怎样接入生产程序和框架？
```

这不是新的 CuTe 数学主线。已经掌握相关工具时，可直接把本章当作速查表。

## 学习顺序

1. [Debugging](01-Debugging/01-Debugging.md)
   - 编译、运行、同步和数值错误的定位顺序；
   - IR/PTX/SASS dump；
   - Compute Sanitizer。
2. [Profiling](02-Profiling/02-Profiling.md)
   - 端到端计时、Nsight Compute 与 IKET 的职责边界；
   - 如何测量异步 issue 和 wait。
3. [Autotuning](03-Autotuning/03-Autotuning.md)
   - 搜索空间、合法性过滤、编译缓存和结果缓存；
   - 稳定 benchmark。
4. [AOT 与 Integration](04-AOT与Integration/04-AOT与Integration.md)
   - DLPack/PyTorch；
   - TVM FFI；
   - CuTe ABI AOT 与 C/C++ 部署。

## 一张决策表

| 目标 | 首选工具 |
|---|---|
| Python trace/编译错误 | `CUTE_DSL_DEBUG=1` |
| 查看生成的 IR/PTX/SASS | `CUTE_DSL_KEEP=...` |
| 非法地址、越界 | Compute Sanitizer `memcheck` |
| SMEM 数据竞争 | Compute Sanitizer `racecheck` |
| 单个 kernel 的硬件瓶颈 | Nsight Compute |
| kernel 内 producer/consumer 时间线 | IKET + Perfetto |
| CPU/GPU 调度与 kernel overlap | Nsight Systems |
| 为固定输入选择 tile/cluster | Autotuning |
| 消除生产环境 JIT 延迟 | AOT |
| PyTorch/JAX 低开销调用 | TVM FFI |

## 推荐工程闭环

```text
1. correctness
   CPU/reference check + sanitizer

2. observability
   保留 IR/PTX/SASS，给 kernel 设置稳定名称

3. profiling
   先确认瓶颈，再改参数

4. autotuning
   只搜索合法配置，缓存编译结果和最佳配置

5. deployment
   根据调用方选择 DLPack、TVM FFI 或 CuTe ABI AOT
```

不要在数值正确性尚未确认时做性能结论，也不要用 debug/instrumented
kernel 的结果代表最终生产性能。

## 官方资料

- [Debugging](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/debugging.html)
- [IKET Profiling](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/iket_profiling.html)
- [Autotuning GEMM](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/autotuning_gemm.html)
- [Ahead-of-Time Compilation](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/ahead_of_time_compilation.html)
- [TVM FFI Compilation](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/tvm_ffi_compilation.html)
- [Framework Integration](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/framework_integration.html)
