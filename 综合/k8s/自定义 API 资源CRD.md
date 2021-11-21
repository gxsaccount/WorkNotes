CRD 的全称是 Custom Resource Definition。顾名思义，它指的就是，允许用户在
Kubernetes 中添加一个跟 Pod、Node 类似的、新的 API 资源类型，即：自定义 API 资源。  

举个例子  
现在要为 Kubernetes 添加一个名叫 Network 的 API 资源类型  
它的作用是，一旦用户创建一个 Network 对象，那么 Kubernetes 就应该使用这个对象定义的
网络参数，调用真实的网络插件，比如 Neutron 项目，为用户创建一个真正的“网络”。这
样，将来用户创建的 Pod，就可以声明使用这个“网络”了。  

这个 Network 对象的 YAML 文件，名叫 example-network.yaml，是一个具体的“**自定义 API 资源**”实例，也叫 **CR（CustomResource）**。它的内容如下所示：    

      apiVersion: samplecrd.k8s.io/v1
      kind: Network
      metadata:
       name: example-network
      spec:
       cidr: "192.168.0.0/16"
       gateway: "192.168.0.1"  
       
       
 Kubernetes 如何知道这个 API（samplecrd.k8s.io/v1/network）的存在，需要编写一个 CRD 的 YAML 文件，它的名字叫作 network.yaml  
 
      apiVersion: apiextensions.k8s.io/v1beta1
      kind: CustomResourceDefinition
      metadata:
       name: networks.samplecrd.k8s.io
      spec:
       group: samplecrd.k8s.io
       version: v1
       names:
       kind: Network
       plural: networks
       scope: Namespaced
 
 可以看到，在这个 CRD 中，我指定了“group: samplecrd.k8s.io”“version:
v1”这样的 API 信息，也指定了这个 CR 的资源类型叫作 Network，复数（plural）是
networks。
然后，我还声明了它的 scope 是 Namespaced，即：我们定义的这个 Network 是一个属于
Namespace 的对象，类似于 Pod。  

接下来，我还需要让 Kubernetes“认识”这种 YAML 文件里描述的“网络”部分，比
如“cidr”（网段），“gateway”（网关）这些字段的含义。  

首先，我要在 GOPATH 下，创建一个结构如下的项目：  
        
        $ tree $GOPATH/src/github.com/<your-name>/k8s-controller-custom-resource
        .
        ├── controller.go
        ├── crd
        │ └── network.yaml
        ├── example
        │ └── example-network.yaml
        ├── main.go
        └── pkg
           └── apis
               └── samplecrd
                   ├── register.go
                   └── v1
                       ├── doc.go
                       ├── register.go
                       └── types.go  
其中，pkg/apis/samplecrd 就是 API 组的名字，v1 是版本，而 v1 下面的 types.go 文件里，
则定义了 Network 对象的完整描述。详细见https://github.com/resouer/k8s-controller-custom-resource   
然后，我在 pkg/apis/samplecrd 目录下创建了一个 register.go 文件，用来放置后面要用到的全局变量。  

      package samplecrd
      const (
       GroupName = "samplecrd.k8s.io"
        Version = "v1"
      )
接着，我需要在 pkg/apis/samplecrd 目录下添加一个 doc.go 文件（Golang 的文档源文
件）。这个文件里的内容如下所示：  
   
    // +k8s:deepcopy-gen=package
    // +groupName=samplecrd.k8s.io
    package v1  
    
在这个文件中，你会看到 **+<tag_name>[=value] 格式的注释，这就是 Kubernetes 进行代码
生成要用的 Annotation 风格的注释**。
其中，+k8s:deepcopy-gen=package 意思是，请为整个 v1 包里的所有类型定义自动生成
DeepCopy 方法；而+groupName=samplecrd.k8s.io，则定义了这个包对应的 API 组的名
字。
可以看到，这些定义在 doc.go 文件的注释，起到的是全局的代码生成控制的作用，所以也被称
为 **Global Tags**。  

