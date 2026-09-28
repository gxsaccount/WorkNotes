# 09 TMA Tensors：看懂 TMA 坐标计算器

> 官方对应：`media/docs/cpp/cute/0z_tma_tensors.md`
>
> 官方基线：NVIDIA CUTLASS `main`，文档最近一次修改提交
> `0d2b201e8c1c4a03efa6e9c468161916e2334725`，核对日期 2026-09-24
>
> 本地整理：2026-09-28

## 1. 先看构造代码

官方教程只展示了目标打印结果，没有给出生成它的完整代码。根据打印中的
Iterator、Shape 和 Stride，可以写出下面的等价构造：

```cpp
auto tensor =
    make_tensor(
        make_inttuple_iter(
            0, Int<0>{}, Int<0>{}, Int<0>{}),

        make_shape(
            make_shape(Int<128>{}, Int<64>{}),
            2, 3, 1),

        make_stride(
            make_stride(E<0>{}, E<1>{}),
            Int<64>{} * E<1>{},
            E<2>{},
            E<3>{}));

print(tensor);
print("\n");
```

这里使用 `print(tensor)` 打印 Tensor 的结构。`print_tensor(tensor)` 会尝试枚举
Tensor 中的坐标值，不只是打印结构。

---

## 2. 这段代码有什么作用

这段代码构造的是一个**坐标计算器**，不是保存矩阵数据的 Tensor。

它接收当前 CuTe view 中的逻辑坐标：

```text
((i,j),k,l,m)
```

然后计算出：

```text
(i, j + 64*k, l, m)
```

在 TMA load/store 中，这个输出表示 TMA descriptor 所描述的原 Tensor 逻辑坐标，
用于告诉硬件：

```text
“从原 Tensor 的这个逻辑位置开始搬数据。”
```

三组构造参数的职责是：

```text
make_inttuple_iter(...)：定义输出坐标的起点
make_shape(...)：        定义允许输入的逻辑坐标范围
make_stride(...)：       定义输入坐标到输出坐标的换算规则
```

---

## 3. `print(tensor)` 的结果

```text
ArithTuple(0,_0,_0,_0) o
((_128,_64),2,3,1):((_1@0,_1@1),_64@1,_1@2,_1@3)
```

它与构造代码一一对应：

```text
make_inttuple_iter(...) → ArithTuple(0,_0,_0,_0)
make_shape(...)         → ((_128,_64),2,3,1)
make_stride(...)        → ((_1@0,_1@1),_64@1,_1@2,_1@3)
```

---

## 4. 打印结果中各部分的作用

```text
ArithTuple(0,_0,_0,_0)   o   ((_128,_64),2,3,1) : ((_1@0,_1@1),_64@1,_1@2,_1@3)
─────────────────────         ─────────────────    ─────────────────────────────
       ① 起点                       ② 形状                    ③ 怎么走
```

### 4.1 ① `ArithTuple(0,_0,_0,_0)`：输出坐标的起点

它表示输出坐标从：

```text
(0,0,0,0)
```

开始。

更准确地说：

```text
ArithmeticTuple：        一个可以进行算术运算的坐标 tuple
ArithmeticTupleIterator：保存和移动这个坐标的 iterator
```

打印中的 `ArithTuple(...)` 表示 iterator 当前保存的坐标值。

`_0` 是 CuTe 的编译期整数 `Int<0>`。它和普通 `0` 的数值相同，但类型不同。

### 4.2 ② `((_128,_64),2,3,1)`：输入坐标的 Shape

这是坐标计算器能够接收的逻辑坐标 Shape：

```text
mode-0 = (128,64)
mode-1 = 2
mode-2 = 3
mode-3 = 1
```

其中 mode-0 自身又包含两个子 mode，所以输入坐标写成：

```text
((i,j),k,l,m)
```

各分量范围为：

```text
i ∈ [0,128)
j ∈ [0, 64)
k ∈ [0,  2)
l ∈ [0,  3)
m ∈ [0,  1)
```

它不是“先分成 2 份，再分成 3 份”的操作过程，而是一个嵌套 Shape。

### 4.3 ③ `((_1@0,_1@1),_64@1,_1@2,_1@3)`：坐标换算规则

普通 CuTe Stride 通常表示：

```text
一个输入坐标增加 1，整数 offset 增加多少。
```

这里的 Basis stride 表示：

```text
一个输入坐标增加 1，输出逻辑坐标的哪个方向增加多少。
```

