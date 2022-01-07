前置内容见有状态的控制器StatefulSet.md    

PV 描述的，是持久化存储数据卷  
PVC 描述的，则是 Pod 所希望使用的持久化存储的属性。比如，Volume 存储的大小、可读写权限等等。  

    PV：  
    apiVersion: v1
    kind: PersistentVolume
    metadata:
     name: nfs
    spec:
     storageClassName: manual
     capacity:
      storage: 1Gi
     accessModes:
      - ReadWriteMany
     nfs:
      server: 10.244.1.4
      path: "/"

    PVC：  
    apiVersion: v1
    kind: PersistentVolumeClaim
    metadata:
     name: nfs
    spec:
     accessModes:
      - ReadWriteMany
     storageClassName: manual
     resources:
      requests:
        storage: 1Gi  
        
用户创建的 PVC 要真正被容器使用起来，就必须先和某个符合条件的 PV 进行绑定    
绑定需要满足如下条件  
第一个条件，当然是 PV 和 PVC 的 spec 字段。比如，PV 的存储（storage）大小，就必须
满足 PVC 的要求。  
而第二个条件，则是 PV 和 PVC 的 storageClassName 字段必须一样。   
  
    pod如何使用pvc:  
    apiVersion: v1
    kind: Pod
    metadata:
     labels:
      role: web-frontend
    spec:
     containers:
     - name: web
      image: nginx
      ports:
         - name: web
         containerPort: 80
     volumeMounts:
        - name: nfs
          mountPath: "/usr/share/nginx/html"
     volumes:
     - name: nfs
       persistentVolumeClaim:
        claimName: nfs
  可以看到，Pod 需要做的，就是在 volumes 字段里声明自己要使用的 PVC 名字。接下来，等
这个 Pod 创建之后，kubelet 就会把这个 PVC 所对应的 PV，也就是一个 NFS 类型的
Volume，挂载在这个 Pod 容器内的目录上。  

PVC 可以理解为持久化存储的“接口”，它提供了对某种持久化存储的描述，但不提供具体的
实现；而这个持久化存储的实现部分则由 PV 负责完成。  
**这样做的好处是，作为应用开发者，我们只需要跟 PVC 这个“接口”打交道，而不必关心具体
的实现是 NFS 还是 Ceph。**  

# Volume Controller # 
Kubernetes 中，实际上存在着一个专门处理持久化存储的控制器，叫作 Volume Controller  
创建 Pod 的时候，系统里并没有合适的 PV 跟它定义的 PVC 绑定，也这时候，Pod 的启动就会报错。
但运维人员创建了一个对应的 PV。这时候ubernetes 能够通过Volume Controller完成 PVC 和 PV 的绑定操作，从而启动 Pod。  
PV 和 PVC 的“红娘”的角色。它的名字叫作 **PersistentVolumeController**    

## PersistentVolumeController工作原理 ##  
PersistentVolumeController 会不断地查看当前每一个 PVC，是不是已经处于 Bound（已绑
定）状态。如果不是，那它就会遍历所有的、可用的 PV，并尝试将其与这个“单身”的 PVC
进行绑定。这样，Kubernetes 就可以保证用户提交的每一个 PVC，只要有合适的 PV 出现，它
就能够很快进入绑定状态，从而结束“单身”之旅。
而所谓将一个 PV 与 PVC 进行“绑定”，其实就是将这个 PV 对象的名字，填在了 PVC 对象的
spec.volumeName 字段上。所以，接下来 Kubernetes 只要获取到这个 PVC 对象，就一定能
够找到它所绑定的 PV。  

#  PV 对象原理 #  
容器的 Volume，其实就是将一个宿主机上的目录，跟一个容器里的目录绑定挂载在了一起。  
**所谓的“持久化 Volume”，指的就是这个宿主机上的目录，具备“持久性”。**    
即：这个目录
里面的内容，既不会因为容器的删除而被清理掉，也不会跟当前的宿主机绑定。这样，当容器被
重启或者在其他节点上重建出来之后，它仍然能够通过挂载这个 Volume，访问到这些内容。  

大多数情况下，持久化 Volume 的实现，往往依赖于一个远程存储服务，比如：远程文
件存储（比如，NFS、GlusterFS）、远程块存储（比如，公有云提供的远程磁盘）等等。  

当一个 Pod 调度到一个节点上之后，kubelet 就要负责为这个 Pod 创建它的 Volume 目录。  
默认情况下，kubelet 为 Volume 创建的目录是如下所示的一个宿主机上的路径：  
    
    /var/lib/kubelet/pods/<Pod 的 ID>/volumes/kubernetes.io~<Volume 类型 >/<Volume 名字 >  

### GCE 提供的远程磁盘服务 ###
如果你的 Volume 类型是远程块存储，比如 Google Cloud 的 Persistent Disk（GCE 提供的远
程磁盘服务），那么 kubelet 就需要先调用 Goolge Cloud 的 API，将它所提供的 Persistent
Disk 挂载到 Pod 所在的宿主机上。   

