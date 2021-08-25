https://tech.meituan.com/2015/03/31/cgroups.html

# 引子 #
cgroups 是Linux内核提供的一种可以限制单个进程或者多个进程所使用资源的机制，可以对 cpu，内存等资源实现精细化的控制，目前越来越火的轻量级容器 Docker 就使用了 cgroups 提供的资源限制能力来完成cpu，内存等部分的资源控制。  
另外，开发者也可以使用 cgroups 提供的精细化控制能力，限制某一个或者某一组进程的资源使用。比如在一个既部署了前端 web 服务，也部署了后端计算模块的八核服务器上，可以使用 cgroups 限制 web server 仅可以使用其中的六个核，把剩下的两个核留给后端计算模块。  

本文从以下四个方面描述一下 cgroups 的原理及用法：  

    1.cgroups 的概念及原理
    2.cgroups 文件系统概念及原理
    3.cgroups 使用方法介绍
    4.cgroups 实践中的例子
    
# 概念及原理 #    
cgroups子系统  
cgroups 的全称是control groups，cgroups为每种可以控制的资源定义了一个子系统。典型的子系统介绍如下：  

    cpu 子系统，主要限制进程的 cpu 使用率。  
    cpuacct 子系统，可以统计 cgroups 中的进程的 cpu 使用报告。  
    cpuset 子系统，可以为 cgroups 中的进程分配单独的 cpu 节点或者内存节点。  
    memory 子系统，可以限制进程的 memory 使用量。  
    blkio 子系统，可以限制进程的块设备 io。  
    devices 子系统，可以控制进程能够访问某些设备。  
    net_cls 子系统，可以标记 cgroups 中进程的网络数据包，然后可以使用 tc 模块（traffic control）对数据包进行控制。  
    freezer 子系统，可以挂起或者恢复 cgroups 中的进程。  
    ns 子系统，可以使不同 cgroups 下面的进程使用不同的 namespace。  
    
这里面每一个子系统都需要与内核的其他模块配合来完成资源的控制，比如对 cpu 资源的限制是通过进程调度模块根据 cpu 子系统的配置来完成的；对内存资源的限制则是内存模块根据 memory 子系统的配置来完成的，而对网络数据包的控制则需要 Traffic Control 子系统来配合完成。(需要更具体的分析才能知道每个子系统的实现)  

# cgroups 层级结构（Hierarchy）#  

1.内核使用 cgroup 结构体来表示一个 control group 对某一个或者某几个 cgroups 子系统的资源限制。  
2.cgroup 结构体可以组织成一颗树的形式，每一棵cgroup 结构体组成的树称之为一个 cgroups 层级结构。  
3.cgroups层级结构可以 attach 一个或者几个 cgroups 子系统，当前层级结构可以对其 attach 的 cgroups 子系统进行资源的限制。  
4.每一个 cgroups 子系统只能被 attach 到一个 cpu 层级结构中。  
![cgroups层级结构示意图](https://user-images.githubusercontent.com/20179983/130719861-d64791d6-4fab-4b84-abc3-1cee5e0fd5e2.png)
