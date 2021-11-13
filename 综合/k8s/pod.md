## 进程组 ##  
在linux中使用  pstree -g  ,当前系统中正在运行的进程的树状结构。  


      systemd(1)─┬─ModemManager(969)─┬─{ModemManager}(969)
           │                   └─{ModemManager}(969)
           ├─NetworkManager(877)─┬─{NetworkManager}(877)
           │                     └─{NetworkManager}(877)
           ├─accounts-daemon(868)─┬─{accounts-daemon}(868)
           │                      └─{accounts-daemon}(868)
           ├─acpid(869)
           ├─avahi-daemon(872)───avahi-daemon(872)
           ...
           |-rsyslogd(1632)-+-{in:imklog}(1632)  
           ...

在一个真正的操作系统里，进程并不是“孤苦伶仃”地独自运行的，而是以进程组的方
式，“有原则的”组织在一起。在这个进程的树状图中，每一个进程后面括号里的数字，就是它的
进程组 ID（Process Group ID, PGID）   
这里有一个叫作 rsyslogd 的程序，它负责的是 Linux 操作系统里的日志处理。可以看到，
rsyslogd 的主程序 main，和它要用到的内核日志模块 imklog 等，同属于 1632 进程组。相互协作，共同完成 rsyslogd 程序的职责。  
对于操作系统来说，这样的进程组更方便管理。举个例子，Linux 操作系统只需要将信号，比如，
SIGKILL 信号，发送给一个进程组，那么该进程组中的所有进程就都会收到这个信号而终止运行。  
而 Kubernetes 项目所做的，其实就是将“进程组”的概念映射到了容器技术中，并使其成为了这
个云计算“操作系统”里的“一等公民”。  

## k8s使用进程组的原因（pod） ##  
以前面的 rsyslogd 为例子。已知 rsyslogd 由三个进程组成：一个 imklog 模块，一个
imuxsock 模块，一个 rsyslogd 自己的 main 函数主进程。这三个进程一定要运行在同一台机器
上，否则，它们之间基于 Socket 的通信和文件交换，都会出现问题。
现在，我要把 rsyslogd 这个应用给容器化，由于受限于容器的“单进程模型”，这三个模块必须被
分别制作成三个不同的容器。而在这三个容器运行的时候，它们设置的内存配额都是 1 GB。  
假设我们的 Kubernetes 集群上有两个节点：node-1 上有 3 GB 可用内存，node-2 有 2.5 GB 可
用内存。  
**使用Docker Swarm**    
这时，假设我要用 Docker Swarm 来运行这个 rsyslogd 程序。为了能够让这三个容器都运行在同
一台机器上，我就必须在另外两个容器上设置一个 affinity=main（与 main 容器有亲密性）的约
束，即：它们俩必须和 main 容器运行在同一台机器上。
然后，我顺序执行：“docker run main”“docker run imklog”和“docker run imuxsock”，
创建这三个容器。
这样，这三个容器都会进入 Swarm 的待调度队列。然后，main 容器和 imklog 容器都先后出队并
被调度到了 node-2 上（这个情况是完全有可能的）。
可是，当 imuxsock 容器出队开始被调度时，Swarm 就有点懵了：node-2 上的可用资源只有 0.5
GB 了，并不足以运行 imuxsock 容器；可是，根据 affinity=main 的约束，imuxsock 容器又只能
运行在 node-2 上。
这就是一个典型的成**组调度（gang scheduling）**\没有被妥善处理的例子。   
**使用k8s**   
Pod 是 Kubernetes 里的**原子调度单位**。这就意味着，Kubernetes 项目的调度器，是统一按照 Pod 而非容器的资源需求进行计算的。
所以，像 imklog、imuxsock 和 main 函数主进程这样的三个容器，正是一个典型的由三个容器组
成的 Pod。Kubernetes 项目在调度时，自然就会去选择可用内存等于 3 GB 的 node-1 节点进行
绑定，而根本不会考虑 node-2。
像这样容器间的紧密协作，我们可以称为“**超亲密关系**”。这些具有“超亲密关系”容器的典型特
征包括但不限于：互相之间会发生直接的文件交换、使用 localhost 或者 Socket 文件进行本地通
信、会发生非常频繁的远程调用、需要共享某些 Linux Namespace（比如，一个容器要加入另一个
容器的 Network Namespace）等等。


