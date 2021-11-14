DaemonSet 的主要作用，是让你在 Kubernetes 集群里，运行一个 Daemon
Pod。 所以，这个 Pod 有如下三个特征：

    1. 这个 Pod 运行在 Kubernetes 集群里的每一个节点（Node）上；
    2. 每个节点上只有一个这样的 Pod 实例；
    3. 当有新的节点加入 Kubernetes 集群后，该 Pod 会自动地在新节点上被创建出来；而当旧节点被删除后，它上面的 Pod 也相应地会被回收掉。  
    
实际例子：  

    1. 各种网络插件的 Agent 组件，都必须运行在每一个节点上，用来处理这个节点上的容器网络；  
    2. 各种存储插件的 Agent 组件，也必须运行在每一个节点上，用来在这个节点上挂载远程存储目录，操作容器的 Volume 目录；  
    3. 各种监控组件和日志组件，也必须运行在每一个节点上，负责这个节点上的监控信息和日志搜集。  




## DaemonSet如何部署 ##  
跟其他编排对象不一样，DaemonSet 开始运行的时机，很多时候比整个Kubernetes 集群出现的时机都要早。  
因为在部署时，整个 Kubernetes 集群里还没有可用的容器网络，所有 Worker 节点的状态都是NotReady（NetworkReady=false）。  
这种情况下，普通的 Pod 肯定不能运行在这个集群上。
在 Kubernetes 项目中，当一个节点的网络插件尚未安装时，这个节点就会被自动加上名为
node.kubernetes.io/network-unavailable的“污点”。    
假如当前 DaemonSet 管理的，是一个网络插件的 Agent Pod，那么你就必须在这个
DaemonSet 的 YAML 文件里，给它的 Pod 模板加上一个能够“容
忍”node.kubernetes.io/network-unavailable“污点”的 Toleration。   

**污点**可以理解为一种特殊的 Label
**Toleration**则是可以容忍这些污点，DaemonSet通过Toleration可以在节点有某些污点的情况下部署    

DaemonSet 如何保证每个 Node 上有且只有一个被管理的 Pod  
DaemonSet Controller，首先从 Etcd 里获取所有的 Node 列表，然后遍历所有的 Node。这
时，它就可以很容易地去检查，当前这个 Node 上是不是有一个携带了 name=【DaemonSet指定的pod名字】 标签的 Pod 在运行。
而检查的结果，可能有这三种情况：
1. 没有这种 Pod，那么就意味着要在这个 Node 上创建这样一个 Pod；
2. 有这种 Pod，但是数量大于 1，那就说明要把多余的 Pod 从这个 Node 上删除掉；
3. 正好只有一个这种 Pod，那说明这个节点是正常的。  

删除节点（Node）上多余的 Pod 直接调用 Kubernetes API 就可以了。
在指定的 Node 上创建新 Pod 用 nodeSelector（新版本使用nodeAffinity，nodeSelector会被废弃），选择Node 的名字即可   

## DaemonSet如何管理版本 ##    
DaemonSet 和 Deployment 一样，也有 DESIRED、CURRENT 等多个状态字段。这也就意味着，DaemonSet 可以像 Deployment 那样，进行版本管理。    
DaemonSet 跟 Deployment 其实非常相似，只不过是没有 replicas 字段；   
Deployment 管理这些版本，靠的是：“一个版本对应一个 ReplicaSet 对象”。可是，DaemonSet 控制器操作的直接
就是 Pod，不可能有 ReplicaSet 这样的对象参与其中。

