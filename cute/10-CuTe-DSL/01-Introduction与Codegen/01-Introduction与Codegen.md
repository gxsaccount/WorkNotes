# DSL Introduction 与 Code Generation

> 官方对应：
>
> - `cute_dsl_general/dsl_introduction.rst`
> - `cute_dsl_general/dsl_code_generation.rst`
>
> 更新：2026-09-28

## 1. CuTe DSL 是什么

CuTe DSL 是面向高性能 GPU kernel 的 Python DSL。它继承 CuTe C++ 的
Layout、Tensor、Copy 和 MMA 抽象，同时提供：

- host 与 GPU 代码的 JIT 编译；
- 基于装饰器的编程接口；
- DLPack 框架互操作；
- JIT 缓存；
- 原生标量类型与类型推导；
- 需要时直接操作底层 GPU/IR 接口的能力。

“Python DSL”不表示逐句由 Python 驱动 GPU。Python 主要承担元编程：
选择 tile、生成布局、组合算法；最终热点路径仍被编译为 GPU 代码。

---

## 2. 两个核心装饰器

### 2.1 `@cute.jit`：host 侧 JIT 入口

它可以：

- 由普通 Python 调用；
- 调用另一个 `@cute.jit`，后者在编译期内联；
- 调用普通 Python helper，helper 也在编译期内联；
- 发射 `@cute.kernel`。

```python
import cutlass
import cutlass.cute as cute


@cute.jit
def add(a: cutlass.Int32, b: cutlass.Int32):
    return a + b


result = add(2, 3)
```

调用点可传 `no_cache=True` 强制重新编译：

```python
result = add(2, 3, no_cache=True)
```

### 2.2 `@cute.kernel`：GPU kernel

普通 Python 不能直接调用 kernel。kernel 必须在 `@cute.jit` 中通过
`.launch(...)` 发射：

```python
@cute.kernel
def hello():
    tid = cute.arch.thread_idx()[0]
    cute.printf("tid=%d\n", tid)


@cute.jit
def run():
    hello().launch(
        grid=[1, 1, 1],
        block=[32, 1, 1],
    )
```

常用 launch 参数：

| 参数 | 含义 |
|---|---|
| `grid` | grid 的三维大小 |
| `block` | block 的三维大小 |
| `cluster` | 首选 cluster 大小 |
| `fallback_cluster` | 硬件无法满足首选值时的兜底 cluster |
| `smem` | 动态共享内存字节数；默认自动计算 |
| `max_number_threads` | `maxntid`/线程数约束 |
| `min_blocks_per_mp` | `minctasm`/每个 SM 的最小 block 提示 |
| `use_pdl` | 启用 Programmatic Dependent Launch |
| `cooperative` | 启用 cooperative launch |
| `smem_merge_branch_allocs` | 让互斥分支复用 shared memory，实验特性 |
| `preferred_smem_carveout` | shared memory 与 L1 carveout 提示 |

### 2.3 调用关系

| Caller | Callee | 是否允许 | 发生位置 |
|---|---|---:|---|
| Python | `@jit` | 是 | DSL runtime |
| Python | `@kernel` | 否 | 必须由 `@jit` launch |
| `@jit` | `@jit` | 是 | 编译期内联 |
| `@jit` | Python helper | 是 | 编译期内联 |
| `@jit` | `@kernel` | 是 | 通过 runtime/driver 发射 |
| `@kernel` | `@jit` | 是 | 编译期内联 |
| `@kernel` | Python helper | 是 | 编译期内联 |
| `@kernel` | `@kernel` | 否 | 不支持 device-side kernel call |

---

## 3. 为什么是 Hybrid DSL

CuTe DSL 同时使用 **AST rewrite** 和 **tracing**。

### 3.1 只做 tracing 的问题

tracing 会用代理参数执行函数，并记录实际执行到的算术和 Tensor 操作。
它简单且编译快，但只看得到“这一次走过的路径”：

```python
if predicate:
    path_a()
else:
    path_b()
```

若 tracing 时只进入 `path_a`，纯 tracing 无法自然保留 `path_b`。循环也可能按
本次迭代次数展开，数据相关控制流会被冻结。

