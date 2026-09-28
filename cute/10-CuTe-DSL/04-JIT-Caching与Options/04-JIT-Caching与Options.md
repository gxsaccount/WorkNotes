# JIT Caching 与 Compilation Options

> 官方对应：
>
> - `cute_dsl_general/dsl_jit_caching.rst`
> - `cute_dsl_general/dsl_jit_compilation_options.rst`
>
> 更新：2026-09-28

## 1. `cute.compile` 与 JIT Executor

`cute.compile` 显式编译函数，并返回可调用的 **JIT Executor**：

```python
import cutlass
import cutlass.cute as cute


@cute.jit
def add(a: cutlass.Int32, b: cutlass.Int32):
    return a + b


executor = cute.compile(add, 1, 2)
result = executor(10, 20)
```

JIT Executor 持有执行所需资源：

- 已编译 host 函数及 MLIR execution engine；
- 可选的 CUDA module 和 kernel function pointer；
- 把 Python 运行时参数转换为 C ABI 参数的规格。

`Constexpr` 参数已在编译期求值，因此不在 executor 的运行时参数中：

```python
@cute.jit
def add(
    a: cutlass.Int32,
    b: cutlass.Int32,
    verbose: cutlass.Constexpr,
):
    if cutlass.const_expr(verbose):
        cute.printf("result=%d\n", a + b)
    return a + b


executor = cute.compile(add, 1, 2, True)
executor(10, 20)  # 不再传 verbose
```

这就是官方所称的 **Zero Compile** 使用方式：把编译放到明确的准备阶段，热
路径只调用已经准备好的 executor。

---

## 2. 自定义缓存

`cute.compile` 本身绕过 DSL 隐式缓存，每次调用都会执行编译。它返回的固定
executor 很适合放进应用自己的 cache：

```python
executors = {}


def get_executor(shape_key, sample):
    if shape_key not in executors:
        executors[shape_key] = cute.compile(my_op, sample)
    return executors[shape_key]
```

自定义 key 应至少覆盖所有会改变生成程序或 ABI 的因素，例如：

- dtype；
- rank、静态 shape、stride/layout 类别；
- 目标 GPU 架构；
- tile、pipeline stage、epilogue 等 Constexpr 配置；
- 所用编译选项。

优点：

- 请求热路径不再重新生成 MLIR；
- 生命周期和淘汰策略由应用掌控；
- 更容易预热固定的一组 kernel 变体。

---

## 3. DSL 隐式缓存

直接调用被装饰函数时，DSL 默认启用缓存：

```python
@cute.jit
def add(b):
    return global_a + b


global_a = 1
add(2)  # miss：生成 IR、编译并缓存
add(2)  # hit：复用 executor

global_a = 2
add(2)  # IR 改变，形成另一个缓存项
```

官方缓存 key 组合了以下内容的 hash：

- DSL 生成的 MLIR bytecode；
- 所有 DSL Python 源文件；
- 所有 DSL shared library；
- 所有 DSL 环境变量。

缓存 value 是 JIT Executor。

### 为什么命中前仍需生成 MLIR

Python 全局变量、helper 逻辑等动态因素可能改变最终 IR。为了判断当前程序与
过去缓存的程序是否相同，DSL 仍必须运行 meta-stage 并生成 MLIR，再计算
key。

因此：

```text
隐式缓存命中 ≠ 零 Python/IR 生成开销
```

若主机 launch latency 很敏感，官方建议显式 `cute.compile` 后自行缓存
executor。

---

## 4. 文件缓存

默认文件缓存目录：

```text
/tmp/{current_user}/cutlass_python_cache
```

它可能因重启或系统清理而消失。使用持久目录：

```bash
export CUTE_DSL_CACHE_DIR=/home/user/cute_dsl_cache
```

关闭文件缓存、保留进程内缓存：

```bash
export CUTE_DSL_DISABLE_FILE_CACHING=True
```

工程建议：

- CI 中若追求干净、可复现实验，可为每次 job 使用独立缓存目录；
- 开发机可使用持久目录减少跨进程编译；
- 修改编译器、DSL 源码或关键环境后，不要假设旧缓存仍然命中；
- 性能测量要区分冷编译、文件缓存恢复、内存命中和纯 executor 调用。

