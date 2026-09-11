# CuTe 从入门到深入学习计划

> 更新：2026-09-11  
> 目录依据：NVIDIA CUTLASS `main` 分支中的 CuTe C++ 与 CuTe DSL 官方文档
> 推荐周期：16 周左右，每周约 10.5 小时

## 1. 学习强度

### 推荐安排

- 工作日：每天 1.5 小时
- 周末：选择一天学习 3 小时
- 每周学习 6 天，休息 1 天
- 每周总投入约 10.5 小时

### 每天 1.5 小时

| 时间 | 内容 |
|---|---|
| 15 分钟 | 复习前一天的概念与错题 |
| 30 分钟 | 阅读官方文档和本地笔记 |
| 35 分钟 | 手算 Layout 或编写实验 |
| 10 分钟 | 运行测试并整理结论 |

CuTe 学习中，手算、代码实验和结果验证应占一半以上时间。

---

## 2. 两条学习主线

### 概念主线

按照官方 CuTe C++ 文档顺序：

```text
Quickstart
  → Layout
  → Layout Algebra
  → Tensor
  → Tensor Algorithms
  → MMA Atom
  → GEMM
  → Predication
  → TMA Tensor
```

### CuTe DSL 实践主线

本仓库现有实验使用 `cutlass.cute`，因此需要并行学习：

```text
@cute.jit
  → Code Generation
  → Control Flow
  → JIT Arguments
  → JIT Cache / Options
  → WMMA / WGMMA / TCGen05
  → Debug / Profile / Autotune / Integration
```

详细对应关系见：[官方目录映射](官方目录映射.md)。

---

## 3. 第 1～2 周：前置知识

目录：[00-前置知识](00-前置知识/README.md)

### 学习内容

- CUDA thread、warp、block、grid
- global、shared、register memory
- 合并访存和 bank conflict
- row-major 与 column-major
- GEMM 的 M、N、K
- CTA、warp、thread tiling
- shape、stride、coordinate、offset

### 完成标准

能够从 CUDA 线程和存储层级解释矩阵分块的目的，并手算二维矩阵地址。

---

## 4. 第 3 周：Quickstart 与 CuTe DSL 入门

目录：

- [01-Quickstart](01-Quickstart/README.md)
- [10-CuTe-DSL](10-CuTe-DSL/README.md)

### 学习内容

- 环境、示例和库结构
- 打印 CuTe 对象
- `@cute.jit`
- Host 与 Device 代码边界
- Code Generation
- 静态与动态控制流

### 完成标准

能够运行和修改最小 CuTe DSL 程序，并打印 Shape、Stride 和 Layout。

---

## 5. 第 4～5 周：Layout

目录：[02-Layout](02-Layout/README.md)

### 官方子主题

1. [基础类型与概念](02-Layout/01-基础类型与概念/README.md)
2. [创建与使用](02-Layout/02-创建与使用/README.md)
3. [坐标与兼容性](02-Layout/03-坐标与兼容性/README.md)
4. [Layout 操作](02-Layout/04-Layout操作/README.md)

### 学习内容

- Integer、Tuple、IntTuple
- Shape、Stride、Layout、Tensor
- mode、rank、depth
- `size`、`cosize`、`compatible`
- `idx2crd` 与 `crd2idx`
- sublayout、concatenation、grouping、flattening、slicing
- 单射、广播、空洞和地址别名

### 必做练习

展开并分析：

```text
(4,3):(1,4)
(4,3):(3,1)
(2,2):(1,1)
(2,2,2):(2,1,4)
```

### 完成标准

能够把 Layout 解释为坐标映射、嵌套循环、混合进制计数器和地址生成器。

---

## 6. 第 6～8 周：Layout Algebra

目录：[03-Layout-Algebra](03-Layout-Algebra/README.md)

### 6.1 Coalesce

目录：[01-Coalesce](03-Layout-Algebra/01-Coalesce/README.md)

掌握退化 mode、相邻 mode 合并条件和 by-mode coalesce。

### 6.2 Composition

目录：[02-Composition](03-Layout-Algebra/02-Composition/README.md)

掌握：

```text
R = A ∘ B
R(c) = A(B(c))
```

学习 `/d`、`%s`、divisibility condition、integral/multimodal 分支和循环融合。

### 6.3 Composition Tilers

目录：[03-Composition-Tilers](03-Layout-Algebra/03-Composition-Tilers/README.md)

区分普通 concatenation、tuple tiler 和 by-mode tiler。

### 6.4 Complement

目录：[04-Complement](03-Layout-Algebra/04-Complement/README.md)

理解 complement 是 tile 副本的基址 Layout，而不是遗漏元素列表。

### 6.5 Division

目录：[05-Division](03-Layout-Algebra/05-Division/README.md)

