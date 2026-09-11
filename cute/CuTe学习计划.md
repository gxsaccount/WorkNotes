# CuTe 从入门到深入学习计划

> 更新：2026-09-11  
> 适用对象：具有基本 C++ 或 Python 编程能力，希望系统学习 NVIDIA CUTLASS CuTe 的开发者。  
> 推荐周期：10～12 周，每周投入约 10 小时。

## 1. 每天学习多久

### 推荐方案

- 工作日：每天 **1.5 小时**
- 周末：选择一天学习 **3 小时**
- 每周学习 6 天，休息 1 天
- 每周总投入约 **10.5 小时**

按这个强度，完成第一轮学习大约需要 **10～12 周**。

### 每天 1.5 小时如何安排

| 时间 | 内容 |
|---|---|
| 15 分钟 | 回顾前一天的概念和错题 |
| 30 分钟 | 阅读文档、理解新概念 |
| 35 分钟 | 手算 Layout 或编写小实验 |
| 10 分钟 | 运行验证、整理笔记 |

学习 CuTe 时，动手计算和实验的时间应不少于总时间的一半。

### 其他强度

| 模式 | 时间投入 | 预计周期 |
|---|---:|---:|
| 轻量 | 每天 1 小时，每周 6 天 | 16～20 周 |
| 推荐 | 工作日 1.5 小时，周末 3 小时 | 10～12 周 |
| 强化 | 每天 3～4 小时 | 6～8 周 |

不建议长期每天学习超过 4 小时。CuTe 的抽象较密集，持续手算、编码和复盘通常比连续阅读更有效。

---

## 2. 第一阶段：CUDA 与矩阵计算基础

**时间：第 1～2 周**

### 学习内容

- CUDA 的 thread、warp、block、grid
- global、shared、register memory
- 合并访存和 shared memory bank conflict
- row-major 与 column-major
- GEMM 的 `M/N/K`
- CTA tile、warp tile、thread tile
- shape、stride、coordinate、offset

### 练习

手算以下 Layout：

```text
shape  = (4, 3)
stride = (1, 4)

(i, j) -> i + 4*j
```

尝试回答：

1. 哪个 mode 变化最快？
2. 自然序下的 offset 序列是什么？
3. 如果 stride 改为 `(3,1)`，访问顺序如何变化？

### 达标标准

- 能解释线程、warp 和 block 的关系
- 能解释矩阵分块为什么有利于数据复用
- 能根据 shape 和 stride 手算任意坐标的 offset

---

## 3. 第二阶段：CuTe Layout 基础

**时间：第 3 周**

### 核心模型

```text
Layout = Shape : Stride
coordinate -> offset
```

### 学习内容

- Shape、Stride、Layout
- mode、rank、depth
- 层级 tuple
- `size` 与 `cosize`
- `idx2crd` 与 `crd2idx`
- CuTe column-major 自然序
- 静态值与动态值
- injective、surjective、bijective
- broadcasting 与地址 alias
- `flatten` 与 `coalesce`

### 仓库学习材料

1. `03-Composition/用循环理解Composition.md` 的第 0 节
2. `03-Composition/代码实验/sim.py` 中的 `L`
3. `03-Composition/代码实验/quiz.py` 的 Coalesce 部分

### 练习

对下面的 Layout 展开完整 offset 序列：

```text
(4,3):(1,4)
(4,3):(3,1)
(2,2):(1,1)
(2,2,2):(2,1,4)
```

分别判断它们是否：

- 单射
- 紧凑
- 存在空洞
- 存在地址重叠
- 可以 coalesce

### 达标标准

看到一个 Layout 后，能够把它同时理解为：

- 坐标到 offset 的函数
- 多层嵌套循环
- 混合进制计数器
- GPU 地址生成器

---

## 4. 第三阶段：Composition

**时间：第 4～5 周**

### 核心公式

```text
R = A ∘ B
R(c) = A(B(c))
```

### 学习内容

- A 和 B 在 composition 中分别负责什么
- B 提供循环骨架，A 提供最终 offset
- concatenation 与 composition 的区别
- composition 左分配律
- integral layout 的闭式解
- multimodal layout 的 `/d` 与 `%s`
- stride divisibility condition
- shape divisibility condition
- 为什么 composition 可以消除运行时除法和取模

