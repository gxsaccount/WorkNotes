# CUDA 与矩阵计算基础

> 更新：2026-09-11

## 1. 本章在 CuTe 学习中的位置

CuTe 的 Layout 最终服务于 GPU kernel 中的坐标和地址计算。后续看到复杂的
`Shape`、`Stride`、`Tensor`、`TiledCopy` 和 `TiledMMA` 时，都可以回到三个问题：

1. 当前坐标属于哪个 tile？
2. 当前 thread 负责 tile 中的哪些元素？
3. 这些元素对应哪些内存地址？

因此第一章的重点不是记忆 CUDA API，而是建立“线程坐标 → 数据坐标 → 内存地址”的完整链路。

---

## 2. CUDA 执行层级

```text
Grid
└── Block / CTA
    └── Warp
        └── Thread
```

### 2.1 Thread

Thread 是 kernel 的一个执行实例。每个 thread 都有自己的：

- `threadIdx`
- 局部变量
- register 状态

矩阵 kernel 中，常见的第一步是让一个 thread 对应一个或多个矩阵元素。

### 2.2 Warp

Warp 是 GPU 执行和调度线程时的重要分组。一个 warp 中的线程共同执行指令。

如果同一个 warp 中的线程走向不同控制分支，硬件通常需要分别执行不同分支路径，
这就是常说的 warp divergence。

学习 CuTe 时，需要经常思考：

- 一个 warp 覆盖多大的矩阵区域？
- warp 内相邻 lane 访问的地址是否连续？
- 每个 lane 最终持有多少个 accumulator？

### 2.3 Block / CTA

Block 在 CUTLASS 和 CuTe 语境中也常称为 CTA。

同一个 block 中的线程可以：

- 使用同一块 shared memory
- 通过 `__syncthreads()` 进行 block 内同步
- 合作加载和计算一个矩阵 tile

普通 kernel 中，不应假设不同 block 之间存在执行顺序，也不能用
`__syncthreads()` 同步不同 block。

### 2.4 Grid

一次 kernel launch 会产生一个 grid。Grid 由多个 block 构成，用来覆盖完整问题规模。

---

## 3. 从线程索引得到矩阵坐标

### 3.1 一维索引

```cpp
int x = blockIdx.x * blockDim.x + threadIdx.x;
```

其中：

- `blockIdx.x`：当前 block 在 grid 中的位置
- `blockDim.x`：每个 block 的线程数
- `threadIdx.x`：当前 thread 在 block 中的位置

### 3.2 二维索引

```cpp
int x = blockIdx.x * blockDim.x + threadIdx.x;
int y = blockIdx.y * blockDim.y + threadIdx.y;
```

在矩阵代码中通常写成：

```cpp
int col = blockIdx.x * blockDim.x + threadIdx.x;
int row = blockIdx.y * blockDim.y + threadIdx.y;
```

这是约定，不是 CUDA 强制规定。关键是代码中的坐标含义必须保持一致。

### 3.3 Grid 大小

如果矩阵大小为 `M × N`，block 大小为 `BM × BN`，那么需要向上取整：

```cpp
dim3 block(BN, BM);
dim3 grid((N + BN - 1) / BN,
          (M + BM - 1) / BM);
```

因为 `M`、`N` 不一定能整除 tile 大小，所以 kernel 中还需要边界判断：

```cpp
if (row < M && col < N) {
    // 访问合法矩阵元素
}
```

---

## 4. GPU 内存层级

| 存储 | 主要可见范围 | 典型用途 |
|---|---|---|
| Register | 单个 thread | 局部变量、thread tile、accumulator |
| Shared memory | 单个 block | CTA 内线程协作、tile 缓存和数据重排 |
| Global memory | 整个 device | 输入、输出和大规模数据 |

### 4.1 Register

Register 通常用于保存单个 thread 的临时数据和计算结果。

GEMM 中，每个 thread 常在 register 中维护一个小的 C 子块：

```text
thread tile / accumulator fragment
```

Register 数量有限。单线程 register 使用过多可能降低同时驻留在 SM 上的 block 或 warp 数量。

