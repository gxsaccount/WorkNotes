# 08 Predication：不完整 Tile 的安全边界处理

> 官方对应：`media/docs/cpp/cute/0y_predication.md`
>
> 官方基线：NVIDIA CUTLASS `main`，文档最近一次修改提交
> `8bdbfca68287232e5bf5793145f987569ecd312e`，核对日期 2026-09-24
>
> 前置章节：[GEMM Tutorial](../07-GEMM-Tutorial/README.md) 与
> [`copy_if`](../05-Tensor-Algorithms/02-Copy-If/README.md)

前面的 GEMM 示例默认 `M`、`N`、`K` 都能被 tile 整除。本章解决实际问题：

```text
问题尺寸不能整除 tile 时，
怎样保持固定 tile 和固定循环结构，同时避免越界 load/store？
```

CuTe 的答案不是缩小最后一个 tile，而是：

```text
完整 tile + 原始逻辑坐标 + predicate
```

---

## 1. 为什么最后一个 Tile 不单独缩小

以长度 `1000` 的向量和大小 `128` 的 tile 为例：

```text
ceil_div(1000, 128) = 8
8 × 128             = 1024
```

`logical_divide` 会产生概念上的：

```text
(tile 内位置, tile 编号) = (128, 8)
```

最后一个 tile 中：

```text
104 个位置合法
24 个位置越界
```

CuTe 不把结果描述成“7 个 128 元素 tile 加 1 个 104 元素 tile”，而是仍让
8 个 tile 具有相同 Shape，再使用 predicate 屏蔽最后 24 次访问。

这样做的价值是：

- 每个 CTA、warp、线程仍执行相同形状的循环；
- tiling、copy 和 MMA 的静态结构不因边界改变；
- 不需要为各种余数分别设计 Layout；
- 同一套方法可以推广到任意 rank、任意 Stride 和任意线程分区。

注意：

```text
round-up 只保证 tiled view 能覆盖整个逻辑问题，
并不意味着越界地址可以安全访问。
```

是否访问必须由 predicate 决定。

---

## 2. 核心思想：让坐标跟着数据走

普通 Tensor 回答：

```text
逻辑坐标 → 内存地址 → 数据
```

identity coordinate Tensor 回答：

```text
逻辑坐标 → 原始逻辑坐标
```

例如：

```cpp
Tensor mC = /* shape (M,N) 的数据 Tensor */;
Tensor cC = make_identity_tensor(shape(mC));
```

二者的逻辑区别是：

```text
mC(m,n) = C 数据
cC(m,n) = (m,n)
```

接着，对 `cC` 重放与 `mC` **完全相同**的操作：

```text
CTA tiling
→ thread partition
→ value slicing
```

最终，每个线程既拿到自己的数据 view，也拿到与每个 value 一一对应的全局坐标：

```text
tCgC(i)  = 当前线程第 i 个 C 数据位置
tCcC(i)  = 该位置在原始 C 中的坐标 (m,n)
```

于是边界判断变成：

```cpp
elem_less(tCcC(i), shape(mC))
```

对于二维 Shape，它等价于：

```cpp
get<0>(tCcC(i)) < M &&
get<1>(tCcC(i)) < N
```

### 最重要的性质

数据 Tensor 和坐标 Tensor 不要求具有相同的 Engine，也不要求返回相同类型；
它们需要在 tiling 和 partition 后保持**同构（congruent）**：

```text
同一个局部索引 i
必须同时指向一个数据位置及其对应的原始逻辑坐标。
```

这就是为什么不能随意构造一个元素数量相同的 bool 数组来充当 predicate。

---

## 3. 官方方法的四个步骤

可以把官方教程归纳为固定流程：

### 第一步：为原始问题创建 identity Tensor

```cpp
Tensor coord = make_identity_tensor(shape(data));
```

### 第二步：重放数据 Tensor 的变换

数据做过什么，坐标就做什么：

```text
local_tile(data, ...)
local_partition(data_tile, ...)

local_tile(coord, ...)
local_partition(coord_tile, ...)
```

