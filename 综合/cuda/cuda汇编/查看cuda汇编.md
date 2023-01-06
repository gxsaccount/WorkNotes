1.生成cubin文件  

nvcc -cubin xxx.cu

2.查看sass汇编结果：cuobjdump -sass  
cuobjdump -sass xxx.cubin

2.查看ptx汇编结果：cuobjdump -ptx   
cuobjdump -sass xxx
