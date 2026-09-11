# -*- coding: utf-8 -*-
"""
用「循环」模拟 CuTe composition 的 /d 和 %s
核心思想：把 Layout A 看成一个数组（按自然序展开），
         composition 就是对这个数组做「隔 d 取 1，再取前 s 个」。
"""
from math import prod

def sep(t=""):
    print("\n" + "="*62)
    if t: print(t); print("="*62)

# ---------- Layout：shape/stride 都是扁平 list ----------
class L:
    def __init__(self, shape, stride):
        assert len(shape) == len(stride)
        self.shape, self.stride = list(shape), list(stride)
    def size(self): return prod(self.shape)
    def crd(self, n):                      # idx2crd：整数 -> 各 mode 坐标
        c = []
        for s in self.shape:
            c.append(n % s); n //= s
        return c
    def __call__(self, n):                 # 内积
        # CuTe's integral-layout composition rule is unbounded for a scalar
        # coordinate: a:b evaluated at n is b*n, not b*(n % a).
        # Multimodal examples below are evaluated only within their valid
        # logical domain; composition's divisibility checks guard that case.
        if len(self.shape) == 1:
            return n * self.stride[0]
        return sum(ci*di for ci, di in zip(self.crd(n), self.stride))
    def seq(self): return [self(n) for n in range(self.size())]
    def __str__(self):
        sh = self.shape[0] if len(self.shape)==1 else tuple(self.shape)
        st = self.stride[0] if len(self.stride)==1 else tuple(self.stride)
        return f"{sh}:{st}"

# ---------- 把 layout 当成循环展开：for a: for b: ... ----------
def as_loop(lay):
    """用嵌套循环产生自然序下的 offset 序列（等价于 lay.seq()）"""
    out = []
    def rec(depth, coord):
        if depth == len(lay.shape):
            out.append(sum(c*d for c, d in zip(coord, lay.stride)))
            return
        for i in range(lay.shape[depth]):          # mode 越大越外层
            rec(depth+1, coord + [i])
    rec(0, [])
    return out

# ---------- /d ：隔 d 取 1 ----------
def slash_d(lay, d):
    """返回 (新shape, 新stride)。语义：只取 A 的第 0, d, 2d, ... 个"""
    sh, st, rem = [], [], d
    for s_i, d_i in zip(lay.shape, lay.stride):
        f = min(rem, s_i)                 # 这个 mode 能吸收多少
        if s_i % f != 0: raise ValueError(f"/d 失败：{s_i} 不能被 {f} 整除")
        sh.append(s_i // f)
        st.append(d_i * f)
        rem //= f
        if rem == 1:                      # 后面的 mode 原样
            sh += lay.shape[len(sh):]
            st += lay.stride[len(st):]
            break
    return sh, st

# ---------- %s ：只保留前 s 个 ----------
def percent_s(shape, s):
    """贪心：从左到右，每个 mode 取 min(s_i, rem)，rem 整除下去。stride 不动"""
    out, rem = [], s
    for s_i in shape:
        take = min(s_i, rem)
        out.append(take)
        rem //= take
    return out

# ---------- coalesce：相邻两层能否拍平 ----------
def coalesce(shape, stride):
    sh, st = list(shape), list(stride)
    i = 0
    while i < len(sh)-1:
        if sh[i] == 1:            sh.pop(i);   st.pop(i);  i = max(i-1,0); continue
        if sh[i+1] == 1:          sh.pop(i+1); st.pop(i+1); i = max(i-1,0); continue
        if st[i+1] == sh[i]*st[i]:            # 外层步长 == 内层 size × 内层步长
            sh[i] = sh[i]*sh[i+1]; sh.pop(i+1)
            st.pop(i+1)                       # stride 抄内层，不计算
            i = max(i-1,0); continue
        i += 1
    return L(sh, st)

# ============ 主流程 ============
def compose_show(A, s, d, note=""):
    sep(f"A = {A}   ∘   {s}:{d}      {note}")
    print(f"A 当成数组（自然序展开）：")
    print("   ", A.seq())

    print(f"\n【第1步 /d = {d}】对 A 隔 {d} 个取 1 个")
    sh1, st1 = slash_d(A, d)
    print(f"    shape : {A.shape} -- /{d} --> {sh1}      (trip count ÷ d)")
    print(f"    stride: {A.stride} -- *{d} --> {st1}      (stride × d)")
    print(f"    总跨度不变: {A.shape[0]}×{A.stride[0]} = {sh1[0]}×{st1[0]}"
          f" = {A.shape[0]*A.stride[0]}")
    sampled = [A(n) for n in range(0, A.size(), d)]
    print(f"    实际取到的元素 A[0], A[{d}], A[{2*d}], ... = {sampled}")

    print(f"\n【第2步 %{s}】只要前 {s} 个")
    sh2 = percent_s(sh1, s)
    print(f"    shape : {sh1} -- %{s} --> {sh2}      (stride 完全不动)")
    print(f"    size  : {prod(sh2)}  （目标 s = {s}）", "✓" if prod(sh2)==s else "✗ 失败")
    picked = sampled[:s]
    print(f"    保留的元素 = {picked}")

    R = coalesce(sh2, st1)
    print(f"\n【结果】R = {R}")
    print(f"    用 R 的循环算一遍: {R.seq()}")
    print(f"    与「保留的元素」一致? ", "✓ 完全吻合" if R.seq()==picked else "✗ 不一致")
    return R

if __name__ == "__main__":
    A = L([6,2],[8,2])
    compose_show(A, 4, 3, "官方例子·分支1")
    compose_show(A, 3, 1, "官方例子·分支2")
    compose_show(A, 2, 6, "d 大而跨 mode")
    compose_show(A, 6, 1, "d=1 纯截断")