掌握 logical、zipped、tiled、flat divide，以及 permutation/gather 的边界。

### 6.6 Product

目录：[06-Product](03-Layout-Algebra/06-Product/README.md)

掌握 logical、blocked、raked、zipped 和 tiled product。

### 本章测试

```bash
python3 -m unittest -v 03-Layout-Algebra/02-Composition/代码实验/tests/test_note_invariants.py
```

### 完成标准

能够逐点验证代数变换前后的 Layout 映射，并解释每个结果 mode 的物理意义。

---

## 7. 第 9 周：Tensor

目录：[04-Tensor](04-Tensor/README.md)

### 学习内容

- Tensor Engine
- owning 与 nonowning Tensor
- global、shared、register Tensor
- Tiling 与 Slicing
- inner/outer partitioning
- thread-value partitioning
- `local_tile`、`local_partition`
- `partition_S`、`partition_D`

### 完成标准

给定线程编号，能够说明该线程负责哪些逻辑坐标和物理数据。

---

## 8. 第 10 周：Tensor Algorithms

目录：[05-Tensor-Algorithms](05-Tensor-Algorithms/README.md)

### 学习内容

- `copy`
- `copy_if`
- `gemm` 算法接口
- `axpby`、`fill`、`clear`
- Copy 参数类型与并行/同步语义

### 项目

实现并验证 global → shared → register 的 tiled copy。

---

## 9. 第 11 周：MMA Atom

目录：[06-MMA-Atom](06-MMA-Atom/README.md)

### 学习内容

- MMA Operation Struct
- MMA Traits
- `fma`
- Atom 的 Shape 与数据类型
- Thread/Value Layout
- Accumulator Mapping
- A/B Operand Mapping
- TiledMMA

### 完成标准

能够解释一次 MMA 中每个线程持有哪些 A、B 和 C fragment。

---

## 10. 第 12～13 周：完整 GEMM

目录：[07-GEMM-Tutorial](07-GEMM-Tutorial/README.md)

### 学习顺序

1. Full Tensor 与 M/N/K 主序
2. CTA Partitioning
3. Shared Memory Tensor
4. Copy Partitioning
5. Math Partitioning
6. K-loop 和 Mainloop
7. SIMT GEMM
8. Tensor Core GEMM

### 项目顺序

```text
CPU Reference
  → Naive CUDA GEMM
  → Shared-memory GEMM
  → CuTe SIMT GEMM
  → CuTe Tensor Core GEMM
```

每个版本都必须增加正确性测试，并与 CPU reference 比较。

---

## 11. 第 14 周：Predication

目录：[08-Predication](08-Predication/README.md)

### 学习内容

- 非整除问题尺寸
- Identity Coordinate Tensor
- 边界谓词
- Predicated Copy
- GEMM 边界处理

### 完成标准

GEMM 能正确处理 M、N、K 不是 tile 整数倍的情况。

---

## 12. 第 15 周：TMA Tensor

目录：[09-TMA-Tensors](09-TMA-Tensors/README.md)

### 学习内容

- TMA 指令模型
- Implicit CuTe Tensor
- ArithTuple 与 Iterator
- Basis stride
- 坐标和地址变换
- TMA Tensor 构造

---

## 13. 第 16 周及以后：架构专项与工程化

目录：

- [11-Architecture-MMA](11-Architecture-MMA/README.md)
- [12-Engineering-Guides](12-Engineering-Guides/README.md)

### 架构专项

- WMMA
- Hopper WGMMA
- Blackwell TCGen05
- Pipeline、mbarrier、warp specialization

### 工程化

- Debugging
- IKET 与 Nsight Compute Profiling
- GEMM Autotuning
- AOT Compilation
- TVM FFI
- Framework Integration

### 完成标准

能够根据性能测量判断瓶颈，提出 tile、copy、MMA、pipeline 或调度优化方案，并用基准测试验证。

---

## 14. 每周固定节奏

| 日期 | 内容 |
|---|---|
| 周一 | 阅读官方章节，建立术语和整体模型 |
| 周二 | 手算基础例子 |
| 周三 | 手算复杂和边界例子 |
| 周四 | 编写 Python/CuTe DSL 实验 |
| 周五 | 整理错误案例和本章笔记 |
| 周六 | 综合项目、测试和性能测量 |
| 周日 | 休息或轻量复习 |

## 15. 学习方法

对每个概念执行：

```text
官方定义
  → 手算
  → Python 模拟
  → CuTe DSL 实跑
  → 单元测试
  → 放入真实 Kernel
```

对每个 Layout 都回答：

1. 定义域和 codomain 是什么？
2. 每个 mode 表示什么？
3. 自然序 offset 是什么？
4. 是否单射、紧凑或存在空洞？
5. 是否可以 coalesce？
6. 与哪个线程、value、memory space 对应？
