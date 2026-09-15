# 03 Layout Algebra

> 官方对应：`media/docs/cpp/cute/02_layout_algebra.md`
>
> 更新：2026-09-15

## 官方顺序

1. [Coalesce](01-Coalesce/README.md)
2. [Composition](02-Composition/README.md)
3. [Composition Tilers](03-Composition-Tilers/README.md)
4. [Complement](04-Complement/README.md)
5. [Division](05-Division/README.md)
6. [Product](06-Product/README.md)

## 当前完整笔记

- [Layout 的八种物理身份（跨章节速查）](Layout多视角速查.md)
- [Coalesce 教程与练习](01-Coalesce/README.md)
- [Composition](02-Composition/用循环理解Composition.md)
- [Composition Tilers](03-Composition-Tilers/README.md)
- [Complement](04-Complement/Complement补集概念.md)
- [Division 官方例子教程](05-Division/README.md)
- [Product 官方例子教程](06-Product/README.md)
- [Division 与 Product](Division与Product.md)

这一章学习的是 Layout 的代数变换。每个函数单独成子目录，便于逐个学习、手算和验证。

## 代码验证

- [Composition 边界条件](02-Composition/代码实验/tests/test_note_invariants.py)
- [Complement / Divide / Product 关系](代码实验/tests/test_tiling_relations.py)

```bash
python3 -m unittest -v \
  03-Layout-Algebra/01-Coalesce/代码实验/test_coalesce_examples.py \
  03-Layout-Algebra/02-Composition/代码实验/tests/test_note_invariants.py \
  03-Layout-Algebra/代码实验/tests/test_tiling_relations.py
```
