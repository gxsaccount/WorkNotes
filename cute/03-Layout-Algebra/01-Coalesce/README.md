# 01 Coalesce：在不改变一维映射的前提下化简 Layout

> 官方对应：`media/docs/cpp/cute/02_layout_algebra.md` 的 **Coalesce** 与 **By-mode Coalesce**
>
> 官方基线：NVIDIA CUTLASS `main`，核对日期 2026-09-11
>
> 更新：2026-09-11

## 1. 本节目标

学完本节后，应当能够：

1. 说清 `coalesce` 保留了什么、可能改变什么；
2. 判断两个相邻 mode 能否合并；
3. 手算普通 `coalesce` 和 by-mode `coalesce`；
4. 区分 `flatten`、`coalesce`、连续、紧凑和单射；
5. 使用逐点枚举验证化简前后的映射。

---

## 2. 先把 Layout 看成一维整数函数

上一章中，Layout 被定义为：

```text
Layout：coordinate -> index
```

`coalesce` 采用一个更具体的观察角度：

```text
只考虑标量输入 i，0 <= i < size(layout)
```

它尝试减少 Layout 的 mode 数量，同时保持标量自然序下的函数值不变。

官方给出的三个后置条件是：

```text
size(result) == size(layout)
depth(result) <= 1

对所有 0 <= i < size(layout)：
result(i) == layout(i)
```

因此可以把它暂时理解为：

> `coalesce` 是对 Layout 地址生成函数的循环化简。

### 它可能改变什么？

- Shape 的写法；
- Stride 的写法；
- mode 数量；
- tuple 层级；
- 可以使用的结构化坐标形式。

### 它不会改变什么？

- Layout 的 `size`；
- 合法标量输入 `i` 的输出序列。

注意，官方保证的是：

```text
result(i) == layout(i)
```

这里的 `i` 是标量自然序号。不要擅自扩展成“二者接受完全相同的 tuple 坐标”。

---

## 3. 为什么相邻 mode 有时可以合并？

考虑两个相邻 mode：

```text
(s0,s1):(d0,d1)
```

标量自然序号 `i` 会先被分解成：

```text
c0 = i % s0
c1 = i / s0
```

原 Layout 的输出是：

```text
L(i) = c0*d0 + c1*d1
```

如果满足：

```text
d1 == s0*d0
```

那么：

```text
L(i)
= (i % s0)*d0 + (i / s0)*(s0*d0)
= i*d0
```

所以它与下面的一维 Layout 完全相同：

```text
(s0*s1):d0
```

这就是相邻 mode 的合并条件。

### 循环视角

原来的两层循环：

```cpp
for (int c1 = 0; c1 < s1; ++c1) {
  for (int c0 = 0; c0 < s0; ++c0) {
    offset = c0 * d0 + c1 * d1;
  }
}
```

当 `d1 == s0*d0` 时，可以融合成：

```cpp
for (int i = 0; i < s0 * s1; ++i) {
  offset = i * d0;
}
```

---

## 4. 官方四条二元规则

把两个相邻 integral mode 的合并写成：

```text
s0:d0 ++ s1:d1
```

官方列出四种情况。

### 规则 1：删除右侧静态 size-1 mode

```text
s0:d0 ++ _1:d1  =>  s0:d0
```

size 为 1 时，该 mode 的自然坐标永远是 0，因此其 stride 不会贡献任何输出。

### 规则 2：删除左侧静态 size-1 mode

```text
_1:d0 ++ s1:d1  =>  s1:d1
```

同理，左侧退化 mode 也可以删除。

### 规则 3：连续相邻 mode 合并

```text
s0:d0 ++ s1:(s0*d0)  =>  (s0*s1):d0
```

例如：

```text
2:1 ++ 4:2  =>  8:1
```

因为：

```text
2 == 2*1
```

### 规则 4：条件不成立则保留

```text
s0:d0 ++ s1:d1  =>  (s0,s1):(d0,d1)
```

例如：

```text
4:2 ++ 2:1
```

不能合并，因为：

```text
1 != 4*2
```

结果仍是：

```text
(4,2):(2,1)
```

> 官方规则中的 `_1` 是静态 1。若 shape 或关系只能在运行时获知，编译器未必能够执行同样的类型级化简。

---

## 5. 普通 `coalesce` 的计算步骤

普通 `coalesce(layout)` 可以按以下方法手算：

1. 将 Shape 和 Stride 的叶子 mode 按原顺序拍平；
2. 删除静态 size-1 mode；
3. 从左到右检查相邻 mode；
4. 满足 `d_next == s_current*d_current` 就合并；
5. 合并后继续检查新 mode 与右侧 mode；
6. 直到不能继续化简。

它不是只检查一次相邻 pair。一次合并可能触发下一次合并。

---

## 6. 官方示例逐步推导

官方示例：

```cpp
auto layout = Layout<
    Shape <_2, Shape <_1, _6>>,
    Stride<_1, Stride<_6, _2>>>{};

auto result = coalesce(layout);   // _12:_1
```

原 Layout：

```text
(2,(1,6)):(1,(6,2))
```

### 第一步：拍平叶子

```text
(2,1,6):(1,6,2)
```

### 第二步：删除静态 size-1 mode

```text
(2,6):(1,2)
```

注意：该退化 mode 的 stride 是 6，但它的坐标始终为 0：

```text
0 * 6 = 0
```

所以可以直接删除。

### 第三步：检查相邻 mode

```text
s0 = 2
d0 = 1
d1 = 2
```

满足：

```text
d1 == s0*d0
2  == 2*1
```

因此：

```text
(2,6):(1,2) => 12:1
```

### 第四步：逐点验证

两者的标量输出都是：

```text
0,1,2,3,4,5,6,7,8,9,10,11
```