---

## 5. 字符串形式的编译选项

```python
executor = cute.compile(
    add,
    1,
    2,
    options="--opt-level 2 --generate-line-info --keep-ptx",
)
```

官方当前列出的选项：

| 选项 | 默认值 | 作用 |
|---|---:|---|
| `--opt-level` | `3` | 优化级别，范围 0–3 |
| `--enable-assertions` | false | 启用 host/device assertion |
| `--keep-cubin` | false | 保留 CUBIN |
| `--keep-ptx` | false | 保留 PTX |
| `--keep-sass` | false | 保留 SASS 反汇编 |
| `--nvdisasm-options` | `"-g -c"` | 传给 `nvdisasm` 的参数 |
| `--ptxas-options` | `""` | 传给 PTX Compiler 的参数 |
| `--generate-line-info` | false | 生成调试行号 |
| `--gpu-arch` | `""` | 指定目标 GPU 架构 |
| `--host-target` | `""` | AOT host 交叉编译目标 |
| `--enable-tvm-ffi` | false | 启用 Apache TVM FFI |

无效选项会被 `argparse` 拒绝。

### 常用调试组合

```python
debug_executor = cute.compile(
    my_kernel,
    ...,
    options=(
        "--opt-level 1 "
        "--enable-assertions "
        "--generate-line-info "
        "--keep-ptx "
        "--keep-cubin "
        "--keep-sass"
    ),
)
```

保存中间产物会增加磁盘占用，建议只在调试或汇编分析时开启。

---

## 6. 类型化编译选项

类型化写法可以更早发现拼写和组合错误：

```python
from cutlass.cute import (
    EnableAssertions,
    GenerateLineInfo,
    KeepCUBIN,
    KeepPTX,
    KeepSASS,
    NvdisasmOptions,
    OptLevel,
    PtxasOptions,
)


debug_options = (
    OptLevel(1),
    EnableAssertions,
    GenerateLineInfo,
    KeepCUBIN,
    KeepPTX,
)

executor = cute.compile[debug_options](my_kernel, ...)
```

单项或直接组合：

```python
e1 = cute.compile[OptLevel(2)](add, 1, 2)
e2 = cute.compile[EnableAssertions](add, 1, 2)
e3 = cute.compile[KeepSASS, NvdisasmOptions("-c")](add, 1, 2)
e4 = cute.compile[PtxasOptions("--opt-level=2")](add, 1, 2)
```

布尔选项类型直接写类名，DSL 会把它解释为启用该选项。

---

## 7. 可重复构建与性能测试

记录一次编译至少应包含：

```text
CUTLASS commit
GPU 架构
Python/CUDA/driver 版本
静态参数和 Layout
编译选项
缓存目录及冷/热状态
```

推荐分开测量：

1. **cold compile**：空缓存下 `cute.compile` 或首次隐式调用；
2. **disk-cache restore**：新进程从文件缓存恢复；
3. **implicit in-memory hit**：同一进程再次调用装饰函数；
4. **executor-only**：直接调用预编译 JIT Executor；
5. **device time**：使用 CUDA event 或 profiler 测 kernel，避免混入 Python
   与编译开销。

---

## 8. 常见误区

1. `cute.compile` **不会**自动复用 DSL 隐式缓存；它是显式编译入口。
2. 隐式 cache hit 前仍可能执行 Python meta-stage 和 MLIR 生成。
3. `Constexpr` 在编译后不能作为 executor 的运行时参数再次修改。
4. 文件缓存默认在 `/tmp`，不保证跨重启保留。
5. `--keep-sass` 依赖反汇编流程；保存 SASS 不等同于证明 kernel 性能更好。
6. 缓存 key 必须覆盖 ABI 和代码生成因素，不能只用输入 shape 的字符串。

## 9. 练习

1. 比较首次隐式调用、第二次隐式调用和 executor 调用的 host 时间。
2. 将同一函数分别以两个 Constexpr 值编译，确认得到两个固定 executor。
3. 设置持久 `CUTE_DSL_CACHE_DIR`，在新进程中观察文件缓存效果。
4. 以 `OptLevel(0)` 和 `OptLevel(3)` 保存 PTX/SASS，对比指令和性能。
