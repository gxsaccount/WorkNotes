容器的持久化存储，就是用来保存容器存储状态的重要手段：存储插件会在容器里挂载一个基于
网络或者其他机制的远程数据卷，使得在容器里创建的文件，实际上是保存在远程存储服务器上，
或者以分布式的方式保存在多个节点上，而与当前宿主机没有任何绑定关系。这样，无论你在其他
哪个宿主机上启动新的容器，都可以请求挂载指定的持久化存储卷，从而访问到数据卷里保存的内
容。这就是“持久化”的含义。
由于 Kubernetes 本身的松耦合设计，绝大多数存储项目，比如 Ceph、GlusterFS、NFS 等，都可
以为 Kubernetes 提供持久化存储能力。在这次的部署实战中，我会选择部署一个很重要的
Kubernetes 存储插件项目：Rook。


kubectl apply -f https://raw.githubusercontent.com/rook/rook/master/cluster/examples/kubernetes 
kubectl apply -f https://raw.githubusercontent.com/rook/rook/master/cluster/examples/kubernetes
