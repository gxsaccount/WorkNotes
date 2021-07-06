当cache（swap）缓存占用太大，服务起不来，需要查看清理缓存  
项目现象：服务的cpu占用很高，长时间稳定性出现ssh连不上，服务卡死现象。长时间清理cache缓存操作系统回收内存碎片暂用较大耗时。  
查看缓存：  
free -m  
输入运行下面一行：  

操作系统时刻监控/proc/sys/vm/drop_caches文件，将3写入触发清空缓存，使用Inotify 进行监控
echo 3 > /proc/sys/vm/drop_caches
![image](https://user-images.githubusercontent.com/20179983/113653678-e08e9b80-96c8-11eb-8ba9-5acf3c6476d5.png)

# 释放缓存区内存的方法

1）清理pagecache（页面缓存）

# echo 1 > /proc/sys/vm/drop_caches     或者 # sysctl -w vm.drop_caches=1

2）清理dentries（目录缓存）和inodes

# echo 2 > /proc/sys/vm/drop_caches     或者 # sysctl -w vm.drop_caches=2

3）清理pagecache、dentries和inodes

# echo 3 > /proc/sys/vm/drop_caches     或者 # sysctl -w vm.drop_caches=3

注：上面三种方式都是临时释放缓存的方法，要想永久释放缓存，需要在/etc/sysctl.conf文件中配置：vm.drop_caches=1/2/3，然后sysctl -p生效即可！
