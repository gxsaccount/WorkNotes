https://blog.csdn.net/rockrockwu/article/details/79976833  
https://zhuanlan.zhihu.com/p/358891862


在Linux中，**伙伴分配器（buddy allocator）是以页为单位管理和分配内存。**  
但在内核中的需求却以字节为单位（在内核中面临频繁的结构体内存分配问题）。假如我们需要动态申请一个内核结构体（占 20 字节），若仍然分配一页内存，这将严重浪费内存。  
**作用1:**   
slab 分配器专为小内存分配而生。**slab分配器分配内存以字节为单位，基于伙伴分配器的大内存进一步细分成小内存分配。换句话说，slab 分配器仍然从 Buddy 分配器中申请内存，之后自己对申请来的内存细分管理。**  
**作用2:**  
除了提供小内存外，**slab 分配器的第二个任务是维护常用对象的缓存**。对于内核中使用的许多结构，初始化对象所需的时间可等于或超过为其分配空间的成本。当创建一个新的slab 时，许多对象将被打包到其中并使用构造函数（如果有）进行初始化。释放对象后，它会保持其初始化状态，这样可以快速分配对象。  

      举例来说, 为管理与进程关联的文件系统数据, 内核必须经常生成struct fs_struct的新实例. 此类型实例占据的内存块同样需要经常回收(在进程结束时).   
      换句话说, 内核趋向于非常有规律地分配并释放大小为sizeof(fs_struct)的内存块. slab分配器将释放的内存块保存在一个内部列表中. 并不马上返回给伙伴系统. 
      在请求为该类对象分配一个新实例时, 会使用最近释放的内存块。
      S这有两个优点. 首先, 由于内核不必使用伙伴系统算法, 处理时间会变短. 其次, 由于该内存块仍然是”新”的，因此其仍然驻留在CPU硬件缓存的概率较高.[3]  

**作用3：**        
SLAB分配器的最后一项任务是提高CPU硬件缓存的利用率。   
如果将对象包装到SLAB中后仍有剩余空间，则将**剩余空间用于为SLAB着色**。   
SLAB着色是一种尝试使不同SLAB中的对象使用CPU硬件缓存中不同行的方案。  
通过将对象放置在SLAB中的不同起始偏移处，对象可能会在CPU缓存中使用不同的行，从而有助于确保来自同一SLAB缓存的对象不太可能相互刷新。  
通过这种方案，原本被浪费掉的空间可以实现一项新功能。  

通过命令sudo cat /proc/slabinfo可查看系统当前 slab 使用情况。以vm_area_struct结构体为例，当前系统已分配了 13014 个vm_area_struct缓存，每个大小为 216 字节，其中 active 的有 12392 个。  
      
        [root@VM-8-9-centos]# cat /proc/slabinfo
        slabinfo - version: 2.1
        # name            <active_objs> <num_objs> <objsize> <objperslab> <pagesperslab> : tunables <limit> <batchcount> <sharedfactor> : slabdata <active_slabs> <num_slabs> <sharedavail>
        ...
        vm_area_struct     12392  13014    216   18    1 : tunables    0    0    0 : slabdata    723    723      0
        mm_struct            184    200   1600   20    8 : tunables    0    0    0 : slabdata     10     10      0
        shared_policy_node   5015   5015     48   85    1 : tunables    0    0    0 : slabdata     59     59      0
        numa_policy           15     15    264   15    1 : tunables    0    0    0 : slabdata      1      1      0
        radix_tree_node    15392  17234    584   14    2 : tunables    0    0    0 : slabdata   1231   1231      0
        idr_layer_cache      240    240   2112   15    8 : tunables    0    0    0 : slabdata     16     16      0
        kmalloc-8192          39     44   8192    4    8 : tunables    0    0    0 : slabdata     11     11      0
        kmalloc-4096         117    144   4096    8    8 : tunables    0    0    0 : slabdata     18     18      0
        kmalloc-2048         458    528   2048   16    8 : tunables    0    0    0 : slabdata     33     33      0
        kmalloc-1024        1399   1424   1024   16    4 : tunables    0    0    0 : slabdata     89     89      0
        kmalloc-512          763    800    512   16    2 : tunables    0    0    0 : slabdata     50     50      0
        kmalloc-256         3132   3376    256   16    1 : tunables    0    0    0 : slabdata    211    211      0
        kmalloc-192         2300   2352    192   21    1 : tunables    0    0    0 : slabdata    112    112      0
        kmalloc-128         1376   1376    128   32    1 : tunables    0    0    0 : slabdata     43     43      0
        kmalloc-96          1596   1596     96   42    1 : tunables    0    0    0 : slabdata     38     38      0
        kmalloc-64         16632  20800     64   64    1 : tunables    0    0    0 : slabdata    325    325      0
        kmalloc-32          1664   1664     32  128    1 : tunables    0    0    0 : slabdata     13     13      0
        kmalloc-16          4608   4608     16  256    1 : tunables    0    0    0 : slabdata     18     18      0
        kmalloc-8           4096   4096      8  512    1 : tunables    0    0    0 : slabdata      8      8      0
        ...
  
  
