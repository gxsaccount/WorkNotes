# -*- coding: utf-8 -*-
from sim import L, sep

A = L([6,2],[8,2])
print("A =", A)
print("A 数组（索引 0..11）:", A.seq())
print("A 的索引:            ", list(range(12)))

sep("对照1: B = 4:3   →  「隔 3 取 1」，共取 4 个")
print("""
for (k = 0; k < 4; k++) {        // s=4 : 循环跑 4 次 = 总共取 4 个
    n = k * 3;                   // d=3 : 每步 n 前进 3 = 隔 3
    offset = A(n);               // 循环体只访问一个 → 「取 1」
}
""")
idx = [k*3 for k in range(4)]
print("   A 的索引序列 :", idx)
print("   取到的元素   :", [A(i) for i in idx])
print("   → 4 个点，彼此间隔 3，每个点只取 1 个")

sep("对照2: B = (4,3):(3,1) → 「隔 3 取 3」，共取 12 个")
print("""
for (k = 0; k < 4; k++)          // 外层：步长 3（块间距）
  for (j = 0; j < 3; j++) {      // 内层：步长 1（块内连续）
      n = 3*k + 1*j;             // 每个块取 3 个连续元素
      offset = A(n);
  }
""")
idx2 = [3*k + j for k in range(4) for j in range(3)]
print("   A 的索引序列 :", idx2)
print("   取到的元素   :", [A(i) for i in idx2])
print("   → 12 个点，分 4 组，每组连续 3 个（把 A 全取了）")

sep("结论：d 决定「隔多少」，s 决定「取几个」，「取1」是循环体性质")
print("""
  s:d          →  步长 d，共 s 个点    →  「隔 d 取 1，重复 s 次」
  (s,m):(d,1)  →  块间距 d，块内连续 m →  「隔 d 取 m，重复 s 次」

  注意：B 的每一个 mode 都贡献一层「取」。
  单 mode s:d 只有一层 → 每次取 1 个；
  要「取 m 个」，就得有内层 mode（shape=m, stride=1）。
""")

sep("极端验证: d = 0 （广播 mode）")
print("   n = k*0 = 0 恒成立 → 反复取同一个元素 A(0)")
for k in range(4):
    print(f"   k={k}: n={k*0}  A(n)={A(k*0)}")
print("   → d 就是「步长」的最直接证据：d=0 意味着 n 不前进")