### 仓库学习顺序

1. `03-Composition/用循环理解Composition.md`
2. `03-Composition/代码实验/sim.py`
3. `03-Composition/代码实验/sim3.py`
4. `03-Composition/代码实验/sim2.py`
5. `03-Composition/代码实验/quiz.py`
6. `03-Composition/代码实验/p7.py`
7. `03-Composition/代码实验/p8.py`

### 必做练习

给定：

```text
A = (6,2):(8,2)
```

计算并实跑验证：

```text
A ∘ 4:3
A ∘ 3:1
A ∘ 2:6
A ∘ (4,3):(3,1)
```

同时找出至少两个不满足 divisibility condition 的例子，并说明失败原因。

### 达标标准

- 能通过函数复合直接验证结果
- 能手算 `/d`、`%s` 和 coalesce
- 能说明结果 Layout 为什么与原始复合函数等价
- 能区分 compatible 与普通的数值范围检查

---

## 5. 第四阶段：Complement

**时间：第 6 周**

### 核心概念

```text
B* = complement(B, M)
```

Complement 不是“B 没选中的元素列表”，而是描述多个 B 副本如何无重叠摆放的基址 Layout。

### 学习内容

- cotarget
- ordered complement
- disjoint codomain
- 完整副本与向上覆盖
- cotarget 不能整除时的边界行为
- `(B, B*)` 的拼接含义
- complement 与 tile 基址的关系

### 仓库学习材料

- `04-Complement/Complement补集概念.md`
- `03-Composition/代码实验/tests/test_note_invariants.py`

### 必做练习

计算或验证：

```text
complement(4:1, 24)
complement(4:2, 24)
complement(4:1, 10)
```

对每个结果展开：

```text
(B, B*)(i,j) = B(i) + B*(j)
```

检查：

- 是否发生重叠
- 覆盖到哪个 offset
- 定义域大小是否等于 cotarget

### 达标标准

- 不再把 complement 误解为补集元素列表
- 能解释为什么 cotarget 为 10 时可能覆盖到 11
- 能解释 `B*` 为什么表示 tile 间的移动方式

---

## 6. 第五阶段：Divide 与 Product

**时间：第 7 周**

### 核心公式

```text
Divide:  A ∘ (B, B*)
Product: (A, A* ∘ B)
```

### 学习内容

- tile 内与 tile 间的区别
- `logical_divide`
- `zipped_divide`
- `tiled_divide`
- `flat_divide`
- by-mode tiler
- divide 什么时候是 permutation
- divide 什么时候只是 gather 或 reindex
- A 非单射时产生的重复访问

### 仓库学习材料

- `05-Divide与Product/Division与Product.md`

### 必做练习

给定：

```text
A = (4,2,3):(2,1,8)
B = 4:2
```

完成：

1. 计算 `B*`
2. 展开 `(B,B*)`
3. 计算 `A ∘ (B,B*)`
4. 列出每个 tile 的元素
5. 判断结果是否为 permutation

然后把 A 改成：

```text
10:0
(2,2):(1,1)
```

观察 divide 为什么不再是 permutation。

### 达标标准

- 能从公式推导 divide
- 能从结果中识别 tile mode 和 rest mode
- 能正确选择 logical、zipped、tiled 或 flat 形式

---

## 7. 第六阶段：Tensor 与线程切片

**时间：第 8 周**

### 核心模型

```text
Tensor = Engine + Layout
```

### 学习内容

- global、shared、register Tensor
- `make_tensor`
- Tensor slicing
- `_` 占位符
- `local_tile`
- `local_partition`
- `partition_S` 与 `partition_D`
- identity tensor
- coordinate tensor
- block、warp、thread 的数据所有权

### 练习项目

对一个 `128×128` 矩阵：

1. 切成 `32×32` CTA tile
2. 将 CTA tile 分配给 warp
3. 将 warp tile 分配给线程
4. 打印每个线程负责的逻辑坐标
5. 检查是否遗漏或重复

