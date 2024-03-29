多进程服务(MPS)是CUDA应用程序编程接口(API)的另一种二进制兼容实现。MPS运行时架构被设计成透明地启用协作的多进程CUDA应用程序(通常是MPI作业)，以利用最新的NVIDIA(基于kepler) gpu上的Hyper-Q功能。Hyper-Q允许CUDA内核在同一GPU上并行处理;这可以在GPU计算能力被单个应用程序进程未充分利用的情况下提高性能。
  
MPS是一个二进制兼容的客户端-服务器运行时实现的CUDA API，它由几个组件组成。  

控制守护进程——控制守护进程负责启动和停止服务器，以及协调客户端和服务器之间的连接。  

客户端运行时——MPS客户端运行时被构建到CUDA驱动程序库中，可以被任何CUDA应用程序透明地使用。  

服务器进程——服务器是客户端与GPU的共享连接，并在客户端之间提供并发性。  

MPS的好处：

１.提高GPU利用率  

单个进程可能无法利用GPU上所有可用的计算和内存带宽容量。MPS允许不同进程的内核和memcopy操作在GPU上重叠，从而实现更高的利用率和更短的运行时间。  

２.减少了对gpu的上下文存储

在没有MPS的情况下，使用GPU的每个CUDA进程在GPU上分配独立的存储和调度资源。相比之下，MPS服务器分配一个GPU存储副本，并调度所有客户端共享的资源。Volta MPS支持增加MPS客户机之间的隔离，因此资源减少的程度要小得多。

２.减少GPU上下文切换

如果没有MPS，当进程共享GPU时，它们的调度资源必须在GPU上和GPU外进行交换。MPS服务器在所有客户端之间共享一组调度资源，从而消除了GPU在这些客户端之间调度时的交换开销。
