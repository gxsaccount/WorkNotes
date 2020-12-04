以VC6为例，VC10小区块的操作已经潜到操作系统  
[main函数的前后操作]  
main()是c++的接入函数  
mainCRTStartup():gcc也有类似操作，c runtime   
_heap_init():  
crt_heap:先要4096的堆大小初始化crt_heap  
sbh_heap:再初始化16个sbh_heap的Header，用来做内存管理(crt_heap)      
[Header结构]  
_ioinit():  
1.根据dbg与否，来选择用malloc或是malloc_dbg  
2.再malloc256字节，n_size（？作用）  
3._heap_alloc_dbg():  
计算block_size:再n_size基础上，dbg模式需要附加一些header(_crtMemberBlockHeader和gap4字节，检查是否越界)，
4._heap_alloc_base():   
根据计算好的block_size来分配内存  
小于1016+(8)的小区块需要单独做处理  
