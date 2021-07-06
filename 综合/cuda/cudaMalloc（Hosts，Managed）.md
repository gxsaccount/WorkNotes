https://developer.nvidia.com/blog/how-optimize-data-transfers-cuda-cc/  

# cudaMalloc #  
分配显存内存  

# cuMemAllocPitch #   
cuMemAllocPitch ( CUdeviceptr* dptr, size_t* pPitch, size_t WidthInBytes, size_t Height, unsigned int  ElementSizeBytes )
Allocates pitched device memory.

# malloc  #  
分配host上Pageable的host内存
# cudaMallocHosts  #    
cudaHostAlloc(), cudaFreeHost()来分配和释放host上pinned memory；


# host内存类别 #
host内存：分为pageable memory 和 pinned memory    
pageable memory： 通过操作系统API（malloc（），new（））分配的存储器空间；   
Pinned(Page-locked)，实质是强制让系统在物理内存中完成内存申请和释放的工作，不参与页交换，从而提高系统效率    
Pageable(交换页)与Pinned(Page-locked)都是“Write-back”，现在X86/X64CPU，会直接在内部使用一个特别的缓冲区，将写入合并，等没满64B（一个cache line)，集中直接写入一次，越过所有的缓存，而读取的时候会直接从内存读取，同样无视各级缓存。  
这种最大的用途可以用来在CUDA上准备输入数据，因为它在跨PCI-E传输的时候，可能会更快一些（因为不需要询问CPU的cache数据是否在里面）。  
使用pinned memory优点：主机端-设备端的数据传输带宽高；某些设备上可以通过zero-copy功能映射到设备地址空间，从GPU直接访问，省掉主存与显存间进行数据拷贝的工作；  
使用pinned memory缺点：pinned memory 不可以分配过多：导致操作系统用于分页的物理内存变少， 导致系统整体性能下降；通常由哪个cpu线程分配，就只有这个线程才有访问权限；  

**主机(CPU)数据分配的内存默认是可分页的。GPU不能直接访问可分页的主机内存，所以当从可分页内存到设备内存的进行数据传输时，CUDA驱动必须首先分配一个临时的不可分页的或者固定的主机数组，然后将主机数据拷贝到固定数组里，最后再将数据从固定数组转移到设备内存**  

**write back与write through**    
Cache写机制分为write through和write back两种。  

Write-through- Write is done synchronously both to the cache and to the backing store.  
Write-back (or Write-behind) - Writing is done only to the cache. A modified cache block is written back to the store, just before it is replaced.  
Write-through（直写模式）在数据更新时，同时写入缓存Cache和后端存储。此模式的优点是操作简单；缺点是因为数据修改需要同时写入存储，数据写入速度较慢。  
Write-back（回写模式）在数据更新时只写入缓存Cache。只在数据被替换出缓存时，被修改的缓存数据才会被写到后端存储。此模式的优点是数据写入速度快，因为不需要写存储；缺点是一旦更新后的数据未被写入存储时出现系统掉电的情况，数据将无法找回。  



# cuMemAllocManaged #  

Unified memory在程序员的视角中，维护了一个统一的内存池，在CPU与GPU中共享。使用了单一指针进行托管内存，由系统来自动地进行内存迁移。  
是的编程更接近cpu，省去了cudaMalloc或者cudaMemcpy等操作显存的指令  
    void sortfile(FILE *fp, int N)                       void sortfile(FILE *fp, int N)                   
    {                                                    {
        char *data;                                          char *data; 
        data = (char*)malloc(N);                             cudaMallocManaged(data, N);

        fread(data, 1, N, fp);                               fread(data, 1, N, fp);

        qsort(data, N, 1, compare);                          qsort<<<...>>>(data, N, 1, compare);
                                                             cudaDeviceSynchronize();

        usedata(data);                                       usedata(data);
        free(data);                                          free(data);
    }
    
    
    
    
        问：UM会消除System Memory和GPU Memory之间的拷贝么？
        答：不会，只是这部分copy工作交给CUDA在runtime期间执行，只是对程序员透明而已。memory copy的overhead依然存在，还有race conditions的问题依然需要考虑，从而确保GPU与CPU端的数据一致。简单的说，如果你手动管理内存能力优秀，UM不可能为你带来更好的性能，只是减少你的工作量。
        问：既然并没有消除数据间的拷贝，看起来这只是compiler time的事情，为什么仍需要算力3.0以上？难道是为了骗大家买卡么？
        wait....到目前为止，实际上我们省略了很多实现细节。因为原则上不可能消除拷贝，无法在compile期间获知所有消息。而且重要的一点，在Pascal以后的GPU架构中，提供了49-bit的虚拟内存寻址，和按需页迁移的功能。49位寻址长度足够GPU来cover整个sytem memory和所有的GPUmemory。而页迁移引擎通过内存将任意的可寻址范围内的内存迁移到GPU内存中，来使得GPU线程可以访问non-resident memory。
        简言之，新架构的卡物理上允许GPU访问”超额“的内存，不用通过修改程序代码，就使得GPU可以处理out-of-core运算（也就是待处理数据超过本地物理内存的运算）。
        而且在Pascal和Volta上甚至支持系统范围的原子内存操作，可以跨越多个GPU，在multi-GPU下，可以极大地简化代码复杂度。
        同时，对于数据分散的程序，按需页迁移功能可以通过page fault更小粒度地加载内存，而非加载整个内存，节约更多数据迁移的成本。（其实CPU很早就有类似的事情，原理很相似。）