若数据使用 `TiledCopy` 或 `TiledMMA` 分区，坐标也应使用相应 slice 的同类
partition 操作。

### 第三步：坐标与原始 Shape 比较

```cpp
bool valid = elem_less(coord_element, shape(data));
```

### 第四步：在访问发生之前使用 predicate

```cpp
if (valid) {
  destination = source;
}
```

或：

```cpp
copy_if(pred, src, dst);
```

一句话记忆：

```text
不要从地址猜边界；
保存逻辑坐标，用坐标与原始 Shape 比较。
```

---

## 4. 一维例子：1000 个元素按 128 分块

官方教程先用一维问题解释完整过程：

```cpp
Tensor gmem = /* size 1000 */;
Tensor smem = /* size 128 */;

Tensor gmem_tiled = logical_divide(gmem, size(smem));  // (128,8)

Layout id_layout = make_layout(shape(gmem));           // 1000:1
Layout id_tiled  = logical_divide(id_layout,
                                  size(smem));          // (128,8):(1,128)

Tensor pred = make_tensor<bool>(shape(id_tiled));

for (int i = 0; i < size(pred); ++i) {
  pred(i) = id_tiled(i) < size(id_layout);
}
```

对第 `tile_i` 个 tile 的第 `value_j` 个位置：

```cpp
if (pred(value_j, tile_i)) {
  smem(value_j) = gmem_tiled(value_j, tile_i);
}
```

其坐标关系为：

```text
global_index = tile_i * 128 + value_j
valid        = global_index < 1000
```

前 7 个 tile 的 predicate 全为 true。最后一个 tile 中：

```text
value_j = 0..103    → true
value_j = 104..127  → false
```

`make_layout(shape(gmem))` 是一维 Layout 版本的 identity 映射；处理多维问题时，
`make_identity_tensor(shape(...))` 更直接，因为它能保留 tuple coordinate。

---

## 5. GEMM Epilogue：保护 C 的读写

假设：

```text
mC：完整 C Tensor，shape = (M,N)
gC：当前 CTA 的 C tile
tCgC：当前线程负责的 global C 子 Tensor
tCrC：当前线程的 accumulator fragment
```

数据路径：

```cpp
auto cta_coord = make_coord(blockIdx.x, blockIdx.y, _);

Tensor gC = local_tile(
    mC, cta_tiler, cta_coord, Step<_1,_1,X>{});

auto thr_mma = mma.get_slice(threadIdx.x);
Tensor tCgC = thr_mma.partition_C(gC);
Tensor tCrC = thr_mma.make_fragment_C(tCgC);
```

现在建立对应的坐标路径：

```cpp
Tensor cC = make_identity_tensor(shape(mC));

Tensor cta_cC = local_tile(
    cC, cta_tiler, cta_coord, Step<_1,_1,X>{});

Tensor tCcC = thr_mma.partition_C(cta_cC);
```

对应关系：

| 数据 Tensor | 坐标 Tensor | 含义 |
|---|---|---|
| `mC` | `cC` | 完整问题 |
| `gC` | `cta_cC` | 当前 CTA tile |
| `tCgC` | `tCcC` | 当前线程负责的位置 |
| `tCrC` | 与 `tCcC` 同构 | 当前线程的计算结果 |

带边界保护的 epilogue：

```cpp
CUTE_UNROLL
for (int i = 0; i < size(tCgC); ++i) {
  if (elem_less(tCcC(i), shape(mC))) {
    tCgC(i) = alpha * tCrC(i) + beta * tCgC(i);
  }
}
```

这个 `if` 同时保护：

- `tCgC(i)` 右侧对旧 C 的读取；
- `tCgC(i)` 左侧对新 C 的写入。

不能先无条件读取 C，再只对 store 加判断：

```cpp
// 错误：load 已经可能越界
auto old_c = tCgC(i);
if (valid) {
  tCgC(i) = alpha * tCrC(i) + beta * old_c;
}
```

### 41 × 55、Tile 为 4 × 8

CTA grid 为：

```text
ceil_div(41,4) × ceil_div(55,8) = 11 × 7
```

右下角 CTA 覆盖：

```text
m = 40..43
n = 48..55
```

