https://docs.nvidia.com/cuda/cuda-compiler-driver-nvcc/index.html#cuda-compilation-trajectory__cuda-compilation-from-cu-to-executable  

cuda程序有两种代码，一种是运行在cpu上的host代码，一种是运行在gpu上的device代码，所以NVCC编译器要保证两部分代码能够编译成二进制文件在不同的机器上执行。  
文件后缀名表格：  
![image](https://user-images.githubusercontent.com/20179983/126259248-49f22877-de62-4214-b82f-e4957a01c731.png)

cuda的整个编译流程分成两个分支，分支1预处理device代码并进行编译生成cubin或者ptx，然后整合到二进制文件fatbin中，分支2预处理host代码，再和fatbin一起生成目标文件  
![image](https://user-images.githubusercontent.com/20179983/126258917-1f59ecb5-aad5-4779-8c29-0ca08a14d7bc.png)  

NVCC实际上调用了很多工具来完成编译步骤  
通过如下命令可以查看编译过程：
    
    nvcc --cuda test.cu -keep --dryrun  
    
    //输出
    #$ _SPACE_=
    #$ _CUDART_=cudart
    #$ _HERE_=/usr/local/cuda/bin
    #$ _THERE_=/usr/local/cuda/bin
    #$ _TARGET_SIZE_=
    #$ _TARGET_DIR_=
    #$ _TARGET_DIR_=targets/x86_64-linux
    #$ TOP=/usr/local/cuda/bin/..
    #$ NVVMIR_LIBRARY_DIR=/usr/local/cuda/bin/../nvvm/libdevice
    #$ LD_LIBRARY_PATH=/usr/local/cuda/bin/../lib:/usr/local/clang_9.0.0/lib:
    #$ PATH=/usr/local/cuda/bin/../nvvm/bin:/usr/local/cuda/bin:/usr/local/cuda/bin:/home/gaoxiang/anaconda3/bin:/usr/local/clang_9.0.0/bin:/home/gaoxiang/bin:/home/gaoxiang/.local/bin:/home/gaoxiang/anaconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin
    #$ INCLUDES="-I/usr/local/cuda/bin/../targets/x86_64-linux/include"
    #$ LIBRARIES=  "-L/usr/local/cuda/bin/../targets/x86_64-linux/lib/stubs" "-L/usr/local/cuda/bin/../targets/x86_64-linux/lib"
    #$ CUDAFE_FLAGS=
    #$ PTXAS_FLAGS=
    --------------------------------------------------------编译---------------------------------------------------------------
    #$ gcc -D__CUDA_ARCH__=300 -E -x c++  -DCUDA_DOUBLE_MATH_FUNCTIONS -D__CUDACC__ -D__NVCC__  "-I/usr/local/cuda/bin/../targets/x86_64-linux/include"    -D__CUDACC_VER_MAJOR__=10 -D__CUDACC_VER_MINOR__=1 -D__CUDACC_VER_BUILD__=168 -include "cuda_runtime.h" -m64 "test.cu" > "test.cpp1.ii"
    #$ cicc --c++14 --gnu_version=60500 --allow_managed   -arch compute_30 -m64 -ftz=0 -prec_div=1 -prec_sqrt=1 -fmad=1 --include_file_name "test.fatbin.c" -tused -nvvmir-library "/usr/local/cuda/bin/../nvvm/libdevice/libdevice.10.bc" --gen_module_id_file --module_id_file_name "test.module_id" --orig_src_file_name "test.cu" --gen_c_file_name "test.cudafe1.c" --stub_file_name "test.cudafe1.stub.c" --gen_device_file_name "test.cudafe1.gpu"  "test.cpp1.ii" -o "test.ptx"
    #$ ptxas -arch=sm_30 -m64  "test.ptx"  -o "test.sm_30.cubin"
    #$ fatbinary --create="test.fatbin" -64 "--image=profile=sm_30,file=test.sm_30.cubin" "--image=profile=compute_30,file=test.ptx" --embedded-fatbin="test.fatbin.c"
    #$ gcc -E -x c++ -D__CUDACC__ -D__NVCC__  "-I/usr/local/cuda/bin/../targets/x86_64-linux/include"    -D__CUDACC_VER_MAJOR__=10 -D__CUDACC_VER_MINOR__=1 -D__CUDACC_VER_BUILD__=168 -include "cuda_runtime.h" -m64 "test.cu" > "test.cpp4.ii"
    #$ cudafe++ --c++14 --gnu_version=60500 --allow_managed  --m64 --parse_templates --gen_c_file_name "test.cudafe1.cpp" --stub_file_name "test.cudafe1.stub.c" --module_id_file_name "test.module_id" "test.cpp4.ii"
    #$ gcc -E -x c++ -D__CUDA_FTZ=0 -D__CUDA_PREC_DIV=1 -D__CUDA_PREC_SQRT=1 "-I/usr/local/cuda/bin/../targets/x86_64-linux/include"   -m64 "test.cudafe1.cpp" > "test.cu.cpp.ii"  
    
1.
    
    gcc -D__CUDA_ARCH__=200 -E -x c++ ... -o "test.cpp1.ii" "test.cu"  
device代码预处理，它将一些定义好的枚举变量(例如cudaError)、struct(例如cuda的数据类型float4)、静态内联函数、extern “c++”和extern的函数、还重新定义了std命名空间、函数模板等内容写在main函数之前。  

2.  
    
    cudafe ... --gen_c_file_name "test.cudafe1.c" --gen_device_file_name "test.cudafe1.gpu" ...  
这一步test.cpp1.ii被cudafe切分成了c/c++ host代码和.gpu结尾的device代码，其中main函数还是在.c结尾的文件中。  

3.
   
    gcc -D__CUDA_ARCH__=200 -E -x c ... -o "test.cpp2.i" "test.cudafe1.gpu"
    cudafe ... --gen_c_file_name "test.cudafe2.c" ... --gen_device_file_name "test.cudafe2.gpu"
    gcc -D__CUDA_ARCH__=200 -E -x c ... -o "test.cpp3.i" "test.cudafe2.gpu"
    filehash -s "test.cpp3.i" > "test.hash"
    gcc -E -x c++ ... -o "test.cpp4.ii" "test.cu"
    cudafe++ ... --gen_c_file_name "test.cudafe1.cpp" --stub_file_name "test.cudafe1.stub.c"
上面这段生成的test.cpp4.ii是在对host代码进行预处理
  
  
  cicc  -arch compute_20 ... --orig_src_file_name "test.cu" "test.cpp3.i" -o "test.ptx"
----------------
test.ptx:
    .version 4.1
    .target sm_20
    .address_size 64
----------------
test.cpp1.ii
    ".../include/sm_11_atomic_functions.h"
    ...
    ".../include/sm_12_atomic_functions.h"
    ...
    ".../include/sm_35_atomic_functions.h"
1
2
3
4
5
6
7
8
9
10
11
12
13
test.ptx文件中只记录了三行编译信息，可以看出对应了上面提到指定ptx的版本，以后可以根据这个版本再进行编译。实际上在host c++代码即每一个test.cpp*文件中，都包含了所有版本的SM头文件，从而可以调用每一种版本的函数进行编译。

ptxas -arch=sm_20 -m64  "test.ptx" -o "test.sm_20.cubin"
1
这一步叫做PTX离线编译，主要的目的是为了将代码编译成一个确定的计算能力和SM版本，对应的版本信息保存在cubin中。

fatbinary --create="test.fatbin" ... "file=test.sm_20.cubin" ... "file=test.ptx" --embedded-fatbin="test.fatbin.c" --cuda
1
这一步叫PTX在线编译，是将cubin和ptx中的版本信息保存在fatbin中。这里针对一个.cu源文件，调用系统的gcc/g++将host代码和fatbin编译成对应的目标文件。最后用c++编译器将目标文件链接起来生成可执行文件。
