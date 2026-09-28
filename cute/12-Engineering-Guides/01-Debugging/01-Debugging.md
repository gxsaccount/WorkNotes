# CuTe DSL Debugging：按失败阶段定位

> 官方文档：[Debugging](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/debugging.html)
>
> 更新：2026-09-28

## 先判断错误发生在哪一层

```text
Python trace 阶段失败
  → 类型、静态/动态值、DSL 限制

编译阶段失败
  → IR、NVVM/PTX diagnostics、资源使用

kernel 运行失败
  → 越界、竞争、同步、非法指令

结果错误
  → partition、predicate、pipeline stage、accumulate

结果正确但性能差
  → 进入 Profiling，不继续靠 print 猜
```

不同阶段使用不同工具。最浪费时间的做法，是看到任何错误都立即查看
SASS。

## 1. 首先开启 Debug Mode

```bash
export CUTE_DSL_DEBUG=1
python your_kernel.py
```

Debug Mode 会提高多项诊断设置的默认级别，包括：

- Python 与 PTX/SASS 的源码行关联；
- 完整 Python stack trace；
- 优化 warning；
- trace-time operation verification；
- 更完整的 launch argument validation。

调试完成后关闭：

```bash
unset CUTE_DSL_DEBUG
```

Debug Mode 会改变编译选项和 cache key，也可能改变生成代码。性能测量必须
使用关闭 Debug Mode 后重新编译的 kernel。

## 2. 保留生成产物

```bash
# 常用组合
export CUTE_DSL_KEEP=ir,ptx,cubin,sass
export CUTE_DSL_DUMP_DIR=./cute_dump

python your_kernel.py
```

可选值：

| 值 | 用途 |
|---|---|
| `ir-debug` | pass 前的原始 IR |
| `ir` | canonicalize/CSE 后的 IR |
| `ptx` | 检查目标 PTX 指令 |
| `cubin` | 保存设备二进制 |
| `sass` | 查看最终机器指令 |
| `all` | 保存全部支持的产物 |

SASS dump 需要兼容版本的 `nvdisasm`。官方推荐安装：

```bash
pip install 'nvidia-cutlass-dsl[sass]'
```

也可以直接从编译结果读取：

```python
compiled = cute.compile(kernel, ...)

print(compiled.__mlir__)
print(compiled.__ptx__)

with open("kernel.cubin", "wb") as f:
    f.write(compiled.__cubin__)
```

## 3. 开启编译器 diagnostics

统一入口：

```bash
export CUTE_DSL_COMPILER_OPT='warnings{nvvm},remarks{nvvm},remarks{ptx},remarks{loop}'
```

| 分类 | 适合定位 |
|---|---|
| `nvvm` warning/remark | `mbarrier`、TMA multicast、bulk copy、TCGen05 协议 |
| `ptx` remark | register spill、local-memory 使用 |
| `loop` remark | unroll、software pipeline 等优化 |

diagnostic 能证明的协议错误应直接修复，不能通过屏蔽 warning 解决。

## 4. 区分 Python `print` 与 `cute.printf`

```python
@cute.kernel
def kernel(x):
    print(x.layout)               # trace/编译期间执行
    cute.printf("x[0] = {}", x[0])  # GPU kernel 运行期间执行
```

用途：

```text
Python print:
  静态 Shape/Layout、类型、编译期分支

cute.printf:
  运行时坐标、数据值、pipeline state
```

`cute.printf` 会修改生成代码并产生较大开销。限制到少量线程和 CTA：

```python
if tidx == 0 and bidx == 0:
    cute.printf("stage={}, value={}", stage, value)
```

## 5. 运行时错误使用 Compute Sanitizer

非法地址：

```bash
compute-sanitizer --tool memcheck python your_kernel.py
```

共享内存竞争：

```bash
compute-sanitizer --tool racecheck python your_kernel.py
```

推荐先缩小问题：

```text
只运行一个小矩阵
→ 减少 CTA 数
→ 关闭复杂调度
→ 保留同一条错误数据路径
→ 再运行 sanitizer
```

## 6. 数值错误的二分方法

不要只比较最终输出。沿数据流设置检查点：

```text
输入 tensor/layout
→ 当前 CTA 的 gA/gB/gC
→ TMA/copy 后的 sA/sB
→ 当前 MMA fragment/descriptor
→ accumulator
→ epilogue 临时结果
→ 最终 GMEM
```

每一步检查：

1. Shape 是否符合预期；
2. 当前 thread/warp/CTA 是否拥有这些坐标；
3. 数据是否已经完成搬运；
4. stage 是否被提前复用；
5. predicate 是否与数据采用相同 partition；
6. 第一轮是覆盖还是累加。

### 一个实用二分法

```text
最终结果错误
├─ accumulator 正确
│  └─ 问题在 epilogue/predicate/store
└─ accumulator 错误
   ├─ SMEM 正确
   │  └─ 问题在 fragment/MMA/pipeline
   └─ SMEM 错误
      └─ 问题在 GMEM partition/TMA/copy/predicate
```

## 7. 为 profiler 设置稳定名称

```python
kernel.set_name_prefix(
    "gemm_sm100",
    remove_cutlass_symbol=True,
    keep_mangled_name=False,
)
```

这样 IR、trace 和 profiler 中更容易定位目标 kernel。名称需要在最终
link/load 范围内保持唯一。

## 8. Kernel 卡死

若 kernel 长时间无响应：

1. 不要连续重复运行同一配置；
2. 记录最后一个可见 pipeline/barrier 状态；
3. 缩小到单个 tile；
4. 检查 producer/consumer arrive、wait、release 是否配对；
5. 使用 compiler diagnostics 和 Compute Sanitizer；
6. 必要时暂停并结束进程：

```bash
Ctrl+Z
kill -9 $(jobs -p | tail -1)
```

卡死通常不是“计算太慢”，而是 barrier 参与者、transaction count、
stage 生命周期或分支一致性出了问题。

## 9. 最短排障清单

```text
[ ] CUTE_DSL_DEBUG=1 后错误是否更明确？
[ ] Python print 的静态 Shape/Layout 是否正确？
[ ] IR 中是否生成了预期的 TMA/MMA 指令？
[ ] ptxas 是否报告 spill/local memory？
[ ] sanitizer 是否报告越界或竞争？
[ ] async copy/MMA 的 wait 是否对应正确完成事件？
[ ] 是否用 CPU/PyTorch reference 比较最小输入？
[ ] 关闭 debug/instrumentation 后问题是否仍存在？
```

## 常见误解

1. **“没有异常就说明异步协议正确。”**
   错误同步可能只表现为偶发错误或不同负载下卡死。
2. **“Python `print` 能看到 GPU 运行时值。”**
   它只在 trace/编译阶段执行；运行时使用 `cute.printf`。
3. **“Debug Mode 下测得的性能可以直接使用。”**
   Debug 设置会改变编译产物和缓存。
4. **“最终结果接近就不需要检查边界。”**
   小规模误差可能掩盖少量越界、未初始化数据或 predicate 错位。
