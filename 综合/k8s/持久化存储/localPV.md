# Local Persistent Volume #   
定义：直接使用宿主机上的本地磁盘目录，而不依赖于远程存储服务，来提供“持久化”的容器 Volume。  
好处：，由于这个 Volume 直接使用的是本地磁盘，尤其是 SSD 盘，它的读写性能相比于大多数远程存储来说，要好得多。  
缺点：
需要明确的是，Local Persistent Volume 并不适用于所有应用。事实上，它的适用
范围非常固定，比如：高优先级的系统应用，需要在多个不同节点上存储数据，并且对 I/O 较
为敏感。典型的应用包括：分布式数据存储比如 MongoDB、Cassandra 等，分布式文件系统
比如 GlusterFS、Ceph 等，以及需要在本地磁盘上进行大量数据缓存的分布式应用。  
其次，相比于正常的 PV，一旦这些节点宕机且不能恢复时，Local Persistent Volume 的数据
就可能丢失。这就要求使用 Local Persistent Volume 的应用必须具备数据备份和恢复的能力，
允许你把这些数据定时备份在其他位置。  

## 为什么不要用hostpath来抽象Local PV ##  
绝不应该把一个宿主机上的目录当作 PV 使用。这是因为，这种本地目录的存储行为
完全不可控，它所在的磁盘随时都可能被应用写满，甚至造成整个宿主机宕机。而且，不同的本
地目录之间也缺乏哪怕最基础的 I/O 隔离机制  

所以，一个 Local Persistent Volume 对应的存储介质，一定是一块额外挂载在宿主机的磁盘或
者块设备（“额外”的意思是，它不应该是宿主机根目录所使用的主硬盘）。这个原则，我们可
以称为“**一个 PV 一块盘**”。  

## 调度器如何保证 Pod 始终能被正确地调度到它所请求的 Local Persistent Volume 所在的节点上 ##  

对于常规的 PV 来说，Kubernetes 都是先调度 Pod 到某个节点
上，然后，再通过“两阶段处理”来“持久化”这台机器上的 Volume 目录，进而完成
Volume 目录与容器的绑定挂载。  
对于 Local PV 来说，节点上可供使用的磁盘（或者块设备），必须是运维人员提前准备
好的。它们在不同节点上的挂载情况可以完全不同，甚至有的节点可以没这种磁盘。  
所以，这时候，调度器就必须能够知道所有节点与 Local Persistent Volume 对应的磁盘的关联
关系，然后根据这个信息来调度 Pod。  
这个原则，我们可以称为“在调度的时候考虑 Volume 分布”。在 Kubernetes 的调度器里，
有一个叫作 **VolumeBindingChecker** 的过滤条件专门负责这个事情。    

基于上述讲述，**在开始使用 Local Persistent Volume 之前，你首先需要在集群里配置好磁盘或者块设备**在公有云上，这个操作等同于给虚拟机额外挂载一个磁盘，比如 GCE 的 Local SSD
类型的磁盘就是一个典型例子。  

    apiVersion: v1
    kind: PersistentVolume
    metadata:
     name: example-pv
    spec:
     capacity:
      storage: 5Gi
     volumeMode: Filesystem
     accessModes:
     - ReadWriteOnce
     persistentVolumeReclaimPolicy: Delete
     storageClassName: local-storage  //StorageClass的name
     local:
      path: /mnt/disks/vol1   // PV 对应的本地磁盘的路径  
     nodeAffinity:  
       required:
         nodeSelectorTerms:
         - matchExpressions:
           - key: kubernetes.io/hostname
             operator: In
             values:
             - node-1    //必须运行在 node-1 上。  
             
             
   path 字段，指定的正是这个 PV 对应的本地磁盘的路径，即：/mnt/disks/vol1。  
    nodeAffinity 字段指定 node-1 这个节点的名字，指定运行在 node-1 上。  
    这样，调度
器在调度 Pod 的时候，就能够知道一个 PV 与节点的对应关系，从而做出正确的选择。  

StorageClass：  

    kind: StorageClass
    apiVersion: storage.k8s.io/v1
    metadata:
     name: local-storage
    provisioner: kubernetes.io/no-provisioner  //local目前不支持Dynamic Provisioning
    volumeBindingMode: WaitForFirstConsumer   //延迟绑定
    
Local Persistent Volume 目前尚不支持 Dynamic Provisioning，所以它没办法在用户创建 PVC 的时候，就自动创建出对应的 PV。  
volumeBindingMode=WaitForFirstConsumer：延迟绑定  


### 延迟绑定 ###  
当你提交了 PV 和 PVC 的 YAML 文件之后，Kubernetes 就会根据它们俩的属性，
以及它们指定的 StorageClass 来进行绑定。只有绑定成功后，Pod 才能通过声明这个 PVC 来
使用对应的 PV。  

