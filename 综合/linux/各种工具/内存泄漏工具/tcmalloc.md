http://lemon0910.github.io/%E7%BC%96%E7%A8%8B/tcmalloc/#


https://blog.csdn.net/bqw2008/article/details/51439037


https://zhuanlan.zhihu.com/p/135571086


export PPROF_PATH=\*\*/gperftools-XX/src/pprof   
   



基本流程：  
1.长时间运行发现内存没有收敛，仍然有涨幅  
2.代码走查  
3.LD_PRELOAD=\*\*/gperftools-XX/.libs/libtcmalloc.so HEAPCHECK=normal  HEAPPROFILE=./save_prefix ./可执行程序     
4.使用pprof 查看  

    c版本  
    **/gperftools-2.8/src/pprof  --text --add_lib=程序运行的动态依赖库  --lines --base 内存快照base  ./可执行程序 内存快照对照组
    
    go版本，食用更佳  
    sudo apt install golang
    go get -u github.com/google/pprof
    **/go/bin/pprof -http 0.0.0.0:50000  --base 内存快照base  ./可执行程序 内存快照对照组   
    
    
https://gperftools.github.io/gperftools/heapprofile.html  
