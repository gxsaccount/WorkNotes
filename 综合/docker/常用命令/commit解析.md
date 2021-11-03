docker commit，实际上就是在容器运行起来后，把最上层的“可读写层”，加上原先容器镜
像的只读层，打包组成了一个新的镜像。当然，下面这些只读层在宿主机上是共享的，不会占用
额外的空间。
而由于使用了联合文件系统，你在容器里对镜像 rootfs 所做的任何修改，都会被操作系统先复
制到这个可读写层，然后再修改。这就是所谓的：Copy-on-Write。
而正如前所说，Init 层的存在，就是为了避免你执行 docker commit 时，把 Docker 自己对
/etc/hosts 等文件做的修改，也一起提交掉。
有了新的镜像，我们就可以把它推送到 Docker Hub 上了：
$ docker push geektime/helloworld:v2   

