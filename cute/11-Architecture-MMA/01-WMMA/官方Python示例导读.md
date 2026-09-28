# Ampere Warp MMA 官方 Python 示例导读

> 官方源码：
> [`examples/python/CuTeDSL/cute/ampere/kernel/dense_gemm/tensorop_gemm.py`](https://github.com/NVIDIA/cutlass/blob/098de2a652cf8f00fd70b2df54051c7eccbb855a/examples/python/CuTeDSL/cute/ampere/kernel/dense_gemm/tensorop_gemm.py)
>
> 本地源码：[代码实验/tensorop_gemm.py](代码实验/tensorop_gemm.py)
>
> 更新：2026-09-28

## 1. 为什么先读这个例子

这个文件不是一套新的 GEMM 算法。它是第 07 章
`sgemm_sm80.cu` 的 Python DSL 对照版本。

阅读目标只有一个：

```text
确认同一条 SM80 数据流在 Python DSL 中分别由哪些对象表达。
```

继续沿用第 07 章的主线：

```text
GMEM
  │ cp.async
  ▼
staged SMEM
  │ ldmatrix
  ▼
A/B RMEM fragment
  │ warp MMA
  ▼
C/D RMEM accumulator
```

## 2. 运行入口

在 CUTLASS 仓库根目录执行：

```bash
python examples/python/CuTeDSL/cute/ampere/kernel/dense_gemm/tensorop_gemm.py \
  --mnkl 8192,8192,8192,1 \
  --atom_layout_mnk 2,2,1 \
  --ab_dtype Float16 \
  --c_dtype Float16 \
  --acc_dtype Float32 \
  --a_major m \
  --b_major n \
  --c_major n
```

需要支持目标架构的 NVIDIA GPU、CUDA 以及可用的 CUTLASS Python DSL
环境。第一次阅读时，不必先运行完整的 `8192³` 问题。

## 3. 先看固定配置

源码中的关键常量表达：

```text
F16/BF16 MMA instruction: 16×8×16
默认 CTA tile:            128×128×32
pipeline stages:          4
一个 Warp MMA Atom:       32 threads
```

当命令行使用：

```text
atom_layout_mnk = (2,2,1)
```

参与 MMA 的线程数为：

```text
2 × 2 × 1 × 32 = 128 threads
```

这与第 07 章 C++ SM80 示例一致。

## 4. 按五个检查点阅读

### 检查点 1：MMA Operation

搜索：

```text
MmaF16BF16Op
MmaFP8Op
```

这里根据输入类型选择具体 Warp MMA Operation。然后搜索：

```text
make_tiled_mma
```

确认它如何把：

```text
instruction shape
+ atom_layout_mnk
+ permutation_mnk
```

组合成最终 `TiledMma`。

不要在这里重新学习 Atom。只需把 Python 对象与第 06、07 章的 C++
对象对应起来。

### 检查点 2：A/B/C fragment

搜索：

```text
make_fragment_A
make_fragment_B
make_fragment_C
```

在这个 Ampere 示例中：

```text
tCrA: A 的 RMEM fragment
tCrB: B 的 RMEM fragment
tCrC: C/D 的 RMEM accumulator
```

`make_fragment_A/B` 只创建寄存器 storage，还没有读取 SMEM。

### 检查点 3：`ldmatrix`

搜索：

```text
LdMatrix
make_tiled_copy_A
make_tiled_copy_B
retile
```

把源码中的对象按下面关系配对：

```text
partition_S(sA/sB)
  → ldmatrix 的 SMEM source view

retile(tCrA/tCrB)
  → ldmatrix 的 RMEM destination view

cute.copy(...)
  → 真正执行 SMEM → RMEM
```

这是该示例与 Hopper WGMMA 最重要的对照点。

### 检查点 4：Mainloop

搜索：

```text
cp_async_wait_group
cute.gemm
```

每个 K-block 的核心关系是：

```text
等待目标 SMEM stage
→ ldmatrix 取得 A/B register fragment
→ cute.gemm 更新 tCrC
→ 为后续 K-block 继续预取
```

`cute.gemm` 本身不会替你完成 `ldmatrix`。

### 检查点 5：Epilogue

搜索：

```text
make_fragment_like
autovec_copy
```

结果路径是：

```text
tCrC [RMEM accumulator]
→ 转换为 output dtype
→ SMEM 重排
→ 向量化 GMEM store
```

这一部分与第 07 章已学过的 epilogue 目的相同。

## 5. 用对象状态检查理解

```text
tCsA/tCsB
  SMEM view，不拥有新数据

tCrA/tCrB（刚创建）
  RMEM storage，尚未装入当前 A/B

tCrA/tCrB（ldmatrix 后）
  当前 K-block 的真实寄存器值

tCrC
  跨 K-block 保留的 RMEM accumulator
```

如果这四行能够在源码中逐一定位，就已经读懂了该示例的架构部分。

## 6. 与第 07 章 C++ 示例的对应

| C++ `sgemm_sm80.cu` | Python `tensorop_gemm.py` |
|---|---|
| `SM80_16x8x16_...` | `warp.MmaF16BF16Op` |
| `make_tiled_mma` | `cute.make_tiled_mma` |
| `Copy_Atom<...LDSM...>` | `warp.LdMatrix...Op` |
| `partition_S` | `partition_S` |
| `retile_D`/register retile | `retile` |
| `gemm(...)` | `cute.gemm(...)` |

语法不同，数据位置和同步关系没有改变。

## 7. 不要从头逐行读

官方文件包含命令行解析、输入验证、布局选择、性能测试和多种数据类型。
第一次阅读只追踪：

```text
MmaOp
→ TiledMma
→ fragment
→ ldmatrix
→ cute.gemm
→ accumulator
```

其余代码等这条链路明确后再补。

## 检查理解

1. `make_fragment_A` 执行后，A 的数据是否已经从 SMEM 进入 RMEM？

   > Hint：继续寻找第一次写入 `tCrA` 的 `cute.copy`。

2. 这个例子中哪一个对象跨越整个 K-loop 保存部分和？

   > Hint：它同时是 `cute.gemm` 的 C 和 D。

3. 切换到 Hopper 示例后，应该首先寻找哪个步骤消失了？

   > Hint：搜索 `LdMatrix`。