相当于执行  

    gcloud compute instances attach-disk < 虚拟机名字 > --disk < 远程磁盘名字 >  
    
这一步为虚拟机挂载远程磁盘的操作，对应的正是“两阶段处理”的第一阶段。在 Kubernetes
中，我们把这个阶段称为 **Attach**。   

Attach 阶段完成后，为了能够使用这个远程磁盘，kubelet 还要进行第二个操作，即：格式化
这个磁盘设备，然后将它挂载到宿主机指定的挂载点上。  
相当于执行    

    # 通过 lsblk 命令获取磁盘设备 ID
    $ sudo lsblk
    # 格式化成 ext4 格式
    $ sudo mkfs.ext4 -m 0 -F -E lazy_itable_init=0,lazy_journal_init=0,discard /dev/< 磁盘设备 ID>
    # 挂载到挂载点
    $ sudo mkdir -p /var/lib/kubelet/pods/<Pod 的 ID>/volumes/kubernetes.io~<Volume 类型 >/<Volume 名

这个将磁盘设备格式化并挂载到 Volume 宿主机目录的操作，对应的正是“两阶段处理”的第
二个阶段，我们一般称为：**Mount**。  

Mount 阶段完成后，这个 Volume 的宿主机目录就是一个“持久化”的目录了，容器在它里面
写入的内容，会保存在 Google Cloud 的远程磁盘中。  

### 远程文件存储/NFS ###
在这种情况下，kubelet 可以跳过“第一阶段”（Attach）的操作，这是因为一般来说，远
程文件存储并没有一个“存储设备”需要挂载在宿主机上。
所以，kubelet 会直接从“第二阶段”（Mount）开始准备宿主机上的 Volume 目录。  
在这一步，kubelet 需要作为 client，将远端 NFS 服务器的目录（比如：“/”目录），挂载到
Volume 的宿主机目录上，即相当于执行如下所示的命令：  

    $ mount -t nfs <NFS 服务器地址 >:/ /var/lib/kubelet/pods/<Pod 的 ID>/volumes/kubernetes.io~<Volum  
 
通过这个挂载操作，Volume 的宿主机目录就成为了一个远程 NFS 目录的挂载点，后面你在这
个目录里写入的所有文件，都会被保存在远程 NFS 服务器上。所以，我们也就完成了对这个
Volume 宿主机目录的“持久化”。  

## Attach/Mount的区分 ##  

在具体的 Volume 插件的实现接口上，Kubernetes 分别给这两个阶段提供了两种
不同的参数列表：
对于“第一阶段”（Attach），Kubernetes 提供的可用参数是 nodeName，即宿主机的名
字。
而对于“第二阶段”（Mount），Kubernetes 提供的可用参数是 dir，即 Volume 的宿主
机目录。  

经过了“两阶段处理”，我们就得到了一个“持久化”的 Volume 宿主机目录。所以，接下
来，kubelet 只要把这个 Volume 目录通过 CRI 里的 Mounts 参数，传递给 Docker，然后就
可以为 Pod 里的容器挂载这个“持久化”的 Volume 了。其实，这一步相当于执行了如下所示
的命令：  

    $ docker run -v /var/lib/kubelet/pods/<Pod 的 ID>/volumes/kubernetes.io~<Volume 类型 >/<Volume 名  

对应地，在删除一个 PV 的时候，Kubernetes 也需要 Unmount 和
Dettach 两个阶段来处理。  

“**第一阶段**”的 Attach（以及 Dettach）操作，是由 Volume Controller 负责维护的，
这个控制循环的名字叫作：AttachDetachController。而它的作用，就是不断地检查每一个
Pod 对应的 PV，和这个 Pod 所在宿主机之间挂载情况。从而决定，是否需要对这个 PV 进行
Attach（或者 Dettach）操作。  

需要注意，作为一个 Kubernetes 内置的控制器，Volume Controller 自然是 kubecontroller-manager 的一部分。所以，AttachDetachController 也一定是运行在 Master 节
点上的。当然，Attach 操作只需要调用公有云或者具体存储项目的 API，并不需要在具体的宿
主机上执行操作，  

“**第二阶段**”的 Mount（以及 Unmount）操作，必须发生在 Pod 对应的宿主机上，所以它
必须是 kubelet 组件的一部分。这个控制循环的名字，叫作：**VolumeManagerReconciler**，
它运行起来之后，是一个独立于 kubelet 主循环的 Goroutine。
通过这样**将 Volume 的处理同 kubelet 的主循环解耦，Kubernetes 就避免了这些耗时的远程
挂载操作拖慢 kubelet 的主控制循环，进而导致 Pod 的创建效率大幅下降的问题**。  
**实际上，kubelet 的一个主要设计原则，就是它的主控制循环绝对不可以被 block。**


# StorageClass #  

