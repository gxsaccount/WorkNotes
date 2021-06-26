# cudaMalloc  #  
分配Pageable的host内存
# cudaMallocHosts   #  
cudaHostAlloc(), cudaFreeHost()来分配和释放pinned memory；


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
    
    
