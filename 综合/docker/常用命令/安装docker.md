https://blog.csdn.net/y353027520dx/article/details/88872643

在unbuntu上面安装docker肥肠简单。。首先确保自己的linux内核是3.10以上的版本
输入命令查看内核版本

uname -a
1
安装docker的命令很简单

sudo apt-get update
sudo apt-get install -y docker.io
1
2
安装的时间可能有一点长，请耐心等待。。。
安装完成后可能需要启动下。。

systemctl start docker
1
设置开机就启动docker

systemctl enable docker
1
查看docker是否安装成功

docker version
1

注意这里只显示了Client的信息，下面有一个报错: persission denied…，这个是因为我们安装的时候是用的sudo安装，在这里是没有权限连接docker的服务端，解决办法是把当前用户加入到docker组里面去。

首先新建一个docker组

sudo groupadd docker
1
但是很可能已经有了docker组了，已有的话就不用管了，继续下一步

然后把当前用户加入docker组

sudo gpasswd -a ${USER} docker
1
重启docker

sudo service docker restart
1
最后一步肥肠重要。。切换当前会话到新 group

newgrp - docker
1
最后一步是必须的，如果不切换，组信息不会立刻生效的。

最后测试下效果

docker version
1

最后的最后，因为国内网速问题，下载镜像比较慢所以可以使用国内大厂提供的加速器，我这里使用的是阿里云提供的加速器，使用镜像加速必须得改一下docker的配置文件 /etc/docker/daemon.json

sudo vim /etc/docker/daemon.json
1
在里面加入镜像加速器地址。。

{
  "registry-mirrors": ["https://vii0v3oj.mirror.aliyuncs.com"]
}
1
2
3
完美。。。。
————————————————
版权声明：本文为CSDN博主「迷失的蜗牛」的原创文章，遵循CC 4.0 BY-SA版权协议，转载请附上原文出处链接及本声明。
原文链接：https://blog.csdn.net/y353027520dx/article/details/88872643
