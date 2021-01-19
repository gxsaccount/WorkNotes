[toc]

# 基础命令 #  
## 在docker环境中执行一个程序 ##   
    
    Docker 以 ubuntu15.10 镜像创建一个新容器，然后在容器里执行 bin/echo "Hello world"，然后输出结果
    docker run ubuntu:15.10 /bin/echo "Hello world"  
    docker: Docker 的二进制执行文件。
    run: 与前面的 docker 组合来运行一个容器。
    ubuntu:15.10 指定要运行的镜像，Docker 首先从本地主机上查找镜像是否存在，如果不存在，Docker 就会从镜像仓库 Docker Hub 下载公共镜像。
    /bin/echo "Hello world": 在启动的容器里执行的命令
    
    当我们创建一个容器的时候，docker 会自动对它进行命名。另外，我们也可以使用 --name 标识来命名容器，例如：
    runoob@runoob:~$  docker run -d -P --name runoob training/webapp python app.py
    43780a6eabaaf14e590b6e849235c75f3012995403f97749775e38436db9a441
    我们可以使用 docker ps 命令来查看容器名称。
    runoob@runoob:~$ docker ps -l
    CONTAINER ID     IMAGE            COMMAND           ...    PORTS                     NAMES
    43780a6eabaa     training/webapp   "python app.py"  ...     0.0.0.0:32769->5000/tcp   runoob

## 启动docker的bash（交互式容器） ##  

    docker run -i -t ubuntu:15.10 /bin/bash 
    -t: 在新容器内指定一个伪终端或终端。
    -i: 允许你对容器内的标准输入 (STDIN) 进行交互。  
    
    通过运行 exit 命令或者使用 CTRL+D 来退出容器  
    
    
## 启动docker的后台模式 ##  
    
    docker run -d ubuntu:15.10 /bin/sh -c "while true; do echo hello world; sleep 1; done"
    输出容器ID：2b1b7a428627c51ab8810d541d759f072b4fc75487eed05812646b8534a2fe63        


## 查看运行的容器 ##  

        docker ps
        CONTAINER ID        IMAGE                  COMMAND              ...  
        5917eac21c36        ubuntu:15.10           "/bin/sh -c 'while t…"    ...
        
        docker ps -l 查询最后一次创建的容器
    
输出详情介绍：
CONTAINER ID: 容器 ID。
IMAGE: 使用的镜像。
COMMAND: 启动容器时运行的命令。
CREATED: 容器的创建时间。
STATUS: 容器状态。

        状态有7种：
        created（已创建）
        restarting（重启中）
        running 或 Up（运行中）
        removing（迁移中）
        paused（暂停）
        exited（停止）
        dead（死亡）
PORTS: 容器的端口信息和使用的连接类型（tcp\udp）。
NAMES: 自动分配的容器名称。  

## 查看容器内的标准输出 ##  
    #docker logs [ID或者名字] 
    # -f: 让 docker logs 像使用 tail -f 一样来输出容器内部的标准输出
    docker logs -f 2b1b7a428627
    docker logs amazing_cori
    
#3 停止docker ##  

    docker stop amazing_cori
    
# 容器使用 #  
## 获取镜像 ##      
    docker pull ubantu
## 启动容器 ##  
    docker run -it ubuntu /bin/bash   
    
    参数说明：
        -i: 交互式操作。
        -t: 终端。
        ubuntu: ubuntu 镜像。
        /bin/bash：放在镜像名后的是命令，这里我们希望有个交互式 Shell，因此用的是 /bin/bash  
            
    
## 启动/重启已停止运行的容器  ##  
    docker start b750bbbcfd88 
    docker restart b750bbbcfd88 

## 进入容器 ##  
    在使用 -d 参数时，容器启动后会进入后台。此时想要进入容器，可以通过以下指令进入：
    docker attach:如果从这个容器退出，会导致容器的停止
    docker exec：推荐大家使用 docker exec 命令，因为此退出容器终端，不会导致容器的停止。

## 导出和导入容器 ##  
    # 导出   
    docker export 1e560fca3906 > ubuntu.tar  
    # 导入/通过url导入   
    cat docker/ubuntu.tar | docker import - test/ubuntu:v1
    docker import http://example.com/exampleimage.tgz example/imagerepo  
    
## 删除容器 ##  
     docker rm -f 1e560fca3906  
     
