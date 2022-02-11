select/poll/epoll用法  
 
接口：

    int select{
        int n,// 待测试的描述符数量+1  
        fd_set *readset,//读描述符集合
        fd_set *readset,//写描述符集合
        fd_set *readset,//异常描述符集合
        const struct timeval *timeout
      }

使用流程：  
1.告诉内核你对哪些fd感兴趣  
2.内核将遍历这些fd，将准备就绪的bitmap返还给你  
3.你遍历这些bitmap得到就绪的fd  

![image](https://user-images.githubusercontent.com/20179983/133450469-ec816361-66cc-4787-98bb-846da41efc22.png)

![image](https://user-images.githubusercontent.com/20179983/133456081-7e739673-5337-401a-9f52-1a8a47123e2a.png)

    #include <stdio.h>
    #include <stdlib.h>
    #include <sys/time.h>
    #include <sys/types.h>
    #include <unistd.h>
    #include<strings.h>
    #include<sys/socket.h>
    #include<iostream>
    #include<arpa/inet.h>
    using namespace std;

    int main(void) {

        /**step1 :  select工作之前,需要知道要监管哪些套接字**/
       int listen_fd=0;

        fd_set  read_set;   
        FD_ZERO(&read_set);
        FD_SET(listen_fd,&read_set);


        /*step2 : select开始工作,设定时间内阻塞轮询套接字是否就绪*/
        struct timeval tv;
           tv.tv_sec = 5;
            tv.tv_usec = 0;
        int ret=select(listen_fd+1,&read_set,NULL,NULL,&tv);

        /*step3 : select完成工作,即如果出现就绪或者超时 ,则返回*/
        if(ret==-1){
            cout<<"errno!"<<endl;
        }
        else if(ret==0){
            cout<<"time out"<<endl;
        }
        else if(ret>0){   //缺点之一：ret在fd多时，并不知道哪个fd准备好了，需要一个一个查看
                 //一个一个检查准备好的fd，并作处理  
                 if(FD_ISSET(listen_fd,&read_set));
                 {  
                     char *buffer=new char[10];
                     read(listen_fd,buffer,sizeof(buffer));
                     cout<<"Input String : "<<buffer<<endl;
                 }

        }
    }

源码：  
![image](https://user-images.githubusercontent.com/20179983/133450558-69cf5dcd-5c49-4fa6-987f-f98a2546b6dc.png)


源码细节
将注释都写好了 细节可以看注释

select对应的系统调用如下

    SYSCALL_DEFINE5(select, int, n, fd_set __user *, inp, fd_set __user *, outp,
        fd_set __user *, exp, struct timeval __user *, tvp)
将其展开后得到如下函数

    long sys_select(int n, fd_set __user * inp, fd_set __user * outp,
                        fd_set __user * exp, struct timeval __user * tvp)
    SYSCALL_DEFINE5(select, int, n, fd_set __user *, inp, fd_set __user *, outp,
        fd_set __user *, exp, struct timeval __user *, tvp)
    {
        /* 从应用层会传递过来三个需要监听的集合，可读，可写，异常 */
        ret = core_sys_select(n, inp, outp, exp, to);

        return ret;
    }
    
接下来看core_sys_select

    int core_sys_select(int n, fd_set __user *inp, fd_set __user *outp,
             fd_set __user *exp, struct timespec *end_time)
    {
        /* 在栈上分配一段内存32*8总计256字节，对于fd数量不多时提高性能（因为栈的申请和释放快于堆） */  
        long stack_fds[SELECT_STACK_ALLOC/sizeof(long)];
        
        /* 根据fd的数量，计算预留的long数组长度，一个long代表64个fd是否ready，最多1024/64=16个 */
        size = FDS_BYTES(n); //n个文件描述符需要多少个字节  
        

        /*
         * 如果栈上的内存太小，那么就kmalloc重新分配内存
         * 为什么是除以6呢？
         * 因为每个文件描述符要占6个bit（输入：可读，可写，异常；输出结果：可读，可写，异常）
         */
        if (size > sizeof(stack_fds) / 6)
        bits = kmalloc(6 * size, GFP_KERNEL);

        /* 设置好bitmap对应的内存空间 */
        fds.in      = bits; //可读
        fds.out     = bits +   size; //可写
        fds.ex      = bits + 2*size; //异常
        fds.res_in  = bits + 3*size; //返回结果，可读
        fds.res_out = bits + 4*size; //返回结果，可写
        fds.res_ex  = bits + 5*size; //返回结果，异常

        /* 将应用层的监听集合拷贝到内核空间，select拷贝会耗时间 */
        get_fd_set(n, inp, fds.in);
        get_fd_set(n, outp, fds.out);
        get_fd_set(n, exp, fds.ex);

        /* 清空三个输出结果的集合 */
        zero_fd_set(n, fds.res_in);
        zero_fd_set(n, fds.res_out);
        zero_fd_set(n, fds.res_ex);

        /* 调用do_select阻塞，满足条件时返回 */
        ret = do_select(n, &fds, end_time);

        /* 将结果拷贝回应用层 */
        set_fd_set(n, inp, fds.res_in);
        set_fd_set(n, outp, fds.res_out);
        set_fd_set(n, exp, fds.res_ex);

        return ret;
    }
    
下面来看一看do_select函数

    int do_select(int n, fd_set_bits *fds, struct timespec *end_time)
    {
        for (;;) {
            /* 遍历所有监听的文件描述符， */
          for (i = 0; i < n; ++rinp, ++routp, ++rexp)
            {
                //
                for (j = 0; j < __NFDBITS; ++j, ++i, bit <<= 1)
                {
                    /* 调用每一个文件描述符对应驱动的poll函数，得到一个掩码 */
                    mask = (*f_op->poll)(file, wait);

                    /* 根据掩码设置相应的bit */
                    if ((mask & POLLIN_SET) && (in & bit)) {
                        res_in |= bit;
                        retval++;
                    }

                    if ((mask & POLLOUT_SET) && (out & bit)) {
                        res_out |= bit;
                        retval++;
                    }

                    if ((mask & POLLEX_SET) && (ex & bit)) {
                        res_ex |= bit;
                        retval++;
                    }
                }
            }

            /* 如果条件满足，则退出 */
            if (retval || timed_out || signal_pending(current))
                break;

            /* 调度，进程睡眠 */
            poll_schedule_timeout(&table, TASK_INTERRUPTIBLE, to, slack);
        }
    }
    
do_select会遍历所有要监听的文件描述符，调用对应驱动程序的poll函数，驱动程序的poll一般实现如下

    static unsigned int button_poll(struct file *fp, poll_table * wait)
    {
      unsigned int mask = 0;

        /* 调用poll_wait */
      poll_wait(fp, &wq, wait); //wq为自己定义的一个等待队列头

      /* 如果条件满足，返回相应的掩码 */
      if(condition)
        mask |= POLLIN;

      return mask;
    }
看看poll_wait做了什么

    static inline void poll_wait(struct file * filp, wait_queue_head_t * wait_address, poll_table *p)
    {
      if (p && wait_address)
        p->qproc(filp, wait_address, p);
    }
    p->qproc在之前又被初始化为__pollwait

    static void __pollwait(struct file *filp, wait_queue_head_t *wait_address,
            poll_table *p)
    {
        /* 分配一个结构体 */
        struct poll_table_entry *entry = poll_get_entry(pwq);

        /* 将等待队列元素加入驱动程序的等待队列头中 */
      add_wait_queue(wait_address, &entry->wait);
    }


select缺点：  
(1)select能监听的文件描述符个数受限于FD_SETSIZE,  
一般为1024  
 
(2)源码中的do_select部分是采用for循环的形式来遍历的,  
也就是select采用轮询的方式扫描文件描述符，  
文件描述符数量越多，性能越差；  
 
(3)源码中的code_sys_select在每次在轮询期间  
都需要将用户态的监听位数组拷贝到内核态的fds对象中,  
select需要复制大量的句柄数据结构到内核空间，  
产生巨大的开销；  
 
(4)select返回的是含有整个句柄的数组，  
应用程序需要遍历整个数组才能发现哪些句柄发生了事件 比较繁琐；  
 
(5)select的触发方式是水平触发，  
应用程序如果没有完成  
对一个已经就绪的文件描述符进行IO操作，  
那么之后每次select调用还是会  
将这些文件描述符通知进程。  



select优点：  
  (1)用户可以在一个线程内  
  同时处理多个socket的IO请求。  
  同时没有多线程多进程那样耗费系统资源    
   (2)目前几乎在所有的平台上支持，  
   其良好跨平台支持也是它的一个优点  


  
文件与poll函数  
等待队列  
