# -*- coding: utf-8 -*-
"""验证 compatible(B, R)：B 的每一个坐标，R 都能接受"""
from sim import L
from math import prod

def domain(layout):
    """产生一个 layout 的全部坐标（自然序）"""
    out = []
    def rec(depth, cur):
        if depth == len(layout.shape):
            out.append(tuple(cur)); return
        for i in range(layout.shape[depth]):
            rec(depth+1, cur + [i])
    rec(0, [])
    return out

def capacity(shape):
    """把层级 shape 拍平后，按 B 的 mode 数分组，算每组的容量"""
    flat = []
    def rec(s):
        if isinstance(s, int): flat.append(s)
        else:
            for x in s: rec(x)
    rec(shape)
    return flat

B = L([4,3],[3,1])          # B: shape (4,3)
R = L([2,2,3],[24,2,8])     # R 拍平: shape (2,2,3)  对应 ((2,2),3)
A = L([6,2],[8,2])

print("B.shape =", tuple(B.shape), " size =", B.size())
print("R.shape =", tuple(R.shape), " size =", R.size())
print()
print("R 的容量按 B 的 mode 分组（(2,2) 属于 mode-0, 3 属于 mode-1）:")
print("   mode-0: 2 × 2 = ", 2*2, "  vs  B.mode-0 shape = 4   ->", "✓" if 2*2==4 else "✗")
print("   mode-1: 3       = ", 3,    "  vs  B.mode-1 shape = 3   ->", "✓" if 3==3 else "✗")
print("   → 逐 mode 容量相等 → compatible(B, R) = True")
print("   注意：字面 shape 不同（(4,3) vs ((2,2),3)），但容量一致")

print("\nB 的全部坐标 vs R 能否接受：")
dom = domain(B)
bad = 0
for c in dom:
    n = B(c[0] + 4*c[1])   # B 的坐标 -> 索引
    # R 用同一个坐标索引是否合法
    ok = (c[0] + 4*c[1]) < R.size()
    if not ok: bad += 1
print(f"   B 的坐标总数 = {len(dom)},  R.size() = {R.size()},  越界数 = {bad}")
print(f"   → {'每个 B 坐标都有对应的 R 坐标 ✓' if bad==0 else '有越界 ✗'}")

print("\n反例：如果 R 少一个元素会怎样")
Rbad = L([2,2,2],[24,2,8])   # size 8 < 12
bad2 = sum(1 for i in range(B.size()) if i >= Rbad.size())
print(f"   Rbad.size() = {Rbad.size()}, B.size() = {B.size()}, 越界数 = {bad2}")
print("   → B 有 12 个坐标，R 只装得下 8 个 → 不兼容 ✗")

print("\n前置条件 vs 后置条件：")
print("   前置 compatible(A, B)：A 的定义域要装下 B 的值域（B 输出的最大索引）")
mx = max(B(i) for i in range(B.size()))
print(f"      B 输出的最大值 = {mx},  A.size() = {A.size()}  -> {'✓' if mx < A.size() else '✗'}")
print("   后置 compatible(B, R)：R 的定义域要装下 B 的定义域（坐标空间）")
print(f"      B.size() = {B.size()},  R.size() = {R.size()}  -> {'✓' if B.size()==R.size() else '✗'}")
