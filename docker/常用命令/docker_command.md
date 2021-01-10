# 在docker环境中执行一个程序 #  
    
    Docker 以 ubuntu15.10 镜像创建一个新容器，然后在容器里执行 bin/echo "Hello world"，然后输出结果
    docker run ubuntu:15.10 /bin/echo "Hello world"  
    docker: Docker 的二进制执行文件。
    run: 与前面的 docker 组合来运行一个容器。
    ubuntu:15.10 指定要运行的镜像，Docker 首先从本地主机上查找镜像是否存在，如果不存在，Docker 就会从镜像仓库 Docker Hub 下载公共镜像。
    /bin/echo "Hello world": 在启动的容器里执行的命令
        
# 启动docker的bash #  

    docker run -i -t ubuntu:15.10 /bin/bash 
    -t: 在新容器内指定一个伪终端或终端。
    -i: 允许你对容器内的标准输入 (STDIN) 进行交互。  
    
    通过运行 exit 命令或者使用 CTRL+D 来退出容器  
    
    

