- [基础命令](#----)
  * [在docker环境中执行一个程序](#-docker---------)
  * [启动docker的bash（交互式容器）](#--docker-bash-------)
  * [启动docker的后台模式](#--docker-----)
  * [查看运行的容器](#-------)
  * [查看容器内的标准输出](#----------)
- [容器使用](#----)
  * [获取镜像](#----)
  * [启动容器](#----)
  * [启动/重启已停止运行的容器](#-------------)
  * [进入容器](#----)
  * [导出和导入容器](#-------)
  * [删除容器](#----)
- [运行一个web应用程序](#----web----)
- [管理和使用本地 Docker 主机镜像](#--------docker-----)
  * [列出镜像列表](#------)
  * [查找镜像](#----)
  * [拖取/使用/删除镜像](#----------)
- [创建镜像](#----)
  * [更新镜像](#----)
  * [构建镜像](#----)
  * [设置镜像标签](#------)
- [Docker 容器连接](#docker-----)
- [Docker 容器互联](#docker-----)
  * [连接容器](#----)
  * [配置 DNS](#---dns)

<small><i><a href='http://ecotrust-canada.github.io/markdown-toc/'>Table of contents generated with markdown-toc</a></i></small>

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

# docker仓库管理 #  
仓库（Repository）是集中存放镜像的地方  

## Docker Hub ## 
目前 Docker 官方维护了一个公共仓库 Docker Hub。  
大部分需求都可以通过在 Docker Hub 中直接下载( https://hub.docker.com )镜像来实现。  

## 登录和退出 ##  
  docker login/docker logout  

## 拉取镜像 ##  
  docker search ubantu  
  docker pull ubantu  

## 推送镜像 ##  

   $ docker tag ubuntu:18.04 username/ubuntu:18.04
   $ docker image ls

   REPOSITORY      TAG        IMAGE ID            CREATED           ...  
   ubuntu          18.04      275d79972a86        6 days ago        ...  
   username/ubuntu 18.04      275d79972a86        6 days ago        ...  
   $ docker push username/ubuntu:18.04
   $ docker search username/ubuntu
   NAME             DESCRIPTION       STARS         OFFICIAL    AUTOMATED
   username/ubuntu

# Dockerfile #  
Dockerfile 是一个用来构建镜像的文本文件  
## 使用dockerfile定制化镜像 ##   
定制一个 nginx 镜像（构建好的镜像内会有一个 /usr/share/nginx/html/index.html 文件）  

  mkdir Dockerfile
  cd Dockerfile
  vi Dockerfile
  //在Dockerfile中添加一下内容
  FROM nginx
  RUN echo '这是一个本地构建的nginx镜像' > /usr/share/nginx/html/index.html


## FROM和RUN指令 ##  
FROM：定制的镜像都是基于 FROM 的镜像，这里的 nginx 就是定制需要的**基础镜像**。后续的操作都是基于 nginx。  
RUN：用于执行后面跟着的命令行命令。有以下俩种格式：  
**shell 格式：**  

  RUN <命令行命令>  
  # <命令行命令> 等同于，在终端操作的 shell 命令。
  
**exec 格式：**    

  RUN ["可执行文件", "参数1", "参数2"]
  例如：
  # RUN ["./test.php", "dev", "offline"] 等价于 RUN ./test.php dev offline
**实例**  
  
  FROM centos
  RUN yum install wget
  RUN wget -O redis.tar.gz "http://download.redis.io/releases/redis-5.0.3.tar.gz"
  RUN tar -xvf redis.tar.gz

**以上执行会创建 3 层镜像。可简化为以下格式：**

  FROM centos
  RUN yum install wget \
      && wget -O redis.tar.gz "http://download.redis.io/releases/redis-5.0.3.tar.gz" \
      && tar -xvf redis.tar.gz  
 
 **，以 && 符号连接命令，这样执行后，只会创建 1 层镜像,Dockerfile 的指令每执行一次都会在 docker 上新建一层。所以过多无意义的层，会造成镜像膨胀过大**  
 
 ## 开始构建镜像 ##  
 通过目录下的 Dockerfile 构建一个 nginx:v3（镜像名称:镜像标签）。 
 ：最后的 . 代表本次执行的上下文路径   
 **上下文路径**，是指 docker 在构建镜像，有时候想要使用到本机的文件（比如复制），docker build 命令得知这个路径后，会将路径下的所有内容打包  
  解析：由于 docker 的**运行模式是 C/S**。本机是 C，docker 引擎是 S。实际的构建过程是在 docker 引擎下完成的，所以这个时候无法用到我们本机的文件。这就需要把我们本机的指定目录下的文件一起打包提供给 docker 引擎使用。  
如果未说明最后一个参数，那么默认上下文路径就是 Dockerfile 所在的位置。  
    docker build -t nginx:v3 .  
   
 ## 指令详解 ##  
 
 指令详解
COPY
复制指令，从上下文目录中复制文件或者目录到容器里指定路径。

格式：

COPY [--chown=<user>:<group>] <源路径1>...  <目标路径>
COPY [--chown=<user>:<group>] ["<源路径1>",...  "<目标路径>"]
[--chown=<user>:<group>]：可选参数，用户改变复制到容器内文件的拥有者和属组。

<源路径>：源文件或者源目录，这里可以是通配符表达式，其通配符规则要满足 Go 的 filepath.Match 规则。例如：

COPY hom* /mydir/
COPY hom?.txt /mydir/
<目标路径>：容器内的指定路径，该路径不用事先建好，路径不存在的话，会自动创建。

ADD
ADD 指令和 COPY 的使用格式一致（同样需求下，官方推荐使用 COPY）。功能也类似，不同之处如下：

ADD 的优点：在执行 <源文件> 为 tar 压缩文件的话，压缩格式为 gzip, bzip2 以及 xz 的情况下，会自动复制并解压到 <目标路径>。
ADD 的缺点：在不解压的前提下，无法复制 tar 压缩文件。会令镜像构建缓存失效，从而可能会令镜像构建变得比较缓慢。具体是否使用，可以根据是否需要自动解压来决定。
CMD
类似于 RUN 指令，用于运行程序，但二者运行的时间点不同:

CMD 在docker run 时运行。
RUN 是在 docker build。
作用：为启动的容器指定默认要运行的程序，程序运行结束，容器也就结束。CMD 指令指定的程序可被 docker run 命令行参数中指定要运行的程序所覆盖。

注意：如果 Dockerfile 中如果存在多个 CMD 指令，仅最后一个生效。

格式：

CMD <shell 命令> 
CMD ["<可执行文件或命令>","<param1>","<param2>",...] 
CMD ["<param1>","<param2>",...]  # 该写法是为 ENTRYPOINT 指令指定的程序提供默认参数
推荐使用第二种格式，执行过程比较明确。第一种格式实际上在运行的过程中也会自动转换成第二种格式运行，并且默认可执行文件是 sh。

ENTRYPOINT
类似于 CMD 指令，但其不会被 docker run 的命令行参数指定的指令所覆盖，而且这些命令行参数会被当作参数送给 ENTRYPOINT 指令指定的程序。

但是, 如果运行 docker run 时使用了 --entrypoint 选项，此选项的参数可当作要运行的程序覆盖 ENTRYPOINT 指令指定的程序。

优点：在执行 docker run 的时候可以指定 ENTRYPOINT 运行所需的参数。

注意：如果 Dockerfile 中如果存在多个 ENTRYPOINT 指令，仅最后一个生效。

格式：

ENTRYPOINT ["<executeable>","<param1>","<param2>",...]
可以搭配 CMD 命令使用：一般是变参才会使用 CMD ，这里的 CMD 等于是在给 ENTRYPOINT 传参，以下示例会提到。

示例：

假设已通过 Dockerfile 构建了 nginx:test 镜像：

FROM nginx

ENTRYPOINT ["nginx", "-c"] # 定参
CMD ["/etc/nginx/nginx.conf"] # 变参 
1、不传参运行

$ docker run  nginx:test
容器内会默认运行以下命令，启动主进程。

nginx -c /etc/nginx/nginx.conf
2、传参运行

$ docker run  nginx:test -c /etc/nginx/new.conf
容器内会默认运行以下命令，启动主进程(/etc/nginx/new.conf:假设容器内已有此文件)

nginx -c /etc/nginx/new.conf
ENV
设置环境变量，定义了环境变量，那么在后续的指令中，就可以使用这个环境变量。

格式：

ENV <key> <value>
ENV <key1>=<value1> <key2>=<value2>...
以下示例设置 NODE_VERSION = 7.2.0 ， 在后续的指令中可以通过 $NODE_VERSION 引用：

ENV NODE_VERSION 7.2.0

RUN curl -SLO "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-x64.tar.xz" \
  && curl -SLO "https://nodejs.org/dist/v$NODE_VERSION/SHASUMS256.txt.asc"
ARG
构建参数，与 ENV 作用一至。不过作用域不一样。ARG 设置的环境变量仅对 Dockerfile 内有效，也就是说只有 docker build 的过程中有效，构建好的镜像内不存在此环境变量。

构建命令 docker build 中可以用 --build-arg <参数名>=<值> 来覆盖。

格式：

ARG <参数名>[=<默认值>]
VOLUME
定义匿名数据卷。在启动容器时忘记挂载数据卷，会自动挂载到匿名卷。

作用：

避免重要的数据，因容器重启而丢失，这是非常致命的。
避免容器不断变大。
格式：

VOLUME ["<路径1>", "<路径2>"...]
VOLUME <路径>
在启动容器 docker run 的时候，我们可以通过 -v 参数修改挂载点。

EXPOSE
仅仅只是声明端口。

作用：

帮助镜像使用者理解这个镜像服务的守护端口，以方便配置映射。
在运行时使用随机端口映射时，也就是 docker run -P 时，会自动随机映射 EXPOSE 的端口。
格式：

EXPOSE <端口1> [<端口2>...]
WORKDIR
指定工作目录。用 WORKDIR 指定的工作目录，会在构建镜像的每一层中都存在。（WORKDIR 指定的工作目录，必须是提前创建好的）。

docker build 构建镜像过程中的，每一个 RUN 命令都是新建的一层。只有通过 WORKDIR 创建的目录才会一直存在。

格式：

WORKDIR <工作目录路径>
USER
用于指定执行后续命令的用户和用户组，这边只是切换后续命令执行的用户（用户和用户组必须提前已经存在）。

格式：

USER <用户名>[:<用户组>]
HEALTHCHECK
用于指定某个程序或者指令来监控 docker 容器服务的运行状态。

格式：

HEALTHCHECK [选项] CMD <命令>：设置检查容器健康状况的命令
HEALTHCHECK NONE：如果基础镜像有健康检查指令，使用这行可以屏蔽掉其健康检查指令

HEALTHCHECK [选项] CMD <命令> : 这边 CMD 后面跟随的命令使用，可以参考 CMD 的用法。
ONBUILD
用于延迟构建命令的执行。简单的说，就是 Dockerfile 里用 ONBUILD 指定的命令，在本次构建镜像的过程中不会执行（假设镜像为 test-build）。当有新的 Dockerfile 使用了之前构建的镜像 FROM test-build ，这是执行新镜像的 Dockerfile 构建时候，会执行 test-build 的 Dockerfile 里的 ONBUILD 指定的命令。

格式：

ONBUILD <其它指令>
   
# Docker Compose #  
通过 Compose，可以使用 YML 文件来配置应用程序需要的所有服务。
   
  Compose 使用的三个步骤：
  使用 Dockerfile 定义应用程序的环境。
  使用 docker-compose.yml 定义构成应用程序的服务，这样它们可以在隔离环境中一起运行。
  最后，执行 docker-compose up 命令来启动并运行整个应用程序。

https://www.runoob.com/docker/docker-compose.html

##可选参数：##

endpoint_mode：访问集群服务的方式。

endpoint_mode: vip 
# Docker 集群服务一个对外的虚拟 ip。所有的请求都会通过这个虚拟 ip 到达集群服务内部的机器。
endpoint_mode: dnsrr
# DNS 轮询（DNSRR）。所有的请求会自动轮询获取到集群 ip 列表中的一个 ip 地址。
labels：在服务上设置标签。可以用容器上的 labels（跟 deploy 同级的配置） 覆盖 deploy 下的 labels。

mode：指定服务提供的模式。

replicated：复制服务，复制指定服务到集群的机器上。

global：全局服务，服务将部署至集群的每个节点。

图解：下图中黄色的方块是 replicated 模式的运行情况，灰色方块是 global 模式的运行情况。



replicas：mode 为 replicated 时，需要使用此参数配置具体运行的节点数量。

resources：配置服务器资源使用的限制，例如上例子，配置 redis 集群运行需要的 cpu 的百分比 和 内存的占用。避免占用资源过高出现异常。

restart_policy：配置如何在退出容器时重新启动容器。

condition：可选 none，on-failure 或者 any（默认值：any）。
delay：设置多久之后重启（默认值：0）。
max_attempts：尝试重新启动容器的次数，超出次数，则不再尝试（默认值：一直重试）。
window：设置容器重启超时时间（默认值：0）。
rollback_config：配置在更新失败的情况下应如何回滚服务。

parallelism：一次要回滚的容器数。如果设置为0，则所有容器将同时回滚。
delay：每个容器组回滚之间等待的时间（默认为0s）。
failure_action：如果回滚失败，该怎么办。其中一个 continue 或者 pause（默认pause）。
monitor：每个容器更新后，持续观察是否失败了的时间 (ns|us|ms|s|m|h)（默认为0s）。
max_failure_ratio：在回滚期间可以容忍的故障率（默认为0）。
order：回滚期间的操作顺序。其中一个 stop-first（串行回滚），或者 start-first（并行回滚）（默认 stop-first ）。
update_config：配置应如何更新服务，对于配置滚动更新很有用。

parallelism：一次更新的容器数。
delay：在更新一组容器之间等待的时间。
failure_action：如果更新失败，该怎么办。其中一个 continue，rollback 或者pause （默认：pause）。
monitor：每个容器更新后，持续观察是否失败了的时间 (ns|us|ms|s|m|h)（默认为0s）。
max_failure_ratio：在更新过程中可以容忍的故障率。
order：回滚期间的操作顺序。其中一个 stop-first（串行回滚），或者 start-first（并行回滚）（默认stop-first）。
注：仅支持 V3.4 及更高版本。

devices
指定设备映射列表。

devices:
  - "/dev/ttyUSB0:/dev/ttyUSB0"
dns
自定义 DNS 服务器，可以是单个值或列表的多个值。

dns: 8.8.8.8

dns:
  - 8.8.8.8
  - 9.9.9.9
dns_search
自定义 DNS 搜索域。可以是单个值或列表。

dns_search: example.com

dns_search:
  - dc1.example.com
  - dc2.example.com
entrypoint
覆盖容器默认的 entrypoint。

entrypoint: /code/entrypoint.sh
也可以是以下格式：

entrypoint:
    - php
    - -d
    - zend_extension=/usr/local/lib/php/extensions/no-debug-non-zts-20100525/xdebug.so
    - -d
    - memory_limit=-1
    - vendor/bin/phpunit
env_file
从文件添加环境变量。可以是单个值或列表的多个值。

env_file: .env
也可以是列表格式：

env_file:
  - ./common.env
  - ./apps/web.env
  - /opt/secrets.env
environment
添加环境变量。您可以使用数组或字典、任何布尔值，布尔值需要用引号引起来，以确保 YML 解析器不会将其转换为 True 或 False。

environment:
  RACK_ENV: development
  SHOW: 'true'
expose
暴露端口，但不映射到宿主机，只被连接的服务访问。

仅可以指定内部端口为参数：

expose:
 - "3000"
 - "8000"
extra_hosts
添加主机名映射。类似 docker client --add-host。

extra_hosts:
 - "somehost:162.242.195.82"
 - "otherhost:50.31.209.229"
以上会在此服务的内部容器中 /etc/hosts 创建一个具有 ip 地址和主机名的映射关系：

162.242.195.82  somehost
50.31.209.229   otherhost
healthcheck
用于检测 docker 服务是否健康运行。

healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost"] # 设置检测程序
  interval: 1m30s # 设置检测间隔
  timeout: 10s # 设置检测超时时间
  retries: 3 # 设置重试次数
  start_period: 40s # 启动后，多少秒开始启动检测程序
image
指定容器运行的镜像。以下格式都可以：

image: redis
image: ubuntu:14.04
image: tutum/influxdb
image: example-registry.com:4000/postgresql
image: a4bc65fd # 镜像id
logging
服务的日志记录配置。

driver：指定服务容器的日志记录驱动程序，默认值为json-file。有以下三个选项

driver: "json-file"
driver: "syslog"
driver: "none"
仅在 json-file 驱动程序下，可以使用以下参数，限制日志得数量和大小。

logging:
  driver: json-file
  options:
    max-size: "200k" # 单个文件大小为200k
    max-file: "10" # 最多10个文件
当达到文件限制上限，会自动删除旧得文件。

syslog 驱动程序下，可以使用 syslog-address 指定日志接收地址。

logging:
  driver: syslog
  options:
    syslog-address: "tcp://192.168.0.42:123"
network_mode
设置网络模式。

network_mode: "bridge"
network_mode: "host"
network_mode: "none"
network_mode: "service:[service name]"
network_mode: "container:[container name/id]"
networks

配置容器连接的网络，引用顶级 networks 下的条目 。

services:
  some-service:
    networks:
      some-network:
        aliases:
         - alias1
      other-network:
        aliases:
         - alias2
networks:
  some-network:
    # Use a custom driver
    driver: custom-driver-1
  other-network:
    # Use a custom driver which takes special options
    driver: custom-driver-2
aliases ：同一网络上的其他容器可以使用服务名称或此别名来连接到对应容器的服务。

restart
no：是默认的重启策略，在任何情况下都不会重启容器。
always：容器总是重新启动。
on-failure：在容器非正常退出时（退出状态非0），才会重启容器。
unless-stopped：在容器退出时总是重启容器，但是不考虑在Docker守护进程启动时就已经停止了的容器
restart: "no"
restart: always
restart: on-failure
restart: unless-stopped
注：swarm 集群模式，请改用 restart_policy。

secrets
存储敏感数据，例如密码：

version: "3.1"
services:

mysql:
  image: mysql
  environment:
    MYSQL_ROOT_PASSWORD_FILE: /run/secrets/my_secret
  secrets:
    - my_secret

secrets:
  my_secret:
    file: ./my_secret.txt
security_opt
修改容器默认的 schema 标签。

security-opt：
  - label:user:USER   # 设置容器的用户标签
  - label:role:ROLE   # 设置容器的角色标签
  - label:type:TYPE   # 设置容器的安全策略标签
  - label:level:LEVEL  # 设置容器的安全等级标签
stop_grace_period
指定在容器无法处理 SIGTERM (或者任何 stop_signal 的信号)，等待多久后发送 SIGKILL 信号关闭容器。

stop_grace_period: 1s # 等待 1 秒
stop_grace_period: 1m30s # 等待 1 分 30 秒 
默认的等待时间是 10 秒。

stop_signal
设置停止容器的替代信号。默认情况下使用 SIGTERM 。

以下示例，使用 SIGUSR1 替代信号 SIGTERM 来停止容器。

stop_signal: SIGUSR1
sysctls
设置容器中的内核参数，可以使用数组或字典格式。

sysctls:
  net.core.somaxconn: 1024
  net.ipv4.tcp_syncookies: 0

sysctls:
  - net.core.somaxconn=1024
  - net.ipv4.tcp_syncookies=0
tmpfs
在容器内安装一个临时文件系统。可以是单个值或列表的多个值。

tmpfs: /run

tmpfs:
  - /run
  - /tmp
ulimits
覆盖容器默认的 ulimit。

ulimits:
  nproc: 65535
  nofile:
    soft: 20000
    hard: 40000
volumes
将主机的数据卷或着文件挂载到容器里。

version: "3.7"
services:
  db:
    image: postgres:latest
    volumes:
      - "/localhost/postgres.sock:/var/run/postgres/postgres.sock"
      - "/localhost/data:/var/lib/postgresql/data"

 
 # Docker Machine #   
Docker Machine 是一种可以让您在虚拟主机上安装 Docker 的工具，并可以使用 docker-machine 命令来管理主机。
Docker Machine 也可以集中管理所有的 docker 主机，比如快速的给 100 台服务器安装上 docker。
 https://www.runoob.com/docker/docker-machine.html
 
 # Swarm 集群管理 #  
 Docker Swarm 是 Docker 的集群管理工具。它将 Docker 主机池转变为单个虚拟 Docker 主机。 Docker Swarm 提供了标准的 Docker API，所有任何已经与 Docker 守护程序通信的工具都可以使用 Swarm 轻松地扩展到多个主机。

支持的工具包括但不限于以下各项：

Dokku
Docker Compose
Docker Machine
Jenkins
 
 
 https://www.runoob.com/docker/docker-swarm.html
