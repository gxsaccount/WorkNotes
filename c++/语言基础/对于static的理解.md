# 全局静态变量 #  
语义：该变量可见性只能在**声明变量的文件**中可见。  

    //test.h:    
    static int i;
    
    //test1.h
    #include<test.h>
    
    //test2.h
    #include<test.h>
    
    //test.c
    #include<test1.h>
    #include<test2.h>  
    
结果编译报错“static int i”重定义。  
#include相当于将后面的头文件复制到当前文件中，test.c的代码类似于下面： 
  
    static int i;
    static int i;

所以重定义，这意味着，static int i 在test1.h和test2.h中各自存在一份。  

