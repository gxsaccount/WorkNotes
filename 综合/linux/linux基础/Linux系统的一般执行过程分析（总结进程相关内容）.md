三、Linux系统的一般执行过程分析

1、最一般的情况：正在运行的用户态进程X切换到运行用户态进程Y的过程
（1）正在运行的用户态进程X
（2）发生中断——save cs:eip/esp/eflags(current) to kernel stack,then load cs:eip(entry of a specific ISR) and ss:esp(point to kernel stack).
（3）SAVE_ALL //保存现场
（4）中断处理过程中或中断返回前调用了schedule()，其中的switch_to做了关键的进程上下文切换
（5）标号1之后开始运行用户态进程Y(这里Y曾经通过以上步骤被切换出去过因此可以从标号1继续执行)
（6）restore_all //恢复现场
（7）iret - pop cs:eip/ss:esp/eflags from kernel stack
（8）继续运行用户态进程Y
2、关键：**中断上下文的切换**和**进程上下文的切换**(见同级目录相关代码)  

四、Linux系统执行过程中的几个特殊情况
1、几种特殊情况
（1）通过**中断处理过程中的调度时机（都在内核态发生）**，用户态进程与内核线程之间互相切换和内核线程之间互相切换，与最一般的情况非常类似，只是内核线程运行过程中发生中断没有进程用户态和内核态的转换，**CS段没有变化**；  
（2）**内核线程**主动调用schedule()，只有进程上下文的切换，没有发生中断上下文的切换，与最一般的情况略简略；
（3）**创建子进程的系统调用**在子进程中的执行起点**next_ip = ret_from_fork及返回用户态**，如fork；
（4）加载一个新的可执行程序后返回到用户态的情况，如execve。
2、X86_32位系统下，每个进程的地址空间4G。**0-3G用户态，3G-4G仅内核态**。
**所有的进程3G以上的部分是共享的。（代码段，堆栈段，内核堆栈等等都是相同的）**  
内核是各种中断处理过程和内核线程的集合。

五、Linux操作系统架构概览  
1、操作系统的基本概念  
![image](https://user-images.githubusercontent.com/20179983/131236413-bfe43892-02b9-41c0-b38a-ff0f4fcec251.png)  
2、典型的Linux操作系统的结构  
![image](https://user-images.githubusercontent.com/20179983/131236422-e3b43242-a412-4e10-b80d-82bfab669196.png)  
六、最简单也是最复杂的操作---执行ls命令  
![image](https://user-images.githubusercontent.com/20179983/131236430-61fca423-674a-43ab-86af-21a91f6b94ac.png)  
七、从CPU和内存的角度看Linux系统的执行    
![image](https://user-images.githubusercontent.com/20179983/131236434-3c6e957c-cd11-4d1f-a6d7-39d25154287e.png)  
0xc0000000以下是3G的部分，用户态。  
（1）c=gets();系统调用，陷入内核态，将eip/esp/cs/ds等信息压栈。  
（2）进程管理：等待键盘敲入指令。  
（3）中断处理：在键盘上敲击ls发生I/O中断。  
进程x陷入内核态后没有内容执行变成阻塞态，发生I/O中断后变成就绪态。  
（4）系统调用返回。    

2、从内存的角度  
![image](https://user-images.githubusercontent.com/20179983/131236445-d5e49a35-a3c8-46d4-80af-cb0988c686b2.png)