---

## 7. 三个必须理解的反例

### 7.1 Row-major 不一定能被普通 `coalesce` 合并

```text
L = (2,4):(4,1)
```

检查条件：

```text
1 != 2*4
```

因此不能合并。

标量自然序下的输出为：

```text
0,4,1,5,2,6,3,7
```

显然不等于 `8:1` 的：

```text
0,1,2,3,4,5,6,7
```

这里“内存整体连续”不代表“按照 CuTe 的 mode-0-first 自然序连续”。

### 7.2 能 coalesce 不代表单射

```text
L = (4,3):(0,0)
```

因为：

```text
d1 == s0*d0
0  == 4*0
```

所以：

```text
coalesce(L) = 12:0
```

但输出序列仍然全部是 0。它是广播，不是单射。

因此：

```text
可合并 != 单射
可合并 != 无广播
可合并 != 地址连续
```

### 7.3 正 stride 也不保证能合并

```text
L = (2,2):(1,1)
```

因为：

```text
1 != 2*1
```

所以不能合并。它的输出：

```text
0,1,1,2
```

还存在地址别名。

---

## 8. `flatten` 与 `coalesce` 的区别

给定：

```text
L = ((2,3),4):((1,2),6)
```

### `flatten`

只删除 tuple 层级：

```text
flatten(L) = (2,3,4):(1,2,6)
```

### `coalesce`

拍平后还会应用代数合并规则：

```text
2:1 ++ 3:2 => 6:1
6:1 ++ 4:6 => 24:1
```

所以：

```text
coalesce(L) = 24:1
```

结论：

```text
flatten：结构操作，只去括号
coalesce：函数化简，可能减少 mode
```

---

## 9. By-mode Coalesce

普通 `coalesce` 把整个 Layout 当作一维函数，可能跨越原来的 mode 边界进行合并。

但有时我们希望：

```text
输入是二维 Layout，输出仍保留两个顶层 mode
```

CuTe 为此提供带 target profile 的重载：

```cpp
coalesce(layout, trg_profile)
```

官方示例：

```cpp
auto a = Layout<
    Shape <_2, Shape <_1, _6>>,
    Stride<_1, Stride<_6, _2>>>{};

auto result = coalesce(a, Step<_1,_1>{});
// (_2,_6):(_1,_2)
```

它等价于分别化简两个顶层 sublayout，再重新拼接：

```cpp
auto same_r = make_layout(
    coalesce(layout<0>(a)),
    coalesce(layout<1>(a)));
```

逐 mode 观察：

```text
mode-0：2:1          -> 2:1
mode-1：(1,6):(6,2) -> 6:2
```

重新组合：

```text
(2,6):(1,2)
```

普通 `coalesce(a)` 还会继续跨顶层 mode 合并，得到：

```text
12:1
```

所以二者用途不同：

| 操作 | 目标 |
|---|---|
| `coalesce(a)` | 尽可能化简整个一维映射 |
| `coalesce(a, Step<_1,_1>{})` | 分别化简指定 mode，同时保留目标结构 |

---

## 10. C++ 最小示例

```cpp
#include <cute/tensor.hpp>
#include <iostream>

using namespace cute;

int main() {
  auto a = Layout<
      Shape <_2, Shape <_1, _6>>,
      Stride<_1, Stride<_6, _2>>>{};

  auto flat_result = coalesce(a);
  auto mode_result = coalesce(a, Step<_1,_1>{});

  print(a);            // (2,(1,6)):(1,(6,2))
  print(flat_result);  // 12:1
  print(mode_result);  // (2,6):(1,2)
  std::cout << '\n';

  static_assert(size(flat_result) == size(a));

  for (int i = 0; i < size(a); ++i) {
    if (flat_result(i) != a(i)) {
      std::cerr << "coalesce mismatch at i=" << i << '\n';
      return 1;
    }
  }

  return 0;
}
```

验证 Layout 代数时，建议始终保留这种逐点检查：

```text
变换前.size == 变换后.size
变换前(i)   == 变换后(i)
```

---

## 11. 常见误区

### 误区 1：Shape 的乘积相同就能合并

错误。还必须检查 stride 递推关系：

```text
d_next == s_current*d_current
```

### 误区 2：只要地址落在一段连续区间就能合并

错误。`coalesce` 保持的是标量自然序下的输出顺序，不只是像集。

### 误区 3：`coalesce` 等于 `flatten`

错误。`flatten` 只去括号；`coalesce` 还会删除退化 mode 并融合满足条件的相邻 mode。

### 误区 4：结果是一维 Layout，所以原来的二维坐标仍可直接使用

错误。普通 `coalesce` 只承诺标量输入映射等价，不承诺保留原坐标结构。

### 误区 5：能合并说明 Layout 连续且无别名

错误。`12:0` 也可以是合法的 coalesce 结果。

---

## 12. 本节练习

练习题及参考答案分别见：

- [练习题](练习题.md)
- [参考答案](自测参考答案.md)

建议先手算，再运行：

```bash
python3 -m unittest -v 03-Layout-Algebra/01-Coalesce/代码实验/test_coalesce_examples.py
```

---

## 13. 完成标准

看到任意静态 Layout 后，能够：

1. 拍平 Shape/Stride 的叶子；
2. 删除静态 size-1 mode；
3. 从左到右应用相邻 mode 合并条件；
4. 写出化简前后的标量输出序列；
5. 判断是否需要 by-mode coalesce；
6. 不把可合并误认为连续、单射或无广播。

## 官方资料

- NVIDIA CUTLASS CuTe Layout Algebra：`media/docs/cpp/cute/02_layout_algebra.md`
- NVIDIA CUTLASS Coalesce unit test：`test/unit/cute/core/coalesce.cpp`