### 达标标准

能够回答：

> 给定一个线程编号，这个线程负责矩阵中的哪些元素？

---

## 8. 第七阶段：Copy 与数据搬运

**时间：第 9 周**

### 学习内容

- Copy Atom
- TiledCopy
- thread layout
- value layout
- global → shared
- shared → register
- vectorized copy
- predication
- shared-memory swizzle
- 异步数据搬运

### 练习项目

依次实现：

1. 向量复制
2. 矩阵转置
3. tiled global-to-shared copy
4. shared-to-register copy
5. 非整除尺寸下的 predicated copy

### 达标标准

- 能说明每个线程搬运哪些元素
- 能判断访问是否合并
- 能检查 shared memory bank conflict
- 能处理矩阵边界

---

## 9. 第八阶段：MMA 与 GEMM

**时间：第 10～11 周**

### 学习内容

- MMA Atom
- TiledMMA
- thread/value ownership
- `partition_A`
- `partition_B`
- `partition_C`
- accumulator fragment
- SIMT GEMM
- Tensor Core GEMM
- GEMM mainloop
- K-loop
- double buffering
- epilogue

### 项目顺序

1. CPU reference GEMM
2. naive CUDA GEMM
3. shared-memory tiled GEMM
4. CuTe SIMT GEMM
5. CuTe Tensor Core GEMM
6. 支持非整除尺寸的 GEMM

每个实现都与 CPU reference 比较结果，并添加正确性测试。

### 达标标准

- 能解释 A、B、C Tensor 如何被线程划分
- 能解释一次 MMA 指令中每个线程持有哪些值
- 能阅读简单的 CuTe GEMM kernel
- 能使用正确性测试验证 kernel

---

## 10. 第九阶段：性能分析与高级架构

**时间：第 12 周及以后**

### 学习内容

- Nsight Compute
- memory throughput
- Tensor Core utilization
- occupancy
- register pressure
- roofline 分析
- multistage pipeline
- warp specialization
- Hopper TMA
- `mbarrier`
- warpgroup MMA
- cluster
- persistent kernel
- Split-K 与 Stream-K
- epilogue fusion
- Hopper SM90 与 Blackwell SM100

### 达标标准

面对一个性能不理想的 kernel，能够判断瓶颈主要来自：

- 计算
- global memory
- shared memory
- 同步
- occupancy
- register pressure
- tile 选择

---

## 11. 每周学习节奏

建议固定使用下面的节奏：

| 日期 | 学习内容 |
|---|---|
| 周一 | 阅读新概念，建立整体模型 |
| 周二 | 手算简单例子 |
| 周三 | 手算复杂和边界例子 |
| 周四 | 编写 Python 或 CuTe DSL 实验 |
| 周五 | 整理结论，记录错误案例 |
| 周六 | 3 小时综合项目和测试 |
| 周日 | 休息，或者只做轻量复习 |

---

## 12. 学习方法

每学习一个 CuTe 概念，都完成下面四步：

```text
手算 → Python 模拟 → CuTe DSL 验证 → 放入真实 kernel
```

每遇到一个 Layout，都回答：

1. 它的定义域是什么？
2. shape 每个 mode 表示什么？
3. stride 每个 mode 表示什么？
4. 自然序下的 offset 序列是什么？
5. 是否单射？
6. 是否紧凑？
7. 是否可以 coalesce？
8. 每个线程最终负责什么数据？

不要只记 API。CuTe 的关键是理解 Layout 所描述的映射和数据所有权。

---

## 13. 第一轮学习完成标准

完成第一轮后，应能够：

- 熟练手算常见 Layout
- 理解 composition、complement、divide 和 product
- 使用 Layout 描述 tile 和线程映射
- 理解 Tensor、Copy 和 MMA 的基本关系
- 阅读简单的 CuTe GEMM kernel
- 编写并验证一个基础 CuTe tiled kernel
- 使用性能工具定位明显的访存和计算问题

第一轮不要求记住所有模板和 API。真正的完成标准是：看到 CuTe 代码时，能够逐层还原它描述的坐标映射、线程分工和数据移动过程。