`@` 后面的数字是输出方向编号，从 0 开始。

| 输入逻辑维度 | Stride | 意思 |
|---|---|---|
| mode-0 的子维 0，大小 128 | `_1@0` | 走一步，输出第 0 个方向 `+1` |
| mode-0 的子维 1，大小 64 | `_1@1` | 走一步，输出第 1 个方向 `+1` |
| mode-1，大小 2 | `_64@1` | 走一步，输出第 1 个方向 `+64` |
| mode-2，大小 3 | `_1@2` | 走一步，输出第 2 个方向 `+1` |
| mode-3，大小 1 | `_1@3` | 走一步，输出第 3 个方向 `+1` |

可以直接把它读成：

```text
1@0：把对应输入放到输出坐标第 0 维
1@1：把对应输入放到输出坐标第 1 维
64@1：把对应输入乘 64，再放到输出坐标第 1 维
1@2：把对应输入放到输出坐标第 2 维
1@3：把对应输入放到输出坐标第 3 维
```

#### 逐行解释 `make_stride`

代码：

```cpp
make_stride(
    make_stride(E<0>{}, E<1>{}),
    Int<64>{} * E<1>{},
    E<2>{},
    E<3>{})
```

它必须和 Shape 的层级结构对齐：

```cpp
make_shape(
    make_shape(Int<128>{}, Int<64>{}),
    2,
    3,
    1)
```

对应关系为：

```text
Shape  = ((128,64), 2,    3,   1)
Stride = ((1@0,1@1),64@1,1@2,1@3)
```

因此输入坐标为：

```text
((i,j),k,l,m)
```

每一项的含义如下。

##### `make_stride(E<0>{}, E<1>{})`

它对应 Shape 中嵌套的第一个 mode：

```text
(128,64)
```

其中：

```text
E<0>{} = 1@0 ≈ (1,0,0,0)
E<1>{} = 1@1 ≈ (0,1,0,0)
```

所以：

```text
i * E<0>{} → (i,0,0,0)
j * E<1>{} → (0,j,0,0)
```

##### `Int<64>{} * E<1>{}`

它对应输入坐标 `k`：

```text
k * (64@1) → (0,64*k,0,0)
```

`j` 和 `k` 都写入输出坐标第 1 维，因此会相加：

```text
输出第 1 维 = j + 64*k
```

这里的 `64` 正好是 `j` 所在 mode 的大小。可以把 `(j,k)` 理解成：

```text
j：一个 64 元素分块中的位置
k：选择第几个 64 元素分块
```

所以将它们还原为原 Tensor 坐标时：

```text
original_j = j + 64*k
```

##### `E<2>{}`

它对应输入坐标 `l`：

```text
l * E<2>{} → (0,0,l,0)
```

即直接把 `l` 放入输出坐标第 2 维。

##### `E<3>{}`

它对应输入坐标 `m`：

```text
m * E<3>{} → (0,0,0,m)
```

即直接把 `m` 放入输出坐标第 3 维。

##### 最终相加

```text
(i,0,0,0)
+ (0,j,0,0)
+ (0,64*k,0,0)
+ (0,0,l,0)
+ (0,0,0,m)
= (i, j + 64*k, l, m)
```

---

## 举个具体例子

假设输入逻辑坐标为：

```text
((i=2,j=3),k=1,l=0,m=0)
```

按规则计算：

```text
i=2 → 输出第 0 个方向 +2
j=3 → 输出第 1 个方向 +3
k=1 → 输出第 1 个方向 +64×1
l=0 → 输出第 2 个方向 +0
m=0 → 输出第 3 个方向 +0
```

最终坐标为：

```text
(2,67,0,0)
```

因为：

```text
67 = 3 + 64×1
```

所以整行打印表达的完整映射就是：

```text
输入：((i,j),k,l,m)
输出：(i, j + 64*k, l, m)
```

这就是它的全部工作。

---

## 为什么需要这东西

在 Hopper 及后续 GPU 上使用 TMA 搬数据时：

1. 原 Tensor 在显存中的基址、Shape 和 Stride 由 TMA descriptor 描述；
2. 本次从原 Tensor 的哪个逻辑位置开始搬，由 TMA coordinate 指定。

TMA 一次可以搬运整个多维 tile，不需要每个线程分别计算每个元素的 GMEM 地址。
官方教程还特别说明：

