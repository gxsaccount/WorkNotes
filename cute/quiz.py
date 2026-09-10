# -*- coding: utf-8 -*-
from sim import L, slash_d, percent_s, coalesce, as_loop
from math import prod

def compose(A, s, d):
    sh1, st1 = slash_d(A, d)
    sh2 = percent_s(sh1, s)
    assert prod(sh2) == s, f"失败: size={prod(sh2)} != s={s}"
    return coalesce(sh2, st1)

def compose_full(A, B):
    """B 是扁平的 [(s,d), ...] 列表 -> 逐 mode 复合再拼接"""
    modes = [compose(A, s, d) for (s, d) in B]
    sh, st = [], []
    for m in modes:
        sh.append(m.shape if len(m.shape) != 1 else m.shape[0])
        st.append(m.stride if len(m.stride) != 1 else m.stride[0])
    # 只做跨 mode 边界之外的合并：这里简单起见返回未跨mode合并的形式
    return sh, st

def show_compose(A, B):
    print(f"A={A}  B={B}")
    for (s, d) in B:
        sh1, st1 = slash_d(A, d)
        sh2 = percent_s(sh1, s)
        R = coalesce(sh2, st1)
        print(f"   mode s={s},d={d}:  /{d} -> shape {sh1} stride {st1} | %{s} -> {sh2} | -> {R}  seq={R.seq()}")
    sh, st = compose_full(A, B)
    print(f"   >>> 拼接结果 shape={sh} stride={st}")
    print()

print("="*60)
print("第1档 Coalesce")
print("="*60)
for (sh, st) in [([2,4],[1,2]), ([4,2],[2,1]), ([3,3],[1,3]),
                 ([2,3,2],[1,2,12]), ([4,1,3],[2,5,8]), ([2,2],[1,4])]:
    print(f"coalesce({tuple(sh)}:{tuple(st)})  = {coalesce(sh,st)}")

print()
print("="*60)
print("第2档 Composition (A o s:d)")
print("="*60)
A1 = L([6,2],[8,2])
for (s,d) in [(4,3),(3,1),(2,6),(6,1),(12,1),(2,4)]:
    try:
        print(f"{A1} o {s}:{d} = {compose(A1,s,d)}   seq={compose(A1,s,d).seq()}")
    except Exception as e:
        print(f"{A1} o {s}:{d} -> 失败: {e}")

print()
A2 = L([8],[1])
for (s,d) in [(4,2),(3,3),(8,1),(2,5)]:
    try:
        print(f"{A2} o {s}:{d} = {compose(A2,s,d)}")
    except Exception as e:
        print(f"{A2} o {s}:{d} -> 失败: {e}")

print()
A3 = L([4,4],[1,4])
for (s,d) in [(8,1),(4,2),(2,8),(16,1),(6,1)]:
    try:
        print(f"{A3} o {s}:{d} = {compose(A3,s,d)}  seq={compose(A3,s,d).seq()}")
    except Exception as e:
        print(f"{A3} o {s}:{d} -> 失败: {e}")

print()
print("="*60)
print("第3档 完整复合 A o B")
print("="*60)
show_compose(L([6,2],[8,2]), [(4,3),(3,1)])
show_compose(L([8],[1]), [(4,1),(2,2)])
show_compose(L([4,4],[1,4]), [(2,2),(4,1)])
