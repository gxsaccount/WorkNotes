https://man7.org/linux/man-pages/man1/perf.1.html  

可以从以下三种事件为调优方向：  

Hardware Event由PMU部件产生，在特定的条件下探测性能事件是否发生以及发生的次数。比如cache命中。  
Software Event是内核产生的事件，分布在各个功能模块中，统计和操作系统相关性能事件。比如进程切换，tick数等。  
Tracepoint Event是内核中静态tracepoint所触发的事件，这些tracepoint用来判断程序运行期间内核的行为细节（这些tracepint的对应的sysfs节点在/sys/kernel/debug/tracing/events目录下）。比如slab分配器的分配次数等。  

# perf 的使用 #

序号|命令|作用
-|-|-
1|annotate|解析perf record生成的perf.data文件，显示被注释的代码。
2|archive|根据数据文件记录的build-id，将所有被采样到的elf文件打包。利用此压缩包，可以再任何机器上分析数据文件中记录的采样数据。
3|bench|perf中内置的benchmark，目前包括两套针对调度器和内存管理子系统的benchmark。
4|buildid-cache|管理perf的buildid缓存，每个elf文件都有一个独一无二的buildid。buildid被perf用来关联性能数据与elf文件。
5|buildid-list|列出数据文件中记录的所有buildid。
6|diff|对比两个数据文件的差异。能够给出每个符号（函数）在热点分析上的具体差异。
7|evlist|列出数据文件perf.data中所有性能事件。
8|inject|该工具读取perf record工具记录的事件流，并将其定向到标准输出。在被分析代码中的任何一点，都可以向事件流中注入其它事件。
9|kmem|针对内核内存（slab）子系统进行追踪测量的工具
10|kvm|用来追踪测试运行在KVM虚拟机上的Guest OS。
11|list|列出当前系统支持的所有性能事件。包括硬件性能事件、软件性能事件以及检查点。
12|lock|分析内核中的锁信息，包括锁的争用情况，等待延迟等。
13|mem|内存存取情况
14|record|收集采样信息，并将其记录在数据文件中。随后可通过其它工具对数据文件进行分析。
15|report|读取perf record创建的数据文件，并给出热点分析结果。
16|sched|针对调度器子系统的分析工具。
17||执行perl或python写的功能扩展脚本、生成脚本框架、读取数据文件中的数据信息等。
18|stat|执行某个命令，收集特定进程的性能概况，包括CPI、Cache丢失率等。
19|test|perf对当前软硬件平台进行健全性测试，可用此工具测试当前的软硬件平台是否能支持perf的所有功能。
20|timechart|针对测试期间系统行为进行可视化的工具
21|top|类似于linux的top命令，对系统性能进行实时分析。
22|trace|关于syscall的工具。
23|probe|用于定义动态检查点。
全局性概况：  

    perf list查看当前系统支持的性能事件；
    perf bench对系统性能进行摸底；
    perf test对系统进行健全性测试；
    perf stat对全局性能进行统计；

全局细节：

    perf top可以实时查看当前系统进程函数占用率情况；
    perf probe可以自定义动态事件；

特定功能分析：

    perf kmem针对slab子系统性能分析；
    perf kvm针对kvm虚拟化分析；
    perf lock分析锁性能；
    perf mem分析内存slab性能；
    perf sched分析内核调度器性能；
    perf trace记录系统调用轨迹；
    
最常用功能perf record，可以系统全局，也可以具体到某个进程，更甚具体到某一进程某一事件；可宏观，也可以很微观。

    pref record记录信息到perf.data；
    perf report生成报告；
    perf diff对两个记录进行diff；
    perf evlist列出记录的性能事件；
    perf annotate显示perf.data函数代码；
    perf archive将相关符号打包，方便在其它机器进行分析；
    perf 将perf.data输出可读性文本；

可视化工具perf timechart

    perf timechart record记录事件；
    perf timechart生成output.svg文档；


查看cache miss  
perf stat -e L1-dcache-load-misses ./a.out  

常规查看  
sudo perf  record -g -a -p pid ;   
perf report  
perf diff [oldfile] [newfile]  
perf report -n --stdio //查看调用链比例

# 运行时程序某一线程性能排查 #  
    1.获得程序进程号pid  
    2.gdb attach pid =>set logging file log.txt =>set logging on 
    3.在要分析的代码处打断点
    4.thread apply all bt  
    5.在log.txt中grep 断点的函数，获得线程号tid（linux的线程是轻量级线程，这里需要LWP的号码）
    6.sudo perf  record -g -a -p tid
    7.perf report 

# 火焰图  

    git clone https://github.com/brendangregg/FlameGraph.git
    cd FlameGraph  
    
    perf script -i perf.data &> perf.unfold
    # 生成折叠后的调用栈
    ./stackcollapse-perf.pl perf.unfold &> perf.folded
    # 生成火焰图
    ./flamegraph.pl perf.folded > perf.svg
    
    perf script | ./stackcollapse-perf.pl | ./flamegraph.pl > perf.svg  
    
    ​ chrome打开perf.svg  

