# DSL Control Flow

> 官方对应：`cute_dsl_general/dsl_control_flow.rst`
>
> 更新：2026-09-28

## 1. 核心规则

CuTe DSL 会检查 Python AST，并根据条件或边界属于编译期值还是 IR 值，
决定控制流在哪里执行：

```text
编译期控制流：Python 当场执行，生成代码时已消失
运行期控制流：生成结构化 IR，在 host/device 运行时执行
```

不能把动态 IR 值强行交给只在 Python 编译期执行的控制流。

---

## 2. 三种 `for` 循环

| 写法 | 执行阶段 | 特点 |
|---|---|---|
| `range(...)` | 运行期 IR | 即使边界是 Python 值，也生成 IR loop |
| `cutlass.range(...)` | 运行期 IR | 支持展开和软件流水控制 |
| `cutlass.range_constexpr(...)` | 编译期 | 由 Python 完全展开 |

### 2.1 `range`

```python
@cute.jit
def print_dynamic(bound: cutlass.Int32):
    for i in range(bound):
        cute.printf("%d\n", i)
```

这里 `bound` 是运行时标量，循环必须保留到生成代码中。

即使写成：

```python
for i in range(10):
    ...
```

在 DSL 预处理器中，它仍按 IR loop 处理，而不是普通 Python `range` 的
编译期循环。

### 2.2 `cutlass.range`

它与 `range` 一样生成 IR loop，但可附带编译提示：

```python
for i in cutlass.range(bound, unroll=2):
    cute.printf("%d\n", i)
```

这表示让循环按因子 2 展开。提示不等于无条件保证最终机器码一定采用某个
展开形式，后端仍会参与优化。

### 2.3 `cutlass.range_constexpr`

```python
@cute.jit
def print_static():
    n = 4
    for i in cutlass.range_constexpr(n):
        cute.printf("%d\n", i)
```

Python 在 meta-stage 展开四次，IR 中不再保留循环。

下面是错误用法：

```python
@cute.jit
def wrong(bound: cutlass.Int32):
    for i in cutlass.range_constexpr(bound):
        ...
```

`bound` 是运行时 IR 值，Python 编译期不知道它的整数值。

### 2.4 怎么选

- tile stage、固定维数、固定小循环：考虑 `range_constexpr`；
- 依赖输入尺寸、线程数据或动态 Layout：使用 `range`；
- 还需要 unroll/pipeline 提示：使用 `cutlass.range`；
- 不要为“消灭所有循环”盲目 constexpr 展开，大循环会增加 IR 和代码体积。

---

## 3. `if / elif / else`

### 3.1 运行期分支

普通谓词默认降低为 IR：

```python
@cute.jit
def classify(x: cutlass.Int32):
    if x >= 0:
        cute.printf("non-negative\n")
    else:
        cute.printf("negative\n")
```

### 3.2 编译期分支

使用 `cutlass.const_expr(...)` 明确要求 Python 在 meta-stage 决策：

```python
@cute.jit
def choose(do_relu: cutlass.Constexpr):
    if cutlass.const_expr(do_relu):
        print("compile ReLU path")
    else:
        print("compile identity path")
```

这种模式常用于 kernel 特化：

```python
@cute.kernel
def gemm(..., do_relu: cutlass.Constexpr):
    ...
    if cutlass.const_expr(do_relu):
        # 仅 do_relu=True 的版本含有这段 IR
        ...
```

`do_relu=True` 和 `False` 会形成不同的特化版本，但运行时没有这次判断。

### 3.3 典型错误

```python
@cute.jit
def wrong(x: cutlass.Int32):
    if cutlass.const_expr(x == 10):
        ...
```

`x == 10` 只能到运行时才能确定，不能包装成编译期表达式。

---

## 4. `while`

规则与 `if` 相同。

运行期：

```python
@cute.jit
def countdown(x: cutlass.Int32):
    while x > 0:
        cute.printf("%d\n", x)
        x -= 1
```

编译期：

```python
@cute.jit
def emit_ten_times():
    n = 0
    while cutlass.const_expr(n < 10):
        cute.printf("%d\n", n)
        n += 1
```

编译期 `while` 必须确保 Python 条件最终变为假，否则会在代码生成阶段形成
死循环。

---

## 5. 软件流水

多 stage copy/compute 循环通常手工写成：

```text
预取前 N 个 tile
for 当前 tile:
    预取未来 tile
    等待当前 tile
    计算当前 tile
```

`cutlass.range` 可请求编译器生成这类流水：

```python
for i in cutlass.range(k_tiles, prefetch_stages=stages):
    cute.copy(
        tma_atom,
        gmem[i],
        smem[i % total_stages],
        tma_bar_ptr=mbar_ptr,
    )
    # 等待与 mbarrier 配对的当前 stage
    use(smem[i % total_stages])
```

编译器会尝试生成预取循环和主循环。当前官方限制：

- 属于实验特性；
- 仅支持 SM90 及以上；
- 必须识别到合法 split point：
  - TMA bulk copy 与同一 mbarrier 的 wait；或
  - canonical `cp.async` group；
- `cp.async` 形式要求循环从 0 开始、步长为 1，并使用
  `i % stages` 访问 circular buffer；
- 无法识别时会警告
  `software pipelining ('prefetch_stages') skipped`，随后不做流水化。

因此“写了 `prefetch_stages`”并不等于流水一定生效，必须查看编译警告与
生成代码。

---

## 6. 动态控制流限制

当前动态控制流 body 不支持：

- `break`；
- `continue`；
- `pass`；
- 从 body 中 `return`；
- 从 body 中抛异常；
- 在 body 内改变已有变量的类型；
- 把只在动态 body 内创建的值直接拿到 body 外使用。

错误示例：

```python
@cute.jit
def invalid(pred: cutlass.Boolean):
    if pred:
        value = cutlass.Int32(10)

    # value 只在一个动态分支中定义
    cute.printf("%d\n", value)
```

应改为在控制流前定义类型稳定的状态，并在每个路径中更新它：

```python
@cute.jit
def valid(pred: cutlass.Boolean):
    value = cutlass.Int32(0)
    if pred:
        value = cutlass.Int32(10)
    cute.printf("%d\n", value)
```

---

## 7. 速查表

| 写法 | 运行期 | 编译期 |
|---|---:|---:|
| `if pred` | 是 | 否 |
| `if cutlass.const_expr(pred)` | 否 | 是 |
| `while pred` | 是 | 否 |
| `while cutlass.const_expr(pred)` | 否 | 是 |
| `for i in range(...)` | 是 | 否 |
| `for i in cutlass.range(...)` | 是 | 否 |
| `for i in cutlass.range_constexpr(...)` | 否 | 是 |

## 8. 练习

1. 用三种 range 分别实现 4 次打印，并比较生成 IR 的循环/展开差异。
2. 用 `Constexpr` 开关控制可选 epilogue，确认两个特化版本中只有一个包含
   epilogue IR。
3. 写一个动态循环，故意加入 `break`，记录编译器报错，再改写成谓词控制。
4. 为一个 TMA circular buffer 循环添加 `prefetch_stages`，确认是否出现
   “pipelining skipped”警告。
