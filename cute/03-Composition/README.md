# 第 3 章：Composition

> 建议时间：第 4～5 周

## 学习目标

- 理解 `R = A ∘ B` 与 `R(c) = A(B(c))`
- 理解 A 提供 offset、B 提供循环骨架
- 区分 concatenation 与 composition
- 掌握 integral 和 multimodal 两类 composition
- 掌握 `/d`、`%s`、coalesce 及 divisibility condition

## 当前笔记

- [用循环理解 Composition](用循环理解Composition.md)——推荐主入口
- [composition.md](composition.md)——与上面的中文文件内容相同，作为原文件名副本保留

## 代码实验

- [`sim.py`](代码实验/sim.py)：Layout 模型及 composition 分步模拟
- [`sim2.py`](代码实验/sim2.py)：失败案例与循环融合
- [`sim3.py`](代码实验/sim3.py)：隔 `d` 取 1 与隔 `d` 取 `m`
- [`quiz.py`](代码实验/quiz.py)：Coalesce 和 Composition 练习
- [`p7.py`](代码实验/p7.py)：CuTe DSL compatible 实验
- [`p8.py`](代码实验/p8.py)：compatible 的纯 Python 解释
- [`tests/test_note_invariants.py`](代码实验/tests/test_note_invariants.py)：笔记边界条件测试

## 运行

从仓库根目录执行：

```bash
python3 03-Composition/代码实验/sim.py
python3 03-Composition/代码实验/sim2.py
python3 03-Composition/代码实验/sim3.py
python3 -m unittest -v 03-Composition/代码实验/tests/test_note_invariants.py
```

`p7.py` 依赖本地已经安装并可用的 NVIDIA CuTe Python DSL。

## 完成标准

能够手算 composition，并用函数逐点验证结果 Layout 与 `A(B(c))` 等价。

