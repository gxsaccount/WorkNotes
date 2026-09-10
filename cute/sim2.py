# -*- coding: utf-8 -*-
from sim import L, slash_d, percent_s, coalesce, sep
from math import prod

def try_compose(A, s, d):
    sep(f"A = {A}  ∘  {s}:{d}")
    print(f"A 数组 = {A.seq()}")
    sh1, st1 = slash_d(A, d)
    print(f"/{d}  ->  shape {sh1},  stride {st1}")
    print("\n%s 的贪心过程（每个 mode 取 min(s_i, rem)，rem 整数除下去）：" % s)
    rem, out = s, []
    for i, si in enumerate(sh1):
        take = min(si, rem)
        old = rem
        rem //= take
        out.append(take)
        print(f"   mode{i}: shape={si:2d},  rem={old:2d}  ->  取 {take:2d}  (rem {old}//{take} = {rem})")
    print(f"   最终 shape = {out},  size = {prod(out)}")
    if prod(out) != s:
        print(f"   ✗ size={prod(out)} != s={s}  →  composition 失败！")
        print(f"   原因：{s} 无法沿 A 的 mode 边界 {sh1} 整除分解（{sh1[0]} 之后要再取 {s}/{sh1[0]} 个，非整数）")
    else:
        R = coalesce(out, st1)
        print(f"   ✓ R = {R}   验证: {R.seq()}")

A = L([6,2],[8,2])
try_compose(A, 8, 1)    # 失败
try_compose(A, 4, 3)    # 成功对照

# ================= 循环融合前后对比 =================
sep("循环融合：朴素 A(B(c))  vs  复合后 R(c)")
A = L([6,2],[8,2]); B = L([4,3],[3,1]); R = L([2,2,3],[24,2,8])

print("【朴素写法】两层循环 + 查表（每步要 idx2crd：除法+取模）")
print("""
for (q = 0; q < 3; q++)
  for (p = 0; p < 4; p++) {
      n = 3*p + 1*q;                 // B 的循环
      c0 = (n / 8) % 6;              // ← A 的查表：除法 + 取模
      c1 = (n / 2) % 2;              // ← 又是除法 + 取模
      offset = 8*c0 + 2*c1;
  }
""")
print("【复合之后】一层循环，纯乘加（零 div/mod）")
print("""
for (q = 0; q < 3; q++)
  for (b = 0; b < 2; b++)
    for (a = 0; a < 2; a++) {
        offset = 24*a + 2*b + 8*q;   // 全是常量 stride，直接算
    }
""")
bad = 0
for q in range(3):
    for p in range(4):
        naive = A(B(p + 4*q))
        crd = R.crd(p + 4*q)
        fused = R(p + 4*q)
        if naive != fused: bad += 1
        print(f"   B坐标(p={p},q={q}): 朴素={naive:3d}   融合(坐标{crd})={fused:3d}   {'✓' if naive==fused else '✗'}")
print(f"\n不一致数量 = {bad}  →  {'两个循环完全等价 ✓' if bad==0 else '有问题 ✗'}")