### 4.2 Shared memory

Shared memory 由同一 block 内的线程共享，常用于：

- 缓存 A、B 的 tile
- 让一次 global memory 加载被多个线程复用
- 调整数据布局以适配后续计算
- 在 global memory 和 register 之间建立中间层

Shared memory 是显式管理的存储，需要正确处理：

- 合作加载
- 越界填零或 predication
- `__syncthreads()`
- bank conflict

### 4.3 Global memory

Global memory 容量大，但访问成本相对较高。优化目标通常不是完全避免 global memory，
而是：

- 让访问尽量合并
- 让加载的数据得到充分复用
- 使用足够的并行计算隐藏延迟

---

## 5. 合并访存、数据复用与 bank conflict

这三个概念解决的是不同问题，不能混为一谈。

### 5.1 合并访存

当一个 warp 中的相邻线程访问相邻 global memory 地址时，硬件更容易把这些访问组织成
较少的内存事务。

友好的访问形式：

```cpp
float value = data[base + threadIdx.x];
```

跨步访问：

```cpp
float value = data[base + threadIdx.x * stride];
```

后者不一定错误，但可能需要更多内存事务。

需要特别注意：

> 合并访存通常不会改变源码中每个 thread 发出的 load 数量，它主要减少完成这些
> load 所需要的 global memory transaction。

### 5.2 数据复用

数据复用指同一份数据被多个计算使用，却不需要每次都重新从 global memory 获取。

典型方法：

1. 线程合作把数据加载到 shared memory。
2. 多个线程从 shared memory 使用这份数据。
3. 单线程把反复使用的数据保存在 register 中。

因此：

```text
合并访存：优化一批 global memory 请求怎样完成
数据复用：减少需要重复发出的 global memory 请求
```

### 5.3 Shared memory bank conflict

Shared memory 在硬件上被划分为多个 bank。

同一个 warp 中的线程如果访问落在同一 bank 的不同地址，这些请求可能产生冲突并被拆分。
如果多个线程读取同一个地址，则可能通过广播高效完成，不能简单地把“同一 bank”全部理解为冲突。

矩阵转置中经常看到：

```cpp
__shared__ float tile[32][33];
```

多出的一列会改变相邻行的起始地址，从而避免某些固定跨步访问集中映射到相同 bank。

---

## 6. Shape、Stride、Coordinate 与 Offset

### 6.1 Layout 的基础模型

```text
Layout = Shape : Stride
coordinate -> offset
```

对于二维 Layout：

```text
shape  = (S0,S1)
stride = (D0,D1)
```

坐标 `(i,j)` 的 offset 为：

```text
offset(i,j) = i*D0 + j*D1
```

坐标范围：

```text
0 <= i < S0
0 <= j < S1
```

Shape 决定合法坐标范围，Stride 决定每个坐标分量变化一次时，offset 增加多少。

### 6.2 `(4,3):(1,4)`

```text
shape  = (4,3)
stride = (1,4)

(i,j) -> i + 4*j
```

按 CuTe 自然序展开时，第 0 个 mode 变化最快：

| 自然序编号 | 坐标 | offset |
|---:|---:|---:|
| 0 | `(0,0)` | 0 |
| 1 | `(1,0)` | 1 |
| 2 | `(2,0)` | 2 |
| 3 | `(3,0)` | 3 |
| 4 | `(0,1)` | 4 |
| 5 | `(1,1)` | 5 |
| 6 | `(2,1)` | 6 |
| 7 | `(3,1)` | 7 |
| 8 | `(0,2)` | 8 |
| 9 | `(1,2)` | 9 |
| 10 | `(2,2)` | 10 |
| 11 | `(3,2)` | 11 |

完整 offset 序列：

```text
0 1 2 3 4 5 6 7 8 9 10 11
```

例如：

```text
(2,1) -> 2*1 + 1*4 = 6
```

### 6.3 `(4,3):(3,1)`

```text
(i,j) -> 3*i + j
```

仍按 mode 0 变化最快的坐标顺序展开：

