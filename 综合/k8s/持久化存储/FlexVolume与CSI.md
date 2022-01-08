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

![368ff429363523f2d82c404ce28f0c4](https://user-images.githubusercontent.com/20179983/148630576-041fd38b-061b-4cf7-9073-4be8d0a19dcc.png)
可以看到，在上述体系下，无论是 FlexVolume，还是 Kubernetes 内置的其他存储插件，它们
实际上担任的角色，仅仅是 Volume 管理中的“Attach 阶段”和“Mount 阶段”的具体执行
者。而像 Dynamic Provisioning 这样的功能，就不是存储插件的责任，而是 Kubernetes 本身
存储管理功能的一部分。  

# CSI #  

CSI 插件体系的设计思想，就是把这个 Provision 阶段，以及 Kubernetes 里的一部
分存储管理功能，从主干代码里剥离出来，做成了几个单独的组件。这些组件会通过 Watch
API 监听 Kubernetes 里与存储相关的事件变化，比如 PVC 的创建，来执行具体的存储管理动
作。
而这些管理动作，比如“Attach 阶段”和“Mount 阶段”的具体操作，实际上就是通过调用
CSI 插件来完成的。  
![ba4e9ca13787cba25b3959d9028a4d8](https://user-images.githubusercontent.com/20179983/148631178-b863c727-18ac-4e0b-a560-226bfed0d9e8.png)


这套存储插件体系多了三个独立的外部组件（External Components），即：
Driver Registrar、External Provisioner 和 External Attacher，对应的正是从 Kubernetes 项
目里面剥离出来的那部分存储管理功能。  

而图中最右侧的部分，就是需要我们编写代码来实现的 CSI 插件。一个 CSI 插件只有一个二进
制文件，但它会以 gRPC 的方式对外提供三个服务（gRPC Service），分别叫作：CSI
Identity、CSI Controller 和 CSI Node。  

## External Components ##  
### Driver Registrar ###  
Driver Registrar 组件，负责将插件注册到 kubelet 里面（这可以类比为，将可执行文件
放在插件目录下）。而在具体实现上，Driver Registrar 需要请求 CSI 插件的 Identity 服务来
获取插件信息  
  
### External Provisioner ###  
负责的正是 Provision 阶段。在具体实现上，External
Provisioner 监听（Watch）了 APIServer 里的 PVC 对象。当一个 PVC 被创建时，它就会调用
CSI Controller 的 CreateVolume 方法，为你创建对应 PV。
此外，如果你使用的存储是公有云提供的磁盘（或者块设备）的话，这一步就需要调用公有云
（或者块设备服务）的 API 来创建这个 PV 所描述的磁盘（或者块设备）了。
不过，由于 CSI 插件是独立于 Kubernetes 之外的，所以在 CSI 的 API 里不会直接使用
Kubernetes 定义的 PV 类型，而是会自己定义一个单独的 Volume 类型。   

### External Attacher ###  

External Attacher 组件，负责的正是“Attach 阶段”。在具体实现上，它监听了
APIServer 里 VolumeAttachment 对象的变化。VolumeAttachment 对象是 Kubernetes 确
认一个 Volume 可以进入“Attach 阶段”的重要标志，  
一旦出现了 VolumeAttachment 对象，External Attacher 就会调用 CSI Controller 服务的
ControllerPublish 方法，完成它所对应的 Volume 的 Attach 阶段。  

而 Volume 的“Mount 阶段”，并不属于 External Components 的职责。当 kubelet 的
VolumeManagerReconciler 控制循环检查到它需要执行 Mount 操作的时候，会通过
pkg/volume/csi 包，直接调用 CSI Node 服务完成 Volume 的“Mount 阶段”。
在实际使用 CSI 插件的时候，我们会将这三个 External Components 作为 sidecar 容器和 CSI
插件放置在同一个 Pod 中。由于 External Components 对 CSI 插件的调用非常频繁，所以这
种 sidecar 的部署方式非常高效。  


 ## CSI 插件服务  ##   
 ### CSI Identity ###  
 CSI 插件的 CSI Identity 服务，负责对外暴露这个插件本身的信息，如下所示：  
   
   service Identity {
      // return the version and name of the plugin
      rpc GetPluginInfo(GetPluginInfoRequest)
      returns (GetPluginInfoResponse) {}
      // reports whether the plugin has the ability of serving the Controller interface
      rpc GetPluginCapabilities(GetPluginCapabilitiesRequest)
      returns (GetPluginCapabilitiesResponse) {}
      // called by the CO just to check whether the plugin is running or not
      rpc Probe (ProbeRequest)
      returns (ProbeResponse) {}
  }  



### CSI Controller ###  
CSI Controller 服务，定义的则是对 CSI Volume（对应 Kubernetes 里的 PV）的管理接
口，比如：创建和删除 CSI Volume、对 CSI Volume 进行 Attach/Dettach（在 CSI 里，这个
操作被叫作 Publish/Unpublish），以及对 CSI Volume 进行 Snapshot 等，它们的接口定义
如下所示：   

   service Controller {
       // provisions a volume
       rpc CreateVolume (CreateVolumeRequest)
       returns (CreateVolumeResponse) {}

       // deletes a previously provisioned volume
       rpc DeleteVolume (DeleteVolumeRequest)
       returns (DeleteVolumeResponse) {}

       // make a volume available on some required node
       rpc ControllerPublishVolume (ControllerPublishVolumeRequest)
       returns (ControllerPublishVolumeResponse) {}

       // make a volume un-available on some required node
       rpc ControllerUnpublishVolume (ControllerUnpublishVolumeRequest)
       returns (ControllerUnpublishVolumeResponse) {}

       ...

       // make a snapshot
       rpc CreateSnapshot (CreateSnapshotRequest)
       returns (CreateSnapshotResponse) {}

       // Delete a given snapshot
       rpc DeleteSnapshot (DeleteSnapshotRequest)
       returns (DeleteSnapshotResponse) {}

       ...
   }
   
   
   CSI Controller 服务里定义的这些操作有个共同特点，那就是它们都无需在宿主机上
进行，而是属于 Kubernetes 里 Volume Controller 的逻辑，也就是属于 Master 节点的一部
分   

CSI Controller 服务的实际调用者，并不是
Kubernetes（即：通过 pkg/volume/csi 发起 CSI 请求），而是 External Provisioner 和
External Attacher。这两个 External Components，分别通过监听 PVC 和
VolumeAttachement 对象，来跟 Kubernetes 进行协作。   


 ### CSI Volume ###   
 CSI Volume 需要在宿主机上执行的操作，都定义在了 CSI Node 服务里面，如下所示：  
 
    service Node {
    // temporarily mount the volume to a staging path
    rpc NodeStageVolume (NodeStageVolumeRequest)
    returns (NodeStageVolumeResponse) {}

    // unmount the volume from staging path
    rpc NodeUnstageVolume (NodeUnstageVolumeRequest)
    returns (NodeUnstageVolumeResponse) {}

    // mount the volume from staging to target path
    rpc NodePublishVolume (NodePublishVolumeRequest)
    returns (NodePublishVolumeResponse) {}

    // unmount the volume from staging path
    rpc NodeUnpublishVolume (NodeUnpublishVolumeRequest)
    returns (NodeUnpublishVolumeResponse) {}

    // stats for the volume
    rpc NodeGetVolumeStats (NodeGetVolumeStatsRequest)
    returns (NodeGetVolumeStatsResponse) {}

    ...

    // Similar to NodeGetId
    rpc NodeGetInfo (NodeGetInfoRequest)
    returns (NodeGetInfoResponse) {}
   }


# 总结 #  

  **相比于 FlexVolume，CSI 的设计思想，把插件的职责从“两阶段处理”，扩展成了
Provision、Attach 和 Mount 三个阶段。其中，Provision 等价于“创建磁盘”，Attach 等价
于“挂载磁盘到虚拟机”，Mount 等价于“将该磁盘格式化后，挂载在 Volume 的宿主机目录
上”。**   
attach和mount和pv中会有所不同  
当 AttachDetachController 需要进行“Attach”操作时（“Attach 阶段”），它实际上会
执行到 pkg/volume/csi 目录中，创建一个 VolumeAttachment 对象，从而触发 External
Attacher 调用 CSI Controller 服务的 ControllerPublishVolume 方法。
当 VolumeManagerReconciler 需要进行“Mount”操作时（“Mount 阶段”），它实际
上也会执行到 pkg/volume/csi 目录中，直接向 CSI Node 服务发起调用
NodePublishVolume 方法的请求。