合法范围是：

```text
m < 41
n < 55
```

因此该 CTA 的 32 个逻辑位置中，只有：

```text
m = 40
n = 48..54
```

共 7 个位置合法。tile 形状仍然是 `4×8`，只是另外 25 个位置不执行 global
memory 访问。

---

## 6. GEMM Mainloop：保护 A、B 的 Global Load

仅保护 C store 还不够。边界 CTA 加载 A、B 时也可能越界。

数据 Tensor 的 CTA 与线程分区：

```cpp
auto cta_coord = make_coord(blockIdx.x, blockIdx.y, _);

Tensor gA = local_tile(
    mA, cta_tiler, cta_coord, Step<_1,X,_1>{});
Tensor gB = local_tile(
    mB, cta_tiler, cta_coord, Step<X,_1,_1>{});

Tensor tAgA = local_partition(gA, tA, thread_idx);
Tensor tAsA = local_partition(sA, tA, thread_idx);

Tensor tBgB = local_partition(gB, tB, thread_idx);
Tensor tBsB = local_partition(sB, tB, thread_idx);
```

这里：

```text
A shape = (M,K)
B shape = (N,K)

tAgA shape ≈ (THR_M, THR_K, K_tile_count)
tBgB shape ≈ (THR_N, THR_K, K_tile_count)
```

为 A、B 创建 identity Tensor：

```cpp
Tensor cA = make_identity_tensor(shape(mA));  // (m,k) -> (m,k)
Tensor cB = make_identity_tensor(shape(mB));  // (n,k) -> (n,k)
```

重放 CTA tiling：

```cpp
Tensor cta_cA = local_tile(
    cA, cta_tiler, cta_coord, Step<_1,X,_1>{});
Tensor cta_cB = local_tile(
    cB, cta_tiler, cta_coord, Step<X,_1,_1>{});
```

重放线程分区：

```cpp
Tensor tAcA = local_partition(cta_cA, tA, thread_idx);
Tensor tBcB = local_partition(cta_cB, tB, thread_idx);
```

此时：

```text
tAgA(i) ↔ tAcA(i) = 对应的全局 (m,k)
tBgB(i) ↔ tBcB(i) = 对应的全局 (n,k)
```

---

## 7. 为什么 M/N Predicate 可以预计算并广播

对于固定 CTA：

- A 的 `m` 坐标不会随 mainloop 的 `k_tile` 改变；
- B 的 `n` 坐标不会随 mainloop 的 `k_tile` 改变。

因此 M、N 边界可以在 prologue 中计算一次，并在所有 K tile 中复用。

官方教程使用 stride-0 mode 表达广播：

```cpp
Tensor tApA =
    make_tensor<bool>(
        make_shape (size<0>(tAcA), size<1>(tAcA)),
        make_stride(Int<1>{},      Int<0>{}));

Tensor tBpB =
    make_tensor<bool>(
        make_shape (size<0>(tBcB), size<1>(tBcB)),
        make_stride(Int<1>{},      Int<0>{}));
```

含义：

```text
tApA shape  = (THR_M, THR_K)
tApA stride = (1, 0)
```

第二个 mode 的 stride 为 0，所以：

```text
tApA(m,0)
tApA(m,1)
tApA(m,2)
...
```

都引用同一个 predicate 值。它表达的是：

```text
这个 m 是否合法，与当前线程所搬的 k value 无关。
```

填充 predicate：

```cpp
CUTE_UNROLL
for (int m = 0; m < size<0>(tApA); ++m) {
  tApA(m,0) =
      elem_less(get<0>(tAcA(m,0,0)), shape<0>(mA));
}

CUTE_UNROLL
for (int n = 0; n < size<0>(tBpB); ++n) {
  tBpB(n,0) =
      elem_less(get<0>(tBcB(n,0,0)), shape<0>(mB));
}
```

随后可以写：

```cpp
copy_if(tApA, tAgA(_,_,k_tile), tAsA);
copy_if(tBpB, tBgB(_,_,k_tile), tBsB);
```

但这段代码只表达了 **M/N 方向**的边界保护。若 `K` 不能被 `BLK_K` 整除，
还必须处理 K 边界。