但是local volume无法通过上述流程  
原因：  
现在你有一个 Pod，它声明使用的 PVC 叫作 pvc-1。并且，我们规定，这个 Pod 只能运行在 **node-2** 上。  
而在 Kubernetes 集群中，有两个属性（比如：大小、读写权限）相同的 Local 类型的 PV。  
第一个 PV 的名字叫作 pv-1，它对应的磁盘所在的节点是 node-1。  
而第二个 PV 的名字叫作 pv-2，它对应的磁盘所在的节点是 node-2  
现在，Kubernetes 的 Volume 控制循环里，首先检查到了 pvc-1 和 pv-1 的属性是匹配的，于是就将它们俩绑定在一起。  
你用 kubectl create 创建了这个 Pod。  
调度器看到，这个 Pod 所声明的 pvc-1 已经绑定了 pv-1，而 pv-1 所在的节点是 node-1，根
据“**调度器必须在调度的时候考虑 Volume分布**”的原则，这个 Pod 自然会被调度到 node-1  
可是，我们前面已经规定过，这个 Pod 根本不允许运行在 node-1 上。所以。最后的结果就
是，这个 Pod 的调度必然会失败。（**核心：pod和pv的node-affinity冲突**）  

所以要推迟绑定，**具体推迟到调度的时候**。  
，StorageClass 里的 volumeBindingMode=WaitForFirstConsumer 的含义，就是告
诉 Kubernetes 里的 Volume 控制循环（“红娘”）：虽然你已经发现这个 StorageClass 关联
的 PVC 与 PV 可以绑定在一起，但请不要现在就执行绑定操作（即：设置 PVC 的
VolumeName 字段）。
而要等到第一个声明使用该 PVC 的 Pod 出现在调度器之后，**调度器再综合考虑所有的调度规
则，当然也包括每个 PV 所在的节点位置，来统一决定，这个 Pod 声明的 PVC，到底应该跟哪
个 PV 进行绑定**。  

在具体实现中，调度器实际上维护了一个与 Volume Controller 类似的控制循环，专门
负责为那些声明了“延迟绑定”的 PV 和 PVC 进行绑定工作。
通过这样的设计，这个额外的绑定操作，并不会拖慢调度器的性能。而当一个 Pod 的 PVC 尚未
完成绑定时，调度器也不会等待，而是会直接把这个 Pod 重新放回到待调度队列，等到下一个
调度周期再做处理。  

声明pvc时storageClassName是 local-storage，这样即可  
    kind: PersistentVolumeClaim
    apiVersion: v1
    metadata:
     name: example-local-claim
    spec:
     accessModes:
     - ReadWriteOnce
     resources:
     requests:
     storage: 5Gi
     storageClassName: local-storage
像 Kubernetes 这样构建出来的、基于本地存储的 Volume，完全可以提供容器持久
化存储的功能。所以，像 StatefulSet 这样的有状态编排工具，也完全可以通过声明 Local 类型
的 PV 和 PVC，来管理应用的存储状态。
需要注意的是，我们上面手动创建 PV 的方式，即 Static 的 PV 管理方式，在删除 PV 时需要按
如下流程执行操作：

    1. 删除使用这个 PV 的 Pod；
    2. 从宿主机移除本地磁盘（比如，umount 它）；
    3. 删除 PVC；
    4. 删除 PV。
如果不按照这个流程的话，这个 PV 的删除就会失败。
当然，由于上面这些创建 PV 和删除 PV 的操作比较繁琐，Kubernetes 其实提供了一个 Static
Provisioner 来帮助你管理这些 PV

比如，我们现在的所有磁盘，都挂载在宿主机的 /mnt/disks 目录下。
那么，当 Static Provisioner 启动后，它就会通过 DaemonSet，自动检查每个宿主机的
/mnt/disks 目录。然后，调用 Kubernetes API，为这些目录下面的每一个挂载，创建一个对
应的 PV 对象出来。  
这些自动创建的 PV，如下所示：  

      $ kubectl get pv
      NAME CAPACITY ACCESSMODES RECLAIMPOLICY STATUS CLAIM STORAGECLASS
      local-pv-ce05be60 1024220Ki RWO Delete Available local-storag
      $ kubectl describe pv local-pv-ce05be60 
      Name: local-pv-ce05be60
      ...
      StorageClass: local-storage
      Status: Available
      Claim: 
      Reclaim Policy: Delete
      Access Modes: RWO
      Capacity: 1024220Ki
      NodeAffinity:
       Required Terms:
       Term 0: kubernetes.io/hostname in [node-1]
      Message: 
      Source:
       Type: LocalVolume (a persistent volume backed by local storage on a node)
       Path: /mnt/disks/vol1
       
  这个 PV 里的各种定义，比如 StorageClass 的名字、本地磁盘挂载点的位置，都可以通过
provisioner 的配置文件（https://github.com/kubernetes-retired/external-storage/tree/master/local-volume/helm）指定。当然，provisioner 也会负责前面提到的 PV 的删除工作。
而这个 provisioner 本身，其实也是一个我们前面提到过的External Provisioner（https://github.com/kubernetes-retired/external-storage/tree/master/local-volume），它的部署方
法，在对应的文档（https://github.com/kubernetes-retired/external-storage/tree/master/local-volume#option-1-using-the-local-volume-static-provisioner）里有详细描述。  
