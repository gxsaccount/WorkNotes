# 网络协议相关 #  
![image](https://user-images.githubusercontent.com/20179983/149624764-ab307219-9f7b-4dc2-8f93-152ac7af6a6f.png)

# Overlay Network介绍 #   

在 Docker 的默认配置下，一台宿主机上的 docker0 网桥，和其他宿主机上的 docker0 网桥，
没有任何关联，它们互相之间也没办法连通。
容器的跨主机通讯可以通过软件的方式，创建一个整个集群“公用”的网桥，然后把集群里的所有容器都连接
到这个网桥上。   
![3f91c5c7e5f75078ad83675871fed7c](https://user-images.githubusercontent.com/20179983/148673899-e64e2296-2b8a-4f3a-8cc0-4278658d333d.png)

构建这种容器网络的核心在于：需要在已有的宿主机网络上，再通过软件构建一
个覆盖在已有宿主机网络之上的、可以把所有容器连通在一起的虚拟网络。所以，这种技术就被
称为：Overlay Network（覆盖网络）。  


# Flannel 项目 #  
Flannel 项目本身只是一个框架，真正为我们提供容器网络功能的，是 Flannel 的后端实现。目前，Flannel 支持三种后端实现，分别是：
    
    1. VXLAN；
    2. host-gw；
    3. UDP。 

## UDP 模式 ##  
 UDP 模式，是 Flannel 项目最早支持的一种方式，也是性能最差的一种方式。   
 ![95d96f3dc4dbfb234edd6e9c4cf2baf](https://user-images.githubusercontent.com/20179983/148676566-b3ba2da3-e2a1-4c1d-a361-1b4c267d8778.png)  
**原理**：Flannel UDP 模式提供的其实是一个**三层的 Overlay 网络（为什么是三层？？？）**，**首先对发出端的 IP包进行 UDP 封装，然后在接收端进行解封装拿到原始的 IP 包，进而把这个 IP 包转发给目标容器。**  
Flannel 在不同宿主机上的两个容器之间打通了一条“隧道”，使得这两个容器可
以直接使用 **IP 地址**进行通信，而无需关心容器和宿主机的分布情况。   
**缺点：**    
相比于两台宿主机之间的直接通信，基于 Flannel UDP 模式的容器通信多了**flanneld 的处理过程**。  
而这个过程，由于使用到了 flannel0 这个 TUN 设备，在**发出 IP包的过程中需要经过三次用户态与内核态之间的数据拷贝**，如下所示：  
![521a8dfb3b59352721896396f0dd994](https://user-images.githubusercontent.com/20179983/148676596-875082e7-2b2b-4882-b28e-2bd101044b39.png)
我们可以看到：  
**第一次**：用户态的容器进程发出的 IP 包经过 docker0 网桥进入内核态；  
**第二次**：IP 包根据路由表进入 TUN（flannel0）设备，从而回到用户态的 flanneld 进程；  
**第三次**：flanneld 进行 UDP 封包之后重新进入内核态，将 UDP 包通过宿主机的 eth0 发出去。  
此外，**Flannel 进行 UDP 封装（Encapsulation）和解封装（Decapsulation）  
的过程，也都是在用户态完成的**。  
在 Linux 操作系统中，上述这些上下文切换和用户态操作的代价其实是比较高的，这也正是造成 Flannel UDP 模式性能不好的主要原因     

**实例：**    
现在有两台宿主机。  

    宿主机 Node 1 上有一个容器 container-1，
    它的 IP 地址是 100.96.1.2，
    对应的 docker0 网桥的地址是：100.96.1.1/24。    
    
    宿主机 Node 2 上有一个容器 container-2，
    它的 IP 地址是 100.96.2.3，
    对应的 docker0 网桥的地址是：100.96.2.1/24。  

**目的：**  
让 container-1 访问 container-2，即让源地址 100.96.1.2，目的地址就是100.96.2.3的IP包能正常转发。      
**发送步骤**  
* 容器将数据包发送到虚拟网卡，通过Veth Pair同时发到docker0  
* docker0将数据包路由到flannel0    
目的地址 100.96.2.3 并不在 Node 1 的 docker0 网桥的网段里，所以这个 IP 包会被交给默认路由规则，通过容器的网关进入 docker0 网桥（如果是同一台宿主机上的容器间通
信，走的是直连规则）。  
Flannel会在宿主机上创建出了一系列的路由规则，以 Node 1 为例，如下所示：  

        # 在 Node 1 上
        $ ip route
        default via 10.168.0.1 dev eth0
        100.96.0.0/16 dev flannel0 proto kernel scope link src 100.96.1.0
        100.96.1.0/24 dev docker0 proto kernel scope link src 100.96.1.1
        10.168.0.0/24 dev eth0 proto kernel scope link src 10.168.0.2    

由目的地址100.96.2.3进行路由回到flannel0上  
IP 包的目的地址是 100.96.2.3，匹配不到本机 docker0 网桥对应的100.96.1.0/24 网段，只能匹配到第二条、也就是 100.96.0.0/16 对应的这条路由规则，从而进入到一个叫作 flannel0 的TUN 设备中。  

* flannel0封装UDP传递给内核    
**flannel0通过etcd查找容器ip对应的主机ip，并封装到udp报文中**   
* 内核转发udp到对应node节点的8285端口      

**接受步骤**  
* 网卡接受到udp报文，通过8285端口发送到flanneld    
* flanneld解UDP封装，得到IP包    
* flanneld 会直接把这个 IP 包发送给它所管理的 TUN 设备，即 flannel0 设备。**（用户态向内核态的流动方向（Flannel 进程向TUN 设备发送数据包））**      
* Linux 内核网络栈将IP路由到docker0。    
Node 2 上的路由表，跟 Node 1 非常类似，如下所示：    
    
        # 在 Node 2 上
        $ ip route
        default via 10.168.0.1 dev eth0
        100.96.0.0/16 dev flannel0 proto kernel scope link src 100.96.2.0
        100.96.2.0/24 dev docker0 proto kernel scope link src 100.96.2.1
        10.168.0.0/24 dev eth0 proto kernel scope link src 10.168.0.3    

由于这个 IP 包的目的地址是 100.96.2.3，它跟第三条、也就是 100.96.2.0/24 网段对应的路由规则匹配更加精确。所以，Linux 内核就会按照这条路由规则，把这个 IP 包转发给 docker0 网桥。  
* docker0通过转发数据包到Veth Pair
docker0 网桥会扮演二层交换机的角色，将数据包发送给正确的端口，进而通过 Veth Pair 设备进入到 container-2 的Network Namespace 里。  


**Flannel转发原理/Flannel如何知道ip对应的容器**  

flannel0 是一个 TUN 设备（Tunnel 设备）。    
**TUN 设备是一种工作在三层（Network Layer）的虚拟网络设备。TUN 设备的功能是在操作系统内核和用户应用程序之间传递 IP 包。**     
当操作系统将一个 IP 包发送给 flannel0 设备之后，flannel0 就会把这个 IP包，交给创建这个设备的应用程序，也就是 Flannel 进程。**（内核态向用户态（Flannel 进程））**。  
如果 Flannel 进程向 flannel0 设备发送了一个 IP 包，那么这个 IP 包就会出现在宿主机网络栈中，然后根据宿主机的路由表进行下一步处理。**（用户态向内核态）**。
所以，当 IP 包从容器经过 docker0 出现在宿主机，然后又根据路由表进入 flannel0 设备后，宿主机上的 flanneld 进程（Flannel 项目在每个宿主机上的主进程），就会收到这个 IP 包。  
然后，flanneld 看到了这个 IP 包的目的地址，是 100.96.2.3，就把它发送给了 Node 2 宿主机。  

**在由 Flannel 管理的容器网络里，一台宿主机上的所有容器，都属于该宿主机被分配的一个“子网”。子网与宿主机的对应关系，保存在 Etcd 当中**  
在我们的例子中，Node 1 的子网是 100.96.1.0/24，container-1 的 IP 地址是100.96.1.2。
Node 2 的子网是 100.96.2.0/24，container-2 的 IP 地址是 100.96.2.3。
    
        $ etcdctl ls /coreos.com/network/subnets
        /coreos.com/network/subnets/100.96.1.0-24
        /coreos.com/network/subnets/100.96.2.0-24
    
flanneld 进程在处理由 flannel0 传入的 IP 包时，就可以根据目的 IP 的地址（比如100.96.2.3），匹配到对应的子网（比如 100.96.2.0/24），  
从 Etcd 中找到这个子网对应的宿主机的 IP 地址是 10.168.0.3，如下所示：   
    
        $ etcdctl get /coreos.com/network/subnets/100.96.2.0-24
        {"PublicIP":"10.168.0.3"}  

flanneld 在收到 container-1 发给 container-2 的 IP 包之后，就会把这个 IP 包直接封装在一个 UDP 包里，然后发送给 Node 2。  
**这个 UDP 包的源地址，就是 flanneld 所在的 Node 1 的地址，而目的地址，则是 container-2 所在的宿主机 Node 2 的地址。**    
每台宿主机上的 flanneld，都监听着一个 8285 端口，所以flanneld 只要把 UDP 包发往 Node 2 的 8285 端口即可。  
Node 2 上监听 8285 端口的进程也是 flanneld，所以这时候，flanneld 就可以从这个 UDP 包里解析出封装在里面的、container-1 发来的原 IP 包。    


## VXLAN 模式 ##   
VXLAN，即 Virtual Extensible LAN（虚拟可扩展局域网），是 Linux 内核本身就支持的一种网络虚似化技术。  
**VXLAN 可以完全在内核态实现上述封装和解封装的工作**，从而通过与前面相似的“隧道”机制，构建出覆盖网络（Overlay Network）。    
VXLAN 的覆盖网络的设计思想是：在三层网络之上，“覆盖”一层虚拟的、由内核 VXLAN模块负责维护的二层网络，  
使得连接在这个 VXLAN 二层网络上的“主机”（虚拟机或者容器都可以）之间，可以像在同一个局域网（LAN）里那样自由通信。  
为了能够在二层网络上打通“隧道”，VXLAN 会在宿主机上设置一个特殊的网络设备作为“隧道”的两端。这个设备就叫作 **VTEP，即：VXLAN Tunnel End Point（虚拟隧道端点）**。  
而 VTEP 设备的作用，其实跟前面的 flanneld 进程非常相似。  
只不过，它**进行封装和解封装的对象，是二层数据帧（Ethernet frame）；而且这个工作的执行流程，全部是在内核里完成的（因为  
VXLAN 本身就是 Linux 内核中的一个模块）**。
![bd23d59db436f44d2abfc9d78b69ade](https://user-images.githubusercontent.com/20179983/148676662-bea0ccc6-caee-48c3-bc3b-2cff07e38c23.png)  
可以看到，图中每台宿主机上名叫 flannel.1 的设备，就是 VXLAN 所需的 VTEP 设备，它既有 IP地址，也有 MAC 地址。  
现在，我们的 container-1 的 IP 地址是 10.1.15.2，要访问的 container-2 的 IP 地址是10.1.16.3。  
那么，与前面 UDP 模式的流程类似，当 container-1 发出请求之后，这个目的地址是 10.1.16.3的 IP 包，会先出现在 docker0 网桥，然后被路由到本机 flannel.1 设备进行处理。   
为了能够将“原始 IP 包”封装并且发送到正确的宿主机，VXLAN 就需要找到这条“隧道”的出口，即：目的宿主机的 VTEP 设备。  
而这个设备的信息，正是每台宿主机上的 flanneld 进程负责维护的。  
比如，**当 Node 2 启动并加入 Flannel 网络之后，在 Node 1（以及所有其他节点）上，flanneld就会添加一条如下所示的路由规则：**   

      $ route -n
      Kernel IP routing table
      Destination   Gateway     Genmask         Flags   Metric  Ref Use Iface
      ...
      10.1.16.0     10.1.16.0   255.255.255.0   UG      0       0   0   flannel.1  
      
这条规则的意思是：**凡是发往 10.1.16.0/24 网段的 IP 包，都需要经过 flannel.1 设备发出，并且，它最后被发往的网关地址是：10.1.16.0。**  
从图 3 的 Flannel VXLAN 模式的流程图中我们可以看到，10.1.16.0 正是 Node 2 上的 VTEP 设备（也就是 flannel.1 设备）的 IP 地址。
**“源 VTEP 设备”收到“原始 IP 包”后，需要把“原始 IP 包”加上一个目的 MAC 地址，封装成一个二层数据帧，然后发送给“目的 VTEP 设备”**。   

**“目的 VTEP 设备”的 MAC 地址是什么？**  
根据前面的路由记录，经知道了“目的 VTEP 设备”的 IP 地址。  
而要根据三层 IP 地址查询对应的二层 MAC 地址，这正是 ARP（Address Resolution Protocol ）表的功能。  

**这里要用到的 ARP 记录，也是 flanneld 进程在 Node 2 节点启动时，自动添加在 Node 1 上的**。   
我们可以通过 ip 命令看到它，如下所示：  

      # 在 Node 1 上
      $ ip neigh show dev flannel.1
      10.1.16.0 lladdr 5e:f8:4f:00:e3:37 PERMANENT  
      
这条记录的意思非常明确，即：IP 地址 10.1.16.0，对应的 MAC 地址是 5e:f8:4f:00:e3:37。  
 
有了这个“目的 VTEP 设备”的 MAC 地址，Linux 内核就可以开始二层封包工作了。这个二层帧
的格式，如下所示：  

![d90ad38aa591d00415492f1d2a88f87](https://user-images.githubusercontent.com/20179983/148676735-f1e4ad42-760f-482a-affc-0f12dad303e0.png)  
可以看到，Linux 内核会把“目的 VTEP 设备”的 MAC 地址，填写在图中的 Inner Ethernet Header 字段，得到一个二层数据帧。  
上述封包过程只是加一个二层头，不会改变“原始 IP 包”的内容。  
所以图中的Inner IP Header 字段，依然是 container-2 的 IP 地址，即 10.1.16.3。
上面提到的这些 VTEP 设备的 MAC 地址，对于宿主机网络来说并没有什么实际意义。  
所以上面封装出来的这个数据帧，并不能在我们的宿主机二层网络里传输。  
为了方便叙述，我们把它称**为“内部数据帧”（Inner Ethernet Frame）**。  
所以接下来，Linux 内核还需要再把“内部数据帧”进一步封装成为宿主机网络里的一个普通的数据帧，好让它“载着”“内部数据帧”，通过宿主机的 eth0 网卡进行传输。  
把这次要封装出来的、宿主机对应的数据帧称**为“外部数据帧”（Outer Ethernet Frame）**。
为了实现这个“搭便车”的机制，**Linux 内核会在“内部数据帧”前面，加上一个特殊的 VXLAN头，用来表示这个“乘客”实际上是一个 VXLAN 要使用的数据帧**。  
而这个 VXLAN 头里有一个重要的标志叫作VNI，它是 VTEP 设备识别某个数据帧是不是应该归自己处理的重要标识。  
而在 Flannel 中，VNI 的默认值是 1，这也是为何，宿主机上的 VTEP 设备都叫作 flannel.1 的原因，这里的“1”，其实就是 VNI 的值。   
然后，**Linux 内核会把这个数据帧封装进一个 UDP 包里发出去**。
所以，跟 UDP 模式类似，在宿主机看来，它会以为自己的 flannel.1 设备只是在向另外一台宿主机
的 flannel.1 设备，发起了一次普通的 UDP 链接。它哪里会知道，这个 UDP 包里面，其实是一个
完整的二层数据帧。
但是，一个 flannel.1 设备只知道另一端的 flannel.1 设备的 MAC 地址，却不知道对应的宿主机地址是什么。  
也就是说，这个 UDP 包该发给哪台宿主机呢？  
在这种场景下，**flannel.1 设备实际上要扮演一个“网桥”的角色，在二层网络进行 UDP 包的转发**。  
而在 Linux 内核里面，“网桥”设备进行转发的依据，来自于一个叫作 FDB（ForwardingDatabase）的转发数据库。  
不难想到，这个 flannel.1“网桥”对应的 FDB 信息，也是 flanneld 进程负责维护的。  
它的内容可以通过 bridge fdb 命令查看到，如下所示：  

      # 在 Node 1 上，使用“目的 VTEP 设备”的 MAC 地址进行查询
      $ bridge fdb show flannel.1 | grep 5e:f8:4f:00:e3:37
      5e:f8:4f:00:e3:37 dev flannel.1 dst 10.168.0.3 self permanent  
      
这条 FDB 记录里，指定了这样一条规则，即：
发往我们前面提到的“目的 VTEP 设备”（MAC 地址是 5e:f8:4f:00:e3:37）的二层数据帧，应该通过 flannel.1 设备，发往 IP 地址为 10.168.0.3 的主机。  
显然，这台主机正是 Node 2，UDP 包要发往的目的地就找到了。  

UDP 包是一个四层数据包，所以 Linux 内核会在它前面加上一个 IP 头，即原理图中的Outer IP Header，组成一个 IP 包。  
并且，在这个 IP 头里，会填上前面通过 FDB 查询出来的目的主机的 IP 地址，即 Node 2 的 IP 地址 10.168.0.3。  
然后，Linux 内核再在这个 IP 包前面加上二层数据帧头，即原理图中的 Outer Ethernet Header，并把 Node 2 的 MAC 地址填进去。  
这个 MAC 地址本身，是 Node 1 的 ARP 表要学习的内容，无需 Flannel 维护。这时候，我们封装出来的“外部数据帧”的格式，如下所示：  

![4b70782a15016fffaad078ca969eadc](https://user-images.githubusercontent.com/20179983/148676796-875bc7bb-de17-485c-9487-0ed80c380d7d.png)


接下来，Node 1 上的 flannel.1 设备就可以把这个数据帧从 Node 1 的 eth0 网卡发出去。  
显然，这个帧会经过宿主机网络来到 Node 2 的 eth0 网卡。  
这时候，Node 2 的内核网络栈会发现这个数据帧里有 VXLAN Header，并且 VNI=1。  
所以 Linux内核会对它进行拆包，拿到里面的内部数据帧，然后根据 VNI 的值，把它交给 Node 2 上的flannel.1 设备。  
而 flannel.1 设备则会进一步拆包，取出“原始 IP 包”。接下来就回到了我在上一篇文章中分享的单机容器网络的处理流程。  
最终，IP 包就进入到了 container-2 容器的 Network Namespace里。
以上，就是 Flannel VXLAN 模式的具体工作原理了。

**VXLAN有IP包发出过程有1次用户态与内核态之间的数据拷贝**  
第一次：用户态的容器进程发出的 IP 包经过 docker0 网桥进入内核态；


## VXLAN与udp区别 ##  
主要在数据包封装方式和获取mac地址方法  

* udp  
当新容器加入Flannel网络时，容器的ip信息是宿主的子网，子网与宿主机的对应关系记录在etcd中。  
通过查找etcd来获取对应的ip的宿主机的ip地址  
Flannel会将需要传递的IP 包封装在一个 UDP 包里（**用户态**），然后发送给 Node 2（源地址，就是 flanneld 所在的 Node 1 的地址，而目的地址，则是 container-2 所在的宿主机 Node 2 的地址）  
Node2的flanneld解了udp后，在由ip包的目的地址进行路由，传递到容器2  

* vxlan    
 flanneld 进程在 Node 2 节点启动时，自动添加在 Node 1 上路由规则（到目的 VTEP 设备的路由），ARP表，并且还会维护FDB的数据（因为封装在二层发生）      
 Flannel会将需要传递的IP 包封装进行**二层封包工作**，封装目的 VTEP 设备”的 MAC 地址（ARP记录得到，“目的 VTEP 设备”的 IP 地址10.1.16.0找到“目的 VTEP 设备”的 mac地址，5e:f8:4f:00:e3:37）。    
 为了标识数据帧是VXLAN的数据帧，需要添加**VXLAN 头**，为了能在宿主机传送，需要再封装成为UDP包（内核态，node的ip由FDB得到，如“目的 VTEP 设备”（MAC 地址是 5e:f8:4f:00:e3:37）的二层数据帧，应该通过 flannel.1 设备，发往 IP 地址为 10.168.0.3 的主机，即发往 10.168.0.3是到10.1.16.0的下一个中转的ip ）  
 

**FDB**  
交换机从它的所有端口接收Media Access Control (MAC)地址信息，形成MAC地址表并维护它。当交换机收到一帧数据时，它将根据自己的MAC地址表来决定是将这帧数据进行过滤还是转发。此时，维护的这张MAC表就是FDB地址表。  

**FDB与ARP表**
ARP表：IP和MAC的对应关系；  
FDB表：MAC+VLAN和PORT的对应关系；  

两个最大的区别在于ARP是三层转发，FDB是用于二层转发。也就是说，就算两个设备不在一个网段或者压根没配IP，只要两者之间的链路层是连通的，就可以通过FDB表进行数据的转发！  

FDB表的最主要的作用就是在于交换机二层选路，试想，如果仅仅有ARP表，没有FDB表，就好像只知道地名和方位，而不知道经过哪条路才能到达目的地，设备是无法正常工作的。FDB表的作用就在于告诉设备从某个端口出去就可以到某个目的MAC。  

那么FDB表是怎么形成的呢？很简单，交换机会在收到数据帧时，提取数据帧中的源MAC、VLAN和接收数据帧的端口等组成FDB表的条目。当下次有到该VLAN中的该MAC的报文就直接从该端口丢出去就OK了。  

当然，FDB表和ARP表一样，都有一个老化时间。  


思考题
可以看到，Flannel 通过上述的“隧道”机制，实现了容器之间三层网络（IP 地址）的连通性。但
是，根据这个机制的工作原理，你认为 Flannel 能负责保证二层网络（MAC 地址）的连通性吗？
为什么呢？

