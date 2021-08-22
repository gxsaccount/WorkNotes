1. 进程控制块PCB——task_struct  
源码：https://elixir.bootlin.com/linux/v3.18.6/source/include/linux/sched.h#L1235   
解析：https://blog.csdn.net/hongchangfirst/article/details/7075026  
为了管理进程，内核必须对每个进程进行清晰的描述，进程描述符提供了内核所需了解的进程信息。task_struct 数据结构很庞大， 比较重要的定义有：
  ● 进程状态
      ○ Linux进程的状态与操作系统原理中的描述的进程状态似乎有所不同，**比如就绪状态和运行状态都是TASK_RUNNING**。  
      
        volatile long state;	/* -1 unrunnable, 0 runnable, >0 stopped */   
  ● Linux为每个进程分配一个8KB大小的内存区域，用于存放该进程两个不同的数据结构：Thread_info和进程的内核堆栈  
      ○ 进程处于内核态时使用，不同于用户态堆栈，即PCB中指定了内核栈
      ○ 内核控制路径所用的堆栈很少，因此对栈和Thread_info来说，8KB足够了
        
        void *stack; 
      
  ● 进程的标示pid  
  
      //这个是进程号，注意这是内核自己维护的进程号，因为在Linux中线程是由进程实现的，用户看到的进程号是tgid域。
       pid_t pid;
      //这个是线程组号，和线程组内的领头进程的进程号一致，我们在用户程序中调用getpid()其实返回的是tgid值。
       pid_t tgid;

        
  ● 所有进程链表struct list_head tasks;  
      ○ 内核的**双向循环链表**的实现方法 - 一个更简略的双向循环链表  
        
        struct list_head tasks;
  ● 程序创建的进程具有父子关系，在编程时往往需要引用这样的父子关系。进程描述符中有几个域用来表示这样的关系
        
        /*
         * pointers to (original) parent process, youngest child, younger sibling,
         * older sibling, respectively.  (p->father can be replaced with
         * p->real_parent->pid)
        */
        struct task_struct __rcu *real_parent; /* real parent process */
        struct task_struct __rcu *parent; /* recipient of SIGCHLD, wait4() reports */
        /*
         * children/sibling forms the list of my natural children
         */
        struct list_head children;	/* list of my children */
        struct list_head sibling;	/* linkage in my parent's children list */
        struct task_struct *group_leader;	/* threadgroup leader */

  ![image](https://user-images.githubusercontent.com/20179983/130340447-d51828f8-cc68-4158-859c-a79b58671dc2.png)
      
  ● struct thread_struct thread; //CPU-specific state of this task，包括eip和esp的值，主要用于进程切换，详细见进程切换讲解  
  ● 文件系统和文件描述符  
      
      /* filesystem information */
      struct fs_struct *fs;
    /* open file information */
      struct files_struct *files;  
  
  ● 信号相关信息的句柄  
  
     struct signal_struct *signal;
     struct sighand_struct *sighand;
  ● 内存管理——进程的地址空间

      //这里出现了mm_struct 结构体，该结构体记录了进程内存使用的相关情况，详情请参考http://blog.csdn.net/hongchangfirst/article/details/7076207
      struct mm_struct *mm, *active_mm;  //32位逻辑地址有4G的进程地址空间，分段分页相关


进程状态的切换过程：  
![image](https://user-images.githubusercontent.com/20179983/130340151-9ea616e5-f2d1-4263-b0ef-1ae6aa8ec3d0.png)
![image](https://user-images.githubusercontent.com/20179983/130340165-eb1742e2-63ae-4099-87df-c7fc928dc3d9.png)

进程状态：  
进程根据运行状态可分为： 就绪态、运行态、可中断睡眠态、不可中断睡眠态和僵死态。  
每个状态都对应一个宏定义，定义的宏在：  
include/linux/sched.h：

    203 #define TASK_RUNNING		0  //就绪态和阻塞态都是该状态，区别在于是否在cpu上运行  
    204 #define TASK_INTERRUPTIBLE	1
    205 #define TASK_UNINTERRUPTIBLE	2

    208 /* in tsk->exit_state */
    209 #define EXIT_DEAD		16
    210 #define EXIT_ZOMBIE		32

