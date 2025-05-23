c语言形成可执行文件的过程：  
![image](https://user-images.githubusercontent.com/20179983/130347584-3aed32a9-0c88-4eee-a760-02410a7605c6.png)
预处理：-E
负责把include的文件包含进来及宏替换等工作，生成.i 文件
编译：-S
把预处理过后的源码编译成汇编代码，生成.s 文件
汇编：-c
把汇编代码编译成目标文件，生成.o文件
链接：-o
链接动态库，生成可执行文件ELF

    shiyanlou:~/ $ cd Code                                                [9:27:05]
    shiyanlou:Code/ $ vi hello.c                                          [9:27:14]
    shiyanlou:Code/ $ gcc -E -o hello.cpp hello.c -m32                    [9:34:55]
    shiyanlou:Code/ $ vi hello.cpp                                        [9:35:04]
    shiyanlou:Code/ $ gcc -x cpp-output -S -o hello.s hello.cpp -m32      [9:35:21]
    shiyanlou:Code/ $ vi hello.s                                          [9:35:28]
    shiyanlou:Code/ $ gcc -x assembler -c hello.s -o hello.o -m32         [9:35:58]
    shiyanlou:Code/ $ vi hello.o                                          [9:38:44]
    shiyanlou:Code/ $ gcc -o hello hello.o -m32                           [9:39:37]
    shiyanlou:Code/ $ vi hello                                            [9:39:44]
    shiyanlou:Code/ $ gcc -o hello.static hello.o -m32 -static            [9:40:21]
    shiyanlou:Code/ $ ls -l                                               [9:41:13]
    -rwxrwxr-x 1 shiyanlou shiyanlou   7292  3\u6708 23 09:39 hello
    -rw-rw-r-- 1 shiyanlou shiyanlou     64  3\u6708 23 09:30 hello.c
    -rw-rw-r-- 1 shiyanlou shiyanlou  17302  3\u6708 23 09:35 hello.cpp
    -rw-rw-r-- 1 shiyanlou shiyanlou   1020  3\u6708 23 09:38 hello.o
    -rw-rw-r-- 1 shiyanlou shiyanlou    470  3\u6708 23 09:35 hello.s
    -rwxrwxr-x 1 shiyanlou shiyanlou 733254  3\u6708 23 09:41 hello.static
    
目标文件格式，ABI文件(可被cpu解析的二进制文件)  
格式：elf（executable and linkable format）： 见elf解析  
ELF中三种目标文件：

    一个可重定位（relocatable）文件保存着代码和适当的数据，用来和其他的object文件一起创建一个可执行文件或者是一个共享文件。主要是.o文件
    一个可执行（executeable）文件保存着一个用来执行的程序；该文件指出了exec（BA_OS）如何来创建进程映象。
    一个共享object文件保存着代码和合适的数据，用来被下面的两个链接器链接。
     -第一个是连接编辑器（静态链接）【请查看ld（SD_CMD）】，可以和其他的可重定位和共享object文件来创建其他的object。
     -第二个是动态链接器，联合一个可执行文件和其他的共享object文件来创建一个进程映象。主要是.so文件


# 二. 可执行程序、共享库和动态链接 #   
## 静态链接可执行文件如何加载到内存 ##  
当创建或增加一个进程映像的时候，系统在理论上将拷贝一个文件的段到一个虚拟的内存段：   
32位系统x86有4G的进程地址空间，栈的上方是内核使用(**0xc00000以上**)，其余是用户态访问  
一般静态链接会将所有代码放在一个代码段  
动态链接的进程会有多个代码段  

**ELF与Linux进程虚拟空间内存的对应关系如下图：**  
![image](https://user-images.githubusercontent.com/20179983/130624705-86c6fc2a-b7e3-417e-9cb4-f91d03c8236e.png)

默认从0x8048000开始加载  
从0x8048000开始加载elf的文件头  
加载过后文件头中的程序入口即为程序的实际入口（文件加载到内存执行的第一行代码）  

## 1. 可执行文件的装载/执行shell的系统调用=> execve ##  
命令行参数和shell环境，一般我们执行一个程序的Shell环境，这会使用**execve系统调用**。  
**execve：装载可执行文件并将当前进程给给覆盖掉，ret_from_fork返回可执行文件的main函数地址**  

$ ls -l /usr/bin 列出/usr/bin下的目录信息  
Shell本身不限制命令行参数的个数，命令行参数的个数受限于命令自身  
      例如，int main() //不接受任何参数
            int main(int argc, char \*argv[]) //接受命令行参数
      又如， int main(int argc, char \*argv[], char \*envp[])  //接受shell的相关环境变量

Shell会调用execve将命令行参数和环境参数传递给可执行程序的main函数
      int execve(const char * filename,char * const argv[ ],char * const envp[ ]);
      库函数exec\*都是execve的封装例程
实例：  

        #include <stdio.h>
        #include <stdlib.h>
        #include <unistd.h>
        int main(int argc, char * argv[])
        {
            int pid;
            /* fork another process */
            pid = fork();
            if (pid<0) 
            { 
                /* error occurred */
                fprintf(stderr,"Fork Failed!");
                exit(-1);
            } 
            else if (pid==0) 
            {
                /*   child process   */
                execlp("/bin/ls","ls",NULL);
            } 
            else 
            {  
                /*     parent process  */
                /* parent will wait for the child to complete*/
                wait(NULL);
                printf("Child Complete!");
                exit(0);
            }
        }

1） 命令行参数和环境变量是如何保存和传递的？
![image](https://user-images.githubusercontent.com/20179983/130349613-720e8338-079a-45c2-83d8-4fb3fd632ac4.png)  
fork后加载参数和环境，用户态堆栈也被清空
2） 命令行参数和环境变量是如何进入新程序堆栈的？
当创建一个新的用户堆栈的时候，实际上是把命令行参数的内容和环境变量的内容，**通过指令的形式传递给了系统调用execve的内核处理函数，然后内核处理函数在创建一个新的用户态堆栈的时候会把这些命令行参数和环境变量拷贝到用户堆栈中，来初始化新程序的上下文环境，所以新程序能从main函数开始执行，接受对应的参数。**  

## 动态链接 ##
动态链接分为**可执行程序装载时动态链接**和**运行时动态链接**，如下代码演示了这两种动态链接。  
源码见：https://github.com/gxsaccount/LanguageNotes/blob/master/%E7%BB%BC%E5%90%88/linux/linux%E5%9F%BA%E7%A1%80/%E5%8F%AF%E6%89%A7%E8%A1%8C%E7%A8%8B%E5%BA%8F%E8%AE%B2%E8%A7%A3%E6%BA%90%E7%A0%81.zip  
1.准备.so文件  
       
       shlibexample.h (1.3 KB) - Interface of Shared Lib Example
       shlibexample.c (1.2 KB) - Implement of Shared Lib Example

编译成libshlibexample.so文件（**可执行文件加载时装载，共享库文件**）  

       $ gcc -shared shlibexample.c -o libshlibexample.so -m32
       dllibexample.h (1.3 KB) - Interface of Dynamical Loading Lib Example
       dllibexample.c (1.3 KB) - Implement of Dynamical Loading Lib Example

编译成libdllibexample.so文件（**可执行文件加载时装载，使用dlopen，动态加载文件**）见更改程序行文动态篇  

       $ gcc -shared dllibexample.c -o libdllibexample.so -m32

2.分别以共享库和动态加载共享库的方式使用libshlibexample.so文件和libdllibexample.so文件  
       
       main.c  (1.9 KB) - Main program
       编译main，注意这里只提供shlibexample的-L（库对应的接口头文件所在目录）和-l（库名，  如libshlibexample.so去掉lib和.so的部分），并没有提供dllibexample的相关信息，只是指明了-ldl


        $ gcc main.c -o main -L/path/to/your/dir -lshlibexample -ldl -m32
        $ export LD_LIBRARY_PATH=$PWD #将当前目录加入默认路径，否则main找不到依赖的库文件，当然也可以将库文件copy到默认路径下。
        $ ./main
        This is a Main program!
        Calling SharedLibApi() function of libshlibexample.so!
        This is a shared libary!
        Calling DynamicalLoadingLibApi() function of libdllibexample.so!
        This is a Dynamical Loading libary!

 
# 三. 可执行程序的装载 #    
execve和fork都是特殊一点的系统调用  
子进程是从ret_from_fork开始执行然后返回用户态
通过修改内核堆栈中EIP的值作为新程序的起点

1.可执行程序的装载相关关键问题分析

## sys_execve内部会解析可执行文件格式  ##  

1.do_execve -> do_execve_common -> exec_binprm
    
2.search_binary_handler根据文件头，寻找文件格式对应的解析模块，如下：

    list_for_each_entry(fmt, &formats, lh) {  //在链表中寻找对应格式  
        if  (!try_module_get(fmt->module))
             continue ;
        read_unlock(&binfmt_lock);
        bprm->recursion_depth++;
        retval = fmt->load_binary(bprm);//实际执行load_elf_binary，多态的机制
        read_lock(&binfmt_lock);
3.对于ELF格式的可执行文件fmt->load_binary(bprm);执行的应该是load_elf_binary其内部是和ELF文件格式解析的部分需要和ELF文件格式标准结合起来阅读 
4.Linux内核是如何支持多种不同的可执行文件格式的？

    static  struct  linux_binfmt elf_format = {
      .module     = THIS_MODULE,
      .load_binary    = load_elf_binary, //函数指针
      .load_shlib = load_elf_library,
      .core_dump  = elf_core_dump,
      .min_coredump   = ELF_EXEC_PAGESIZE,
    };

    static  int  __init init_elf_binfmt( void )
    {
        register_binfmt(&elf_format);// 注册elf_format到list_for_each_entry的list
         return  0;
    }

elf_format 和 init_elf_binfmt，这里是**观察者模式中的观察者**,**search_binary_handler是被观察者**  


2.sys_execve的内部处理过程

装载和启动一个可执行程序依次调用以下函数：

sys_execve() -> do_execve() -> do_execve_common() -> exec_binprm() ->   
**search_binary_handler**()打开文件的处理函数-> **list_for_each_entry**()寻找装载程序 -> load_binary=load_elf_binary()//加载处理函数 -> start_thread()    

**start_thread 的new_ip对于静态链接就是静态文件的elf_entry(main函数0x8048000之后附近的某一位置)  
对于动态链接则是load_elf_interp(...)(即动态链接器的起点)，cpu将控制权交给ld来加载依赖库并完成动态链接**  

3.使用gdb跟踪sys_execve内核函数的处理过程（见课后作业）

4.可执行程序的装载与庄生梦蝶的故事

庄周（调用execve的可执行程序）入睡（调用execve陷入内核），醒来（系统调用execve返回用户态）发现自己是蝴蝶（被execve加载的可执行程序）

修改int 0x80压入内核堆栈的EIP

load_elf_binary ->  **start_thread**  start_thread:在中断时，将flag，ip和sp都压栈  

![image](https://user-images.githubusercontent.com/20179983/130360241-e42e1478-9ba8-4a00-ba5a-ce3befad10b5.png)  
![image](https://user-images.githubusercontent.com/20179983/130360235-25856ac2-7d9a-4527-b4c0-1e02138385dc.png)  

5.浅析动态链接的可执行程序的装载
    
（1）可以关注ELF格式中的interp和dynamic,源码中**elf_entry = load_elf_interp(...)**。  
（2）动态链接库的装载过程是一个广度优先的图的遍历。(linux加载可执行文件依赖的动态链接库，加载动态链接库继续加载它依赖的动态链接库)    
（3）装载和连接之后ld将CPU的控制权交给可执行程序。（在动态库加载过程中，做了各种符号表等复杂的操作后，再将可执权移交可给可执行程序的入口，程序再从main开始执行）  
（4）动态链接主要由libc的ld完成，实在用户态完成的  


实例：  
        //hello.c  
        //gcc -o hello hello.c -m32 -static 
        #include <stdio.h>  
        int main(){
            prinf("HELLO WORLD!\n");
        }
        
        //test_exec.c  linux添加exec执行该文件  
        #include <stdio.h>
        #include <stdlib.h>
        #include <unistd.h>
        int main(int argc, char * argv[])
        {
            int pid;
            /* fork another process */
            pid = fork();
            if (pid<0) // pid都是大于等于0的
            { 
                /* error occurred */
                fprintf(stderr,"Fork Failed!");
                exit(-1);
            } 
            else if (pid==0) // 子进程的返回值（eax寄存器保存）是0，所以子进程进入else if条件分支
            {
                /*  child process   */
                execlp("/hello","hello",NULL);// 在子进程中加载指定的可执行文件
            } 
            else  // 父进程的返回值（eax寄存器保存）> 0，所以父进程进入else条件分之
            { 
                /*    parent process  */
                /* parent will wait for the child to complete*/
                wait(NULL);
                printf("Child Complete!");
                exit(0);
            }
        }
