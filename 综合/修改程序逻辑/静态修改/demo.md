# 常用指令机械码 #  

    NOP：NOP指令即“空指令”。执行到NOP指令时，CPU什么也不做，仅仅当做一个指令执行过去并继续执行NOP后面的一条指令。（机器码：90）

    JNE：条件转移指令，如果不相等则跳转。（机器码：75）

    JE：条件转移指令，如果相等则跳转。（机器码：74）

    JMP：无条件转移指令。段内直接短转Jmp short（机器码：EB）段内直接近转移Jmp near（机器码：E9）段内间接转移Jmp word（机器码：FF）段间直接(远)转移Jmp far（机器码：EA）

    CMP：比较指令，功能相当于减法指令，只是对操作数之间运算比较，不保存结果。cmp指令执行后，将对标志寄存器产生影响。其他相关指令通过识别这些被影响的标志寄存器位来得知比较结果。 

# 反汇编与十六进制编程器 #  

实验源码：  

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

    