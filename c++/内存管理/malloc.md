## 程序启动前的流程 ##
**malloc本质是分段管理，段页结合进行和操作系统一起管理内存**  
分段可以更方便的归还内存，
。。。

以VC6为例，VC10小区块的操作已经潜到操作系统  
![image](https://user-images.githubusercontent.com/20179983/131291541-b0de6311-826b-4df4-a144-7240bb4e3c8e.png)
main()是c++的接入函数  
mainCRTStartup():gcc也有类似操作，c runtime   
_heap_init():  
 
   crt_heap:先要4096的堆大小初始化crt_heap，后续不够继续加  
   sbh_heap:再初始化16个sbh_heap的Header，用来做内存管理(crt_heap)      
![image](https://user-images.githubusercontent.com/20179983/131291562-f9d6bbbb-f68b-48e2-9d13-5aafa0c66e4d.png)
_ioinit():  
1.根据dbg与否，来选择用malloc或是malloc_dbg  
2.再malloc256字节，n_size（？作用），第一次malloc    
3._heap_alloc_dbg():  
计算block_size:再n_size基础上，dbg模式需要附加一些header(_crtMemberBlockHeader和gap4字节，检查是否越界)，
4._heap_alloc_base():   
根据计算好的block_size来分配内存  
小于1016+(8)的小区块需要单独做处理  
5.sbh_alloc_block():  
添加上下cookie，并对齐16  
6.sbh_alloc_new_region():  
开始分配内存。用于管理内存大概16k  
7.sbh_alloc_new_group():  

![image](https://user-images.githubusercontent.com/20179983/131291599-3288c168-a7c9-430f-9907-c13d65b78359.png)
 
**tagRegion:**  
size_t 表示当前正在使用的group  
64个char
bitvec是usigned int ，高位低位共32个，对应32个group，  
每个bitvec长度为64对应group的64个链表，管理哪些区块是否存在链表中 ，bit位为1代表有内存挂在group里面，为0则没有   

 

**tagGroup：**  
cnt_Entries: 分配一次+1，释放一次-1，为0时可以将此块还给操作系统  
有64个listhead组成双向链表  
程序申请内存时  
给予程序，八页分配完再申请新的。 
64个链表负责的内存大小依次增加，16字节，32字节... 1K(>=1k)。  
内存不够，group从虚拟空间中取一块（1/32,32k），按页（4k）分成八块，并且使用内嵌指针形成一个双向链表，再挂到group的双向链表中，（>=1k的链表上）。

![image](https://user-images.githubusercontent.com/20179983/131291652-8dd0563e-07d0-4716-939b-22b9fe04a32c.png)  
保留：为了对齐16倍数  
黄色：标识页面的开始和结束，阻隔器，方便回收页面回收，防止切割时越界  
4080：标识这块未被分配的大小  
分配时从上向下进行分配，每次分配带有上下两个4字节的cookie   
  

## 页表的切割过程 ##  
![image](https://user-images.githubusercontent.com/20179983/131291686-6e537bed-b801-4f3c-a82d-06d4be195c48.png)

64条链表，管理最大的内存块为大于1k（最后一条链表）。  
第一条是16个字节，后面依次32，48，64...,直到>1k
被切割的页表cookie调整来标识哪些内存被切割除去，上图切割130的大小，红色部分被切割除去，0x00000ec0是被切割后剩下的大小。  
0x00000131是130+1,加1表示已经被使用（因为切割大小一定是16的倍数，末尾一定是0，所以用来标识是否被使用）   
130对应（130/16+1=8）第8个group，但是此时8的内存为空，boitvec的值为0，依次向下找到32号链表  

![image](https://user-images.githubusercontent.com/20179983/131291736-20d8fedc-80b2-427b-a22e-8087de41648f.png)
1.ioinit.c申请100h，区块大小130h(debug header+ 无人区+100h+上下cookie)  
2.根据group计算，应该使用18号链表，但是18号链表无管理内存，（bitvec为0），从上往下找有内存块的区块，（此时只有最后一块链表有区块）  
3.若内存不够，group从虚拟空间中取一块（1/32,32k），按页（4k）分成八块，并且使用内嵌指针形成一个双向链表，再挂到group的双向链表中，（>=1k的链表上）。  
4.取得一个大小为4080的区块，从底部切130出去，区块大小剪掉130，并计算该区块是否需要更换链表，cntEntries++  


## 内存的归还 ##  
[内存归还]  
1.程序释放240h（调用free，240h/10h），计算后应该是第35号list，将cookie241改为240，将头两个字节变为嵌入式指针，挂到35号链表。bitvec的35号bit更新为1。  
![image](https://user-images.githubusercontent.com/20179983/131291796-8ca1814c-777a-4cfd-aadc-4996cbf01109.png) 
1.相邻的区块都是未使用的，进行合并（通过查看上区块的下cookie和下区块的上cookie获得区块的使用情况(cookie末尾是否为0)和占用大小进行合并），递归进行直至无法合并  
2.将合并后的区块挂到对应链表  



# 计算方法总结 #  
落在哪个Header？  
总共16个Header，暴力遍历  
落在哪个Group？  
地址剪掉Header的头，再除以32k  
落在哪个free-list？  
通过指针的cookie获得指针的内存大小，在通过大小除以16，计算对应的free-list  


全回收  
通过判断cnt_entries是否为0来决定是都回收  
回收时，获得一个可以全回收的group，先不回收，等到第二个全回收的group出现时，再回收这个group  