- descriptor 可以描述 1～5 维 Tensor；
- descriptor 中还包含元素类型、SMEM box、swizzle 和越界行为等配置；
- descriptor 在 kernel 启动前由 host 创建；
- 多个 CTA 可以使用同一个 descriptor。

假设 descriptor 描述矩阵：

```text
A[M,N]
```

那么：

```text
TMA coordinate = (m,n)
```

就是原 Tensor 的逻辑位置：

```text
A(m,n)
```

硬件根据 descriptor 中的基址和 Stride，将 `(m,n)` 转换为真实内存位置。

因此：

```text
TMA descriptor：原 Tensor 的地图
TMA coordinate： 本次从哪里开始搬的逻辑坐标
TMA Tensor：     生成这个逻辑坐标的计算器
```

这里讨论的 `ArithTuple` Tensor 不保存数据，也不输出线性内存地址。它输出的是交给
TMA descriptor 的逻辑坐标。

---

## 再打个比方

想象一个仓库，也就是显存。

```text
TMA descriptor 是仓库地图：
  记录货架从哪里开始、每排多长、各维度如何排列。

TMA coordinate 是提货单：
  写着“从第 m 排、第 n 列开始取货”。

TMA Tensor 是提货单生成器：
  根据当前 tile、CTA 和 pipeline 的坐标，自动算出 (m,n)。

TMA hardware 是仓库管理员：
  根据地图和提货单找到真实地址，并搬运整个 tile。
```

所以看到：

```text
ArithTuple(...) o Shape:Stride
```

可以先把它理解成：

```text
一个将当前 CuTe view 坐标转换成原 Tensor 坐标的计算器。
```

---

## 官网教程补充：为什么 Tensor 可以生成坐标

前面的解释已经足够用来读打印结果，但官网还补了两个概念，用于说明这种坐标
Tensor 为什么能成立。

### 1. Tensor 的 Iterator 不一定是 Pointer

官网首先使用 `counting_iterator`：

```cpp
Tensor values =
    make_tensor(
        counting_iterator<int>(42),
        make_shape(4,5));
```

`counting_iterator<int>(42)` 可以理解为从 `42` 开始的数字生成器：

```text
*iter       = 42
*(iter + 1) = 43
*(iter + 2) = 44
```

它不指向一份真实数组。Tensor 根据 Layout 给出的 offset 即时生成数值：

```text
values(i,j) = 42 + i + 4*j
```

官网用这个例子说明：

> CuTe Tensor 的 Iterator 不一定是内存指针，也可以是一个按需生成值的对象。

既然 Iterator 可以生成整数，也就可以生成坐标。

### 2. `ArithmeticTupleIterator` 是坐标生成器

`ArithmeticTupleIterator` 保存一个 tuple 坐标，并允许加上另一个 tuple：

```cpp
auto coord_iter =
    make_inttuple_iter(42, Int<2>{}, Int<7>{});

auto moved_iter =
    coord_iter + make_tuple(Int<0>{}, 5, Int<2>{});

print(*moved_iter);  // (42,7,_9)
```

计算过程就是：

```text
(42,2,7) + (0,5,2) = (42,7,9)
```

普通 pointer 加的是整数 offset；这个 Iterator 加的是坐标 tuple。

### 3. 官方的最小坐标 Tensor

```cpp
Tensor coord =
    make_tensor(
        make_inttuple_iter(0,0),
        make_shape (     4,      5),
        make_stride(E<0>{}, E<1>{}));
```

其中：

```text
E<0>{} 打印为 1@0
E<1>{} 打印为 1@1
```

因此：

```text
coord(i,j) = (i,j)
```

如果交换两个 Basis stride：

```cpp
Tensor swapped =
    make_tensor(
        make_inttuple_iter(0,0),
        make_shape (     4,      5),
        make_stride(E<1>{}, E<0>{}));
```

则：

```text
swapped(i,j) = (j,i)
```

这不是说 TMA 主要用于转置。官网只是用最简单的坐标交换来证明：Basis stride
可以控制每个输入 mode 应该进入输出坐标的哪个方向。

---

## 它在实际代码里怎么用

下面只保留 CUTLASS 官方 Hopper 示例中的 TMA load 主线。

### 1. Host 侧创建 TMA Atom

先用普通 pointer Tensor 描述原矩阵 A：

```cpp
auto M  = int(m);
auto K  = int(k);
auto dA = make_stride(Int<1>{}, ldA);

Tensor mA =
    make_tensor(
        A,
        make_shape(M, K),
        dA);
```

定义一次 TMA 搬运的 tile 和目标 SMEM Layout：

