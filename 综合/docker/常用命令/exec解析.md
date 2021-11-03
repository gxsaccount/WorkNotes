docker exec 是怎么做到进入容器里的  
Linux Namespace 创建的隔离空间虽然看不见摸不着，但一个进程的 Namespace 信
息在宿主机上是确确实实存在的，并且是以一个文件的方式存在。  
比如，通过如下指令，你可以看到当前正在运行的 Docker 容器的进程号（PID）是 25686：  

    docker inspect --format '{{ .State.Pid }}' 4ddf4638572d
    25686  
    
 这时，你可以通过查看宿主机的 proc 文件，看到这个 25686 进程的所有 Namespace 对应的文件  
 
     $ ls -l /proc/25686/ns 
     total 0 
     lrwxrwxrwx 1 root root 0 Aug 13 14:05 cgroup -> cgroup:[4026531835] 
     lrwxrwxrwx 1 root root 0 Aug 13 14:05 ipc -> ipc:[4026532278] 
     lrwxrwxrwx 1 root root 0 Aug 13 14:05 mnt -> mnt:[4026532276]
     lrwxrwxrwx 1 root root 0 Aug 13 14:05 net -> net:[4026532281] 
     lrwxrwxrwx 1 root root 0 Aug 13 14:05 pid -> pid:[4026532279] 
     lrwxrwxrwx 1 root root 0 Aug 13 14:05 pid_for_children -> pid:[4026532279] 
     lrwxrwxrwx 1 root root 0 Aug 13 14:05 user -> user:[4026531837] 
     lrwxrwxrwx 1 root root 0 Aug 13 14:05 uts -> uts:[4026532277]  
     
  可以看到，一个进程的每种 Linux Namespace，都在它对应的 /proc/[进程号]/ns 下有一个对
应的虚拟文件，并且链接到一个真实的 Namespace 文件上。  
有了这样一个可以“hold 住”所有 Linux Namespace 的文件，我们就可以对 Namespace 做
一些很有意义事情了，比如：加入到一个已经存在的 Namespace 当中。  
这也就意味着：一个进程，可以选择加入到某个进程已有的 Namespace 当中，从而达到“进
入”这个进程所在容器的目的，这正是 docker exec 的实现原理。  
而这个操作所依赖的，乃是一个名叫 **setns()** 的 Linux 系统调用。  

setns()的使用； 

      #define _GNU_SOURCE                                                                                                         
      #include <fcntl.h> 
      #include <sched.h> 
      #include <unistd.h> 
      #include <stdlib.h> 
      #include <stdio.h> 
      #define errExit(msg) do {perror(msg);exit(EXIT_FAILURE);}while (0)                                                                                                                 
      int main(int argc, char *argv[]) {                                                                                      
          int fd;                                                                                                               
          fd = open(argv[1], O_RDONLY);                                                                                         
          if (setns(fd, 0) == -1) {                                                                                             
          errExit("setns");                                                                                                   
          }                                                                                                                     
          execvp(argv[2], &argv[2]);                                                                                            
          errExit("execvp");                                                                                                    
      }
      
这段代码功能非常简单：它一共接收两个参数，第一个参数是 argv[1]，即当前进程要加入的
Namespace 文件的路径，比如 /proc/25686/ns/net；而第二个参数，则是你要在这个
Namespace 里运行的进程，比如 /bin/bash。  
这段代码的的核心操作，则是通过 open() 系统调用打开了指定的 Namespace 文件，并把这个
文件的描述符 fd 交给 setns() 使用。在 setns() 执行后，当前进程就加入了这个文件对应的
Linux Namespace 当中了。  

一旦一个进程加入到了另一个 Namespace 当中，在宿主机的 Namespace 文件上，也会有
所体现。  
在宿主机上，你可以用 ps 指令找到这个 set_ns 程序执行的 /bin/bash 进程，其真实的 PID 是
28499：  

    # 在宿主机上 
    ps aux | grep /bin/bash 
    root 28499 0.0 0.0 19944 3612 pts/0 S 14:15 0:00 /bin/bash
查看一下这个 PID=28499 的进程的 Namespace，你就会
发现这样一个事实   
    
    $ ls -l /proc/28499/ns/net 
    lrwxrwxrwx 1 root root 0 Aug 13 14:18 /proc/28499/ns/net -> net:[4026532281] 
    $ ls -l /proc/25686/ns/net 
    lrwxrwxrwx 1 root root 0 Aug 13 14:05 /proc/25686/ns/net -> net:[4026532281]  
在 /proc/[PID]/ns/net 目录下，这个 PID=28499 进程，与我们前面的 Docker 容器进程
（PID=25686）指向的 Network Namespace 文件完全一样。这说明这两个进程，**共享了这个
名叫 net:[4026532281] 的 Network Namespace。**     

此外，Docker 还专门提供了一个参数，可以让你启动一个容器并“加入”到另一个容器的
Network Namespace 里，这个参数就是 -net，比如:

    $ docker run -it --net container:4ddf4638572d busybox ifconfig  
    
 ，我们新启动的这个容器，就会直接加入到 ID=4ddf4638572d 的容器  
 
 如果我指定–net=host，就意味着这个容器不会为进程启用 Network Namespace。这就意
味着，这个容器拆除了 Network Namespace 的“隔离墙”，所以，它会和宿主机上的其他普
通进程一样，直接共享宿主机的网络栈。这就为容器直接操作和使用宿主机网络提供了一个渠
道。  


    