一个大规模的 Kubernetes 集群里很可能有成千上万个 PVC，运维人员难以创建和维护新的PVC  
Kubernetes 为我们提供了一套可以自动创建 PV 的机制，即：**Dynamic Provisioning**。  
相比之下，前面人工管理 PV 的方式就叫作 **Static Provisioning**。  
Dynamic Provisioning 机制工作的核心，在于一个名叫 StorageClass 的 API 对象。
而 **StorageClass 对象的作用，其实就是创建 PV 的模板（更具PVC）**。  
具体地说，StorageClass 对象会定义如下两个部分内容：  
第一，PV 的属性。比如，存储类型、Volume 的大小等等。  
第二，创建这种 PV 需要用到的存储插件。比如，Ceph 等等。  
有了这样两个信息之后，Kubernetes 就能够根据用户提交的 PVC，找到一个对应的
StorageClass 了。然后，Kubernetes 就会调用该 StorageClass 声明的存储插件，创建出需要
的 PV。  
举个例子，假如我们的 Volume 的类型是 GCE 的 Persistent Disk 的话，运维人员就需要定义
一个如下所示的 StorageClass：  
    apiVersion: storage.k8s.io/v1
    kind: StorageClass
    metadata:
     name: block-service
    provisioner: kubernetes.io/gce-pd
    parameters:
     type: pd-ssd
在这个 YAML 文件里，我们定义了一个名叫 block-service 的 StorageClass。
这个 StorageClass 的 provisioner 字段的值是：kubernetes.io/gce-pd，这正是
Kubernetes 内置的 GCE PD 存储插件的名字。
而这个 StorageClass 的 parameters 字段，就是 PV 的参数。比如：上面例子里的 type=pdssd，指的是这个 PV 的类型是“SSD 格式的 GCE 远程磁盘”。   


使用Rook 存储服务的话，你的 StorageClass 需要使用如下所示的 YAML 文件来定义：  
    apiVersion: ceph.rook.io/v1beta1
    kind: Pool
    metadata:
     name: replicapool
     namespace: rook-ceph
    spec:
     replicated:
      size: 3
    ---
    apiVersion: storage.k8s.io/v1
    kind: StorageClass
    metadata:
     name: block-service
    provisioner: ceph.rook.io/block
    parameters:
     pool: replicapool
     #The value of "clusterNamespace" MUST be the same as the one in which your rook cluster exist
     clusterNamespace: rook-ceph
 
  
  
  有了 StorageClass 的 YAML 文件之后，运维人员就可以在 Kubernetes 里创建这个
StorageClass 了：  

    $ kubectl create -f sc.yaml  
    
作为应用开发者，我们只需要在 PVC 里指定要使用的 StorageClass 名字即可，如下
所示  

    apiVersion: v1
    kind: PersistentVolumeClaim
    metadata:
     name: claim1
    spec:
     accessModes:
      - ReadWriteOnce
     storageClassName: block-service
     resources:
      requests:
        storage: 30Gi  
     
  我们在这个 PVC 里添加了一个叫作 storageClassName 的字段，用于指定该 PVC
所要使用的 StorageClass 的名字是：block-service。  


以 Google Cloud 为例。
当我们通过 kubectl create 创建上述 PVC 对象之后，Kubernetes 就会调用 Google Cloud 的
API，创建出一块 SSD 格式的 Persistent Disk。然后，再使用这个 Persistent Disk 的信息，自
动创建出一个对应的 PV 对象。  

有了 **Dynamic Provisioning** 机制，运维人员在 Kubernetes 集群里创建出了各种各样的
PV 模板。这时候，当开发人员提交了包含 StorageClass 字段的 PVC 之后，Kubernetes 就会
根据这个 StorageClass 创建出对应的 PV。  

## 定制化 Dynamic Provisioning ##
Kubernetes 的官方文档里已经列出了默认支持 Dynamic Provisioning 的内置存
储插件。而对于不在文档里的插件，比如 NFS，或者其他非内置存储插件，你其
实可以通过kubernetes-incubator/external-storage这个库来自己编写一个外部
插件完成这个工作。像我们之前部署的 Rook，已经内置了 external-storage 的
实现，所以 Rook 是完全支持 Dynamic Provisioning 特性的。   


如果你的集群已经开启了名叫 DefaultStorageClass 的 Admission Plugin，它就会为
PVC 和 PV 自动添加一个默认的 StorageClass；否则，PVC 的 storageClassName 的值就
是“”，这也意味着它只能够跟 storageClassName 也是“”的 PV 进行绑定。  

![c145403969a7aad348a665be16d12d3](https://user-images.githubusercontent.com/20179983/148523159-d0e52650-6792-4624-9d1c-df3a65fd7afa.png)
从图中我们可以看到，在这个体系中：
PVC 描述的，是 Pod 想要使用的持久化存储的属性，比如存储的大小、读写权限等。
PV 描述的，则是一个具体的 Volume 的属性，比如 Volume 的类型、挂载目录、远程存储
服务器地址等。  
而 StorageClass 的作用，则是充当 PV 的模板。并且，只有同属于一个 StorageClass 的
PV 和 PVC，才可以绑定在一起。
当然，StorageClass 的另一个重要作用，是指定 PV 的 Provisioner（存储插件）。这时候，如
果你的存储插件支持 Dynamic Provisioning 的话，Kubernetes 就可以自动为你创建 PV 了。  



