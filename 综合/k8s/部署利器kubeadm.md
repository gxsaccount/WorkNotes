个项目的目的，就是要让用户能够通过这样两条指令完成一个 Kubernetes 集群的部署  
    
    # 创建一个 Master 节点 
    $ kubeadm init 
    # 将一个 Node 节点加入到当前集群中 
    $ kubeadm join <Master 节点的 IP 和端口 > 
    
 # kubeadm 的工作原理 #   
 **为什么不用容器部署Kubernetes**   
 除了跟容器运行时打交道外，kubelet 在配置容器网络、管理容器数据卷时，都需要
直接操作宿主机。  
如果现在 kubelet 本身就运行在一个容器里，那么直接操作宿主机就会变得很麻烦。对于网络配
置来说还好，kubelet 容器可以通过不开启 Network Namespace（即 Docker 的 host network
模式）的方式，直接共享宿主机的网络栈。可是，要让 kubelet 隔着容器的 Mount Namespace
和文件系统，操作宿主机的文件系统，就有点儿困难了。  
正因为如此，kubeadm 选择了一种妥协方案：
把 kubelet 直接运行在宿主机上，然后使用容器部署其他的 Kubernetes 组件。  

# 使用 #  

     apt-get install kubeadm  
     kubeadm init //即可部署master  
     
**kubeadm init 的工作流程**  
当你执行 kubeadm init 指令后，kubeadm 首先要做的，是一系列的检查工作，以确定这台机器可
以用来部署 Kubernetes。这一步检查，我们称为“Preflight Checks”，它可以为你省掉很多后续
的麻烦。
其实，Preflight Checks 包括了很多方面，比如：
Linux 内核的版本必须是否是 3.10 以上？
Linux Cgroups 模块是否可用？
机器的 hostname 是否标准？在 Kubernetes 项目里，机器的名字以及一切存储在 Etcd 中的
API 对象，都必须使用标准的 DNS 命名（RFC 1123）。
用户安装的 kubeadm 和 kubelet 的版本是否匹配？
机器上是不是已经安装了 Kubernetes 的二进制文件？
Kubernetes 的工作端口 10250/10251/10252 端口是不是已经被占用？
ip、mount 等 Linux 指令是否存在？
Docker 是否已经安装？
……
在通过了 Preflight Checks 之后，kubeadm 要为你做的，是生成 Kubernetes 对外提供服务所需
的各种证书和对应的目录。
Kubernetes 对外提供服务时，除非专门开启“不安全模式”，否则都要通过 HTTPS 才能访问
kube-apiserver。这就需要为 Kubernetes 集群配置好证书文件。
kubeadm 为 Kubernetes 项目生成的证书文件都放在 Master 节点的 /etc/kubernetes/pki 目录
下。在这个目录下，最主要的证书文件是 ca.crt 和对应的私钥 ca.key。
此外，用户使用 kubectl 获取容器日志等 streaming 操作时，需要通过 kube-apiserver 向
kubelet 发起请求，这个连接也必须是安全的。kubeadm 为这一步生成的是 apiserver-kubeletclient.crt 文件，对应的私钥是 apiserver-kubelet-client.key  


你可以选择不让 kubeadm 为你生成这些证书，而是拷贝现
有的证书到如下证书的目录里：   
/etc/kubernetes/pki/ca.{crt,key}  
这时，kubeadm 就会跳过证书生成的步骤，把它完全交给用户处理。
证书生成后，kubeadm 接下来会为其他组件生成访问 kube-apiserver 所需的配置文件。这些文件
的路径是：/etc/kubernetes/xxx.conf：
ls /etc/kubernetes/ admin.conf controller-manager.conf kubelet.conf scheduler.conf
这些文件里面记录的是，当前这个 Master 节点的服务器地址、监听端口、证书目录等信息。这
样，对应的客户端（比如 scheduler，kubelet 等），可以直接加载相应的文件，使用里面的信息与
kube-apiserver 建立安全连接。
接下来，kubeadm 会为 Master 组件生成 Pod 配置文件。我已经在上一篇文章中和你介绍过
Kubernetes 有三个 Master 组件 kube-apiserver、kube-controller-manager、kubescheduler，而它们都会被使用 Pod 的方式部署起来。
你可能会有些疑问：这时，Kubernetes 集群尚不存在，难道 kubeadm 会直接执行 docker run 来
启动这些容器吗？
当然不是。
在 Kubernetes 中，有一种特殊的容器启动方法叫做“Static Pod”。它允许你把要部署的 Pod 的
YAML 文件放在一个指定的目录里。这样，当这台机器上的 kubelet 启动时，它会自动检查这个目
录，加载所有的 Pod YAML 文件，然后在这台机器上启动它们。
从这一点也可以看出，kubelet 在 Kubernetes 项目中的地位非常高，在设计上它就是一个完全独
立的组件，而其他 Master 组件，则更像是辅助性的系统容器。
在 kubeadm 中，Master 组件的 YAML 文件会被生成在 /etc/kubernetes/manifests 路径下。比
如，kube-apiserver.yaml： 
https://github.com/kubernetes/kubernetes/blob/master/test/fixtures/doc-yaml/admin/high-availability/kube-apiserver.yaml  


    ...
    spec:
    hostNetwork: true
    containers:
    - name: kube-apiserver
      image: k8s.gcr.io/kube-apiserver:9680e782e08a1a1c94c656190011bd02
      command:
      - /bin/sh
      - -c
      - /usr/local/bin/kube-apiserver --address=127.0.0.1 --etcd-servers=http://127.0.0.1:4001
        --cloud-provider=gce   --admission-control=NamespaceLifecycle,LimitRanger,SecurityContextDeny,ServiceAccount,ResourceQuota
        --service-cluster-ip-range=10.0.0.0/16 --client-ca-file=/srv/kubernetes/ca.crt
        --cluster-name=e2e-test-bburns
        --tls-cert-file=/srv/kubernetes/server.cert --tls-private-key-file=/srv/kubernetes/server.key
        --secure-port=443 --token-auth-file=/srv/kubernetes/known_tokens.csv  --v=2
        --allow-privileged=False 1>>/var/log/kube-apiserver.log 2>&1
      ports:
      ...  
    
    
