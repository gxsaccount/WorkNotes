# X86-64寄存器 #  

## 通用寄存器 ##  

![image](https://user-images.githubusercontent.com/20179983/129471005-939aa813-5297-4788-b2cd-044c9e44b733.png)


## 段寄存器 ##  

cs寄存器：cpu在取指令时根据cs+eip来定位一个指令的内存地址  
ss寄存器：进程标识自己的堆栈地址  

![image](https://user-images.githubusercontent.com/20179983/129471215-3f251b71-194a-4187-bf10-8ede05ddaead.png)

    
![image](https://user-images.githubusercontent.com/20179983/124854792-7690d580-dfda-11eb-8f95-7d1108def8b2.png)

## 标志寄存器 ##  
标识当前的一些状态   
![image](https://user-images.githubusercontent.com/20179983/129471371-65076d22-d1e4-4bb5-8997-d5987a76932f.png)  

## 64位寄存器 ##  
机制基本和32，16相同，新增浮点数寄存器
**X86-64有16个通用64位寄存器**  

    %rax，%rbx，%rcx，%rdx，%esi，%edi，%rbp，%rsp，%r8，%r9，%r10，%r11，%r12，%r13，%r14，%r15。

其中：  

    %rax 作为函数返回值使用。
    %rsp 栈指针寄存器，指向栈顶
    %rbp 栈底指针，只有在 -O0 不优化的编译条件下 ，还具有 帧指针的特殊含义。否则作为通用寄存器  
    %rip 下条指令寄存器
    
    %rdi，%rsi，%rdx，%rcx，%r8，%r9 用作函数参数，依次对应第1参数，第2参数。。。
    %rbx，%rbp，%r12，%r13，%14，%15 用作数据存储，遵循被调用者使用规则，简单说就是随便用，调用子函数之前要备份它，以防他被修改
    %r10，%r11 用作数据存储，遵循调用者使用规则，简单说就是使用之前要先保存原值

**Media/浮点寄存器**  
浮点寄存器和Media：MMX*/FPR*  
Media：XMM*

![image](https://user-images.githubusercontent.com/20179983/129471548-4fa269b4-8930-4c05-9d16-49d270e5bbc5.png)
