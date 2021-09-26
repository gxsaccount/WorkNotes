
https://blog.csdn.net/ustc_dylan/article/details/45667227

https://zhuanlan.zhihu.com/p/367993367  

内存被分割成多个区域 BANK，也叫"簇"，依据簇与 CPU 的"距离"的不同，访问不同簇的方式也会有所不同，CPU 被划分为多个节点，每个 CPU 对应一个本地物理内存, 一般一个 CPU-node 对应一个内存簇，也就是说每个内存簇被认为是一个节点。  

而在 UMA 系统中, 内存就相当于一个只使用一个 NUMA 节点来管理整个系统的内存，这样在内存管理的其它地方可以认为他们就是在处理一个(伪)NUMA 系统。  


