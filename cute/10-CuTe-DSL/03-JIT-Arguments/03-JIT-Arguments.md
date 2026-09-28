# JIT Arguments

> 官方对应：
>
> - `cute_dsl_general/dsl_jit_arg_generation.rst`
> - `cute_dsl_general/dsl_dynamic_layout.rst`
> - `cute_dsl_general/dsl_struct_types.rst`
>
> 更新：2026-09-28

## 1. 参数如何进入 JIT 函数

当 `@cute.jit` 或 `@cute.kernel` 被调用时，DSL 根据调用点参数和类型注解
生成函数签名。

四条规则：

1. 默认按**动态参数**处理；
2. 标注 `cutlass.Constexpr` 后成为**静态参数**；
3. 有类型注解时，编译期校验类型；
4. 自定义类型可实现 JIT argument 协议，或注册 adapter。

---

## 2. 静态参数与动态参数

### 2.1 动态参数

动态参数进入生成函数的运行时签名：

```python
@cute.jit
def foo(x: cutlass.Int32):
    print("meta x =", x)
    cute.printf("runtime x = %d\n", x)


foo(2)
```

编译期看到的是代理对象，真正的整数在运行时传入。

### 2.2 静态参数

```python
@cute.jit
def foo(x: cutlass.Int32, y: cutlass.Constexpr):
    print("meta y =", y)
    return x + y


foo(2, 3)
```

`y`：

- 在 meta-stage 就是普通 Python 值；
- 不进入生成函数的运行时签名；
- 能参与 Python 元编程和编译期分支；
- 不同值可能产生不同 IR 和不同缓存项。

静态参数不只可以是数字，也可以是编译期 callable：

```python
@cute.kernel
def epilogue_kernel(..., epilogue_op: cutlass.Constexpr):
    ...
    result = epilogue_op(accumulator)
```

调用时可传 lambda，例如 ReLU。lambda 在代码生成期间被应用，不是 GPU 上的
Python 回调。

### 2.3 类型安全

```python
@cute.jit
def foo(x: cute.Tensor, scale: cutlass.Float16):
    ...
```

若调用点把整数传给 `x`、把 Tensor 传给 `scale`，DSL 会在编译期报告参数
类型不匹配，而不是让错误延迟到 kernel 运行。

---

## 3. 静态 Layout 与动态 Layout

### 3.1 静态 Layout

显式 `from_dlpack` 后传入的 `cute.Tensor` 会保留具体 shape：

```python
import torch
from cutlass.cute.runtime import from_dlpack


@cute.jit
def show(tensor):
    print("layout =", tensor.layout)


a = torch.tensor([1, 2, 3], dtype=torch.uint16)
a_cute = from_dlpack(a)
compiled = cute.compile(show, a_cute)
compiled(a_cute)
```

编译器看到的 Layout 类似：

```text
(3):(1)
```

此 JIT Executor 的运行时 ABI 也期待对应的 Tensor 类型。如果直接把 shape
为 `(5,)` 的 Tensor 传给它，执行器仍可能按 `(3):(1)` 解释数据；不能把
“底层指针兼容”误当成“Tensor 类型兼容”。

固定 shape 的优点：

- size、stride 等信息可在编译期传播；
- 更容易展开循环、消除分支；
- 可能得到更充分的特化优化。

代价是不同 shape 通常需要不同编译版本。

### 3.2 动态 Layout

直接把框架 Tensor 交给 `cute.compile`/JIT 调用时，DSL 会按 leading
dimension 自动调用 `cute.mark_layout_dynamic`：

```python
@cute.jit
def show(tensor):
    print("layout =", tensor.layout)


a = torch.tensor([[1, 2], [3, 4]], dtype=torch.uint16)
compiled = cute.compile(show, a)
compiled(a)

b = torch.tensor(
    [[11, 12], [13, 14], [15, 16]],
    dtype=torch.uint16,
)
compiled(b)
```

动态 Layout 类似：

```text
(?,?):(?,1)
```

同一个编译结果可服务多个兼容 shape。需要更细粒度控制时，可使用
`cute.mark_compact_shape_dynamic` 指定哪些 mode 动态以及动态维度的
divisibility 约束。

### 3.3 动态 Layout 也会改变控制流

```python
@cute.jit
def print_all(tensor):
    for i in range(cute.size(tensor)):
        cute.printf("%d\n", tensor[i])
```

- 静态 Layout：`cute.size(tensor)` 可在编译期已知，编译器可进一步特化；
- 动态 Layout：size 是运行时值，必须生成运行期循环。

选择原则：