接下来，我需要添加 types.go 文件。顾名思义，它的作用就是定义一个 Network 类型到底有
哪些字段（比如，spec 字段里的内容）。这个文件的主要内容如下所示：  

      package v1
      ...
      // +genclient
      // +genclient:noStatus
      // +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object
      // Network describes a Network resource
      type Network struct {
       // TypeMeta is the metadata for the resource, like kind and apiversion
       metav1.TypeMeta `json:",inline"`
       // ObjectMeta contains the metadata for the particular object, including
       // things like...
       // - name
       // - namespace
       // - self link
       // - labels
       // - ... etc ...
       metav1.ObjectMeta `json:"metadata,omitempty"`
       Spec networkspec `json:"spec"`
      }  
      // networkspec is the spec for a Network resource
      type networkspec struct {
       Cidr string `json:"cidr"`
       Gateway string `json:"gateway"`
      }
      // +k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object
      // NetworkList is a list of Network resources
      type NetworkList struct {
       metav1.TypeMeta `json:",inline"`
       metav1.ListMeta `json:"metadata"`
       Items []Network `json:"items"`
      }  
      
  在上面这部分代码里，你可以看到 Network 类型定义方法跟标准的 Kubernetes 对象一样，都
包括了 TypeMeta（API 元数据）和 ObjectMeta（对象元数据）字段。
而其中的 Spec 字段，就是需要我们自己定义的部分。所以，在 networkspec 里，我定义了
Cidr 和 Gateway 两个字段。其中，每个字段最后面的部分比如json:"cidr"，指的就是这个
字段被转换成 JSON 格式之后的名字，也就是 YAML 文件里的字段名字。  

此外，除了定义 Network 类型，你还需要定义一个 NetworkList 类型，用来描述一组
Network 对象应该包括哪些字段。之所以需要这样一个类型，是因为在 Kubernetes 中，获取
所有 X 对象的 List() 方法，返回值都是List 类型，而不是 X 类型的数组。这是不一样的。
同样地，在 Network 和 NetworkList 类型上，也有代码生成注释。
其中，+genclient 的意思是：请为下面这个 API 资源类型生成对应的 Client 代码  

而 +genclient:noStatus 的意思是：这个 API 资源类型定义里，没
有 Status 字段。否则，生成的 Client 就会自动带上 UpdateStatus 方法。  

+k8s:deepcopygen:interfaces=k8s.io/apimachinery/pkg/runtime.Object的注释。它的意思是，
请在生成 DeepCopy 的时候，实现 Kubernetes 提供的 runtime.Object 接口。否则，在某些
版本的 Kubernetes 里，你的这个类型定义会出现编译错误。这是一个固定的操作，记住即可。  

**k8s的代码生成语法：** 
https://blog.openshift.com/kubernetes-deep-dive-code-generation-customresources/


我需要再编写的一个 pkg/apis/samplecrd/v1/register.go 文件。  

在前面对 APIServer 工作原理的讲解中，我已经提到，registry 的作用就是注册一个类型
（Type）到 APIServer 中。而这个内层目录下的 register.go，就是这个注册流程要使用的代
码。它最主要的功能是，定义了如下所示的 addKnownTypes() 方法：   

      package v1
      ...
      // addKnownTypes adds our types to the API scheme by registering
      // Network and NetworkList
      func addKnownTypes(scheme *runtime.Scheme) error {
       scheme.AddKnownTypes(
       SchemeGroupVersion,
       &Network{},
       &NetworkList{},
       )
       // register the type in the scheme
       metav1.AddToGroupVersion(scheme, SchemeGroupVersion)
       return nil
      }  

有了这个方法，Kubernetes 就能够将 Network 和 NetworkList 类型加入到 APIServer 当中。  
像上面这种register.go 文件里的内容其实是非常固定的，你以后可以直接使用我提供的这部分
代码做模板，然后把其中的资源类型、GroupName 和 Version 替换成你自己的定义即可。
这样，Network 对象的定义工作就全部完成了。可以看到，它其实定义了两部分内容：
第一部分是，自定义资源类型的 API 描述，包括：组（Group）、版本（Version）、资源
类型（Resource）等。这相当于告诉了计算机：兔子是哺乳动物。
第二部分是，自定义资源类型的对象描述，包括：Spec、Status 等。这相当于告诉了计算
机：兔子有长耳朵和三瓣嘴。   