```text
0 3 6 9 1 4 7 10 2 5 8 11
```

这里要区分两个问题：

- **哪个坐标 mode 在自然序中变化最快？** mode 0。
- **哪个坐标方向在内存中连续？** stride 为 1 的方向。

### 6.4 Row-major 与 Column-major

如果 `(i,j)` 分别表示 `(row,col)`，矩阵大小为 `M × N`：

```text
row-major:    offset = row*N + col
              stride = (N,1)

column-major: offset = row + col*M
              stride = (1,M)
```

因此：

```text
(4,3):(3,1)  // row-major
(4,3):(1,4)  // column-major
```

“第 0 个 mode 自然序变化最快”是 CuTe 坐标枚举规则；“row-major/column-major”
描述的是坐标到内存地址的映射。两者不是同一个概念。

---

## 7. GEMM 的 M、N、K

矩阵乘法：

```text
A[M,K] * B[K,N] = C[M,N]
```

单个结果元素：

```text
C[m,n] = sum(A[m,k] * B[k,n]), k = 0 ... K-1
```

三个维度分别表示：

- `M`：C 的行数，也是 A 的行数
- `N`：C 的列数，也是 B 的列数
- `K`：A 的列数和 B 的行数，是归约维度

可以把它理解为三层循环：

```cpp
for (int m = 0; m < M; ++m) {
    for (int n = 0; n < N; ++n) {
        float sum = 0.0f;
        for (int k = 0; k < K; ++k) {
            sum += A[m * K + k] * B[k * N + n];
        }
        C[m * N + n] = sum;
    }
}
```

CuTe 和 CUTLASS 做的核心工作之一，就是把这三层逻辑循环映射到 GPU 的多层并行结构和
多层内存结构。

---

## 8. Naive CUDA GEMM

最直接的映射是一个 thread 计算一个 C 元素：

```cpp
__global__ void gemm_naive(const float* A,
                           const float* B,
                           float* C,
                           int M,
                           int N,
                           int K) {
    int col = blockIdx.x * blockDim.x + threadIdx.x;
    int row = blockIdx.y * blockDim.y + threadIdx.y;

    if (row < M && col < N) {
        float sum = 0.0f;

        for (int k = 0; k < K; ++k) {
            sum += A[row * K + k] * B[k * N + col];
        }

        C[row * N + col] = sum;
    }
}
```

启动方式：

```cpp
dim3 block(16, 16);
dim3 grid((N + block.x - 1) / block.x,
          (M + block.y - 1) / block.y);

gemm_naive<<<grid, block>>>(A, B, C, M, N, K);
```

完整程序还应检查 kernel launch 和同步错误，不能静默忽略：

```cpp
cudaError_t launch_error = cudaGetLastError();
if (launch_error != cudaSuccess) {
    // 输出错误并返回失败状态
}

cudaError_t sync_error = cudaDeviceSynchronize();
if (sync_error != cudaSuccess) {
    // 输出错误并返回失败状态
}
```

### 8.1 Naive GEMM 的重复读取

计算多个 C 元素时：

- `A[m,k]` 会被同一行的多个输出 `C[m,n]` 使用。
- `B[k,n]` 会被同一列的多个输出 `C[m,n]` 使用。

Naive kernel 没有显式保留这种跨线程共享关系，因而会重复从 global memory 请求相同数据。

这里还要区分：

- A 的某些相同地址读取可能由硬件广播或 cache 帮助。
- B 的相邻列访问可能是合并的。
- 这些机制可以改善实际访问，但没有改变算法本身缺少显式 tile 复用的事实。

---

## 9. Shared-memory Tiled GEMM

假设一个 block 计算 `BM × BN` 的 C tile，并把 K 维分成长度为 `BK` 的小段：

```text
A tile: BM × BK
B tile: BK × BN
C tile: BM × BN
```

执行过程：

```text
for each K tile:
    线程合作加载 A tile 和 B tile
    同步
    使用 shared memory 中的数据完成局部乘加
    同步

写回 C tile
```