# 运行一个web应用程序 #  

     docker pull training/webapp  # 载入镜像
     docker run -d -P training/webapp python app.py #-d:让容器在后台运行，-P:将容器内部使用的网络端口随机映射到我们使用的主机上  
     
     docker ps #查看正在运行的容器信息  
     CONTAINER ID        IMAGE               COMMAND             ...        PORTS                 
     d3d5e39ed9d3        training/webapp     "python app.py"     ...        0.0.0.0:32769->5000/tcp
     #PORTS结果：Docker 开放了 5000 端口（默认 Python Flask 端口）映射到主机端口 32769 上  
     #可以通过在浏览器localhost:32769访问该程序  
     #也可以用docker port bf08b7f2cd89 或 docker port wizardly_chandrasekhar 来查看容器端口的映射情况
     
     #可以通过 -p 参数来设置不一样的端口：  
     docker run -d -p 5000:5000 training/webapp python app.py   
     
     #使用 docker top 来查看容器内部运行的进程  
     runoob@runoob:~$ docker top wizardly_chandrasekhar
     UID     PID         PPID          ...       TIME                CMD
     root    23245       23228         ...       00:00:00            python app.py  
     
     #查看docker的底层信息
     docker inspect wizardly_chandrasekhar  
     
     
     
     
# 管理和使用本地 Docker 主机镜像 #  

## 列出镜像列表 ##  
    docker images 
    runoob@runoob:~$ docker images           
    REPOSITORY          TAG                 IMAGE ID            CREATED             SIZE
    ubuntu              14.04               90d5884b1ee0        5 days ago          188 MB
    
    #参数说明
    REPOSITORY：表示镜像的仓库源
    TAG：镜像的标签
    IMAGE ID：镜像ID
    CREATED：镜像创建时间
    SIZE：镜像大小  


同一仓库源可以有多个 TAG，代表这个仓库源的不同个版本，如 ubuntu 仓库源里，有 15.10、14.04 等多个不同的版本，我们使用 REPOSITORY:TAG 来定义不同的镜像。

    使用版本为15.10的ubuntu系统镜像来运行容器时，命令如下
    docker run -t -i ubuntu:15.10 /bin/bash 
    
## 查找镜像 ##  
可以使用 docker search 命令来搜索镜像。比如我们需要一个 httpd 的镜像来作为我们的 web 服务。我们可以通过 docker search 命令搜索 httpd 来寻找适合我们的镜像
    
    docker search httpd  
    
## 拖取/使用/删除镜像 ##  
    docker pull httpd
    docker run httpd
    docker rmi hello-world
# 创建镜像 #  
当我们从 docker 镜像仓库中下载的镜像不能满足我们的需求时，我们可以通过以下两种方式对镜像进行更改。  
1、从已经创建的容器中更新镜像，并且提交这个镜像  
2、使用 Dockerfile 指令来创建一个新的镜像  



## 更新镜像 ##   
更新镜像之前，我们需要使用镜像来创建一个容器。
    
    docker run -t -i runoob/ubuntu:v2 /bin/bash  
    
在运行的容器内使用 apt-get update 命令进行更新。
在完成操作之后，输入 exit 命令来退出这个容器。
此时 ID 为 e218edb10161 的容器，是按我们的需求更改的容器。我们可以通过命令 docker commit 来提交容器副本。  

    docker commit -m="has update" -a="runoob" e218edb10161 runoob/ubuntu:v2
    sha256:70bf1840fd7c0d2d8ef0a42a817eb29f854c1af8f7c59fc03ac7bdee9545aff8
    
    各个参数说明：
    -m: 提交的描述信息
    -a: 指定镜像作者
    e218edb10161：容器 ID
    runoob/ubuntu:v2: 指定要创建的目标镜像名  
 
使用我们的新镜像 runoob/ubuntu 来启动一个容器  
    
    docker run -t -i runoob/ubuntu:v2 /bin/bash  
 
