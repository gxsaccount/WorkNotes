# 接口介绍 #
Linux提供了一套API来动态装载库。下面列出了这些API：  


    #include <dlfcn.h>
    void *dlopen(const char *filename, int flag);//打开库，返回动态库句柄
    char *dlerror(void);//返回出现的错误
    void *dlsym(void *handle, const char *symbol);//取函数,在打开的库中查找符号的值。
    int dlclose(void *handle);//关闭库
    
    flags 参数必须包括以下两个值中的一个：
    RTLD_LAZY：执行延迟绑定。只在有需要的时候解析符号
    RTLD_NOW：dlopen()返回之前，将解析共享对象中的所有未定义符号。
    flags 也可以通过以下零或多个值进行或运算设置：

    RTLD_GLOBAL：此共享对象定义的符号将可用于后续加载的共享对象的符号解析。
    RTLD_LOCAL：这与RTLD_GLOBAL相反，如果未指定任何标志，则为默认值。此共享对象中定义的符号不可用于解析后续加载的共享对象中的引用
    当库被装入后，可以把 dlopen() 返回的句柄作为给dlsym()的第一个参数，以获得符号在库中的地址。使用这个地址，就可以获得库中特定函数的指针，并且调用装载库中的相应函数。

C语言用户需要包含头文件dlfcn.h才能使用上述API。glibc还增加了两个POSIX标准中没有的API：  
- dladdr，从函数指针解析符号名称和所在的文件。  
- dlvsym，与dlsym类似，只是多了一个版本字符串参数。  

在Linux上，使用动态链接的应用程序需要和库libdl.so一起链接，也就是使用选项-ldl。但是，编译时不需要和动态装载的库一起链接。  
程序3-1是一个在Linux上使用dl\*例程的简单示例。  



# 延迟重定位(Lazy Relocation) #  
延迟重定位/装载是一个允许符号只在需要时才重定位的特性。这常在各UNIX系统上解析函数调用时用到。  
当一个和共享库一起链接的应用程序几乎不会用到该共享库中的函数时，该特性被证明是非常有用的。  
这种情况下，只有库中的函数被应用程序调用时，共享库才会被装载，否则不会装载，因此会节约一些系统资源。  
但是如果把环境变量LD_BIND_NOW设置成一个非空值，所有的重定位操作都会在程序启动时进行。  
也可以在链接器命令行通过使用-z now链接器选项使延迟绑定对某个特定的共享库失效。   
需要注意的是，除非重新链接该共享库，否则对该共享库的这种设置会一直有效。  


初始化(initializing)和终止化(finalizing)函数
有时候，以前的代码可能用到了两个特殊的函数：\_init和_fini。  
\_init和_fini函数用在装载和卸载某个模块(注释14)时分别控制该模块的构造器和析构器(或构造函数和析构函数)。  
他们的C语言原型如下：
    
    void _init(void);
    void _fini(void);

当一个库通过dlopen()动态打开或以共享库的形式打开时，如果_init在该库中存在且被输出出来，则_init函数会被调用。  
如果一个库通过dlclose()动态关闭或因为没有应用程序引用其符号而被卸载时，\_fini函数会在库卸载前被调用。  
当使用你自己的_init和_fini函数时，需要注意不要与系统启动文件一起链接。可以使用GCC选项 -nostartfiles 做到这一点。  
但是，使用上面的函数或GCC的-nostartfiles选项并不是很好的习惯，因为这可能会产生一些意外的结果。  
相反，库应该使用__attribute__((constructor))和__attribute__((destructor))函数属性来输出它的构造函数和析构函数。  
如下所示：  
void __attribute__((constructor)) x_init(void)  
void __attribute__((destructor)) x_fini(void)  
构造函数会在dlopen()返回前或库被装载时调用。析构函数会在这样几种情况下被调用：dlclose()返回前，或main()返回后，或装载库过程中exit()被调用时。  

# 延迟加载实例 #  
我们通过一个例子来讲解dlopen系列函数的使用和操作:  

**主程序:**  

    int add(int a,int b)
    {
        return (a + b);
    }

    int sub(int a, int b)
    {
        return (a - b);
    }

    int mul(int a, int b)
    {
        return (a * b);
    }

    int div(int a, int b)
    {
        return (a / b);
    }

