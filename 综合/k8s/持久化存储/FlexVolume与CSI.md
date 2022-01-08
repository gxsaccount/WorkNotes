在 Kubernetes 中，存储插件的开发有两种方式：FlexVolume 和 CSI  
# Flexvolume 的原理和使用方法 #   
对于一个 FlexVolume 类型的 PV 来说，它的 YAML 文件如下所示：  

apiVersion: v1
kind: PersistentVolume  
metadata:
 name: pv-flex-nfs
spec:
 capacity:
    storage: 10Gi
 accessModes:
    - ReadWriteMany
 flexVolume:
   driver: "k8s/nfs"
   fsType: "nfs"
   options:
     server: "10.10.0.25" # 改成你自己的 NFS 服务器地址
     share: "export"  

这个 PV 定义的 Volume 类型是 flexVolume。并且，我们指定了这个 Volume 的driver 叫作 k8s/nfs。  
而 Volume 的 options 字段，则是一个自定义字段。也就是说，它的类型，其实是
map[string]string。所以，你可以在这一部分自由地加上你想要定义的参数。  
options 字段指定了 NFS 服务器的地址（server: “10.10.0.25”），以及
NFS 共享目录的名字（share: “export”）。  

可以使用https://github.com/ehough/docker-nfs-server部署一个个试验用的 NFS 服务器  
的一个 PV 被创建后，一旦和某个 PVC 绑定起来，进会进入两阶段处理流程，即“Attach 阶段”和“Mount 阶段”  
而在具体的控制循环中，这两个操作实际上调用的，正是 Kubernetes 的 pkg/volume 目录下
的存储插件（**Volume Plugin**）。在我们这个例子里，就是 pkg/volume/flexvolume 这个目录
里的代码。  

## 缺点 ##  
当然，在前面文章中我也提到过，像 NFS 这样的文件系统存储，并不需要在宿主机上挂载磁盘
或者块设备。所以，我们也就不需要实现 attach 和 dettach 操作了。
不过，像这样的 FlexVolume 实现方式，虽然简单，但局限性却很大。
比如，跟 Kubernetes 内置的 NFS 插件类似，这个 NFS FlexVolume 插件，也不能支持
Dynamic Provisioning（即：为每个 PVC 自动创建 PV 和对应的 Volume）。除非你再为它编
写一个专门的 External Provisioner。
再比如，我的插件在执行 mount 操作的时候，可能会生成一些挂载信息。这些信息，在后面执
行 unmount 操作的时候会被用到。可是，在上述 FlexVolume 的实现里，你没办法把这些信
息保存在一个变量里，等到 unmount 的时候直接使用。


这个原因也很容易理解：FlexVolume 每一次对插件可执行文件的调用，都是一次完全独立的操
作。所以，我们只能把这些信息写在一个宿主机上的临时文件里，等到 unmount 的时候再去读
取。  


# CSI #  
