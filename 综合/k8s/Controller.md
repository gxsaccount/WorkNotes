 kube-controller-manager 的组件,就是一系列控制器的集合  
 
    $cd kubernetes/pkg/controller/ 
    $ls -d */ 
     deployment/  job/               podautoscaler/ 
     cloud/       disruption/        namespace/ 
     replicaset/  serviceaccount/    volume/ 
     cronjob/     garbagecollector/  nodelifecycle/ ...  
    
    这个目录下面的每一个控制器，都以独有的方式负责某种编排功能。而我们的 Deployment，正是
这些控制器中的一种。它们都遵循 Kubernetes
项目中的一个通用编排模式，即：**控制循环（control loop/Reconcile Loop）**。  


## 控制循环 ##  
控制循环主要逻辑：  

    for
    {
        实际状态:= 获取集群中对象 X 的实际状态（Actual State） 
        期望状态 : = 获取集群中对象 X 的期望状态（Desired State） 
        if 实际状态 == 期望状态 
            { 什么都不做 }
        else { 执行编排动作，将实际状态调整(Reconcile)为期望状态 }
    }
实际状态往往来自于 Kubernetes 集群本身。比如，kubelet 通过心跳汇报的容器状态和节点状态，或者监控系统中保存的应用监控数据，或者
控制器主动收集的它自己感兴趣的信息，这些都是常见的实际状态的来源。  
而期望状态，一般来自于用户提交的 YAML 文件。  
## Deployment ##  
以 Deployment 为例，简单描述一下它对控制器模型的实现：   
Deployment 这个 template 字段里的内容，跟一个标准的 Pod 对象的 API 定义，丝毫
不差。而所有被这个 Deployment 管理的 Pod 实例，其实都是根据这个 template 字段的内容创
建出来的,叫PodTemplate（Pod 模板）  
![image](https://user-images.githubusercontent.com/20179983/141662367-31e2f67e-756c-4eb6-9167-1d5811e289cc.png)

Kubernetes 使用的这个“控制器模式”，跟我们平常所说的“事件驱动”，有什么区
别和联系吗？  
事件驱动是被动的：被控制对象要自己去判断是否需要被编排，
调度。实时将事件通知给控制器。
控制器模式是主动的：被控制对象只需要实时同步自己的状态
(实际由kubelet做的)，具体的判断逻辑由控制去做。   



## Pod的“水平扩展 / 收缩”（horizontal scaling out/in） ##   
更新了 Deployment 的 Pod 模板（比如，修改了容器的镜像），那么
Deployment 就需要遵循一种叫作“**滚动更新**”（**rolling update**）的方式，来升级现有的容
器。   
这个能力的实现，依赖的是 Kubernetes 项目中的一个非常重要的概念（API 对象）：
ReplicaSet。  
Deployment 控制 ReplicaSet（版本），ReplicaSet 控制 Pod（副本
数）。  

![image](https://user-images.githubusercontent.com/20179983/141663090-1d885227-31eb-484d-9680-c2eadd530d5a.png)


ReplicaSet 负责通过“控制器模式”，保证系统中 Pod 的个数永远等于指定的个数（比
如，3 个）。这也正是 Deployment 只允许容器的 restartPolicy=Always 的主要原因：只有在
容器能保证自己始终是 Running 状态的前提下，ReplicaSet 调整 Pod 的个数才有意义。
而在此基础上，Deployment 同样通过“控制器模式”，来操作 ReplicaSet 的个数和属性，进
而实现“水平扩展 / 收缩”和“滚动更新”这两个编排动作。
**水平拓展/收缩**  
其中，“水平扩展 / 收缩”非常容易实现，Deployment Controller 只需要修改它所控制的
ReplicaSet 的 Pod 副本个数就可以了。
比如，把这个值从 3 改成 4，那么 Deployment 所对应的 ReplicaSet，就会根据修改后的值自
动创建一个新的 Pod。这就是“水平扩展”了；“水平收缩”则反之。  

**滚动更新**    
要更新3个新版本的Pod，新 ReplicaSet 管理的 Pod 副本数，从 0 个变成 1 个，再变成 2 个，最后变成
3 个。而旧的 ReplicaSet 管理的 Pod 副本数则从 3 个变成 2 个，再变成 1 个，最后变成 0
个（水平收缩）。这样，就完成了这一组 Pod 的版本升级过程。
像这样，将一个集群中正在运行的多个 Pod 版本，交替地逐一升级的过程，就是“滚动更
新”。   


通过RollingUpdateStrategy还可以控制名每次滚动的pod数量  

   ...
   strategy: 
    type: RollingUpdate 
    rollingUpdate: 
     maxSurge: 1 
     maxUnavailable: 1  
   ...  
   
 RollingUpdateStrategy 的配置中，maxSurge 指定的是除了 DESIRED 数量之
外，在一次“滚动”中，Deployment 控制器还可以创建多少个新 Pod；而 maxUnavailable
指的是，在一次“滚动”中，Deployment 控制器可以删除多少个旧 Pod。
同时，这两个配置还可以用前面我们介绍的百分比形式来表示，比如：
maxUnavailable=50%，指的是我们最多可以一次删除“50%*DESIRED 数量”个 Pod。  


通过kubectl rollout undo 命令，就能把整个 Deployment 回滚到上一个版本  

Deployment 实际上并不足以覆盖所有的应用编排，它认为，一个应用的所有 Pod，是完全一样的。所以，它们互相之间**没有顺序**，也无所谓运行
在哪台宿主机上。需要的时候，Deployment 就可以通过 Pod 模板创建新的 Pod；不需要的时
候，Deployment 就可以“杀掉”任意一个 Pod

金丝雀发布、蓝绿发
布，以及 A/B 测试等很多应用发布模式。  
https://github.com/ContainerSolutions/k8s-deployment-strategies/tree/master/canary    



## StatefulSet拓扑状态 ##  
实例之间有不对等关系，以及实例对外部数据有依赖关系的应用，就被称为“**有状态应用**”（**Stateful Application**）。
分布式应用，它的多个实例之间，往往有依赖关系，比如：主从关系、主备关系。   
还有数据存储类应用，它的多个实例，往往都会在本地磁盘上保存一份数据。而这些实例一
旦被杀掉，即便重建出来，实例与数据之间的对应关系也已经丢失，从而导致应用失败。  
Kubernetes 项目很早就在 Deployment 的基础上，扩展出了对“有状态应用”的初步支持。这个编排功能，就是：StatefulSet  
StatefulSet 的设计其实非常容易理解。它把真实世界里的应用状态，抽象为了两种情况：
     
     1. 拓扑状态。这种情况意味着，应用的多个实例之间不是完全对等的关系。这些应用实例，必
     须按照某些顺序启动，比如应用的主节点 A 要先于从节点 B 启动。而如果你把 A 和 B 两个
     Pod 删除掉，它们再次被创建出来时也必须严格按照这个顺序才行。并且，新创建出来的
     Pod，必须和原来 Pod 的网络标识一样，这样原先的访问者才能使用同样的方法，访问到
     这个新 Pod。
     2. 存储状态。这种情况意味着，应用的多个实例分别绑定了不同的存储数据。对于这些应用实
     例来说，Pod A 第一次读取到的数据，和隔了十分钟之后再次读取到的数据，应该是同一
     份，哪怕在此期间 Pod A 被重新创建过。这种情况最典型的例子，就是一个数据库应用的
     多个存储实例。
所以，StatefulSet 的核心功能，就是通过某种方式记录这些状态，然后在 Pod 被重新创建时，能够为新 Pod 恢复这些状态   

## StatefulSet如何维护拓扑状态 ##  
**Headless Service**：有clusterIP: None的Service，可以直接得到pod的IP而不是service的（详见service），这样只要你知道了一个 Pod 的名字，以及它对应的 Service 的名字，你
就可以非常确定地通过这条 DNS 记录访问到 Pod 的 IP 地址  
创建了一个 Headless Service 之后，它所代理的所有 Pod 的 IP 地址，都
会被绑定一个这样格式的 DNS 记录，这个 DNS 记录，正是 Kubernetes 项目为 Pod 分配的唯一的“可解析身份”（Resolvable
Identity）  
   
    <pod-name>.<svc-name>.<namespace>.svc.cluster.local

StatefulSet 可以使用这个 DNS 记录来维持 Pod 的拓扑状态  

StatefulSet比起deployment会多出serviceName字段。
这个字段的作用，就是告诉 StatefulSet 控制器，在执行控制循环（Control Loop）的时候，
请使用 serviceName的指定的 Headless Service 来保证 Pod 的“可解析身份”。  

       $ kubectl get pods -w -l app=nginx 
       NAME READY STATUS RESTARTS AGE 
       web-0 0/1 Pending 0 0s
       web-0 0/1 Pending 0 0s 
       web-0 0/1 ContainerCreating 0 0s 
       web-0 1/1 Running 0 19s 
       web-1 0/1 Pending 0 0s 
       web-1 0/1 Pending 0 0s 
       web-1 0/1 ContainerCreating 0 0s 
       web-1 1/1 Running 0 20s
当把某一些 Pod 删除之后，Kubernetes 会按照**原先编号的顺序**，创建出新的 Pod。并且，Kubernetes 依然为它们分配了与原来相同的“**网络身份**”。  
通过这种严格的对应规则，StatefulSet 就保证了**Pod 网络标识的稳定性**。  
这样如果 web-0 是一个需要先启动的主节点，web-1 是一个后启动的从节点，那么只要这个
StatefulSet 不被删除，你访问 web-0.nginx 时始终都会落在主节点上，访问 web-1.nginx
时，则始终都会落在从节点上，这个关系绝对不会发生任何变化。  
**实现原理**
StatefulSet 这个控制器的主要作用之一，就是使用 Pod 模板创建 Pod 的时候，
对它们进行编号，并且按照编号顺序逐一完成创建工作。而当 StatefulSet 的“控
制循环”发现 Pod 的“实际状态”与“期望状态”不一致，需要新建或者删除
Pod 进行“调谐”的时候，它会严格按照这些 Pod 编号的顺序，逐一完成这些操
作。

## 存储状态 ##  
StatefulSet 对存储状态的管理机制，主要使用**Persistent Volume Claim** 的功能。  
PVC 是一种特殊的Volume。只不过一个 PVC 具体是什么类型的 Volume，要在跟某个 PV 绑定之后才知道。  
不了解持久化存储项目（比如 Ceph、GlusterFS 等），很难写出合适的volums,甚至暴露存储服务器的地址、用户名、授权文件的位置的风险  
Kubernetes 项目引入了一组叫作 Persistent Volume  
Claim（PVC）和 Persistent Volume（PV）的 API 对象，大大降低了用户声明和使用持久化Volume 的门槛。  
运维人员维护好 PV（Persistent Volume）对象，开发人员直接使用  
有了 PVC 之后，一个开发人员想要使用一个 Volume，只需要简单的两步即可。  

第一步：定义一个 PVC，声明想要的 Volume 的属性：  
    
    kind: PersistentVolumeClaim 
    apiVersion: v1 
      metadata: 
        name: 
          pv-claim 
      spec: 
          accessModes: 
          - ReadWriteOnce 
          resources: 
            requests: 
              storage: 1Gi

在这个 PVC 对象里，不需要任何关于 Volume 细节的字段，只有描述性的属性和定
义。比如，storage: 1Gi，表示我想要的 Volume 大小至少是 1 GB；accessModes:
ReadWriteOnce，表示这个 Volume 的挂载方式是可读写，并且只能被挂载在一个节点上而非
被多个节点共享。  

第二步：在应用的 Pod 中，声明使用这个 PVC：  

     ...
     volumes: 
       - name: pv-storage 
          persistentVolumeClaim: 
             claimName: pv-claim
     ...
在这个 Pod 的 Volumes 定义中，我们只需要声明它的类型是
persistentVolumeClaim，然后指定 PVC 的名字，而完全不必关心 Volume 本身的定义。  


**Kubernetes 中 PVC 和 PV 的设计，实际上类似于“接口”和“实现”的思想。开发者
只要知道并会使用“接口”，即：PVC；而运维人员则负责给“接口”绑定具体的实现，即：
PV。**  
这种解耦，就避免了因为向开发者暴露过多的存储系统细节而带来的隐患。此外，这种职责的分
离，往往也意味着出现事故时可以更容易定位问题和明确责任，从而避免“扯皮”现象的出现。  

而 PVC、PV 的设计，也使得 StatefulSet 对存储状态的管理成为了可能。  

为 StatefulSet 额外添加了一个 volumeClaimTemplates 字段。  
凡是被这
个 StatefulSet 管理的 Pod，都会声明一个对应的 PVC；而这个 PVC 的定义，就来自于
volumeClaimTemplates 这个模板字段。更重要的是，这个 PVC 的名字，会被分配一个与这个
Pod 完全一致的编号   

在使用 kubectl create 创建了 StatefulSet 之后，就会看到 Kubernetes 集群里出
现了两个 PVC：  
$ kubectl create -f statefulset.yaml $ kubectl get pvc -l app=nginx NAME STATUS VOLUME CAPACITY ACCESSMODES AGE www-web-0 Bound pvc-15c268c7-b507-11e6-932f-42010a800002 1Gi RWO 48s www-web-1 Bound pvc-15c79307-b507-11e6-932f-42010a800002 1Gi RWO 48s  

**实现原理**  
**当将pod删除后，他的PVC 和 PV不会被删除（里面记录着该pod保留的状态信息）  
重新创建pod时复用PVC，PV，这样存储状态就依然延续给了新的pod**
具体解释：
当你把一个 Pod，比如 web-0，删除之后，这个 Pod 对应的 PVC 和 PV，并不会被删
除，而这个 Volume 里已经写入的数据，也依然会保存在远程存储服务里（比如，我们在这个
例子里用到的 Ceph 服务器）。
此时，StatefulSet 控制器发现，一个名叫 web-0 的 Pod 消失了。所以，控制器就会重新创建
一个新的、名字还是叫作 web-0 的 Pod 来，“纠正”这个不一致的情况。
需要注意的是，在这个新的 Pod 对象的定义里，它声明使用的 PVC 的名字，还是叫作：www-web-0。这个 PVC 的定义，还是来自于 PVC 模板（volumeClaimTemplates），这是
StatefulSet 创建 Pod 的标准流程。
所以，在这个新的 web-0 Pod 被创建出来之后，Kubernetes 为它查找名叫 www-web-0 的
PVC 时，就会直接找到旧 Pod 遗留下来的同名的 PVC，进而找到跟这个 PVC 绑定在一起的
PV。
这样，新的 Pod 就可以挂载到旧 Pod 对应的那个 Volume，并且获取到保存在 Volume 里的
数据。
通过这种方式，Kubernetes 的 StatefulSet 就实现了对应用存储状态的管理。  


**总结！！！**  
首先，StatefulSet 的控制器直接管理的是 Pod。这是因为，StatefulSet 里的不同 Pod 实例，
不再像 ReplicaSet 中那样都是完全一样的，而是有了细微区别的。比如，每个 Pod 的
hostname、名字等都是不同的、携带了编号的。而 StatefulSet 区分这些实例的方式，就是通
过在 Pod 的名字里加上事先约定好的编号。
其次，Kubernetes 通过 Headless Service，为这些有编号的 Pod，在 DNS 服务器中生成带有
同样编号的 DNS 记录。只要 StatefulSet 能够保证这些 Pod 名字里的编号不变，那么 Service
里类似于 web-0.nginx.default.svc.cluster.local 这样的 DNS 记录也就不会变，而这条记录解
析出来的 Pod 的 IP 地址，则会随着后端 Pod 的删除和再创建而自动更新。这当然是 Service
机制本身的能力，不需要 StatefulSet 操心。
最后，StatefulSet 还为每一个 Pod 分配并创建一个同样编号的 PVC。这样，Kubernetes 就可
以通过 Persistent Volume 机制为这个 PVC 绑定上对应的 PV，从而保证了每一个 Pod 都拥有
一个独立的 Volume。
在这种情况下，即使 Pod 被删除，它所对应的 PVC 和 PV 依然会保留下来。所以当这个 Pod
被重新创建出来之后，Kubernetes 会为它找到同样编号的 PVC，挂载这个 PVC 对应的
Volume，从而获取到以前保存在 Volume 里的数据。  



**思考题**  
在实际场景中，有一些分布式应用的集群是这么工作的：当一个新节点加入到集群时，或者老节
点被迁移后重建时，这个节点可以从主节点或者其他从节点那里同步到自己所需要的数据。
在这种情况下，你认为是否还有必要将这个节点 Pod 与它的 PV 进行一对一绑定呢？（提示：
这个问题的答案根据不同的项目是不同的。关键在于，重建后的节点进行数据恢复和同步的时
候，是不是一定需要原先它写在本地磁盘里的数据）
