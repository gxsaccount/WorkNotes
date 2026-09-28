# AOT 与 Framework Integration

> 官方资料：
> [AOT Compilation](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/ahead_of_time_compilation.html)、
> [TVM FFI Compilation](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/tvm_ffi_compilation.html)、
> [Framework Integration](https://docs.nvidia.com/cutlass/latest/media/docs/pythonDSL/guides/framework_integration.html)
>
> 更新：2026-09-28

## 先按目标选路径

| 目标 | 推荐路径 |
|---|---|
| Python 中快速调用 CuTe DSL | JIT + 隐式 tensor conversion |
| 精确控制动态 Shape/Stride | `from_dlpack` + `mark_*_dynamic` |
| PyTorch/JAX eager 低 host overhead | TVM FFI |
| 生产环境不允许首次 JIT | AOT export |
| C/C++ 静态或动态链接 | CuTe ABI AOT |
| 跨框架稳定高层 ABI | TVM FFI AOT |

不要一开始同时使用所有机制。先明确问题是：

```text
需要零拷贝？
需要动态 Shape？
需要降低调用开销？
需要完全移除部署端 JIT？
调用方是 Python 还是 C++？
```

## 1. Framework tensor 到 CuTe tensor

### 隐式转换

DLPack-compatible tensor 可以直接传给 JIT function：

```python
@cute.jit
def launch(src):
    print(src)

launch(torch_tensor)
```

运行时会把输入适配成 CuTe tensor。适合原型和低频调用。

### 显式 `from_dlpack`

```python
from cutlass.cute.runtime import from_dlpack

cute_tensor = from_dlpack(torch_tensor)
```

这是零拷贝视图：

```text
PyTorch tensor ─┐
                ├─ 共用同一块底层存储
CuTe tensor ────┘
```

因此必须保证原始 framework tensor 的生命周期覆盖 CuTe tensor 的使用。

显式转换适合：

- 缓存转换结果；
- 控制 alignment；
- 控制 stride 使用 32-bit 或 64-bit；
- 指定哪些 Shape/Stride 在编译时动态。

## 2. 静态与动态 Layout

`from_dlpack` 默认产生较静态的 layout。若把运行时 Shape 全部固化进
编译结果，输入变化可能触发新的 JIT specialization。

### 全 layout 动态

```python
cute_tensor = from_dlpack(torch_tensor)
cute_tensor = cute_tensor.mark_layout_dynamic()
```

它通常保留：

- leading dimension 的 unit stride；
- 表示 broadcast 的 zero stride。

其余 Shape/Stride 变为动态。

### 只让 compact Shape 动态

```python
cute_tensor = from_dlpack(torch_tensor)
cute_tensor = cute_tensor.mark_compact_shape_dynamic(
    mode=...,
    divisibility=...,
)
```

选择原则：

```text
更静态:
  更强编译期优化
  更多 specialization/cache entry

更动态:
  一个编译结果覆盖更多输入
  运行时地址计算和约束更多
```

## 3. TVM FFI：降低框架调用开销

TVM FFI 路径的核心是：

```text
编译时:
FakeTensor 描述 dtype、Shape、Stride 和约束

运行时:
直接传 torch.Tensor 等 DLPack-compatible tensor
```

### 创建 FakeTensor

```python
n = cute.sym_int(divisibility=16)

fake_a = cute.runtime.make_fake_compact_tensor(
    cute.Float32,
    (n,),
    assumed_align=16,
)
fake_b = cute.runtime.make_fake_compact_tensor(
    cute.Float32,
    (n,),
    assumed_align=16,
)
```

FakeTensor 只有元数据，没有真实 storage，不能读写元素。

### 编译

```python
compiled = cute.compile(
    add_one,
    fake_a,
    fake_b,
    options="--enable-tvm-ffi",
)
```

### 运行时直接传框架 tensor

```python
a = torch.arange(128, device="cuda", dtype=torch.float32)
b = torch.empty_like(a)

compiled(a, b)
```

TVM FFI 会进行编译后的参数检查，包括：

- tensor 类型；
- dtype；
- Shape 变量之间的相等关系；
- divisibility；
- alignment。

## 4. CUDA stream

框架集成必须保证 kernel 发到正确 stream。

可以显式传入支持 CUDA stream protocol 的对象：

```python
compiled(a, b, stream=torch.cuda.current_stream())
```

也可以按官方 TVM FFI 方式使用 environment stream，让调用自动采用当前
framework stream。

错误 stream 可能导致：

```text
前一个 framework op 尚未写完
→ CuTe kernel 提前读取

或

CuTe kernel 尚未写完
→ 后一个 framework op 提前读取
```

这种错误不一定每次复现。

## 5. CuTe ABI AOT

AOT 的目标是：

```text
开发/构建环境:
Python DSL → 编译 → .h + .o

部署环境:
加载或链接产物 → 直接调用
```

### 导出

```python
compiled = cute.compile(my_function, ...)

compiled.export_to_c(
    file_path="./artifacts",
    file_name="my_kernel",
    function_prefix="my_kernel",
)
```

典型产物：

```text
artifacts/my_kernel.h
artifacts/my_kernel.o
```

object 中包含 host entry、GPU fatbin 和运行时元数据。

### Python 加载

```python
module = cute.runtime.load_module(
    "./artifacts/my_kernel.o"
)

module.my_kernel(cute_tensor, stream=stream)
```

这里不再发生 kernel JIT compilation。

### C++ 集成

两种方式：

```text
静态链接:
  include 生成的 header
  链接生成的 object 和 runtime library

动态加载:
  CuteDSLRT_Module_Load
  → CuteDSLRT_Module_Get_Function
  → CuteDSLRT_Function_Run
  → CuteDSLRT_Module_Destroy
```

生成符号必须具有唯一 `function_prefix`，避免多个导出模块发生冲突。

## 6. AOT 错误处理

CuTe ABI wrapper 返回 CUDA launch submission 的错误码：

```text
0             → launch 提交成功
非 0          → 某次 cudaLaunchKernelExC 提交失败
```

它不保证异步 kernel 已经正确执行完毕。非法地址等执行期错误仍需：

```cpp
cudaStreamSynchronize(stream);
// 或 cudaDeviceSynchronize()
```

动态加载时还要区分两层错误：

```text
CuteDSLRT_Error_t
  模块加载、符号查找、runtime 调用错误

cudaError_t
  实际 CUDA kernel launch 错误
```

不要把其中一个状态吞掉。

## 7. TVM FFI AOT

需要高层跨框架 ABI 时：

```python
compiled = cute.compile(
    function,
    fake_inputs,
    options="--enable-tvm-ffi",
)

compiled.export_to_c(
    "./kernel.o",
    function_name="kernel",
)
```

随后将 object 与：

```python
cute.runtime.find_runtime_libraries(
    enable_tvm_ffi=True
)
```

返回的 runtime libraries 链接成 shared library。

TVM FFI AOT 适合：

- 直接接收 `torch.Tensor` 等 framework tensor；
- 使用动态 Shape 约束；
- 减少 Python/DLPack 调用开销；
- 通过 TVM FFI registry 或导出符号从 C++ 调用。

## 8. 三种路径对比

| 项目 | 普通 JIT/DLPack | TVM FFI | CuTe ABI AOT |
|---|---|---|---|
| 开发便利性 | 最高 | 中等 | 较低 |
| 首次编译 | 运行时 | 通常显式提前编译 | 构建期 |
| Framework tensor | DLPack 转换 | 可直接传入 | 需适配生成 ABI |
| 动态 Shape 约束 | `mark_*_dynamic` | FakeTensor/symbolic constraint | 受导出 ABI 支持范围约束 |
| Python 调用 | 支持 | 支持 | 可加载模块调用 |
| C/C++ 调用 | 不适合直接部署 | 支持 registry/extern C | 支持静态或动态链接 |

## 9. 部署前检查

```text
[ ] 输入 dtype、rank、Shape、Stride 和 alignment 是否进入 ABI？
[ ] 哪些维度是静态，哪些是动态？
[ ] cache key 是否与动态策略一致？
[ ] framework tensor 生命周期是否覆盖异步 kernel？
[ ] 是否使用正确 CUDA stream？
[ ] AOT 目标 GPU 架构是否覆盖部署机器？
[ ] host object 架构是否匹配部署 CPU？
[ ] runtime library 版本是否与导出产物兼容？
[ ] launch error 和异步执行错误是否分别检查？
```

## 常见误解

1. **“DLPack 转换会复制 tensor。”**
   通常是零拷贝视图，因此源 tensor 生命周期非常重要。
2. **“AOT 后就不需要 CUDA runtime。”**
   AOT 删除 JIT 编译延迟，不会删除 kernel 加载、launch 和 runtime
   依赖。
3. **“动态 Shape 越多越好。”**
   动态性减少 specialization，但也减少编译期信息。
4. **“wrapper 返回成功表示 kernel 执行正确。”**
   它可能只表示异步 launch 提交成功。
5. **“TVM FFI 与 CuTe ABI 是同一个 ABI。”**
   两者的参数表示、错误约定和框架互操作目标不同。