为上述代码生成 clientset、informer 和 lister  
这个代码生成工具名叫k8s.io/code-generator，使用方法如下所示：  
clientset 就是操作 Network 对象所需要使用的客
户端，而 informer 和 lister 这两个包的主要功能，   


思考题
在了解了 CRD 的定义方法之后，你是否已经在考虑使用 CRD（或者已经使用了 CRD）来描述
现实中的某种实体了呢？能否分享一下你的思路？（举个例子：某技术团队使用 CRD 描述
了“宿主机”，然后用 Kubernetes 部署了 Kubernetes）   

        # 代码生成的工作目录，也就是我们的项目路径
        $ ROOT_PACKAGE="github.com/resouer/k8s-controller-custom-resource"
        # API Group
        $ CUSTOM_RESOURCE_NAME="samplecrd"
        # API Version
        $ CUSTOM_RESOURCE_VERSION="v1"
        # 安装 k8s.io/code-generator
        $ go get -u k8s.io/code-generator/...
        $ cd $GOPATH/src/k8s.io/code-generator
        # 执行代码自动生成，其中 pkg/client 是生成目标目录，pkg/apis 是类型定义目录
        $ ./generate-groups.sh all "$ROOT_PACKAGE/pkg/client" "$ROOT_PACKAGE/pkg/apis" "$CUSTOM_RESOURCE

代码生成工作完成之后，我们再查看一下这个项目的目录结构：  

      $ tree
        .
        ├── controller.go
        ├── crd
        │ └── network.yaml
        ├── example
        │ └── example-network.yaml
        ├── main.go
        └── pkg
         ├── apis
         │     └── samplecrd
         │     ├── constants.go
         │     └── v1
         │         ├── doc.go
         │         ├── register.go
         │         ├── types.go
         │         └── zz_generated.deepcopy.go
         └── client
         ├── clientset
         ├── informers
         └── listers  
         
    其中，pkg/apis/samplecrd/v1 下面的 zz_generated.deepcopy.go 文件，就是自动生成的
DeepCopy 代码文件。
而整个 client 目录，以及下面的三个包（clientset、informers、 listers），都是 Kubernetes
为 Network 类型生成的客户端库，这些库会在后面编写自定义控制器的时候用到  

也可以编写更多的 YAML 文件来创建更多的 Network 对象，这和创建 Pod、
Deployment 的操作，没有任何区别  

# 编写自定义控制器 #  
“声明式 API”并不像“命令式 API”那样有着明显的执行
逻辑。这就使得基于声明式 API 的业务功能实现，往往需要通过控制器模式来“监视”API 对
象的变化（比如，创建或者删除 Network），然后以此来决定实际要执行的具体工作。  

编写自定义控制器代码的过程包括：编写 main 函数、编写自定义控制器的定义，以及编写控制器里的业务逻辑三个部分    

**main 函数**  
main 函数的主要工作就是，定义并初始化一个自定义控制器（Custom Controller），然后启
动它。这部分代码的主要内容如下所示：  

      func main() {
       ...

       cfg, err := clientcmd.BuildConfigFromFlags(masterURL, kubeconfig)
       ...
       kubeClient, err := kubernetes.NewForConfig(cfg)
       ...
       networkClient, err := clientset.NewForConfig(cfg)
       ...

       networkInformerFactory := informers.NewSharedInformerFactory(networkClient, ...)

       controller := NewController(kubeClient, networkClient,
       networkInformerFactory.Samplecrd().V1().Networks())

       go networkInformerFactory.Start(stopCh)
       if err = controller.Run(2, stopCh); err != nil {
       glog.Fatalf("Error running controller: %s", err.Error())
       }
      }


