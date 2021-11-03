容器技术使用了 rootfs 机制和 Mount Namespace，构建出了一个同宿主  
机完全隔离开的文件系统环境。这时候，我们就需要考虑这样两个问题：  
1. 容器里进程新建的文件，怎么才能让宿主机获取到？  
2. 宿主机上的文件和目录，怎么才能让容器里的进程访问到？  
这正是 Docker Volume 要解决的问题：Volume 机制，允许你将宿主机上指定的目录或者文件，挂载到容器里面进行读取和修改操作。   

在 Docker 项目里，它支持两种 Volume 声明方式，可以把宿主机目录挂载进容器的 /test 目
录当中：  

    $ docker run -v /test ... 
    $ docker run -v /home:/test ...  
    
而这两种声明方式的本质，实际上是相同的：都是把一个宿主机的目录挂载进了容器的 /test 目
录。  
只不过，在第一种情况下，由于你并没有显示声明宿主机目录，那么 Docker 就会默认在宿主机
上创建一个临时目录 /var/lib/docker/volumes/[VOLUME_ID]/_data，然后把它挂载到容器的
/test 目录上。而在第二种情况下，Docker 就直接把宿主机的 /home 目录挂载到容器的 /test
目录上    
**Docker如何把一个宿主机上的目录或者文件挂载到容器**  
当容器进程(dockerinit)被创建之后，尽管开启了 Mount Namespace，但是在它执行 chroot（或者 pivot_root）之前，容器进
程一直可以看到宿主机上的整个文件系统。  
而宿主机上的文件系统，也自然包括了我们要使用的容器镜像。这个镜像的各个层，保存在
/var/lib/docker/aufs/diff 目录下，在容器进程启动后，它们会被联合挂载在
/var/lib/docker/aufs/mnt/ 目录中，这样容器所需的 rootfs 就准备好了。
所以，我们只需要**在 rootfs 准备好之后，在执行 chroot 之前**，把 Volume 指定的宿主机目录
（比如 /home 目录），挂载到指定的容器目录（比如 /test 目录）在宿主机上对应的目录（即
/var/lib/docker/aufs/mnt/[**可读写层**ID]/test）上，这个 Volume 的挂载工作就完成了。
更重要的是，由于执行这个挂载操作时，“容器进程”已经创建了，也就意味着此时 Mount
Namespace 已经开启了。所以，这个挂载事件只在这个容器里可见。你在宿主机上，是看不见
容器内部的这个挂载点的。这就保证了容器的隔离性不会被 Volume 打破。  

注意：这里提到的 " 容器进程 "，是 Docker 创建的一个容器初始化进程
(dockerinit)，而不是应用进程 (ENTRYPOINT + CMD)。dockerinit 会负责完成
根目录的准备、挂载设备和目录、配置 hostname 等一系列需要在容器内进行的
初始化操作。最后，它通过 execv() 系统调用，让应用进程取代自己，成为容器里
的 PID=1 的进程  

而这里要使用到的挂载技术，就是 Linux 的绑定挂载（Bind Mount）机制。它的主要作用就
是，允许你将一个目录或者文件，而不是整个设备，挂载到一个指定的目录上。并且，这时你在
该挂载点上进行的任何操作，只是发生在被挂载的目录或者文件上，而原挂载点的内容则会被隐
藏起来且不受影响。  

##绑定挂载##  
如果你了解 Linux 内核的话，就会明白，绑定挂载实际上是一个 inode 替换的过程。在
Linux 操作系统中，inode 可以理解为存放文件内容的“对象”，而 dentry，也叫目录项，就
是访问这个 inode 所使用的“指针”。   
![image](https://user-images.githubusercontent.com/20179983/140018651-546990af-d929-4476-8c6c-ef769964cf09.png)
正如上图所示，mount --bind /home /test，会将 /home 挂载到 /test 上。其实相当于将
/test 的 dentry，重定向到了 /home 的 inode。这样当我们修改 /test 目录时，实际修改的是
/home 目录的 inode。这也就是为何，一旦执行 umount 命令，/test 目录原先的内容就会恢
复：因为修改真正发生在的，是 /home 目录里。  
所以，在一个正确的时机，进行一次绑定挂载，Docker 就可以成功地将一个宿主机上的目录或
文件，不动声色地挂载到容器中。  
这样，进程在容器里对这个 /test 目录进行的所有操作，都实际发生在宿主机的对应目录（比
如，/home，或者 /var/lib/docker/volumes/[VOLUME_ID]/_data）里，而不会影响容器镜像
的内容。  
那么，这个 /test 目录里的内容，既然挂载在容器 rootfs 的可读写层，它会不会被 docker
commit 提交掉呢？  
也不会。  
这个原因其实我们前面已经提到过。容器的镜像操作，比如 docker commit，都是发生在宿主
机空间的。而由于 Mount Namespace 的隔离作用，宿主机并不知道这个绑定挂载的存在。所
以，在宿主机看来，容器中可读写层的 /test 目录（/var/lib/docker/aufs/mnt/[可读写层
ID]/test），始终是空的。  
不过，由于 Docker 一开始还是要创建 /test 这个目录作为挂载点，所以执行了 docker
commit 之后，你会发现新产生的镜像里，会多出来一个空的 /test 目录。毕竟，新建目录操
作，又不是挂载操作，Mount Namespace 对它可起不到“障眼法”的作用  

