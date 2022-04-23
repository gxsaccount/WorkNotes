# 形式 #  
  cuda_kernel<<<grid_size, block_size, sharedMemSize, stream>>>(...)  
cuda_kernel 是 global function 的标识，(...) 中是调用 cuda_kernel 对应的参数，这两者和 C++ 的语法是一样的，  
而 <<<grid_size, block_size, sharedMemSize, stream>>> 是 CUDA 对 C++ 的扩展    

grid_size 和 block_size 分别代表了本次 kernel 启动对应的 block 数量和每个 block 中 thread 的数量，所以显然两者都要大于 0。   
sharedMemSize 设置动态share_memory的大小（如extern __shared__ int _s[];）  
stream 设置streamid  

threadIdx是一个uint3类型，表示一个线程的索引。

blockIdx是一个uint3类型，表示一个线程块的索引，一个线程块中通常有多个线程。

blockDim是一个dim3类型，表示线程块的大小。

gridDim是一个dim3类型，表示网格的大小，一个网格中通常有多个线程块。  



block_size 最大可以取 1024  
同一个 block 中，连续的 32 个线程组成一个 warp，这 32 个线程每次执行同一条指令，也就是所谓的 SIMT，  
即使最后一个 warp 中有效的线程数量不足 32，也要使用相同的硬件资源，所以 block_size 最好是 32 的整数倍  


与 block 对应的硬件级别为 SM，SM 为同一个 block 中的线程提供通信和同步等所需的硬件资源，跨 SM 不支持对应的通信，所以一个 block 中的所有线程都是执行在同一个 SM 上的，而且因为线程之间可能同步，所以一旦 block 开始在 SM 上执行，block 中的所有线程同时在同一个 SM 中执行（并发，不是并行），也就是说 block 调度到 SM 的过程是原子的。SM 允许多于一个 block 在其上并发执行，如果一个 SM 空闲的资源满足一个 block 的执行，那么这个 block 就可以被立即调度到该 SM 上执行，具体的硬件资源一般包括寄存器、shared memory、以及各种调度相关的资源，这里的调度相关的资源一般会表现为两个具体的限制，Maximum number of resident blocks per SM 和 Maximum number of resident threads per SM ，也就是 SM 上最大同时执行的 block 数量和线程数量。  

# Occupancy #  
SM 上并发执行的线程数和SM 上最大支持的线程数的比值，被称为 Occupancy，更高的 Occupancy 代表潜在更高的性能。  

一个 kernel 的 block_size 应大于 SM 上最大线程数和最大 block 数量的比值，否则就无法达到 100% 的 Occupancy，对应不同的架构，这个比值不相同，对于 V100 、 A100、 GTX 1080 Ti 是 2048 / 32 = 64，对于 RTX 3090 是 1536 / 16 = 96，所以为了适配主流架构，如果静态设置 block_size 不应小于 96。考虑到 block 调度的原子性，那么 block_size 应为 SM 最大线程数的约数，否则也无法达到 100% 的 Occupancy，主流架构的 GPU 的 SM 最大线程数的公约是 512，96 以上的约数还包括 128 和 256，也就是到目前为止，block_size 的可选值仅剩下 128 / 256 / 512 三个值。  


还是因为 block 调度到 SM 是原子性的，所以 SM 必须满足至少一个 block 运行所需的资源，资源包括 shared memory 和寄存器， shared memory 一般都是开发者显式控制的，而如果 block 中线程的数量 * 每个线程所需的寄存器数量大于 SM 支持的每 block 寄存器最大数量，kernel 就会启动失败。目前主流架构上，SM 支持的每 block 寄存器最大数量为 32K 或 64K 个 32bit 寄存器，每个线程最大可使用 255 个 32bit 寄存器，编译器也不会为线程分配更多的寄存器，所以从寄存器的角度来说，每个 SM 至少可以支持 128 或者 256 个线程，block_size 为 128 可以杜绝因寄存器数量导致的启动失败，但是很少的 kernel 可以用到这么多的寄存器，同时 SM 上只同时执行 128 或者 256 个线程，也可能会有潜在的性能问题。但把 block_size 设置为 128，相对于 256 和 512 也没有什么损失，128 作为 block_size 的一个通用值是非常合适的。  


确定了 block_size 之后便可以进一步确定 grid_size，也就是确定总的线程数量，对于一般的 elementwise kernel 来说，总的线程数量应不大于总的 element 数量，  
也就是一个线程至少处理一个 element，同时 grid_size 也有上限，为 Maximum x-dimension of a grid of thread blocks ，  
目前在主流架构上都是 2^31 - 1，对于很多情况都是足够大的值。    



https://zhuanlan.zhihu.com/p/442304996
