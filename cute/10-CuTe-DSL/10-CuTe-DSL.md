# 10 CuTe DSL 编程模型

> 官方对应：`media/docs/pythonDSL/cute_dsl.rst` 与
> `media/docs/pythonDSL/cute_dsl_general/`
>
> 官方基线：NVIDIA CUTLASS `main`，commit
> `098de2a652cf8f00fd70b2df54051c7eccbb855a`
>
> 本地整理：2026-09-28

## 本章解决什么问题

前九章使用 CuTe C++ 建立了 Layout、Tensor、Copy、MMA 和 TMA 的概念。
CuTe DSL 保留这些核心抽象，但把“生成 GPU 程序”放进 Python：

```text
Python 源码
   │
   ├─ AST 预处理：保留 for / while / if 的程序结构
   │
   └─ tracing：记录 Tensor、Layout 和算术操作
           ↓
       CuTe / MLIR IR
           ↓
       PTX / CUBIN
           ↓
       GPU 执行
```

理解本章最重要的分界是：

- **meta-stage（编译期）**：Python 解释器运行，构造和特化 GPU 程序；
- **object-stage（运行期）**：编译后的 host/device 代码执行；
- `cutlass.Constexpr` 属于编译期，不进入运行时函数签名；
- 普通 DSL 标量、Tensor 和动态 Layout 属于运行期；
- `print()` 看编译期对象，`cute.printf()` 看运行期值。

## 学习顺序

1. [Introduction 与 Code Generation](01-Introduction与Codegen/01-Introduction与Codegen.md)
   - `@cute.jit`、`@cute.kernel` 与调用边界；
   - AST rewrite、tracing 和三阶段编译流程；
   - meta-stage 与 object-stage。
2. [Control Flow](02-Control-Flow/02-Control-Flow.md)
   - `range`、`cutlass.range`、`cutlass.range_constexpr`；
   - 动态与静态 `if` / `while`；
   - 循环展开、软件流水和当前限制。
3. [JIT Arguments](03-JIT-Arguments/03-JIT-Arguments.md)
   - 静态参数、动态参数和类型检查；
   - 静态/动态 Layout；
   - 自定义协议、NamedTuple、frozen dataclass 与 `@native_struct`。
4. [JIT Caching 与 Options](04-JIT-Caching与Options/04-JIT-Caching与Options.md)
   - `cute.compile` 与 JIT Executor；
   - 隐式缓存、文件缓存与自定义缓存；
   - 优化、断言、PTX/CUBIN/SASS 等编译选项。

## 一条最小主线

```python
import cutlass
import cutlass.cute as cute


@cute.kernel
def print_ids():
    tid = cute.arch.thread_idx()[0]
    cute.printf("thread = %d\n", tid)


@cute.jit
def run():
    print_ids().launch(grid=[1, 1, 1], block=[32, 1, 1])


run()
```

这里：

1. Python 调用 `run()`，触发 `@cute.jit` 的动态编译；
2. `run` 是 host 端入口，负责发射 kernel；
3. `print_ids` 是 device kernel，不能直接由普通 Python 函数调用；
4. `cute.printf` 在 GPU 上执行，因此通常会看到 32 行输出。

## 本章速查

| 需求 | 应使用 |
|---|---|
| 从 Python 进入 DSL | `@cute.jit` |
| 定义 GPU kernel | `@cute.kernel` |
| 编译期常量参数 | `cutlass.Constexpr` |
| 编译期条件 | `if cutlass.const_expr(...)` |
| 运行期条件 | 普通 `if predicate` |
| 编译期展开循环 | `cutlass.range_constexpr(...)` |
| 生成 IR 循环 | `range(...)` / `cutlass.range(...)` |
| 观察编译期对象 | Python `print()` |
| 观察 GPU 运行期值 | `cute.printf()` |
| 显式编译并复用 | `cute.compile(...)` |
| 跨 shape 复用 Tensor 代码 | 动态 Layout |

## 官方资料

- [DSL Programming Model](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/cute_dsl.html)
- [CuTe DSL Python API](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/cute_dsl_api/cute.html)
- [CUTLASS GitHub](https://github.com/NVIDIA/cutlass)

## 完成标准

1. 能区分 `@cute.jit` 与 `@cute.kernel`；
2. 能判断一段语句发生在 meta-stage 还是 object-stage；
3. 能主动选择静态或动态控制流；
4. 能解释为什么某次调用复用了缓存，或为什么发生重编译；
5. 能为固定 shape 与变化 shape 选择合适的 Layout 参数策略。