---

## 8. K Predicate 为什么必须单独处理

M/N predicate 对固定 CTA 是不变量：

```text
A 的 m 合法性：不随 k_tile 改变
B 的 n 合法性：不随 k_tile 改变
```

K predicate 则随 mainloop 位置变化：

```text
global_k = k_tile * BLK_K + tile_local_k
valid_k  = global_k < K
```

因此不能把 K predicate 错误地 stride-0 广播到所有 K tile。

完整有效条件应为：

```text
A load valid = (global_m < M) && (global_k < K)
B load valid = (global_n < N) && (global_k < K)
C store valid = (global_m < M) && (global_n < N)
```

一种直接的理解方式是，在当前 `k_tile` 上利用坐标 Tensor 计算完整条件：

```cpp
auto a_coord = tAcA(i, k_tile);  // 概念代码：得到 (m,k)
auto b_coord = tBcB(i, k_tile);  // 概念代码：得到 (n,k)

bool a_valid = elem_less(a_coord, shape(mA));
bool b_valid = elem_less(b_coord, shape(mB));
```

实际 kernel 可根据 Copy partition 的 profile，把 predicate 拆成：

```text
预计算的 M/N predicate
×
当前 K tile 的 K predicate
```

关键不是采用哪种存储形式，而是最终控制每次 global load 的条件必须覆盖它所涉及
的全部逻辑 mode。

---

## 9. `copy_if` 的 False 分支不会补零

通用 `copy_if` 的语义是：

```text
predicate == true  → 执行 copy
predicate == false → 不修改 destination
```

因此：

```cpp
copy_if(pred, gmem_tile, smem_tile);
```

不会自动把越界位置写成 0。

这对 GEMM mainloop 很重要。若 shared memory 中的无效 K 位置保留了上一轮数据，
MMA 会把旧值当成当前 tile 的输入，得到错误结果。

需要根据 kernel 的 copy 机制选择正确方案，例如：

```cpp
clear(smem_tile);
copy_if(pred, gmem_tile, smem_tile);
```

或使用明确提供 zero-fill 语义的硬件 copy / pipeline 机制。

必须分别确认三个问题：

1. predicate 为 false 时，global load 是否真的没有发生；
2. destination 无效位置最终是否为计算所需的 0；
3. 异步 copy 是否经过正确的 wait 和 barrier。

Predicate 只负责“是否访问”，不替代初始化、等待或线程同步。

---

## 10. Coordinate Predicate 与线性地址判断的区别

不要用下面这种思路替代多维边界判断：

```text
linear_offset < allocated_elements
```

对带 leading dimension、padding、非紧凑 Stride 或子视图的 Tensor，某个线性地址
落在已分配内存中，并不代表它对应的是合法逻辑元素。

Coordinate Tensor 只依赖：

```text
原始逻辑坐标
原始逻辑 Shape
```

不依赖：

```text
数据类型大小
内存基址
row-major / column-major
leading dimension
任意复杂 Stride
```

这也是该方法能统一处理 Layout、TiledCopy 和 TiledMMA 的原因。

---

## 11. 四类 Predicate 不要混淆

| Predicate | 保护对象 | 典型条件 | 生命周期 |
|---|---|---|---|
| M predicate | A load | `m < M` | 固定 CTA 内通常可复用 |
| N predicate | B load | `n < N` | 固定 CTA 内通常可复用 |
| K predicate | A/B load | `k < K` | 通常随 `k_tile` 改变 |
| C predicate | C load/store | `m < M && n < N` | epilogue 使用 |

有时会把 M 与 K 合成一个 A predicate、把 N 与 K 合成一个 B predicate。无论
组织方式如何，都要检查：

```text
每一次可能越界的 global-memory 操作，
是否在访问发生之前被完整条件保护。
```

---

## 12. 常见错误

### 错误 1：只用 `ceil_div` 扩大 grid

`ceil_div` 只保证边界 CTA 被调度，不保证其内存访问安全。

### 错误 2：缩短边界 CTA 的 Tensor Shape