| 场景 | 建议 |
|---|---|
| shape 固定、追求极致特化 | 静态 Layout |
| shape 经常变化、关注编译复用 | 动态 Layout |
| 只有部分维度变化 | 细粒度 dynamic marking |

---

## 4. 自定义 JIT 参数协议

### 4.1 `JitArgument`

用于从 Python 调用 host JIT 函数的对象，需要能够：

- `__c_pointers__()`：生成 C ABI 指针列表；
- `__get_mlir_types__()`：给出对应 MLIR 类型；
- `__new_from_mlir_values__()`：从 MLIR values 重建对象。

### 4.2 `DynamicExpression`

用于 host JIT 调用 device JIT/kernel 时的动态表达式，需要：

- `__extract_mlir_values__()`：提取动态 MLIR values；
- `__new_from_mlir_values__()`：从 values 重建对象。

简化示例：

```python
class TensorWithOffset:
    def __init__(self, tensor, offset):
        self.tensor = tensor
        self.offset = offset

    def __extract_mlir_values__(self):
        return [
            self.tensor.__extract_mlir_values__(),
            self.offset.__extract_mlir_values__(),
        ]

    def __new_from_mlir_values__(self, values):
        return TensorWithOffset(values[0], values[1])
```

协议的核心是“一个 Python 对象可以展开成多个底层参数，并在 JIT 函数内部
重建为原来的结构”。

### 4.3 第三方类型 adapter

不能修改第三方类时，注册 adapter：

```python
@cutlass.register_jit_arg_adapter(MyFrameworkObject)
class MyFrameworkObjectAdapter:
    def __init__(self, arg):
        self.arg = arg

    def __c_pointers__(self):
        return [self.arg.get_cabi_pointer()]

    def __get_mlir_types__(self):
        return [self.arg.get_data().mlir_type]

    def __new_from_mlir_values__(self, values):
        return MyFrameworkObject(values[0])
```

这样可把框架对象与 DSL 的 ABI 适配逻辑分离。

---

## 5. Struct-like 参数

### 5.1 选择表

| 类型 | 字段可变 | 适用场景 |
|---|---:|---|
| `typing.NamedTuple` | 否 | 只读参数、Python 风格 tuple |
| `@dataclass(frozen=True)` | 否 | 只读配置、pytree 容器 |
| `@cute.native_struct` | 是 | kernel 内累加或更新状态 |

### 5.2 NamedTuple

```python
from typing import NamedTuple


class Vec3(NamedTuple):
    x: cutlass.Int32
    y: cutlass.Int32
    z: cutlass.Int32


@cute.jit
def print_vec(v: Vec3):
    cute.printf("x=%d y=%d z=%d\n", v.x, v.y, v.z)
```

DSL 通过 pytree 逐字段 flatten，在函数体中重新构造 NamedTuple。字段可参与
动态循环和分支，但不能写：

```python
v.x = v.x + 1  # AttributeError
```

需要修改时构造新值：

```python
scaled = Vec3(v.x * 2, v.y * 2, v.z * 2)
```

### 5.3 `@cute.native_struct`

```python
@cute.native_struct
class Accumulator:
    total: cutlass.Int32
    count: cutlass.Int32


@cute.jit
def accumulate(acc: Accumulator, values: cute.Tensor, n: cutlass.Int32):
    for i in range(n):
        acc.total = acc.total + values[i]
        acc.count = acc.count + cutlass.Int32(1)
```

字段写入会生成 `llvm.insertvalue`。额外选项：

- `zero_init=False`：以 `llvm.mlir.undef` 而非零初始化；
- `packed=True`：生成无 padding 的 packed LLVM struct；
- `Constexpr` 字段：不进入 native struct，仍按普通 Python 编译期值处理。

---

## 6. 常见误区

1. **无注解不等于静态。** 默认参数是动态参数。
2. **Constexpr 不进入 ABI。** 已编译 executor 的运行时调用不再传该参数。
3. **指针能传入不代表 Layout 匹配。** 错误静态 Layout 可能静默截断或越界。
4. **动态 Layout 不等于任意 Layout。** rank、stride 模式和约束仍须兼容。
5. **自定义对象不会自动变成一个 opaque 参数。** 它需要协议或 adapter 明确
   展开方式。

## 7. 练习

1. 编译一个静态 `(3,)` Tensor executor，再错误传入 `(5,)` Tensor，解释
   为什么输出可能只含前三项。
2. 改用框架 Tensor 的动态 Layout，让一个 executor 正确处理两种 shape。
3. 用 NamedTuple 传入三个动态标量，再改用 `native_struct` 实现原地累计。
4. 写一个两字段自定义动态表达式，列出它展开后的 MLIR value 数量。
