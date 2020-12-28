有coredump，有sdk相关信息 gdb
有coredump，没有sdk相关信息，上delve（可能是go的锅）
没有coredump，没有sdk相关信息 delve attach/gdb attach（爱干嘛干嘛）  

崩在了系统函数中如pthread库 close_log之类（开始甩锅）
首先判断sdk是否调用该类型函数，如果调用那没事了可能是sdk的问题
没有调用，查看core镜像中哪个so用了 进入 /opt/megvii/lib
ls *.so | xargs -I{} bash -c  'readelf -sW {} | grep xxx' #  xxx是 系统调用函数名，可以搜索系统调用最上层api，如timer_helper_thead 应用层api为timer_create
