https://blog.csdn.net/u013982161/article/details/51347944  

总结：将函数做了内联优化  

例子：  

    int foo ( int x )
    {
        int array[] = {1,3,5};
        return array[x];
    }      /* -----  end of function foo  ----- */
    int main ( int argc, char *argv[] )
    {
        int i = 1;
        int j = foo(i);
        fprintf(stdout, "i=%d,j=%d\n", i, j);
        return EXIT_SUCCESS;
    }               /* ----------  end of function main  ---------- */

编译：  
  
    gcc –S –o test.s test.c  
    
    ![image](https://user-images.githubusercontent.com/20179983/124855722-f9fef680-dfdb-11eb-99f4-c66c38c4301d.png)
    ![image](https://user-images.githubusercontent.com/20179983/124855734-fcf9e700-dfdb-11eb-9298-e3b1a8a480cf.png)


    Main函数第40行的指令Callfoo其实干了两件事情：

    Pushl %rip //保存下一条指令（第41行的代码地址）的地址，用于函数返回继续执行
    Jmp foo //跳转到函数foo
    Foo函数第19行的指令ret 相当于：

    popl %rip //恢复指令指针寄存器   
    
    
-O2，这几乎是普遍的选择。在这种优化级别，甚至更低的优化级别-O1，都已经去除了帧指针，也就是%ebp中再也不是保存帧指针，而且另作他途。

在x86-32时代，当前栈帧总是从保存%ebp开始，空间由运行时决定，通过不断push和pop改变当前栈帧空间；x86-64开始，GCC有了新的选择，优化编译选项-O1，可以让GCC不再使用栈帧指针，下面引用 gcc manual 一段话 ：

 

    -O also turns on -fomit-frame-pointer on machines where doing so does not interfere with debugging.

 

这样一来，所有空间在函数开始处就预分配好，不需要栈帧指针；通过%rsp的偏移就可以访问所有的局部变量。说了这么多，还是看看例子吧。同一个例子， 加上-O1选项：

 

Shell>: gcc –O1 –S –o test.s test.c    
![image](https://user-images.githubusercontent.com/20179983/124855989-611cab00-dfdc-11eb-8403-07a6eabb7561.png)
![image](https://user-images.githubusercontent.com/20179983/124856003-64179b80-dfdc-11eb-8a12-5677c1dfbdf9.png)

分析main函数，GCC分析发现栈帧只需要8个字节，于是进入main之后第一条指令就分配了空间(第23行)：

 

Subq $8, %rsp

 

然后在返回上一栈帧之前，回收了空间（第34行）：

 

Addq $8, %rsp

 

等等，为啥main函数中并没有对分配空间的引用呢？这是因为GCC考虑到栈帧对齐需求，故意做出的安排。再来看foo函数，这里你可以看到%rsp是如何引用栈空间的。等等，不是需要先预分配空间吗？这里为啥没有预分配，直接引用栈顶之外的地址？这就要涉及x86-64引入的牛逼特性了。

 

访问栈顶之外
通过readelf查看可执行程序的header信息：