```cpp
auto bM     = Int<128>{};
auto bK     = Int<64>{};
auto stages = Int<3>{};

auto sA_layout =
    tile_to_shape(
        GMMA::Layout_MN_SW128_Atom<ElementA>{},
        make_shape(bM, bK, stages));
```

创建 TMA Atom：

```cpp
auto tmaA =
    make_tma_atom(
        SM90_TMA_LOAD{},
        mA,
        sA_layout(_,_,0),
        make_shape(bM, bK));
```

这一步告诉 CuTe：

```text
从 mA 搬数据
每次搬 (128,64)
搬到 sA_layout 描述的 shared memory
使用 SM90_TMA_LOAD
```

### 2. Kernel 中取得 TMA 坐标计算器

```cpp
Tensor mA_coord =
    tmaA.get_tma_tensor(make_shape(M, K));
```

这里的 `mA_coord` 不保存 A 的数据：

```text
mA_coord(m,k) = 原矩阵逻辑坐标 (m,k)
```

例如：

```text
mA_coord(5,7) = (5,7)
```

### 3. 取得当前 CTA 的坐标 View

```cpp
auto cta_coord =
    make_coord(blockIdx.x, blockIdx.y, _);

Tensor gA_coord =
    local_tile(
        mA_coord,
        cta_tiler,
        cta_coord,
        Step<_1, X, _1>{});
```

`local_tile` 在这里没有加载数据。它只是让坐标计算器指向当前 CTA 负责的 tile。

### 4. 配对 GMEM 坐标与 SMEM 目标

```cpp
Tensor sA =
    make_tensor(
        make_smem_ptr(shared_storage.A.begin()),
        SmemLayoutA{});

auto [tAgA, tAsA] =
    tma_partition(
        tmaA,
        Int<0>{},
        Layout<_1>{},
        group_modes<0,2>(sA),
        group_modes<0,2>(gA_coord));
```

其中：

```text
tAgA：提供当前 GMEM tile 的原 Tensor 逻辑坐标
tAsA：指向当前 pipeline stage 的 SMEM 目标
```

### 5. 真正发起 TMA 搬运

```cpp
copy(
    tmaA.with(tma_barrier[0]),
    tAgA(_, k_tile),
    tAsA(_, pipe));
```

这三个参数可以读成：

```text
tmaA.with(barrier)：使用哪个 descriptor，并在完成时通知哪个 barrier
tAgA(_,k_tile)：    从原 Tensor 的哪个逻辑坐标开始搬
tAsA(_,pipe)：       搬到哪个 SMEM tile
```

真正的数据搬运发生在 `copy(...)`。此前的 `get_tma_tensor`、`local_tile` 和
`tma_partition` 都是在生成、变换或整理逻辑坐标。

完整 TMA kernel 还必须正确初始化和等待 barrier。上面的代码只用于展示坐标
Tensor 如何进入实际 TMA load 数据流。

---

## 完整流程

```text
Host
  A pointer + Shape + Stride
        │
        ▼
  make_tma_atom
        │
        ▼
  TMA descriptor

Kernel
  get_tma_tensor
        │
        ▼
  原 Tensor 坐标计算器
        │ local_tile
        ▼
  当前 CTA tile 的原 Tensor 坐标
        │ tma_partition
        ▼
  GMEM 坐标 + SMEM 目标
        │ copy
        ▼
  GMEM tile ───TMA───► SMEM tile
```

---

## 最后只记三句话

1. **`ArithTuple(...) o Shape:Stride` 是坐标计算器，不是数据 Tensor。**
2. **Basis stride 中的 `n@d` 表示向输出坐标第 `d` 维贡献 `n`。**
3. **TMA Tensor 负责生成原 Tensor 逻辑坐标，`copy(...)` 才负责搬数据。**

## 官方资料

- [CuTe TMA Tensors](https://docs.nvidia.com/cutlass/latest/media/docs/cpp/cute/0z_tma_tensors.html)
- [官方 Markdown](https://github.com/NVIDIA/cutlass/blob/main/media/docs/cpp/cute/0z_tma_tensors.md)
- [官方 Hopper WGMMA + TMA 示例](https://github.com/NVIDIA/cutlass/blob/main/examples/cute/tutorial/hopper/wgmma_tma_sm90.cu)
- [官方 TMA load testbed](https://github.com/NVIDIA/cutlass/blob/main/test/unit/cute/hopper/tma_load_testbed.hpp)
