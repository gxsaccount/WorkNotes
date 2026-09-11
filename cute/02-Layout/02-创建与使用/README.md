# 02 Layout 创建与使用

> 官方对应：`01_layout.md` 的 Layout Creation and Use
>
> 更新：2026-09-11

## 1. 构造 Shape、Stride 和 Layout

CuTe 通常使用 `make_*` 函数构造对象：

```cpp
auto shape  = make_shape(Int<2>{}, 4);
auto stride = make_stride(Int<12>{}, Int<1>{});
auto layout = make_layout(shape, stride);
```

打印形式为：

```text
(_2,4):(_12,_1)
```

下划线表示静态整数，没有下划线的 `4` 是动态整数。

### 1.1 一维 Layout

```cpp
auto static_layout  = make_layout(Int<8>{});
auto dynamic_layout = make_layout(8);
```

当 Stride 被省略时，CuTe 会生成默认 stride。对于一维 Shape，结果相当于：

```text
8:1
```

### 1.2 显式指定 Stride

```cpp
auto layout = make_layout(
    make_shape(Int<2>{}, 4),
    make_stride(Int<12>{}, Int<1>{}));
```

其映射是：

```text
L(i,j) = 12*i + j
```

---

## 2. LayoutLeft 与 LayoutRight

当只提供 Shape 时，`make_layout` 默认按 `LayoutLeft` 生成 Stride。

可以把构造方式分成三种：

```cpp
// 没有提供 Stride：默认用 LayoutLeft 自动生成
make_layout(shape);

// 没有提供具体 Stride，但显式选择生成规则
make_layout(shape, LayoutLeft{});
make_layout(shape, LayoutRight{});

// 已经提供具体 Stride：直接使用，不再自动生成
make_layout(shape, stride);
```

因此，`LayoutLeft` 和 `LayoutRight` 本质上是 **Stride 生成策略**。只有需要 CuTe 根据 Shape 自动生成紧凑 Stride 时，才会使用它们；如果已经显式给出 Stride，最终映射完全由给出的 Stride 决定。

### 2.1 LayoutLeft

`LayoutLeft` 从左向右读取 Shape，用左侧各 mode 的累计乘积生成 Stride：

```text
Shape  = (s0,s1,s2)
Stride = (1, s0, s0*s1)
```

例如：

```text
Shape  = (2,3,4)
Stride = (1,2,6)
L(i,j,k) = i + 2*j + 6*k
```

最左侧 mode-0 的 stride 为 1，所以它是连续方向。对于普通 depth-1 二维 Shape，这通常对应 column-major。

### 2.2 LayoutRight

`LayoutRight` 从右向左读取 Shape，用右侧各 mode 的累计乘积生成 Stride：

```text
Shape  = (s0,s1,s2)
Stride = (s1*s2, s2, 1)
```

例如：

```text
Shape  = (2,3,4)
Stride = (12,4,1)
L(i,j,k) = 12*i + 4*j + k
```

最右侧 mode-2 的 stride 为 1，所以它是连续方向。对于普通 depth-1 二维 Shape，这通常对应 row-major。

两种规则可以并排记忆：

| 生成规则 | `(2,3,4)` 的 Stride | 连续方向 |
|---|---|---|
| `LayoutLeft` | `(1,2,6)` | 最左侧 mode |
| `LayoutRight` | `(12,4,1)` | 最右侧 mode |

这里的 exclusive product 不包含当前 mode：

```text
LayoutLeft：只乘当前 mode 左侧的 Shape
LayoutRight：只乘当前 mode 右侧的 Shape
```

### 2.3 层级 Shape 的注意事项

官方文档特别强调：Stride 生成过程不因为 Shape 的括号层级而停止。

因此，对层级 Shape 使用 `LayoutLeft` 或 `LayoutRight` 时，不要只凭“行主序/列主序”的二维直觉猜结果，应直接：

1. 展开所有叶子 shape；
2. 按对应方向计算前缀积；
3. 再恢复原有 tuple profile。

### 2.4 什么场景会使用 LayoutRight

判断标准是：

> 如果希望最右侧的坐标增加 1 时，最终 index 也增加 1，就适合使用 `LayoutRight`。

#### C/C++ 的普通二维数组

对于：

```cpp
float matrix[M][N];
```

坐标 `(row,col)` 的线性 index 是：

```text
index = row * N + col
```

对应的 CuTe Layout 为：

```text
Shape       = (M,N)
LayoutRight = (M,N):(N,1)
```

同一行中不断增加 `col` 时，访问的 index 连续：

```text
matrix[row][0]
matrix[row][1]
matrix[row][2]
```

因此，对于普通的 depth-1 二维 Shape，`LayoutRight` 通常用来生成 row-major Layout。

#### 最后一维连续的高维数组

对于传统 row-major 的四维 Shape：

```text
(N,C,H,W)
```

`LayoutRight` 生成：

```text
(C*H*W, H*W, W, 1)
```

最右侧的 `W` mode stride 为 1，因此该方向连续。

#### 描述已有的 row-major 数据

当外部数据已经按照 row-major 保存时，可以使用：

```cpp
auto layout = make_layout(make_shape(M, N), LayoutRight{});
```

常见情况包括：

- C/C++ 二维数组；
- 以最后一维连续方式保存的张量；
- row-major 矩阵接口；
- GEMM 中按行连续保存的输入或输出矩阵。

