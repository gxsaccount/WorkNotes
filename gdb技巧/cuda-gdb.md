编译命令：  
nvcc –g –G program.cu –o program  

使用命令：
cuda-gdb 




当检测到 Cuda API 错误 : cudaMemcpy returned (0xb) 时如何查找程序在哪里崩溃：

(cuda-gdb) set cuda api_failures stop  
然后当发生错误时，它会停止:  