**动态库:**  

    #include <stdio.h>
    #include <stdlib.h>
    #include <dlfcn.h>

    //动态链接库路径
    #define LIB_CACULATE_PATH "./mylib.so"

    //函数指针
    typedef int (*CAC_FUNC)(int, int);

    int main()
    {
        void *handle;
        char *error;
        CAC_FUNC cac_func = NULL;

        //打开动态链接库
        handle = dlopen(LIB_CACULATE_PATH, RTLD_LAZY);
        if (!handle) {
        fprintf(stderr, "%s\n", dlerror());
        exit(EXIT_FAILURE);
        }

        //清除之前存在的错误
        dlerror();

        //获取一个函数
        *(void **) (&cac_func) = dlsym(handle, "add");
        if ((error = dlerror()) != NULL)  {
        fprintf(stderr, "%s\n", error);
        exit(EXIT_FAILURE);
        }
        printf("add: %d\n", (*cac_func)(2,7));

        cac_func = (CAC_FUNC)dlsym(handle, "sub");
        printf("sub: %d\n", cac_func(9,2));

        cac_func = (CAC_FUNC)dlsym(handle, "mul");
        printf("mul: %d\n", cac_func(3,2));

        cac_func = (CAC_FUNC)dlsym(handle, "div");
        printf("div: %d\n", cac_func(8,2));

        //关闭动态链接库
        dlclose(handle);
        exit(EXIT_SUCCESS);
    }
主程序编译: gcc test.c -ldl -rdynamic  
动态库编译: gcc -shared -fPIC -nostartfiles -o mylib.so mylib.c  
主程序通过dlopen()加载一个.so的动态库文件, 然后动态库会自动运行 \_init() 初始化函数.   
初始化函数打印一个提示信息, 然后调用主程序的注册函数给结构体重新赋值, 然后调用结构体的函数指针, 打印该结构体的值.   
这样就充分的达到了主程序和动态库的函数相互调用和指针的相互传递.  
gcc参数 -rdynamic 用来通知链接器将所有符号添加到动态符号表中（目的是能够通过使用 dlopen 来实现向后跟踪）.  
gcc参数 -fPIC 作用: 当使用.so等类的库时,当遇到多个可执行文件共用这一个库时, 在内存中,这个库就不会被复制多份,让每个可执行文件一对一的使用,  
而是让多个可执行文件指向一个库文件,达到共用. 宗旨:节省了内存空间,提高了空间利用率.  



# 拦截实例 #  
## 1.dlopen()加载指定路径的SO ##

    //加载指定路径的SO，成功返回库的句柄给调用进程，如果失败返回nullptr
    void *handle = dlopen(path.c_str(), RTLD_LAZY | RTLD_LOCAL);
      if (handle == nullptr) {
        VLOG(2) << "Failed to load OpenCL library from path " << path
                << " error code: " << dlerror();
        return nullptr;
      }
      
## 2.dlsym()取函数 ##    

假如clGetPlatformIDs函数就是外部库中我需要调用的接口之一，通过  
void *ptr = dlsym(handle, “clGetPlatformIDs”);返回这个函数对应的函数指针  
clGetPlatformIDs= reinterpret_cast<clGetPlatformIDsFunc >(ptr);//强制转换成该函数指针  

前面已经声明和定义了该函数指针：

        using clGetPlatformIDsFunc = cl_int (*)(cl_uint, cl_platform_id *, cl_uint *);
        clGetPlatformIDsFunc clGetPlatformIDs= nullptr；
    
        #define MACE_CL_ASSIGN_FROM_DLSYM(func)                          \
          do {                                                           \
            void *ptr = dlsym(handle, #func);                            \
            if (ptr == nullptr) {                                        \
              VLOG(1) << "Failed to load " << #func << " from " << path; \
              continue;                                                  \
            }                                                            \
            func = reinterpret_cast<func##Func>(ptr);                    \
            VLOG(2) << "Loaded " << #func << " from " << path;           \
          } while (false)

          MACE_CL_ASSIGN_FROM_DLSYM(clGetPlatformIDs);
        ...
        #undef MACE_CL_ASSIGN_FROM_DLSYM
    
    
## 3.通过函数指针使用该接口 ##  

在当前工程重新定义一个完全一样的函数，然后利用该函数去调用dlsym取出的接口。
这样就可以在编译的时候不链接该SO，且编译能够通过。

        cl_int clGetPlatformIDs(cl_uint num_entries,
                               cl_platform_id *platforms,
                               cl_uint *num_platforms) {
          auto func = mace::runtime::OpenCLLibrary::Get()->clGetPlatformIDs;//获取取出的函数指针
          if (func != nullptr) {
            return func(num_entries, platforms, num_platforms);//使用该函数
          } else {
            return CL_INVALID_PLATFORM;
          }
        }
## 4.dlclose关闭库 ##

正常库是不需要反复去打开和关闭的，而且库在进程结束时自动回关闭，因此实际应用过程中很少手动添加这一步。    

    
    
# C++使用 #  
extern "C"
C++ has a special keyword to declare a function with C bindings: extern "C". A function declared as extern "C" uses the function name as symbol name, just as a C function. For that reason, only non-member functions can be declared as extern "C", and they cannot be overloaded.  
    
    https://tldp.org/HOWTO/html_single/C++-dlopen/
 

    
 # 更多 #  
    https://jmpews.github.io/2016/12/27/pwn/linux%E8%BF%9B%E7%A8%8B%E5%8A%A8%E6%80%81so%E6%B3%A8%E5%85%A5/