### 3.2 AST rewrite 的作用

DSL 在执行函数前分析 Python AST，把 `for`、`while` 和 `if/else` 改写为
能生成结构化 IR 的形式。这样：

- 未被本次执行选中的分支也能保留；
- 循环能生成真正的 IR loop，而不是只能展开成直线代码；
- 后端可以继续做循环、向量化和流水优化。

AST 重写不尝试重新实现整个 Python，而是只负责程序结构。表达式和 Tensor
操作仍交给 tracing。

### 3.3 两者如何配合

```text
AST rewrite：负责“程序长什么样”
tracing：     负责“每个区域里算什么”
```

这使 Python 类、helper、元编程和多态可以在编译期展开，而 GPU 最终看到的是
结构简单、可优化的运行时代码。

---

## 4. 三阶段编译流程

### Stage 1：Pre-staging

预处理器改写被装饰函数的 AST，在循环、分支和函数边界插入回调，以便后续
显式构造结构化 IR。

### Stage 2：Meta-stage

改写后的函数在 Python 解释器中以代理参数运行：

- 控制流回调产生 loop/branch IR；
- 重载运算符记录 Tensor 与算术操作；
- 编译期已知值被部分求值并折叠；
- Python helper、对象组合和参数选择在这里发生。

### Stage 3：Object-stage

生成的 IR 经过 lowering 和优化，逐步变成硬件相关表示，最终生成
PTX/CUBIN。运行时加载模块并发射 kernel。

```text
Python AST
   ↓ preprocess
带回调的 Python 函数
   ↓ interpreter + proxy tracing
结构化 MLIR
   ↓ lowering / optimization
PTX / CUBIN
   ↓
GPU
```

---

## 5. 一段代码里的两个世界

### 5.1 动态值

```python
@cute.jit
def add_dynamic(b: cutlass.Float32):
    a = cutlass.Float32(2.0)
    result = a + b
    print("[meta]", result)
    cute.printf("[runtime] %f\n", result)


add_dynamic(5.0)
```

概念输出：

```text
[meta] <Float32 proxy>
[runtime] 7.000000
```

`result` 依赖运行时参数，因此编译期只能看到代理对象。

### 5.2 编译期常量

```python
@cute.jit
def add_constexpr(b: cutlass.Constexpr):
    result = 2.0 + b
    print("[meta]", result)
    cute.printf("[runtime] %f\n", result)


add_constexpr(5.0)
```

`b` 不进入运行时签名，Python 在 meta-stage 已能得到 `7.0`，并把常量写入
生成代码。

### 5.3 实用判断

| 想观察什么 | 使用 |
|---|---|
| shape、stride、tile、编译期选择 | `print()` |
| 线程 id、加载数据、GPU 中间值 | `cute.printf()` |

注意：同一个被装饰函数可能因不同参数或缓存未命中而重新编译，所以
`print()` 不是“每次 GPU launch 都打印”，而是“每次 meta-stage 执行时打印”。

---

## 6. 代码生成模式

默认模式是 AST rewrite + tracing：

```python
@cute.jit
def structured(...):
    ...
```

纯 tracing 模式：

```python
@cute.jit(preprocess=False)
def straight_line(...):
    ...
```

纯 tracing 只适合确认没有动态分支和循环的直线代码。否则可能只记录一次
tracing 走到的路径，造成语义错误。

> 官方 `dsl_introduction.rst` 的说明文字曾写作 `preprocessor`，但官方
> 装饰器源码和代码生成文档使用的实际关键字是 `preprocess`。

---

## 7. 练习

1. 写一个 `@cute.jit` 函数，同时使用 `print()` 和 `cute.printf()` 打印同一
   个动态参数，解释两种输出的差别。
2. 把该参数改成 `cutlass.Constexpr`，观察 meta-stage 输出变化。
3. 写一个 Python helper，让 `@cute.kernel` 调用它，确认它是编译期内联而非
   GPU 动态调用。
4. 给含动态 `if` 的函数设置 `preprocess=False`，说明为什么这种写法不安全。