Kubernetes v1.7 之后添加了一个 API 对象，名叫ControllerRevision，专门用来记录某种Controller 对象的版本。  
在 Kubernetes 项目里，ControllerRevision 其实是一个通用的版本管理对象。  
ControllerRevision 对象，实际上是在 Data 字段保存了该版本对应的完整的DaemonSet 的 API 对象。  
并且，在 Annotation 字段保存了创建这个对象所使用的 kubectl命令。  

    $ kubectl describe controllerrevision fluentd-elasticsearch-64dc6799c9 -n kube-system
    Name: fluentd-elasticsearch-64dc6799c9
    Namespace: kube-system
    Labels: controller-revision-hash=2087235575
             name=fluentd-elasticsearch
    Annotations: deprecated.daemonset.template.generation=2
                  kubernetes.io/change-cause=kubectl set image ds/fluentd-elasticsearch fluentd-elas
    API Version: apps/v1
    Data:
     Spec:
        Template:
           $ Patch: replace
           Metadata:
              Creation Timestamp: <nil>
              Labels:
                  Name: fluentd-elasticsearch
           Spec:
              Containers:
                 Image: k8s.gcr.io/fluentd-elasticsearch:v2.2.0
                 Image Pull Policy: IfNotPresent
                 Name: fluentd-elasticsearch
    ...
    Revision: 2
    Events: <none>
    
这个 ControllerRevision 对象，实际上是在 Data 字段保存了该版本对应的完整的
DaemonSet 的 API 对象。并且，在 Annotation 字段保存了创建这个对象所使用的 kubectl
命令。

可以使用如下命令回滚：  
$ kubectl rollout undo daemonset fluentd-elasticsearch --to-revision=1 -n kube-system  
daemonset.extensions/fluentd-elasticsearch rolled back  

这个 kubectl rollout undo 操作，实际上相当于读取到了 Revision=1 的 ControllerRevision
对象保存的 Data 字段。而这个 Data 字段里保存的信息，就是 Revision=1 时这个
DaemonSet 的完整 API 对象。


现在 DaemonSet Controller 就可以使用这个历史 API 对象，对现有的 DaemonSet 做
一次 PATCH 操作（等价于执行一次 kubectl apply -f “旧的 DaemonSet 对象”），从而把
这个 DaemonSet“更新”到一个旧版本。
这也是为什么，在执行完这次回滚完成后，你会发现，DaemonSet 的 Revision 并不会从
Revision=2 退回到 1，而是会增加成 Revision=3。这是因为，一个新的 ControllerRevision
被创建了出来  


 
总结：  
相比于 Deployment，**DaemonSet 只管理 Pod 对象，然后通过 nodeAffinity 和 Toleration
这两个调度器的小功能，保证了每个节点上有且只有一个 Pod**。  
与此同时，DaemonSet 使用 **ControllerRevision**，来保存和管理自己对应的“版本”。  




**问题：**  
在 Kubernetes v1.11 之前，DaemonSet 所管理的 Pod 的调度过程，实际上
都是由 DaemonSet Controller 自己而不是由调度器完成的。你能说出这其中有哪些原因吗？
1. 在上一讲中，有一点我还是没想通，为何MySQL的数据复制操作必须要用sidecar容器来
处理，而不用Mysql主容器来一并解决，你当时提到说是因为容器是单进程模型。如果取消si
decar容器，把数据复制操作和启动MySQL服务这两个操作一并写到MySQL主容器的sh -c命
令中，这样算不算一个进程呢？
2. StatefulSet的容器启动有先后顺序，那么当序号较小的容器由于某种原因需要重启时，会
不会先把序号较大的容器KILL掉，再按照它们本来的顺序重新启动一次？
3. 在这一讲中，你提到了滚动升级时StatefulSet控制新旧副本数的spec.updateStrategy.rol
lingUpdate.Partition字段。假设我现在已经用这个功能已经完成了灰度发布，需要把所有P
OD都更新到最新版本，那么是不是Edit或者Patch这个StatefulSet，把spec.updateStrateg  
y.rollingUpdate.Partition字段修改成总的POD数即可？
4. 在这一讲中提到ControllerRevision这个API对象，K8S会对StatefulSet或DaemonSet的
每一次滚动升级都会产生一个新的ControllerRevision对象，还是每个StatefulSet或Daemo
nSet对象只会有一个关联的ControllerRevision对象，不同的revision记录到同一个Controll
erRevision对象中？
5. Deployment里可以控制保留历史ReplicaSet的数量，那么ControllerRevision这个API对
象能不能做到保留指定数量的版本记录？  