可以看到，系统中存在的 slab 有些形如 kmalloc-xxx 的 slab，我们称其为**通用型 slab**，用来满足分配通用内存。其他含有具体名字的 slab 我们称其为**专用slab** ，用来为特定结构体分配内存，如 vm_area_struct、mm_struct 等。  

为什么要分专用和通用 slab ？ 最直观的一个原因就是通用 slab 会造成内存浪费：出于 slab 管理的方便，每个 slab 管理的对象大小都是一致的，当我们需要分配一个处于 64-96字节中间大小的对象时，就必须从保存 96 字节的 slab 中分配。而对于专用的 slab，其管理的都是同一个结构体实例，申请一个就给一个恰好内存大小的对象，这就可以充分利用空间。  


# slab着色 #  
slab中倾向于把大小相同的对象放在同一个硬件cache line中。为什么呢？方便对齐，方便寻址。  
但这样会带来一个问题。  
假如有两个对象，A，B，它们size一样，都是18个字节。  
这样，如果交替访问这两个对象时，就会造成这两个对象不停地从cache line中换入/换出到RAM中，而其他的cache line很有可能闲着没事干。  
怎么解决这个问题呢？  
slab着色就上场了  

slab着色是怎么回事呢？  
其实就是利用slab中的空余空间去做不同的偏移，这样就可以根据不同的偏移来区分size相同的对象了。  
为什么slab中会有剩余空间？因为slab是以空间换时间。  
做偏移的时候，也要考虑到cache line中的对齐。  
假如slab中有14个字节的剩余空间，cache line以4字节对齐，我们来看看有多少种可能的偏移，也就是有多少种可能的颜色。  
第一种，偏移为0，也就是不偏移，那么剩余的14个字节在哪儿呢？放到结尾处，作为偏移补偿。  
第二种，偏移4字节，此时偏移补偿为10字节。  
第三种，偏移8字节，此时偏移补偿为6字节。  
第四种，偏移12字节，此时偏移补偿为2字节。  
再继续，就只能回归不偏移了，因为上一种的偏移补偿为2字节，已经不够对齐用了。  
来总结一下看看有几种颜色。  
第一种无偏移，后面是剩余空间 free 能满足多少次对齐 align ，就有多少种，总数： free/align +1 。  
如果 free 小于 align ，slab着色就起不到作用，因为颜色只有一种，即不偏移的情况。  
如果size相同的对象很多，但 free 不够大，或者 free/align 不够大，效果也不好。  
因为颜色用完了，会从头再来。  
继续上面的例子，如果有五个相同的对象，第五个对象的颜色与第一个相同，偏移为0.  