#### GPU 合并访存

假设矩阵坐标为 `(m,n)`，相邻线程主要改变 `n`。如果使用：

```text
(M,N):(N,1)
```

那么相邻线程访问的 index 也可能相邻，更容易形成合并访存。

但 `LayoutRight` 本身不保证性能更好。还必须同时检查：

```text
相邻线程改变哪个坐标
该坐标对应的 stride 是多少
元素类型和访问宽度是什么
```

#### 与 LayoutLeft 对比

```text
Shape = (M,N)

LayoutLeft  -> (M,N):(1,M)  // 左侧 M mode 连续
LayoutRight -> (M,N):(N,1)  // 右侧 N mode 连续
```

可以用一句话判断：

```text
希望左侧 mode 连续：LayoutLeft
希望右侧 mode 连续：LayoutRight
需要其他访问规律：显式指定 Stride
```

`LayoutLeft` 和 `LayoutRight` 都只是根据 Shape 自动生成紧凑 Stride 的便利工具，并不是对已有 Layout 执行左移、右移或转置。

---

## 3. 调用 Layout

Layout 的基本使用方式是：

```cpp
layout(coord)
```

对于：

```text
L = (4,2):(1,4)
```

调用：

```cpp
L(m,n)
```

等价于：

```text
m*1 + n*4
```

可以使用二维循环观察映射：

```cpp
for (int m = 0; m < size<0>(layout); ++m) {
  for (int n = 0; n < size<1>(layout); ++n) {
    printf("%d ", layout(m,n));
  }
  printf("\n");
}
```

其中：

```text
size<0>(layout) 取第 0 个 mode 的大小
size<1>(layout) 取第 1 个 mode 的大小
```

`layout(i)` 的一维坐标转换涉及 `idx2crd`、自然坐标和 `crd2idx`，统一放在下一节学习：

[坐标与兼容性：`layout(i)` 的完整计算过程](../03-坐标与兼容性/README.md#5-layouti-的完整计算过程)

---

## 4. Vector Layout

CuTe 将 `rank == 1` 的 Layout 视为 vector。

最简单的一维向量：

```text
8:1

coordinate: 0 1 2 3 4 5 6 7
index:      0 1 2 3 4 5 6 7
```

带间隔的向量：

```text
8:2

coordinate: 0 1 2 3 4 5 6 7
index:      0 2 4 6 8 10 12 14
```

rank 看顶层，而不是叶子 mode 数量。因此下面仍是 rank-1 vector：

```text
((4,2)):((2,1))
```

它的顶层只有一个 mode，只是该 mode 内部又包含两个子 mode。

这种表示可以把复杂的地址顺序包装成一个逻辑向量。

---

## 5. Matrix Layout

CuTe 将 `rank == 2` 的 Layout 视为 matrix。

### 5.1 column-major 示例

```text
(4,2):(1,4)
```

第 0 个 mode 的 stride 为 1，因此沿第 0 个坐标方向连续。

### 5.2 row-major 示例

```text
(4,2):(2,1)
```

第 1 个 mode 的 stride 为 1，因此沿第 1 个坐标方向连续。

对普通 depth-1 矩阵，可以把 majorness 理解为：

```text
哪个 mode 的 stride 为 1，哪个 mode 就是连续方向
```

### 5.3 层级矩阵

下面仍然是 rank-2：

```text
((2,2),2):((4,1),2)
```

原因是顶层 Shape 为：

```text
((2,2), 2)
```

顶层包含两个 mode。第 0 个 mode 是一个包含两个子 mode 的 multi-mode。

它在逻辑上仍可作为二维矩阵访问，但第 0 个方向不再由单一 stride 描述。

---

## 6. 层级访问函数

对于嵌套对象，可以通过多个模板索引向内访问：

```cpp
get<I0,I1,...>(x)
rank<I0,I1,...>(x)
depth<I0,I1,...>(x)
shape<I0,I1,...>(x)
size<I0,I1,...>(x)
```

例如，若：

```text
Shape = (4,(3,6))
```

那么：

```text
get<1>(shape)    -> (3,6)
get<1,0>(shape)  -> 3
size<1>(shape)   -> 18
```

这类接口使算法可以直接操作某个逻辑 mode，而不必先手动拆解整个 tuple。

---

## 7. 可视化

官方提供了两类常见辅助工具：

```cpp
print_layout(layout);
print_latex(layout);
```

- `print_layout` 适合在终端查看 rank-2 Layout 的映射表；
- `print_latex` 可以生成用于可视化的 LaTeX。

学习阶段建议同时记录：

1. Layout 的 `Shape:Stride`；
2. rank-D 表格；
3. 一维自然序下的 index 序列。

三个视角放在一起，最容易发现“逻辑遍历顺序”和“物理 index 顺序”的区别。

---

## 8. 本节自测

以下问题留给学习者作答：

1. 省略 Stride 时，`make_layout` 默认使用哪个方向生成 stride？
2. 为什么 `((4,2)):((2,1))` 是 vector，而不是 matrix？
3. 对层级 Shape 使用 `LayoutRight` 时，为什么应谨慎套用普通 row-major 直觉？
4. 分别用二维表格和一维自然序观察 `(4,2):(2,1)`，两种输出顺序有什么区别？

完成后参阅：[自测参考答案](自测参考答案.md)。