可以看到，这个 main 函数主要通过三步完成了初始化并启动一个自定义控制器的工作。
第一步：main 函数根据我提供的 Master 配置（APIServer 的地址端口和 kubeconfig 的路
径），创建一个 Kubernetes 的 client（kubeClient）和 Network 对象的
client（networkClient）。
但是，如果我没有提供 Master 配置呢？
这时，main 函数会直接使用一种名叫InClusterConfig的方式来创建这个 client。这个方式，会
假设你的自定义控制器是以 Pod 的方式运行在 Kubernetes 集群里的。  

Kubernetes 里所
有的 Pod 都会以 Volume 的方式自动挂载 Kubernetes 的默认 ServiceAccount。所以，这个
控制器就会直接使用默认 ServiceAccount 数据卷里的授权信息，来访问 APIServer。  

第二步：main 函数为 Network 对象创建一个叫作 InformerFactory（即：
networkInformerFactory）的工厂，并使用它生成一个 Network 对象的 Informer，传递给控
制器。
第三步：main 函数启动上述的 Informer，然后执行 controller.Run，启动自定义控制器。
至此，main 函数就结束了。  
## 自定义控制器的工作原理 ##  
![image](https://user-images.githubusercontent.com/20179983/142759157-cb20d0cf-3190-4b65-ac5b-3ed5346902fc.png)  

我们先从这幅示意图的最左边看起。
这个控制器要做的第一件事，是从 Kubernetes 的 APIServer 里获取它所关心的对象，也就是
我定义的 Network 对象。
这个操作，依靠的是一个叫作 Informer（可以翻译为：通知器）的代码库完成的。Informer 与
API 对象是一一对应的，所以我传递给自定义控制器的，正是一个 Network 对象的
Informer（Network Informer）。  

不知你是否已经注意到，我在创建这个 Informer 工厂的时候，需要给它传递一个
networkClient。
事实上，Network Informer 正是使用这个 networkClient，跟 APIServer 建立了连接。不过，
真正负责维护这个连接的，则是 Informer 所使用的 Reflector 包。
更具体地说，Reflector 使用的是一种叫作ListAndWatch的方法，来“获取”并“监听”这些
Network 对象实例的变化。
在 ListAndWatch 机制下，一旦 APIServer 端有新的 Network 实例被创建、删除或者更新，
Reflector 都会收到“事件通知”。这时，该事件及它对应的 API 对象这个组合，就被称为增量
（Delta），它会被放进一个 Delta FIFO Queue（即：增量先进先出队列）中。
而另一方面，Informe 会不断地从这个 Delta FIFO Queue 里读取（Pop）增量。每拿到一个增
量，Informer 就会判断这个增量里的事件类型，然后创建或者更新本地对象的缓存。这个缓
存，在 Kubernetes 里一般被叫作 Store。
比如，如果事件类型是 Added（添加对象），那么 Informer 就会通过一个叫作 Indexer 的库
把这个增量里的 API 对象保存在本地缓存中，并为它创建索引。相反地，如果增量的事件类型
是 Deleted（删除对象），那么 Informer 就会从本地缓存中删除这个对象。
这个同步本地缓存的工作，是 Informer 的第一个职责，也是它最重要的职责。
而Informer 的第二个职责，则是根据这些事件的类型，触发事先注册好的
ResourceEventHandler。这些 Handler，需要在创建控制器的时候注册给它对应的
Informer。   

**编写这个控制器的定义**  
      
      func NewController(
       kubeclientset kubernetes.Interface,
       networkclientset clientset.Interface,
       networkInformer informers.NetworkInformer) *Controller {
       ...
       controller := &Controller{
       kubeclientset: kubeclientset,
       networkclientset: networkclientset,
       networksLister: networkInformer.Lister(),
       networksSynced: networkInformer.Informer().HasSynced,
       workqueue: workqueue.NewNamedRateLimitingQueue(..., "Networks"),
       ...
       }
       networkInformer.Informer().AddEventHandler(cache.ResourceEventHandlerFuncs{
       AddFunc: controller.enqueueNetwork,
       UpdateFunc: func(old, new interface{}) {  
        oldNetwork := old.(*samplecrdv1.Network)
       newNetwork := new.(*samplecrdv1.Network)
       if oldNetwork.ResourceVersion == newNetwork.ResourceVersion {
       return
       }
       controller.enqueueNetwork(new)
       },
       DeleteFunc: controller.enqueueNetworkForDelete,
       return controller
      }


我前面在 main 函数里创建了两个 client（kubeclientset 和 networkclientset），然后在这段
代码里，使用这两个 client 和前面创建的 Informer，初始化了自定义控制器。
值得注意的是，在这个自定义控制器里，我还设置了一个工作队列（work queue），它正是处
于示意图中间位置的 WorkQueue。这个工作队列的作用是，负责同步 Informer 和控制循环之
间的数据。   

然后，我为 networkInformer 注册了三个 Handler（AddFunc、UpdateFunc 和
DeleteFunc），分别对应 API 对象的“添加”“更新”和“删除”事件。而具体的处理操作，
都是将该事件对应的 API 对象加入到工作队列中。  

需要注意的是，实际入队的并不是 API 对象本身，而是它们的 Key，即：该 API 对象的/。  

而我们后面即将编写的控制循环，则会不断地从这个工作队列里拿到这些 Key，然后开始执行真
正的控制逻辑。
综合上面的讲述，你现在应该就能明白，所谓 Informer，其实就是一个带有本地缓存和索引机
制的、可以注册 EventHandler 的 client。它是自定义控制器跟 APIServer 进行数据同步的重
要组件。
更具体地说，Informer 通过一种叫作 ListAndWatch 的方法，把 APIServer 中的 API 对象缓
存在了本地，并负责更新和维护这个缓存。
其中，ListAndWatch 方法的含义是：首先，通过 APIServer 的 LIST API“获取”所有最新版
本的 API 对象；然后，再通过 WATCH API 来“监听”所有这些 API 对象的变化。
而通过监听到的事件变化，Informer 就可以实时地更新本地缓存，并且调用这些事件对应的
EventHandler 了  

此外，在这个过程中，每经过 resyncPeriod 指定的时间，Informer 维护的本地缓存，都会使
用最近一次 LIST 返回的结果强制更新一次，从而保证缓存的有效性。在 Kubernetes 中，这个
缓存强制更新的操作就叫作：resync。
需要注意的是，这个定时 resync 操作，也会触发 Informer 注册的“更新”事件。但此时，这
个“更新”事件对应的 Network 对象实际上并没有发生变化，即：新、旧两个 Network 对象
的 ResourceVersion 是一样的。在这种情况下，Informer 就不需要对这个更新事件再做进一步
的处理了。
这也是为什么我在上面的 UpdateFunc 方法里，先判断了一下新、旧两个 Network 对象的版
本（ResourceVersion）是否发生了变化，然后才开始进行的入队操作。
以上，就是 Kubernetes 中的 Informer 库的工作原理了。  

接下来，我们就来到了示意图中最后面的控制循环（Control Loop）部分，也正是我在 main
函数最后调用 controller.Run() 启动的“控制循环”。  

      func (c *Controller) Run(threadiness int, stopCh <-chan struct{}) error {
       ...
       if ok := cache.WaitForCacheSync(stopCh, c.networksSynced); !ok {
       return fmt.Errorf("failed to wait for caches to sync")
       }

       ...
       for i := 0; i < threadiness; i++ {
       go wait.Until(c.runWorker, time.Second, stopCh)
       }

       ...
       return nil
      }
      
 可以看到，启动控制循环的逻辑非常简单：
首先，等待 Informer 完成一次本地缓存的数据同步操作；
然后，直接通过 goroutine 启动一个（或者并发启动多个）“无限循环”的任务。
而这个“无限循环”任务的每一个循环周期，执行的正是我们真正关心的业务逻辑。
所以接下来，我们就来编写这个自定义控制器的业务逻辑，它的主要内容如下所示：   

func (c *Controller) runWorker() {
 for c.processNextWorkItem() {
 }  
 
 。。。  
 
 可以看到，在这个执行周期里（processNextWorkItem），我们首先从工作队列里出队
（workqueue.Get）了一个成员，也就是一个 Key（Network 对象的：
namespace/name）。
然后，在 syncHandler 方法中，我使用这个 Key，尝试从 Informer 维护的缓存中拿到了它所
对应的 Network 对象。
可以看到，在这里，我使用了 networksLister 来尝试获取这个 Key 对应的 Network 对象。这
个操作，其实就是在访问本地缓存的索引。实际上，在 Kubernetes 的源码中，你会经常看到控
制器从各种 Lister 里获取对象，比如：podLister、nodeLister 等等，它们使用的都是
Informer 和缓存机制。
而如果控制循环从缓存中拿不到这个对象（即：networkLister 返回了 IsNotFound 错误），那
就意味着这个 Network 对象的 Key 是通过前面的“删除”事件添加进工作队列的。所以，尽管
队列里有这个 Key，但是对应的 Network 对象已经被删除了。
这时候，我就需要调用 Neutron 的 API，把这个 Key 对应的 Neutron 网络从真实的集群里删
除掉。
而如果能够获取到对应的 Network 对象，我就可以执行控制器模式里的对比“期望状
态”和“实际状态”的逻辑了。
其中，自定义控制器“千辛万苦”拿到的这个 Network 对象，正是 APIServer 里保存的“期望
状态”，即：用户通过 YAML 文件提交到 APIServer 里的信息。当然，在我们的例子里，它已
经被 Informer 缓存在了本地。
那么，“实际状态”又从哪里来呢？
当然是来自于实际的集群了。
所以，我们的控制循环需要通过 Neutron API 来查询实际的网络情况。  

比如，我可以先通过 Neutron 来查询这个 Network 对象对应的真实网络是否存在。
如果不存在，这就是一个典型的“期望状态”与“实际状态”不一致的情形。这时，我就需
要使用这个 Network 对象里的信息（比如：CIDR 和 Gateway），调用 Neutron API 来创
建真实的网络。
如果存在，那么，我就要读取这个真实网络的信息，判断它是否跟 Network 对象里的信息一
致，从而决定我是否要通过 Neutron 来更新这个已经存在的真实网络。
这样，我就通过对比“期望状态”和“实际状态”的差异，完成了一次调协（Reconcile）的过
程。
至此，一个完整的自定义 API 对象和它所对应的自定义控制器，就编写完毕了。  

这套流程不仅可以用在自定义 API 资源上，也完全可以用在 Kubernetes 原生的默认
API 对象上。
比如，我们在 main 函数里，除了创建一个 Network Informer 外，还可以初始化一个
Kubernetes 默认 API 对象的 Informer 工厂，比如 Deployment 对象的 Informer。  

**总结**  
所谓的 Informer，就是一个自带缓存和索引机制，可以触发 Handler 的客户端库。这个本地缓
存在 Kubernetes 中一般被称为 Store，索引一般被称为 Index。
Informer 使用了 Reflector 包，它是一个可以通过 ListAndWatch 机制获取并监视 API 对象变
化的客户端封装。
Reflector 和 Informer 之间，用到了一个“增量先进先出队列”进行协同。而 Informer 与你
要编写的控制循环之间，则使用了一个工作队列来进行协同。
在实际应用中，除了控制循环之外的所有代码，实际上都是 Kubernetes 为你自动生成的，即：
pkg/client/{informers, listers, clientset}里的内容。
而这些自动生成的代码，就为我们提供了一个可靠而高效地获取 API 对象“期望状态”的编程
库。
所以，接下来，作为开发者，你就只需要关注如何拿到“实际状态”，然后如何拿它去跟“期望
状态”做对比，从而决定接下来要做的业务逻辑即可。
以上内容，就是 Kubernetes API 编程范式的核心思想。  


请思考一下，为什么 Informer 和你编写的控制循环之间，一定要使用一个工作队列来进行协作
呢？  

Informer 和控制循环分开是为了解耦，防止控制循环执行过慢把Informer 拖死   