**容器的“单进程模型**  
再次强调一下：容器的“单进程模型”，并不是指容器里只能运行“一个”进程，而是指容器没
有管理多个进程的能力。这是因为容器里 PID=1 的进程就是应用本身，其他的进程都是这个
PID=1 进程的子进程。可是，用户编写的应用，并不能够像正常操作系统里的 init 进程或者
systemd 那样拥有进程管理的功能。比如，你的应用是一个 Java Web 程序（PID=1），然后你
执行 docker exec 在后台启动了一个 Nginx 进程（PID=3）。可是，当这个 Nginx 进程异常退
出的时候，你该怎么知道呢？这个进程退出后的垃圾收集工作，又应该由谁去做呢？   


## pod的实现原理 ##  
Pod 里的所有容器，共享的是同一个 Network Namespace，并且可以声明共享同一个
Volume  
通过docker的“docker run --net=B --volumes-from=B --name=A image-A ...“也能实现相似的功能  
但是如果真这样做的话，容器 B 就必须比容器 A 先启动，这样一个 Pod 里的
多个容器就不是对等关系，而是拓扑关系了。  
所以，在 Kubernetes 项目里，Pod 的实现需要使用一个中间容器，这个容器叫作 **Infra 容器**。它使用的是一个非常特殊的镜像，叫
作：k8s.gcr.io/pause。这个镜像是一个用汇编语言编写的、永远处于“暂停”状态的容器，解
压后的大小也只有 100~200 KB 左右在
这个 Pod 中，Infra 容器永远都是第一个被创建的容器，而其他用户定义的容器，则通过 Join
Network Namespace 的方式，与 Infra 容器关联在一起。这样的组织关系，可以用下面这样一个
示意图来表达：  