## 构建镜像 ##  
使用命令 docker build ， 从零开始来创建一个新的镜像。为此，我们需要创建一个 Dockerfile 文件，其中包含一组指令来告诉 Docker 如何构建我们的镜像  

    cat Dockerfile 
    FROM    centos:6.7
    MAINTAINER      Fisher "fisher@sudops.com"

    RUN     /bin/echo 'root:123456' |chpasswd
    RUN     useradd runoob
    RUN     /bin/echo 'runoob:123456' |chpasswd
    RUN     /bin/echo -e "LANG=\"en_US.UTF-8\"" >/etc/default/local
    EXPOSE  22
    EXPOSE  80
    CMD     /usr/sbin/sshd -D
    
    FROM，指定使用哪个镜像源
    RUN 指令告诉docker 在镜像内执行命令   
 使用 Dockerfile 文件，通过 docker build 命令来构建一个镜像   
    docker build -t runoob/centos:6.7 .  
    参数说明：
    -t ：指定要创建的目标镜像名
    . ：Dockerfile 文件所在目录，可以指定Dockerfile 的绝对路径   
  
  ## 设置镜像标签 ##  
  使用 docker tag 命令，为镜像添加一个新的标签  
    
    docker tag 860c279d2fec runoob/centos:dev  
  
docker tag 镜像ID，这里是 860c279d2fec ,用户名称、镜像源名(repository name)和新的标签名(tag)。
使用 docker images 命令可以看到，ID为860c279d2fec的镜像多一个标签  
    
    docker images
    REPOSITORY          TAG                 IMAGE ID            CREATED             SIZE
    runoob/centos       6.7                 860c279d2fec        5 hours ago         190.6 MB
    runoob/centos       dev                 860c279d2fec        5 hours ago         190.6 MB  
    
# Docker 容器连接 #  

    docker run -d -P training/webapp python app.py  
    -P :是容器内部端口随机映射到主机的高端口。
    -p : 是容器内部端口绑定到指定的主机端口。  

可以指定容器绑定的网络地址，比如绑定 127.0.0.1。  

    docker run -d -p 127.0.0.1:5001:5000 training/webapp python app.py  
可以通过访问 127.0.0.1:5001 来访问容器的 5000 端口  

默认都是绑定 tcp 端口，如果要绑定 UDP 端口，可以在端口后面加上 /udp    
    
    docker run -d -p 127.0.0.1:5000:5000/udp training/webapp python app.py  
    
docker port 命令可以让我们快捷地查看端口的绑定情况  
    docker port adoring_stonebraker 5000  

# Docker 容器互联 #  
端口映射并不是唯一把 docker 连接到另一个容器的方法。
docker 有一个连接系统允许将多个容器连接在一起，共享连接信息。
docker 连接会创建一个父子关系，其中父容器可以看到子容器的信息。  
##新建网络##  

    docker network create -d bridge test-net    
    参数说明：  
    -d：参数指定 Docker 网络类型，有 bridge、overlay。  
    其中 overlay 网络类型用于 Swarm mode。  

## 连接容器 ##  

    #运行一个容器并连接到新建的 test-net 网络:
    $ docker run -itd --name test1 --network test-net ubuntu /bin/bash
    #打开新的终端，再运行一个容器并加入到 test-net 网络:
    $ docker run -itd --name test2 --network test-net ubuntu /bin/bash
    通过 ping 来证明 test1 容器和 test2 容器建立了互联关系  
    
    apt-get update
    apt install iputils-ping  
    
## 配置 DNS ##  

    #我们可以在宿主机的 /etc/docker/daemon.json 文件中增加以下内容来设置全部容器的 DNS：
    {
      "dns" : [
        "114.114.114.114",
        "8.8.8.8"
      ]
    }
    设置后，启动容器的 DNS 会自动配置为 114.114.114.114 和 8.8.8.8。
    配置完，需要重启 docker 才能生效。
    查看容器的 DNS 是否生效可以使用以下命令，它会输出容器的 DNS 信息：
    $ docker run -it --rm  ubuntu  cat etc/resolv.conf
    
    如果只想在指定的容器设置 DNS，则可以使用以下命令：
    $ docker run -it --rm -h host_ubuntu  --dns=114.114.114.114 --dns-search=test.com ubuntu  
    
    参数说明：

    --rm：容器退出时自动清理容器内部的文件系统。
    -h HOSTNAME 或者 --hostname=HOSTNAME： 设定容器的主机名，它会被写到容器内的 /etc/hostname 和 /etc/hosts。
    --dns=IP_ADDRESS： 添加 DNS 服务器到容器的 /etc/resolv.conf 中，让容器用这个服务器来解析所有不在 /etc/hosts 中的主机名。
    --dns-search=DOMAIN： 设定容器的搜索域，当设定搜索域为 .example.com 时，在搜索一个名为 host 的主机时，DN不仅搜索 host，还会搜索 host.example.com。
    如果在容器启动时没有指定 --dns 和 --dns-search，Docker 会默认用宿主主机上的 /etc/resolv.conf 来配置容器的 DNS。

