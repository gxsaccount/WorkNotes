# X86-64寄存器 #  

X86-64有16个64位寄存器，分别是：  

    %rax，%rbx，%rcx，%rdx，%esi，%edi，%rbp，%rsp，%r8，%r9，%r10，%r11，%r12，%r13，%r14，%r15。

其中：  

    %rax 作为函数返回值使用。
    %rsp 栈指针寄存器，指向栈顶
    %rbp 栈底指针  
    %rip 下条指令寄存器
    
    %rdi，%rsi，%rdx，%rcx，%r8，%r9 用作函数参数，依次对应第1参数，第2参数。。。
    %rbx，%rbp，%r12，%r13，%14，%15 用作数据存储，遵循被调用者使用规则，简单说就是随便用，调用子函数之前要备份它，以防他被修改
    %r10，%r11 用作数据存储，遵循调用者使用规则，简单说就是使用之前要先保存原值
    
另：
    ![image](https://user-images.githubusercontent.com/20179983/124875788-dfd51080-dffb-11eb-8230-cbceb1dec429.png)

    
    ![image](https://user-images.githubusercontent.com/20179983/124854792-7690d580-dfda-11eb-8f95-7d1108def8b2.png)
