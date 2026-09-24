# Composition

## 核心公式

```text
R = A ∘ B
R(c) = A(B(c))
```

## 当前笔记

- [用循环理解 Composition](用循环理解Composition.md)——主入口
- [composition.md](composition.md)——保留的同内容原文件

## 代码实验

- [`sim.py`](代码实验/sim.py)
- [`sim2.py`](代码实验/sim2.py)
- [`sim3.py`](代码实验/sim3.py)
- [`quiz.py`](代码实验/quiz.py)
- [`p7.py`](代码实验/p7.py)
- [`p8.py`](代码实验/p8.py)
- [边界条件测试](代码实验/tests/test_note_invariants.py)

## 运行

```bash
python3 03-Layout-Algebra/02-Composition/代码实验/sim.py
python3 -m unittest -v 03-Layout-Algebra/02-Composition/代码实验/tests/test_note_invariants.py
```