动态改变 tile Shape 会破坏固定 partition、固定循环和 MMA 结构。CuTe 的常规
方法是保持完整 tile，使用 predicate。

### 错误 3：数据与坐标使用不同的 partition

这样 `pred(i)` 将不再描述 `data(i)` 的坐标，可能放行错误地址。

### 错误 4：只保护 C store

A、B 的 global load 可能在进入 epilogue 前就已经越界。

### 错误 5：只检查 M/N，忘记最后一个 K tile

这会让 mainloop 在 `K % BLK_K != 0` 时读取越界数据。

### 错误 6：认为 `copy_if(false, ...)` 会写零

通用 `copy_if` 不写 destination。无效输入必须通过清零或 zero-fill 机制处理。

### 错误 7：先读取，再判断是否写入

predicate 必须包住所有可能越界的 load 与 store。

### 错误 8：用物理地址代替逻辑坐标判断

Predication 关心的是逻辑问题边界，不是地址是否落在某个已分配缓冲区中。

---

## 13. 调试与验证清单

建议至少测试以下尺寸：

```text
1. M、N、K 都能整除 tile
2. 只有 M 不整除
3. 只有 N 不整除
4. 只有 K 不整除
5. M、N、K 都不整除
6. M/N/K 小于对应 tile 尺寸
7. 某一维等于 1
```

正确性验证：

```text
GPU result vs CPU reference
```

内存安全验证：

```text
compute-sanitizer --tool memcheck <program>
```

调试时打印或检查：

```text
data Tensor 的 Shape
coordinate Tensor 的 Shape
partition 后二者是否 congruent
边界 CTA 中每个线程的坐标
predicate 的 true/false 分布
无效 shared-memory 位置是否为 0
```

---

## 14. 本章最小心智模型

```text
数据 Tensor
    │ 相同 tiling / partition
    ▼
当前线程的数据位置

Identity Coordinate Tensor
    │ 相同 tiling / partition
    ▼
当前线程数据位置对应的全局逻辑坐标
    │ 与原始 Shape 比较
    ▼
predicate
    │
    ├─ true  → 允许 load/store
    └─ false → 跳过访问；需要时另行补零
```

不要记成“为最后一个 tile 写特殊代码”，而要记成：

```text
tile 始终完整；
坐标保留来源；
访问由边界谓词决定。
```

---

## 15. 自测

1. 为什么 `logical_divide` round-up 后不能直接访问最后一个完整 tile？
2. identity coordinate Tensor 中保存的是数据、地址还是逻辑坐标？
3. 为什么坐标 Tensor 必须重放数据 Tensor 的 tiling 和 partition？
4. `elem_less(make_coord(m,n), make_shape(M,N))` 表达什么条件？
5. GEMM epilogue 的 predicate 要保护哪些 global-memory 操作？
6. 为什么 M/N predicate 可以跨 K-loop 复用，而 K predicate 通常不可以？
7. `copy_if` 的 predicate 为 false 时，destination 会变成 0 吗？
8. 为什么最后一个 K tile 的无效 shared-memory 位置必须具有确定值？
9. 仅测试 `M=N=K=tile_size` 为什么无法验证 predication？
10. Coordinate Tensor 方法为什么不依赖原数据的 Stride？

## 学完标准

你应该能够为一个已有 GEMM kernel：

1. 为 A、B、C 建立 identity coordinate Tensor；
2. 对坐标重放 CTA 与线程级分区；
3. 为 A load 构造 M/K 边界条件；
4. 为 B load 构造 N/K 边界条件；
5. 为 C epilogue 构造 M/N 边界条件；
6. 明确处理 predicate false 时 shared memory 的零填充；
7. 用非整除尺寸和 `compute-sanitizer` 验证正确性与内存安全。

## 官方资料

- [CuTe Predication Tutorial](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0y_predication.html)
- [官方 Markdown](https://github.com/NVIDIA/cutlass/blob/main/media/docs/cpp/cute/0y_predication.md)
- [`copy_if` 所在的 `copy.hpp`](https://github.com/NVIDIA/cutlass/blob/main/include/cute/algorithm/copy.hpp)
