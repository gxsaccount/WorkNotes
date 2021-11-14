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



金丝雀发布、蓝绿发
布，以及 A/B 测试等很多应用发布模式。  
https://github.com/ContainerSolutions/k8s-deployment-strategies/tree/master/canary   
