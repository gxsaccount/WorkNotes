# 全局架构 #   
![image](https://user-images.githubusercontent.com/20179983/140022021-0eeee6f8-14e6-4a65-92de-f1cf6d5dd26b.png)
Kubernetes 项目的架构，都由 Master 和 Node两种节点组成，而这两种角色分别对应着**控制节点**和**计算节点**    
控制节点，即 Master 节点，由三个紧密协作的独立组件组合而成，它们分别是负责   
1.API 服务的 kube-apiserver、  
2.负责调度的 kube-scheduler，  
3.负责容器编排的 kube-controller-manager。  
整个集群的持久化数据，则由 kube-apiserver 处理后保存在 Ectd 中。
而计算节点上最核心的部分，则是一个叫作 kubelet 的组件。  
kubelet 主要负责同容器运行时（比如 Docker 项目）打交道。而这个交
互所依赖的，是一个称作 CRI（Container Runtime Interface）的远程调用接口，这个接口定义了
容器运行时的各项核心操作，比如：启动一个容器需要的所有参数。  

##kubelet##  
**namaspace和cgroups的交互**
而具体的容器运行时，比如 Docker 项目，则一般通过 OCI 这个容器运行时规范同底层的 Linux 操
作系统进行交互，即：把 CRI 请求翻译成对 Linux 操作系统的调用（操作 Linux Namespace 和
Cgroups 等）。
**宿主机物理设备的主要组件的交互**
此外，kubelet 还通过 gRPC 协议同一个叫作 Device Plugin 的插件进行交互。这个插件，是
Kubernetes 项目用来管理 GPU 等宿主机物理设备的主要组件，也是基于 Kubernetes 项目进行机
器学习训练、高性能作业支持等工作必须关注的功能。  
**配置网络和持久化存储**  
而kubelet 的另一个重要功能，则是调用网络插件和存储插件为容器配置网络和持久化存储。这两
个插件与 kubelet 进行交互的接口，分别是 CNI（Container Networking Interface）和
CSI（Container Storage Interface）。



Kubernetes 项目对容器间的“访问”进行了分类，首先总结出了一类非常常见的**紧密交互**的关系，即：这些应用之间需要非常频繁的交互和访问；又或者，它们会直接通过本地文件进
行信息交换。  
在常规环境下，这些应用往往会被直接部署在同一台机器上，通过 Localhost 通信，通过本地磁盘
目录交换文件。而在 Kubernetes 项目中，这些容器则会被划分为**一个“Pod”**，Pod 里的容器共
享同一个 Network Namespace、同一组数据卷，从而达到高效率交换信息的目的。  

而对于另外一种更为常见的需求，比如 Web 应用与数据库之间的访问关系，Kubernetes 项目则提供了一种叫作**Service的服务**。  
像这样的两个应用，往往故意**不部署在同一台机器上**，这样即使
Web 应用所在的机器宕机了，数据库也完全不受影响。可是，我们知道，对于一个容器来说，它的
IP 地址等信息不是固定的，那么 Web 应用又怎么找到数据库容器的 Pod 呢？  
所以，Kubernetes 项目的做法是给 Pod 绑定一个 Service 服务，而 Service 服务声明的 IP 地址等
信息是“终生不变”的。这个Service 服务的主要作用，就是作为 Pod 的代理入口（Portal），从
而代替 Pod 对外暴露一个固定的网络地址。   

对于 Web 应用的 Pod 来说，它需要关心的就是数据库 Pod 的 Service 信息。不难想象，
Service 后端真正代理的 Pod 的 IP 地址、端口等信息的自动更新、维护，则是 Kubernetes 项目的
职责。  

围绕着容器和 Pod 不断向真实的技术场景扩展，我们就能够摸索出一幅如下所示的
Kubernetes 项目核心功能的“全景图”。  
![image](https://user-images.githubusercontent.com/20179983/140030987-9fef545e-b26b-402c-a9ef-41a7e7ae832c.png)
按照这幅图的线索，我们从容器这个最基础的概念出发，首先遇到了容器间“紧密协作”关系的难
题，于是就扩展到了 Pod；有了 Pod 之后，我们希望能一次启动多个应用的实例，这样就需要
Deployment 这个 Pod 的多实例管理器；而有了这样一组相同的 Pod 后，我们又需要通过一个固
定的 IP 地址和端口以负载均衡的方式访问它，于是就有了 Service。
可是，如果现在两个不同 Pod 之间不仅有“访问关系”，还要求在发起时加上授权信息。最典型的
例子就是 Web 应用对数据库访问时需要 Credential（数据库的用户名和密码）信息。那么，在
Kubernetes 中这样的关系又如何处理呢？
Kubernetes 项目提供了一种叫作 Secret 的对象，它其实是一个保存在 Etcd 里的键值对数据。这
样，你把 Credential 信息以 Secret 的方式存在 Etcd 里，Kubernetes 就会在你指定的 Pod（比
如，Web 应用的 Pod）启动时，自动把 Secret 里的数据以 Volume 的方式挂载到容器里。这样，
这个 Web 应用就可以访问数据库了  





