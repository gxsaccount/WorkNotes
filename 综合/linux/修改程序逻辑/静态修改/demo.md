# 常用指令机械码 #  

    NOP：NOP指令即“空指令”。执行到NOP指令时，CPU什么也不做，仅仅当做一个指令执行过去并继续执行NOP后面的一条指令。（机器码：90）

    JNE：条件转移指令，如果不相等则跳转。（机器码：75）

    JE：条件转移指令，如果相等则跳转。（机器码：74）

    JMP：无条件转移指令。段内直接短转Jmp short（机器码：EB）段内直接近转移Jmp near（机器码：E9）段内间接转移Jmp word（机器码：FF）段间直接(远)转移Jmp far（机器码：EA）

    CMP：比较指令，功能相当于减法指令，只是对操作数之间运算比较，不保存结果。cmp指令执行后，将对标志寄存器产生影响。其他相关指令通过识别这些被影响的标志寄存器位来得知比较结果。 

# 反汇编与十六进制编程器 #  

## 实验源码 ##    

    #include<stdio.h>
    void main()
    {
            int pass=123;
            int enter;
            printf("please enter the password:\n");
            scanf("%d",&enter);
            if(enter==pass)
                    printf("right\n");
            else
                    printf("wrong\n");
    }
 编译命令：  
        
        gcc -O0 test.c 
 运行结果：  
 ![image](https://user-images.githubusercontent.com/20179983/125429967-c9688040-7e74-4eb7-83c9-1ceda565f345.png)

 ## 汇编分析 ##  
 
        objdump -d a.out  
       
mian函数节选：  
        
        000000000000071a <main>:
         71a:   55                      push   %rbp
         71b:   48 89 e5                mov    %rsp,%rbp
         71e:   48 83 ec 10             sub    $0x10,%rsp
         722:   64 48 8b 04 25 28 00    mov    %fs:0x28,%rax
         729:   00 00
         72b:   48 89 45 f8             mov    %rax,-0x8(%rbp)
         72f:   31 c0                   xor    %eax,%eax
         731:   c7 45 f4 7b 00 00 00    movl   $0x7b,-0xc(%rbp)
         738:   48 8d 3d e5 00 00 00    lea    0xe5(%rip),%rdi        # 824 <_IO_stdin_used+0x4>
         73f:   e8 8c fe ff ff          callq  5d0 <puts@plt>
         744:   48 8d 45 f0             lea    -0x10(%rbp),%rax
         748:   48 89 c6                mov    %rax,%rsi
         74b:   48 8d 3d ed 00 00 00    lea    0xed(%rip),%rdi        # 83f <_IO_stdin_used+0x1f>
         752:   b8 00 00 00 00          mov    $0x0,%eax
         757:   e8 94 fe ff ff          callq  5f0 <__isoc99_scanf@plt>
         75c:   8b 45 f0                mov    -0x10(%rbp),%eax
         75f:   39 45 f4                cmp    %eax,-0xc(%rbp)
         762:   75 0e                   jne    772 <main+0x58>
         764:   48 8d 3d d7 00 00 00    lea    0xd7(%rip),%rdi        # 842 <_IO_stdin_used+0x22>
         76b:   e8 60 fe ff ff          callq  5d0 <puts@plt>
         770:   eb 0c                   jmp    77e <main+0x64>
         772:   48 8d 3d cf 00 00 00    lea    0xcf(%rip),%rdi        # 848 <_IO_stdin_used+0x28>
         779:   e8 52 fe ff ff          callq  5d0 <puts@plt>
         77e:   90                      nop
         77f:   48 8b 45 f8             mov    -0x8(%rbp),%rax
         783:   64 48 33 04 25 28 00    xor    %fs:0x28,%rax
         78a:   00 00
         78c:   74 05                   je     793 <main+0x79>
         78e:   e8 4d fe ff ff          callq  5e0 <__stack_chk_fail@plt>
         793:   c9                      leaveq
         794:   c3                      retq
         795:   66 2e 0f 1f 84 00 00    nopw   %cs:0x0(%rax,%rax,1)
         79c:   00 00 00
         79f:   90                      nop
其中：
        
        75c:   8b 45 f0                mov    -0x10(%rbp),%eax
        75f:   39 45 f4                cmp    %eax,-0xc(%rbp)
对应了if(enter==pass)  。
        
        762:   75 0e                   jne    772 <main+0x58>
则对应了enter！=pass时，跳转到772<main+0x58>（即000000000000071a+0x58=772）
75：jne指令，0e：跳转的相对偏移地址（764+0e=772）   


# case1 修改可执行文件另其无论输入什么密码的是正确的。#  
修改思路：将jne 跳转偏移量改为0，这样40063a位置的指令就相当于继续执行输出right。  
        
        1.vim a.out 
        2.&!xxd //然后进入16进制编辑模式：
        3./750e  //找到750e(jne指令)
        4.替换为/7500
        5.%!xxd -r //切换回原模式  
        6.wq  
将750c改成7500表示跳转到下一条指令继续执行，相当于NOP：
![image](https://user-images.githubusercontent.com/20179983/125439941-deb8185b-ebcd-4ccc-93d3-2ec72d1994ff.png)
修改后效果：  
![image](https://user-images.githubusercontent.com/20179983/125440765-2e2b00b3-0b3d-4e79-b336-30a5d2756775.png)

   

    https://blog.csdn.net/faihung/article/details/79503825  
    
