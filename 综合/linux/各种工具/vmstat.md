# 介绍 #   
vmstat命令可以对整个机器的进程、内存、页面交换空间、磁盘IO、CPU活动进行监控。这些信息反映了系统的负载情况。   

# 基础使用 #  

vmstat 5 8 #每5秒采样一次，共采集8次  
vmstat 10 #每10秒采样一次  

结果：  

    $ vmstat 10 
    procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
     r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
     2  0      0 22563752 1966512 28117528    0    0     0     5    1    1  0  0 99  0  0
     0  0      0 22568540 1966512 28120716    0    0     0   158 10335 14811  1  0 99  0  0
     
     Linux 内存监控vmstat命令输出分成六个部分：

# 详细解释 #  
(1)进程procs：  

    r：在运行队列中等待的进程数 。 
    b：在等待io的进程数 。

(2)Linux 内存监控内存memoy：

    swpd：现时可用的交换内存(单位KB)。
    free：空闲的内存(单位KB)。
    buff: 缓冲去中的内存数(单位：KB)。
    cache：被用来做为高速缓存的内存数(单位：KB)。

(3) Linux 内存监控swap交换页面  

    si: 从磁盘交换到内存的交换页数量，单位：KB/秒。
    so: 从内存交换到磁盘的交换页数量，单位：KB/秒。

(4)Linux 内存监控 io块设备:  

    bi: 发送到块设备的块数，单位：块/秒。
    bo: 从块设备接收到的块数，单位：块/秒。

(5)Linux 内存监控system系统：  

    in: 每秒的中断数，包括时钟中断。  
    cs: 每秒的环境(上下文)转换次数。  

(6)Linux 内存监控cpu中央处理器：  

    cs：用户进程使用的时间 。以百分比表示。  
    sy：系统进程使用的时间。 以百分比表示。  
    id：中央处理器的空闲时间 。以百分比表示。  
    假如 r经常大于 4(cpu核数) ，且id经常小于40，表示中央处理器的负荷很重。  
    假如bi，bo 长期不等于0，表示物理内存容量太小。  

每个参数的含义：  
Procs  
r: The number of processes waiting for run time.等待运行时的进程数  
b: The number of processes in uninterruptible sleep.不间断睡眠中的进程数  

Memory  
swpd: the amount of virtual memory used.使用的虚拟内存量  
free: the amount of idle memory.空闲内存量  
buff: the amount of memory used as buffers.用作buffer的内存量  
cache: the amount of memory used as cache.用作cache的内存量  
inact: the amount of inactive memory. (-a option)非活动内存量  
active: the amount of active memory. (-a option)活动内存量  

Swap  
si: Amount of memory swapped in from disk (/s).swap in  
so: Amount of memory swapped to disk (/s).swap in  

IO  
bi: Blocks received from a block device (blocks/s). blocks in  
bo: Blocks sent to a block device (blocks/s). blocks out  

System  
in: The number of interrupts per second, including the clock.每秒的中断数，包括时钟  
cs: The number of context switches per second.每秒上下文切换次数  

CPU  
These are percentages of total CPU time.些是总CPU时间的百分比  
us: Time spent running non-kernel code. (user time, including nice time)运行非内核代码所花费的时间  
sy: Time spent running kernel code. (system time)运行内核代码所花费的时间  
id: Time spent idle. Prior to Linux 2.5.41, this includes IO-wait time.空闲时间。在Linux 2.5.41之前，这包括IO等待时间。  
wa: Time spent waiting for IO. Prior to Linux 2.5.41, included in idle.等待IO的时间。在Linux 2.5.41之前，包含在空闲状态。  
st: Time stolen from a virtual machine. Prior to Linux 2.6.11, unknown.从虚拟机中窃取的时间。在Linux 2.6.11之前，未知。  
当运行队列r值超过了CPU数目，就会出现CPU瓶颈了。如果运行队列过大，表示你的CPU很繁忙，一般会造成CPU使用率很高。  

b 表示阻塞的进程  
swpd 虚拟内存已使用的大小  
free   空闲的物理内存的大小  
Linux/Unix的聪明之处，把空闲的物理内存的一部分拿来做文件和目录的缓存，是为了提高程序执行的性能，当程序使用内存时，buffer/cached会很快地被使用
cs 每秒上下文切换次数，例如调用系统函数，就要进行上下文切换，线程的切换，也要进程上下文切换，这个值要越小越好。太大了，要考虑调低线程或者进程的数目。例如在 apache 和 nginx 这种 web 服务器中，做性能测试时会进行几千并发甚至几万并发的测试，选择web服务器的进程可以由进程或者线程的峰值一直下调，压测，直到cs到一个比较小的值，这个进程和线程数就是比较合适的值了。系统调用也是，每次调用系统函数，代码就会进入内核空间，导致上下文切换，这个很耗资源，也要尽量避免频繁调用系统函数。上下文切换次数过多表示你的CPU大部分浪费在上下文切换，导致CPU干正经事的时间少了，CPU没有充分利用，是不可取的。
一般来说，id + us + sy +wa= 100,一般认为id是空闲CPU使用率，us是用户CPU使用率，sy是系统CPU使用率。
