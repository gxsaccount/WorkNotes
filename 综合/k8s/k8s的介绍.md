
# 全局架构 #   
![image](https://user-images.githubusercontent.com/20179983/140022021-0eeee6f8-14e6-4a65-92de-f1cf6d5dd26b.png)
Kubernetes 项目的架构，都由 Master 和 Node两种节点组成，而这两种角色分别对应着**控制节点**和**计算节点**    
**控制节点**    
即 Master 节点，由三个紧密协作的独立组件组合而成，它们分别是负责   
        
        1.API 服务的 kube-apiserver、  
        2.负责调度的 kube-scheduler，  
        3.负责容器编排的 kube-controller-manager。  
整个集群的持久化数据，则由 kube-apiserver 处理后保存在 Ectd 中。  


**计算节点**  
计算节点上最核心的部分，则是一个叫作 **kubelet** 的组件。  
kubelet **主要负责同容器运行时（比如 Docker 项目）打交道**。而这个交
互所依赖的，是一个称作 CRI（Container Runtime Interface）的远程调用接口，这个接口定义了
容器运行时的各项核心操作，比如：启动一个容器需要的所有参数。  

## kubelet ##  
**namaspace和cgroups的交互，OCI规范**
具体的容器运行时，比如 Docker 项目，则一般通过 **OCI 这个容器运行时规范**同底层的 Linux 操
作系统进行交互，即：把 CRI 请求翻译成对 Linux 操作系统的调用（操作 Linux Namespace 和
Cgroups 等）。
**宿主机物理设备交互，Device Plugin**
此外，kubelet 还通过 gRPC 协议同一个叫作 Device Plugin 的插件进行交互。这个插件，是
Kubernetes 项目用来管理 GPU 等宿主机物理设备的主要组件，也是基于 Kubernetes 项目进行机
器学习训练、高性能作业支持等工作必须关注的功能。  
**网络和持久化的交互，CNI和CSI**  
而kubelet 的另一个重要功能，则是调用网络插件和存储插件为容器配置网络和持久化存储。这两
个插件与 kubelet 进行交互的接口，分别是 CNI（Container Networking Interface）和
CSI（Container Storage Interface）。



## Kubernetes 项目核心功能 ##  
**核心功能全景图**  
![image](https://user-images.githubusercontent.com/20179983/140030987-9fef545e-b26b-402c-a9ef-41a7e7ae832c.png)   
### k8s如何定义容器间关系和形态 ###  
**基础编排对象pod：一组交互频繁的容器的集合（同机共享资源）**  
这些应用（容器）之间需要非常频繁的交互和访问；又或者，它们会直接通过本地文件进
行信息交换。  
在常规环境下，这些应用往往会被直接部署在**同一台机器**上，通过 Localhost 通信，通过本地磁盘
目录交换文件。  
而在 Kubernetes 项目中，这些容器则会被划分为一个“Pod”，**Pod 里的容器共
享同一个 Network Namespace、同一组数据卷，从而达到高效率交换信息的目的。**    

**服务对象Service：不紧密的交互的应用（可以不同机）**         
有的应用，往往故意**不部署在同一台机器上**，例如Web 应用与数据库之间的访问关系，这样即使Web 应用所在的机器宕机了，数据库也完全不受影响。  
为这样的交互关系，Kubernetes 项目则提供了一种叫作Service的服务。
对于一个容器来说，它的
IP 地址等信息不是固定的，那么 Web 应用又怎么找到数据库容器的 Pod 呢？  
所以，Kubernetes 项目的做法是给 Pod 绑定一个 Service 服务，而 Service 服务声明的 IP 地址等
信息是“终生不变”的。这个**Service 服务的主要作用，就是作为 Pod 的代理入口（Portal），从
而代替 Pod 对外暴露一个固定的网络地址。**   
对于 Web 应用的 Pod 来说，它需要关心的就是数据库 Pod 的 Service 信息。  
**Service 后端真正代理的 Pod 的 IP 地址、端口等信息的自动更新、维护，是 Kubernetes 项目的
职责。**  


**Deployment：pod的控制器**  
我们希望能一次启动多个应用的实例，这样就需要Deployment 这个 Pod 的多实例管理器
它能控制pod扩容缩容，升级回滚，节点间调度等  
**Secret：授权信息**  
两个不同 Pod 之间不仅有“访问关系”，有时候还需要在发起时加上授权信息。  
例如Web 应用对数据库访问时需要 Credential（数据库的用户名和密码）信息。  
Kubernetes 项目提供了一种叫作 Secret 的对象，它其实是一个保存在 Etcd 里的键值对数据。这
样，你把 Credential 信息以 Secret 的方式存在 Etcd 里，Kubernetes 就会在你指定的 Pod（比
如，Web 应用的 Pod）启动时，自动把 Secret 里的数据以 **Volume** 的方式挂载到容器里。  
这个 Web 应用就可以访问数据库了  

**核心功能相关概念总结**    

    1.因为容器间“紧密协作”关系的难题，于是就扩展到了 Pod；  
    2.有了 Pod 之后，我们希望能一次启动多个应用的实例，这样就需要Deployment 这个 Pod 的多实例管理器；
    3.而有了这样一组相同的 Pod 后，我们又需要通过一个固定的 IP 地址和端口以负载均衡的方式访问它，于是就有了 Service。  
    4.两个不同 Pod 之间不仅有“访问关系”，还要求在发起时加上授权信息。把 Credential 信息以 Secret 的方式存在 Etcd 里，Kubernetes 就会在你指定的 Pod（比
    如，Web 应用的 Pod）启动时，自动把 Secret 里的数据以 Volume 的方式挂载到容器里。这样，这个 Web 应用就可以访问数据库了  

**特殊的编排对象**
除了应用与应用之间的关系外，应用运行的形态是影响“如何容器化这个应用”的第二个重要因素。
为此，Kubernetes 定义了新的、基于 Pod 改进后的对象。  
        
        1.比如 **Job**，用来描述一次性运行的Pod（比如，大数据任务）；
        2.再比如 **DaemonSet**，用来描述每个宿主机上必须且只能运行一个副本的守护进程服务；
        3.又比如 **CronJob**，则用于描述定时任务等等。
  

### k8s设计理念 ###  
Kubernetes 项目并没有像其他项目那样，为每一个管理功能创建一个指令，然后在项目中实现其中的逻辑。    
相比之下，在 Kubernetes 项目中，我们所推崇的使用方法是：
首先，通过一个“编排对象”，比如 Pod、Job、CronJob 等，来描述你试图管理的应用；
然后，再为它定义一些“服务对象”，比如 Service、Secret、Horizontal Pod Autoscaler（自动水平扩展器）等。这些对象，会负责具体的平台级功能。
这种使用方法，就是所谓的“**声明式 API**”。这种 API 对应的“编排对象”和“服务对象”，都是Kubernetes 项目中的 API 对象（API Object）。
这就是 Kubernetes 最核心的设计理念。  


## Kubernetes 项目如何启动一个容器化任务呢？##      

比如，我现在已经制作好了一个 Nginx 容器镜像，希望让平台帮我启动这个镜像。并且，我要求平
台帮我运行两个完全相同的 Nginx 副本，以负载均衡的方式共同对外提供服务。
如果是自己 DIY 的话，可能需要启动两台虚拟机，分别安装两个 Nginx，然后使用 keepalived
为这两个虚拟机做一个虚拟 IP。
而如果使用 Kubernetes 项目呢？你需要做的则是编写如下这样一个 YAML 文件（比如名叫
nginx-deployment.yaml）：   

    apiVersion: apps/v1　　#apiVersion是当前配置格式的版本
    kind: Deployment　　　　#kind是要创建的资源类型，这里是Deploymnet
    metadata:　　　　　　　　#metadata是该资源的元数据，name是必须的元数据项
      name: nginx-deployment
      labels:             #标记
        app: nginx          
    spec:　　　　　　　　　　#spec部分是该Deployment的规则说明
      replicas: 2　　　　　 #relicas指定副本数量，默认为1
      selector:
        matchLabels:
          app: nginx
      template:　　　　　　#template定义Pod的模板，这是配置的重要部分（主体部分）
        metadata:　　　　  #metadata定义Pod的元数据，至少要顶一个label，label的key和value可以任意指定
          labels:
            app: nginx
        spec:　　　　　　　#spec描述的是Pod的规则，此部分定义pod中每一个容器的属性，name和image是必需的
          containers:
          - name: nginx
            image: nginx:1.7.9
            ports:
            - containerPort: 80



执行如下代码即可启动nginx容器副本  
    kubectl create -f nginx-deployment.yaml

## k8s的本质 ##  
**调度**：实际上，过去很多的集群管理项目（比如 Yarn、Mesos，以及 Swarm）所擅长的，都是把一个容器，按照某种规则，放置在某个最佳节点上运行起来。这种功能，我们称为“调度”。  
**编排**：按照用户的意愿和整个系统的规则，完全自动化地处理好容器之间的各种关系  
Kubernetes 项目的本质，是为用户提供一个具有普遍意义的容器编排工具。  
容器，就是未来云计算系统中的进程；容器镜像就是这个系统里的“.exe”安装包。Kubernetes 就是未来云计算系统的操作系统。   


## 其他概念 ##
**API对象**:YAML 文件，对应到 Kubernetes 中，就是一个 API Object（API 对象）。当你为这
个对象的各个字段填好值并提交给 Kubernetes 之后，Kubernetes 就会负责创建出这些对象所定义
的容器或者其他类型的 API 资源。不推荐你使用命令行的方式直接运行容器
（虽然 Kubernetes 项目也支持这种方式，比如：kubectl run），而是希望你用 YAML 文件的方
式，这样能知道run了个什么东西    
**Deployment**，是一个定义多副本应用（即多个副本 Pod）的对象
**声明式 API**，作为用户作为用户，你不必
关心当前的操作是创建，还是更新，你执行的命令始终是 kubectl apply，而 Kubernetes 则会根据
YAML 文件的内容变化，自动进行具体的处理。
而这个流程的好处是，它有助于帮助开发和运维人员，围绕着可以版本化管理的 YAML 文件，而不
是“行踪不定”的命令行进行协作，从而大大降低开发人员和运维人员之间的沟通成本。，你不必
关心当前的操作是创建，还是更新，你执行的命令始终是 kubectl apply，而 Kubernetes 则会根据
YAML 文件的内容变化，自动进行具体的处理。
而这个流程的好处是，它有助于帮助开发和运维人员，围绕着可以版本化管理的 YAML 文件，而不
是“行踪不定”的命令行进行协作，从而大大降低开发人员和运维人员之间的沟通成本。  



## 思考题 ##
 这今天的分享中，我介绍了 Kubernetes 项目的架构。你是否了解了 Docker
Swarm（SwarmKit 项目）跟 Kubernetes 在架构上和使用方法上的异同呢？  

从微服务架构来讲，多个独立功能内聚的服务带来了整体的灵活性，但是同时也带来了部署运维的复杂度提升，这时Docker配合Devops带来了不少的便利(轻量、隔离、一致性、CI、CD等)
解决了不少问题，再配合compose，看起来一切都很美了，为什么还需要K8s？可以试着这样理解么？把微服务理解为人，那么服务治理其实就是人之间的沟通而已，人太多了就需要生存空
间和沟通方式的优化，这就需要集群和编排了。Docker Compose，swarm，可以解决少数人之间的关系，比如把手机号给你，你就可以方便的找到我，但是如果手机号变更的时候就会麻烦，人多了也会麻烦。
而k8s是站在上帝视角俯视芸芸众生后的高度抽象，他看到了大概有哪些类人(组织）以及不同组织有什
么样的特点（Job、CornJob、Autoscaler、StatefulSet、DaemonSet...），不同组织之间交流可能需要什么（ConfigMap,Secret...）,这样比价紧密的人们在相同pod中，通过Service-不
会变更的手机号，来和不同的组织进行沟通，Deployment、RC则可以帮组人们快速构建组织。Dokcer 后出的swarm mode，有类似的视角抽象（比如Service），不过相对来说并不完
善。  

在 Kubernetes 之前，很多项目都没办法管理“有状态”的容器，即，不能从一台宿主机“迁
移”到另一台宿主机上的容器。你是否能列举出，阻止这种“迁移”的原因都有哪些呢？  

不能迁移“有状态”的容器，是因为迁移的是容器的rootfs，但是一些动态视图是没有办法伴随迁移一同进行迁移的。
只能删除后在新的节点上重新创建  

存储在文件或者数据库里的数据还是比较好迁移，但是对于缓存，临时存储的数据是不是就不太好迁移。  
如mysql这种有状态服务，当容器被调度到
其他节点时，ip和存储的数据都无法同步了,甚至主从结构的mysql？？？    
阻止迁移的情况有volum 映射，造成数
据文件与固定宿主机绑定；还有就是网络问题。