![image](https://user-images.githubusercontent.com/20179983/141642196-b9f970b8-eb43-49c9-91ae-8ac7a3b88cf2.png)

在 Infra 容器“Hold 住”Network Namespace 后，用户容器就可以加入到 Infra 容器的
Network Namespace 当中了。所以，如果你查看这些容器在宿主机上的 Namespace 文件（这个
Namespace 文件的路径，我已经在前面的内容中介绍过），它们指向的值一定是完全一样的。
这也就意味着，对于 Pod 里的容器 A 和容器 B 来说：
    
    1.它们可以直接使用 localhost 进行通信；
    2.它们看到的网络设备跟 Infra 容器看到的完全一样；
    3.一个 Pod 只有一个 IP 地址，也就是这个 Pod 的 Network Namespace 对应的 IP 地址；
    4.当然，其他的所有网络资源，都是一个 Pod 一份，并且被该 Pod 中的所有容器共享；
    5.Pod 的生命周期只跟 Infra 容器一致，而与容器 A 和 B 无关  

实例：  
们现在有一个 Java Web 应用的 WAR 包，它需要被放在 Tomcat 的 webapps 目录下运行起来  
现在只能用 Docker 来做这件事情，有两种方案  

  *一种方法是，把 WAR 包直接放在 Tomcat 镜像的 webapps 目录下，做成一个新的镜像运行起
  来。可是，这时候，如果你要更新 WAR 包的内容，或者要升级 Tomcat 镜像，就要重新制作一
  个新的发布镜像，非常麻烦。
  *另一种方法是，你压根儿不管 WAR 包，永远只发布一个 Tomcat 容器。不过，这个容器的
  webapps 目录，就必须声明一个 hostPath 类型的 Volume，从而把宿主机上的 WAR 包挂载进
  Tomcat 容器当中运行起来。不过，这样你就必须要解决一个问题，即：如何让每一台宿主机，
  都预先准备好这个存储有 WAR 包的目录呢？这样来看，你只能独立维护一套分布式存储系统
  了。  
  
  有了 Pod 之后，这样的问题就很容易解决了。我们可以把 WAR 包和 Tomcat 分别做成镜
像，然后把它们作为一个 Pod 里的两个容器“组合”在一起。  

但是war包和tomcat有依赖关系，需要war包的镜像先启动，所以war包需要是一个  **Init Container** 
在 Pod 中，所有 Init Container 定义的容器，都会比 spec.containers 定义的用户容器先启动。并
且，Init Container 容器会按顺序逐一启动，而直到它们都启动并且退出了，用户容器才会启动。  

像这样，我们就用一种“组合”方式，解决了 WAR 包与 Tomcat 容器之间耦合关系的问题。
实际上，这个所谓的“组合”操作，正是容器设计模式里最常用的一种模式，它的名字叫：
**sidecar**。  

sidecar 指的就是我们可以在一个 Pod 中，启动一个辅助容器，来完成一些独立于主进
程（主容器）之外的工作  

比如，在我们的这个应用 Pod 中，Tomcat 容器是我们要使用的主容器，而 WAR 包容器的存在，
只是为了给它提供一个 WAR 包而已。所以，我们用 Init Container 的方式优先运行 WAR 包容
器，扮演了一个 sidecar 的角色。  

Pod 的另一个重要特性是，它的所有容器都共享同一个 Network Namespace。这就
使得很多与 Pod 网络相关的配置和管理，也都可以交给 sidecar 完成，而完全无须干涉用户容器。
这里最典型的例子莫过于 Istio 这个微服务治理项目了。  



## Pod和Container的界限 ##  
凡是调度、网络、存储，以及安全相关的属性，基本上是 Pod 级别的  
它们描述的是“机器”这个整体，而不是里面运行的“程序”。比如，配
置这个“机器”的网卡（即：Pod 的网络定义），配置这个“机器”的磁盘（即：Pod 的存储定
义），配置这个“机器”的防火墙（即：Pod 的安全定义）。更不用说，这台“机器”运行在哪个
服务器之上（即：Pod 的调度）。  


## Pod 的状态 ##  
 Pod API 对象的Status 部分，，pod.status.phase，就是 Pod 的当前状态  
            
            1. Pending。这个状态意味着，Pod 的 YAML 文件已经提交给了 Kubernetes，API 对象已经被
            创建并保存在 Etcd 当中。但是，这个 Pod 里有些容器因为某种原因而不能被顺利创建。比
            如，调度不成功。
            2. Running。这个状态下，Pod 已经调度成功，跟一个具体的节点绑定。它包含的容器都已经创
            建成功，并且至少有一个正在运行中。
            3. Succeeded。这个状态意味着，Pod 里的所有容器都正常运行完毕，并且已经退出了。这种情
            况在运行一次性任务时最为常见。
            4. Failed。这个状态下，Pod 里至少有一个容器以不正常的状态（非 0 的返回码）退出。这个状
            态的出现，意味着你得想办法 Debug 这个容器的应用，比如查看 Pod 的 Events 和日志。
            5. Unknown。这是一个异常状态，意味着 Pod 的状态不能持续地被 kubelet 汇报给 kube-apiserver，这很有可能是主从节点（Master 和 Kubelet）间的通信出现了问题。
 Pod 对象的 Status 字段，还可以再细分出一组 Conditions，这些细分状态的值包
括：PodScheduled、Ready、Initialized，以及 Unschedulable。它们主要用于描述造成当前
Status 的具体原因是什么   
Pod 当前的 Status 是 Pending，对应的 Condition 是 Unschedulable，这就意味着它的调
度出现了问题。
而其中，Ready 这个细分状态非常值得我们关注：它意味着 Pod 不仅已经正常启动（Running 状
态），而且已经可以对外提供服务了。这两者之间（Running 和 Ready）是有区别的，你不妨仔细
思考一下。
Pod 的这些状态信息，是我们判断应用运行情况的重要标准，尤其是 Pod 进入了非“Running”状
态后，你一定要能迅速做出反应，根据它所代表的异常情况开始跟踪和定位，而不是去手忙脚乱地
查阅文档。   

GOPATH/src/k8s.io/kubernetes/vendor/k8s.io/api/core/v1/types.go  

 

