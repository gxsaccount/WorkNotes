# copy_if

> 官方对应：`include/cute/algorithm/copy.hpp` 与 `0y_predication.md`
>
> 更新：2026-09-16

`copy_if` 是带 predicate 的 copy：

```text
pred(i) 为真  → dst(i) = src(i)
pred(i) 为假  → 不写 dst(i)
```

它主要用于处理不能被 tile 整除的问题边界。

## 1. 基本接口与语义

通用接口可以概括为：

```cpp
copy_if(pred, src, dst);
```

其核心循环是：

```cpp
for (int i = 0; i < size(dst); ++i) {
  if (pred(i)) {
    dst(i) = src(i);
  }
}
```

predicate 可以是 bool Tensor，也可以是按需计算布尔值的 transform Tensor。

## 2. false 时目标保持不变

假设：

```text
src  = [10, 20, 30, 40]
dst  = [-1, -1, -1, -1]
pred = [ T,  F,  T,  F]
```

执行后：

```text
dst = [10, -1, 30, -1]
```

false predicate 不是“写零”，而是“完全跳过这次写入”。

如果后续计算要求越界位置为零，调用者必须预先：

```cpp
clear(dst);
copy_if(pred, src, dst);
```

或使用具有 zero-fill 语义的特定硬件 copy 机制；不能从通用 `copy_if` 推导出
自动补零。

## 3. predicate Tensor 从哪里来

处理边界时，常见方法是同时构造：

1. 数据 Tensor：访问实际数据；
2. identity coordinate Tensor：保存每个位置对应的逻辑坐标；
3. predicate Tensor：比较坐标与问题 Shape。

抽象过程：

```text
tile 内局部位置
      ↓
对应的全局逻辑坐标
      ↓ 与 problem shape 比较
true / false
```

例如矩阵 A 的某个 tile：

```cpp
pred(m, k) =
    global_m(m, k) < M &&
    global_k(m, k) < K;
```

随后：

```cpp
copy_if(pred, gmem_tile, smem_tile);
```

完整的 identity coordinate Tensor 构造方式放在
[Predication](../../08-Predication/README.md) 章节学习。

## 4. 为什么 predicate 要与 copy 分区一致

predicate 必须描述“当前线程、当前 value”对应的数据是否合法。

若数据经过 TiledCopy 分区：

```text
thread-value position
        ↓
global data coordinate
        ↓
boundary predicate
```

predicate 的逻辑顺序若与 `src`、`dst` 不一致，就可能放行越界 load、错误跳过
合法元素，或让某个线程的 predicate 控制另一个线程的数据。

所以 predicate 不是一个仅按元素数量配对的随意 bool 数组，而应由与数据相同的
tiling/partitioning 过程得到。

## 5. 与 Copy Atom 配合

接口也可以显式指定 Copy Atom：

```cpp
copy_if(copy_atom, pred, src, dst);
```

对于带 Atom 的形式，Tensor 通常组织为：

```text
pred: ([V], Rest...)
src:  ( V,  Rest...)
dst:  ( V,  Rest...)
```

`V` 是一次基础 copy 指令处理的 value mode，`Rest...` 是外层重复空间。
当前官方实现要求相关 rank 匹配；旧式“传一个普通 predicate 函数”的 Atom
重载已标记 deprecated，优先使用 bool Tensor 或 transform Tensor。

## 6. predicate 的广播

某些边界条件在一个 mode 上恒定，可以用 stride-0 mode 广播 predicate，
避免重复存储。

例如，一个 tile 中某个 `m` 位置是否合法，可能与 `k` 无关：

```text
pred shape  = (M_values, K_values)
pred stride = (1, 0)
```

这表示同一个 `m` predicate 在所有 `k` 位置复用。

广播成立的前提是逻辑判断确实与被广播的 mode 无关。若最后一个 K tile 也可能
越界，就必须单独处理 K predicate，不能错误地广播为恒真。

## 7. 典型 global → shared 流程

```cpp
// 1. 若无效位置必须为 0，先初始化目标 tile
clear(smem_tile);

// 2. 只加载合法的 global-memory 元素
copy_if(pred, gmem_tile, smem_tile);

// 3. 等待底层异步事务完成（若使用异步 copy）
// copy_wait(...);

// 4. 保证参与线程都能看到完整 shared-memory tile
__syncthreads();
```

具体 wait API 取决于 Copy Atom 或 pipeline。上面只展示职责顺序，不应直接当成
任意架构都适用的完整代码。

## 8. 常见错误

### 错误 1：认为 false 会写零

通用 `copy_if` 不写目标，必须自行初始化无效位置。

### 错误 2：只检查线性 offset

矩阵边界通常要按坐标 mode 分别判断，例如 `m < M`、`n < N`、`k < K`。

### 错误 3：predicate 与数据采用不同分区

predicate 必须和线程实际负责的 value 对齐。

### 错误 4：只保护 store，不保护 load

越界 global load 本身就可能非法，predicate 应在读源数据之前生效。

### 错误 5：忽略异步同步

predicate 只决定是否发起搬运，不负责等待已发起的异步事务完成。

## 9. 自测

1. `copy_if` 的 false 分支会修改 `dst` 吗？
2. 为什么经 predicated copy 写入 shared memory 前经常先 `clear`？
3. predicate 为什么应经过与数据相同的 partition？
4. stride-0 predicate 广播适用于什么条件？
5. predicate 能否替代异步 copy 的 wait/barrier？

## 官方资料

- [CuTe Tensor Algorithms：copy_if](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/04_algorithms.html#copy-if)
- [CuTe Predication Tutorial](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0y_predication.html)
- [copy.hpp](https://github.com/NVIDIA/cutlass/blob/main/include/cute/algorithm/copy.hpp)