1.这个 Pod 里只定义了一个容器，它使用的镜像是：k8s.gcr.io/kube-apiserver。这个镜像是 Kubernetes 官方维护的一个组件镜像。
2. 这个容器的启动命令（commands）是 kube-apiserver --authorization-mode=Node,RBAC
…，这样一句非常长的命令。其实，它就是容器里 kube-apiserver 这个二进制文件再加上指定
的配置参数而已。
3. 如果你要修改一个已有集群的 kube-apiserver 的配置，需要修改这个 YAML 文件。
4. 这些组件的参数也可以在部署时指定，我很快就会讲解到。

在这一步完成后，kubeadm 还会再生成一个 Etcd 的 Pod YAML 文件，用来通过同样的 Static
Pod 的方式启动 Etcd。所以，最后 Master 组件的 Pod YAML 文件如下所示：  

$ ls /etc/kubernetes/manifests/   
etcd.yaml kube-apiserver.yaml kube-controller-manager.yaml kube-scheduler.yaml  
而一旦这些 YAML 文件出现在被 kubelet 监视的 /etc/kubernetes/manifests 目录下，kubelet 就
会自动创建这些 YAML 文件中定义的 Pod，即 Master 组件的容器。
Master 容器启动后，kubeadm 会通过检查 localhost:6443/healthz 这个 Master 组件的健康检查
URL，等待 Master 组件完全运行起来。
然后，kubeadm 就会为集群生成一个 bootstrap token。在后面，只要持有这个 token，任何一
个安装了 kubelet 和 kubadm 的节点，都可以通过 kubeadm join 加入到这个集群当中。
这个 token 的值和使用方法会，会在 kubeadm init 结束后被打印出来。
在 token 生成之后，kubeadm 会将 ca.crt 等 Master 节点的重要信息，通过 ConfigMap 的方式
保存在 Etcd 当中，供后续部署 Node 节点使用。这个 ConfigMap 的名字是 cluster-info。
kubeadm init 的最后一步，就是安装默认插件。Kubernetes 默认 kube-proxy 和 DNS 这两个插
件是必须安装的。它们分别用来提供整个集群的服务发现和 DNS 功能。  

其实，这两个插件也只是两
个容器镜像而已，所以 kubeadm 只要用 Kubernetes 客户端创建两个 Pod 就可以了。  
**kubeadm join 的工作流程**  
这个流程其实非常简单，kubeadm init 生成 bootstrap token 之后，你就可以在任意一台安装了
kubelet 和 kubeadm 的机器上执行 kubeadm join 了。
可是，为什么执行 kubeadm join 需要这样一个 token 呢？
因为，任何一台机器想要成为 Kubernetes 集群中的一个节点，就必须在集群的 kube-apiserver 上
注册。可是，要想跟 apiserver 打交道，这台机器就必须要获取到相应的证书文件（CA 文件）。可
是，为了能够一键安装，我们就不能让用户去 Master 节点上手动拷贝这些文件。
所以，kubeadm 至少需要发起一次“不安全模式”的访问到 kube-apiserver，从而拿到保存在
ConfigMap 中的 cluster-info（它保存了 APIServer 的授权信息）。而 bootstrap token，扮演的
就是这个过程中的安全验证的角色。
只要有了 cluster-info 里的 kube-apiserver 的地址、端口、证书，kubelet 就可以以“安全模
式”连接到 apiserver 上，这样一个新的节点就部署完成了。
接下来，你只要在其他节点上重复这个指令就可以了。   


## 配置 kubeadm 的部署参数  ##  
我在前面讲解了 kubeadm 部署 Kubernetes 集群最关键的两个步骤，kubeadm init 和 kubeadm
join。相信你一定会有这样的疑问：kubeadm 确实简单易用，可是我又该如何定制我的集群组件参
数呢？
比如，我要指定 kube-apiserver 的启动参数，该怎么办？
在这里，我强烈推荐你在使用 kubeadm init 部署 Master 节点时，使用下面这条指令：

kubeadm init --config kubeadm.yaml  
这时，你就可以给 kubeadm 提供一个 YAML 文件（比如，kubeadm.yaml）

然后，kubeadm 就会使用上面这些信息替换 /etc/kubernetes/manifests/kube-apiserver.yaml
里的 command 字段里的参数了。  
还可以修改 kubelet 和 kube-proxy 的配
置，修改 Kubernetes 使用的基础镜像的 URL（默认的k8s.gcr.io/xxx镜像 URL 在国内访问是
有困难的），指定自己的证书文件，指定特殊的容器运行时等等。  

https://www.zhihu.com/question/315497851  

