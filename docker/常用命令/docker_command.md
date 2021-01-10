# 在docker环境中执行一个程序 #   
    
    Docker 以 ubuntu15.10 镜像创建一个新容器，然后在容器里执行 bin/echo "Hello world"，然后输出结果
    docker run ubuntu:15.10 /bin/echo "Hello world"  
    docker: Docker 的二进制执行文件。
    run: 与前面的 docker 组合来运行一个容器。
    ubuntu:15.10 指定要运行的镜像，Docker 首先从本地主机上查找镜像是否存在，如果不存在，Docker 就会从镜像仓库 Docker Hub 下载公共镜像。
    /bin/echo "Hello world": 在启动的容器里执行的命令
        
# 启动docker的bash（交互式容器） #  

    docker run -i -t ubuntu:15.10 /bin/bash 
    -t: 在新容器内指定一个伪终端或终端。
    -i: 允许你对容器内的标准输入 (STDIN) 进行交互。  
    
    通过运行 exit 命令或者使用 CTRL+D 来退出容器  
    
    
# 启动docker的后台模式 #  
    
    docker run -d ubuntu:15.10 /bin/sh -c "while true; do echo hello world; sleep 1; done"
    输出容器ID：2b1b7a428627c51ab8810d541d759f072b4fc75487eed05812646b8534a2fe63        


# 查看运行的容器 #  

        docker ps
        CONTAINER ID        IMAGE                  COMMAND              ...  
        5917eac21c36        ubuntu:15.10           "/bin/sh -c 'while t…"    ...
    
    
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

# 查看容器内的标准输出 #  

    docker logs 2b1b7a428627
    
    docker logs amazing_cori
    
# 停止docker #  

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
     