两个同步点的作用不同：

1. 第一个同步保证所有线程都完成当前 tile 的加载。
2. 第二个同步保证所有线程都完成当前 tile 的使用，才能覆盖 shared memory。

### 9.1 一个简单的复用估算

以 `BM=BN=BK=16` 为例，一个 block 计算 `16×16` 个 C 元素。

Naive 方式在这一段 K 范围内需要的逻辑读取次数：

```text
2 * 16 * 16 * 16 = 8192
```

Tiled 方式合作加载：

```text
A tile: 16 * 16 = 256
B tile: 16 * 16 = 256
合计：512
```

加载到 shared memory 的每个 A 或 B 元素可被多个计算复用。这个估算用于理解算法层面的
复用，不等同于实际硬件 transaction、cache hit 或最终性能数据。

### 9.2 边界与同步

矩阵尺寸不能整除 tile 大小时，通常需要对越界加载进行 predication：

```cpp
shared_A[local_row][local_k] =
    valid_A ? A[global_row * K + global_k] : 0.0f;
```

需要特别小心：

> 如果某些 thread 在到达 `__syncthreads()` 前直接返回，而其他 thread 仍然执行同步，
> 可能导致错误行为。

因此 tiled kernel 常让所有 block 内线程参与同步，只把越界数据填零，并在最终写回时判断
输出坐标是否合法。

---

## 10. CTA、Warp、Thread 分块

现代 GEMM 通常具有多层 tile：

```text
完整 C 矩阵
└── CTA tile
    └── Warp tile
        └── Thread tile / MMA fragment
```

### 10.1 CTA Tile

一个 block/CTA 负责一块 C：

```text
CTA tile = BM × BN
```

相关线程合作加载对应的 A、B tile 到 shared memory。

### 10.2 Warp Tile

CTA tile 再分给多个 warp：

```text
CTA tile
└── 多个 warp tile
```

Warp tile 决定一个 warp 负责的输出区域，也是组织 MMA 指令和 shared-memory 读取的重要层级。

### 10.3 Thread Tile

一个 thread 通常不只计算一个标量，而是在 register 中维护多个 accumulator：

```text
thread tile = TM × TN
```

这样可以增加 register 中的数据复用，但 thread tile 和 register 使用量过大也会带来资源压力。

---

## 11. 与 CuTe Layout 的连接

不使用 CuTe 时，我们经常手写：

```cpp
int offset = row * stride_row + col * stride_col;
```

CuTe 把这种映射抽象为：

```text
Layout = Shape : Stride
coordinate -> offset
```

更复杂时，coordinate 可能是层级结构：

```text
(CTA coordinate,
 warp coordinate,
 thread coordinate,
 value coordinate)
```

后续的 CuTe Layout Algebra，主要是在编译期组合、切分和变换这些坐标映射，使它们能够描述：

- global memory 中的矩阵布局
- shared memory 中的 tile 布局
- thread 与数据的对应关系
- MMA 指令要求的 fragment 布局

第一章中的矩阵索引不是独立知识，而是后续所有 Layout 计算的具体物理含义。

---

## 12. 易混淆点

### 12.1 合并访存不等于数据复用

```text
合并访存：减少完成一组访问所需的内存事务
数据复用：减少相同数据从 global memory 重复获取
```

### 12.2 自然序不等于内存连续顺序

CuTe 自然序中 mode 0 坐标变化最快，但物理 offset 是否连续取决于 stride。

### 12.3 Block 二维形状不等于矩阵存储布局

`threadIdx.x` 对应 row 还是 col 是程序做出的映射选择。Row-major/column-major 描述的是
数据地址布局，不是 block 的形状。

### 12.4 Shared memory 不只是“缓存一行或一列”

GEMM 通常缓存 A、B 的二维 tile，让 A tile 沿 N 方向复用，让 B tile 沿 M 方向复用。

### 12.5 正确性优先于性能

优化前应先完成：

- 非整除尺寸的边界处理
- CPU reference 对比
- 合理的浮点误差判断
- CUDA API 和 kernel 错误检查

