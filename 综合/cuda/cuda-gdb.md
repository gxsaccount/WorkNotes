http://developer.download.nvidia.com/compute/DevZone/docs/html/C/doc/cuda-gdb.pdf  

# 常用命令 #    
切换cuda线程：  
    
    cuda thread 20


查看share mem的值：  

    (cuda-gdb) print &array
    $1 = (@shared int (*)[0]) 0x20
    (cuda-gdb) print array[0]@4
    $2 = {0, 128, 64, 192}
    (cuda-gdb) print *(@shared int*)0x20
    $3 = 0
    (cuda-gdb) print *(@shared int*)0x24
    $4 = 128
    (cuda-gdb) print *(@shared int*)0x28
    $5 = 64
