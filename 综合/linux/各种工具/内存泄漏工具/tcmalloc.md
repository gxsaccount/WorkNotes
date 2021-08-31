http://lemon0910.github.io/%E7%BC%96%E7%A8%8B/tcmalloc/#


https://blog.csdn.net/bqw2008/article/details/51439037


https://zhuanlan.zhihu.com/p/135571086


export PPROF_PATH=\*\*/gperftools-XX/src/pprof   
LD_PRELOAD=\*\*/gperftools-XX/.libs/libtcmalloc.so HEAPCHECK=normal ./yourapp    
