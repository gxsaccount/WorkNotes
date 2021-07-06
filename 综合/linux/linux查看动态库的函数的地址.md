https://blog.csdn.net/lixiangminghate/article/details/46448491  


LD_PRELOAD提供了平民化的注入方式固然方便，同时也有不便：注入库出错后调试比较困难。我琢磨了几天找到了可行的调试方法，当然未必是最有效的办法。抛出陋文，希望引来美玉~

首先，写一段代码作为普通的动态库，公开接口，供人调用，如下：

    //true.c
    int fake(const char* s1,const char* s2)
    {
        return 0;
    }
    
    gcc -g3 -O0 -o libtrue.so true.c -fPIC -shared
    echo "/root/Desktop">>/etc/ld.so.conf
    ldconfig
这差不多是个空函数。
    下面是LD_PRELOAD将要注入的代码：

    //fake.c
    #include <string.h>
    #include <stdio.h>
    
    int fake(const char* s1,const char* s2)
    {
        printf("s1:%s-s2:%s\n",s1,s2);
        
        while(1)
                sleep(1);
        return 0;
    } 
    
    Makefile
    all:
        gcc -g3 -O0 -fPIC -shared -Wa,-adlhn -c fake.c -fno-builtin-strcmp > fake.cod
        gcc -g3 -O0 -fPIC -shared -o fake.so fake.o -Wl,-Map,Sym.map
fake.c除了生成调试信息以外，同时生成符号映射文件，why？
先不解释为什么，先来看下Sym.map中有什么：

    .init           0x0000000000000498       0x18
    *(.init)
    .init          0x0000000000000498        0x9 /usr/lib/gcc/x86_64-redhat-linux/4.4.7/../../../../lib64/crti.o
                    0x0000000000000498                _init
    .init          0x00000000000004a1        0x5 /usr/lib/gcc/x86_64-redhat-linux/4.4.7/crtbeginS.o
    .init          0x00000000000004a6        0x5 /usr/lib/gcc/x86_64-redhat-linux/4.4.7/crtendS.o
    .init          0x00000000000004ab        0x5 /usr/lib/gcc/x86_64-redhat-linux/4.4.7/../../../../lib64/crtn.o
    
    .plt            0x00000000000004b0       0x40
    *(.plt)
    .plt           0x00000000000004b0       0x40 /usr/lib/gcc/x86_64-redhat-linux/4.4.7/../../../../lib64/crti.o
    *(.iplt)
    
    .text           0x00000000000004f0      0x148
    *(.text.unlikely .text.*_unlikely)
    *(.text .stub .text.* .gnu.linkonce.t.*)
    .text          0x00000000000004f0       0x17 /usr/lib/gcc/x86_64-redhat-linux/4.4.7/../../../../lib64/crti.o
    *fill*         0x0000000000000507        0x9 90909090
    .text          0x0000000000000510       0xaa /usr/lib/gcc/x86_64-redhat-linux/4.4.7/crtbeginS.o
    *fill*         0x00000000000005ba        0x2 90909090
    .text          0x00000000000005bc       0x40 fake.o
                    0x00000000000005bc                fake
    *fill*         0x00000000000005fc        0x4 90909090
    .text          0x0000000000000600       0x36 /usr/lib/gcc/x86_64-redhat-linux/4.4.7/crtendS.o
    *fill*         0x0000000000000636        0x2 90909090
    .text          0x0000000000000638        0x0 /usr/lib/gcc/x86_64-redhat-linux/4.4.7/../../../../lib64/crtn.o
    *(.gnu.warning)
    
    .fini           0x0000000000000638        0xe
    *(.fini)
    .fini          0x0000000000000638        0x4 /usr/lib/gcc/x86_64-redhat-linux/4.4.7/../../../../lib64/crti.o
                    0x0000000000000638                _fini
    .fini          0x000000000000063c        0x5 /usr/lib/gcc/x86_64-redhat-linux/4.4.7/crtbeginS.o
    .fini          0x0000000000000641        0x5 /usr/lib/gcc/x86_64-redhat-linux/4.4.7/../../../../lib64/crtn.o
                    0x0000000000000646                PROVIDE (__etext, .)
                    0x0000000000000646                PROVIDE (_etext, .)
                    0x0000000000000646                PROVIDE (etext, .)
这里仅截取了Sym.map代码段。代码段中有.init节.text节.fini节。每节中又由诺干.o文件组成，如crt运行时库相关的crti.o以及fake.c编译后生成的fake.o。编译器将源码编译为.o中间文件后，还需要把所有的中间文件按相同的页面属性连接到一起，并分配链接地址(关于编译连接的详细介绍可以参看<程序员的自我修养>)。sym.map文件显示了链接时，各个.o文件在整个fake.so文件中的偏移：如fake.o在文件中的偏移是0x5bc
    现在说明一下需要sym.map的原因：因为fake.so是动态库，程序运行时，加载到内存中的位置不固定。因为他的不固定性，所以很难下断点或者反汇编。但是，程序运行起来后，可以通过cat /proc/pidnum/maps查看进程内存加载的情况，并获得fake.so加载的基址。有了基址，加上偏移，就可以确定fake.c提供的代码在进程空间中的具体地址



1.使用LD_PRELOAD加载.so文件  

    [root@localhost Desktop]# gdb test
    (gdb) info files 
    Symbols from "/root/Desktop/test".
    Local exec file:
        `/root/Desktop/test', file type elf64-x86-64.
        Entry point: 0x400520

这样就得到了程序的入口，并于此下断点然后start运行,程序在0x400520处停下：


    (gdb) b *0x400520
    Breakpoint 1 at 0x400520
    (gdb) start 
    Function "main" not defined.
    Make breakpoint pending on future shared library load? (y or [n]) n
    
    Starting program: /root/Desktop/test 
    
    Breakpoint 1, 0x0000000000400520 in ?? ()
    Missing separate debuginfos, use: debuginfo-install glibc-2.12-1.132.el6_5.3.x86_64

这时，进程的依赖的各个动态库也业已完成加载，可以查看内存加载情况：
  
    
    [root@localhost ~]# ps x|grep  test
    4352 pts/8    S+     0:00 gdb test
    4381 pts/8    T      0:00 /root/Desktop/test
 
    
    [root@localhost ~]# cat /proc/4381/maps 
    00400000-00401000 r-xp 00000000 fd:00 131451                             /root/Desktop/test
    00600000-00601000 rw-p 00000000 fd:00 131451                             /root/Desktop/test
    3326400000-3326420000 r-xp 00000000 fd:00 75830                          /lib64/ld-2.12.so
    332661f000-3326620000 r--p 0001f000 fd:00 75830                          /lib64/ld-2.12.so
    3326620000-3326621000 rw-p 00020000 fd:00 75830                          /lib64/ld-2.12.so
    3326621000-3326622000 rw-p 00000000 00:00 0 
    3326c00000-3326d8b000 r-xp 00000000 fd:00 75831                          /lib64/libc-2.12.so
    3326d8b000-3326f8a000 ---p 0018b000 fd:00 75831                          /lib64/libc-2.12.so
    3326f8a000-3326f8e000 r--p 0018a000 fd:00 75831                          /lib64/libc-2.12.so
    3326f8e000-3326f8f000 rw-p 0018e000 fd:00 75831                          /lib64/libc-2.12.so
    3326f8f000-3326f94000 rw-p 00000000 00:00 0 
    7ffff7bea000-7ffff7bed000 rw-p 00000000 00:00 0 
    7ffff7bed000-7ffff7bee000 r-xp 00000000 fd:00 136044                     /root/Desktop/libtrue.so
    7ffff7bee000-7ffff7ded000 ---p 00001000 fd:00 136044                     /root/Desktop/libtrue.so
    7ffff7ded000-7ffff7dee000 rw-p 00000000 fd:00 136044                     /root/Desktop/libtrue.so
    7ffff7dfc000-7ffff7dfd000 r-xp 00000000 fd:00 136014                     /root/Desktop/fake.so
    7ffff7dfd000-7ffff7ffc000 ---p 00001000 fd:00 136014                     /root/Desktop/fake.so
    7ffff7ffc000-7ffff7ffd000 rw-p 00000000 fd:00 136014                     /root/Desktop/fake.so
    7ffff7ffd000-7ffff7ffe000 rw-p 00000000 00:00 0 
    7ffff7ffe000-7ffff7fff000 r-xp 00000000 00:00 0                          [vdso]
    7ffffffea000-7ffffffff000 rw-p 00000000 00:00 0                          [stack]
    ffffffffff600000-ffffffffff601000 r-xp 00000000 00:00 0                  [vsyscall]




嗯，fake.so在7ffff7dfc000，fake.o应该位于7ffff7dfc5bc处了。另外也可以看到，被LD_PRELOAD覆盖的libtrue.so被加载到7ffff7bed000处
可以直接在这个位置下断，当然不放心的话，可以用objdump查看test的反汇编：



    [root@localhost Desktop]# objdump -d test
    
    Disassembly of section .plt:
    
    00000000004004d8 <fake@plt-0x10>:
    4004d8:    ff 35 d2 04 20 00        pushq  0x2004d2(%rip)        # 6009b0 <_fini+0x2002a8>
    4004de:    ff 25 d4 04 20 00        jmpq   *0x2004d4(%rip)        # 6009b8 <_fini+0x2002b0>
    4004e4:    0f 1f 40 00              nopl   0x0(%rax)
    
    00000000004004e8 <fake@plt>:
    4004e8:    ff 25 d2 04 20 00        jmpq   *0x2004d2(%rip)        # 6009c0 <_fini+0x2002b8>
    4004ee:    68 00 00 00 00           pushq  $0x0
    4004f3:    e9 e0 ff ff ff           jmpq   4004d8 <_init+0x18>
    
    ...
    0000000000400520 <.text>:
    400520:    31 ed                    xor    %ebp,%ebp
    400522:    49 89 d1                 mov    %rdx,%r9
    400525:    5e                       pop    %rsi
    400526:    48 89 e2                 mov    %rsp,%rdx
    400529:    48 83 e4 f0              and    $0xfffffffffffffff0,%rsp
    40052d:    50                       push   %rax
    40052e:    54                       push   %rsp
    40052f:    49 c7 c0 30 06 40 00     mov    $0x400630,%r8
    400536:    48 c7 c1 40 06 40 00     mov    $0x400640,%rcx
    40053d:    48 c7 c7 04 06 40 00     mov    $0x400604,%rdi
    400544:    e8 bf ff ff ff           callq  400508 <__libc_start_main@plt>

其中

    00000000004004e8 <fake@plt>:
    4004e8:    ff 25 d2 04 20 00        jmpq   *0x2004d2(%rip)        # 6009c0 <_fini+0x2002b8>
    4004ee:    68 00 00 00 00           pushq  $0x0
    4004f3:    e9 e0 ff ff ff           jmpq   4004d8 <_init+0x18>


是test向fake.so中导出的函数跳转的地址，可以在此处也下个断点。

附注，测试这段代码时，我已经关闭了随机地址加载所以objdump -d输出的连接地址和test加载地址相同，都是0x400520。关闭随机地址加载的方法如下：

    [root@localhost ~]# echo 0>/proc/sys/kernel/randomize_va_space 

    (gdb) b *0x04004e8
    Breakpoint 2 at 0x4004e8
    (gdb) b *0x7ffff7dfc5bc
    Breakpoint 3 at 0x7ffff7dfc5bc: file fake.c, line 5.
    (gdb)

继续运行，程序在0x4004e8出停下后反汇编看看，然后继续运行到fake.so中


    (gdb) c
    Continuing.
    
    Breakpoint 2, 0x00000000004004e8 in fake@plt ()
    (gdb) x /32i $pc
    => 0x4004e8 <fake@plt>:	jmpq   *0x2004d2(%rip)        # 0x6009c0 <fake@got.plt>
    0x4004ee <fake@plt+6>:	pushq  $0x0
    0x4004f3 <fake@plt+11>:	jmpq   0x4004d8


    (gdb) c
    Continuing.
    
    Breakpoint 3, fake (s1=0x3326621188 "", 
        s2=0x332640e9f0 "UH\211\345AWAVAUATE1\344S1\333H\203\354HH\307E\250")
        at fake.c:5
    5	{
    (gdb) x /32i $pc
    (gdb) x /32i $pc
    => 0x7ffff7dfc5bc <fake>:    push   %rbp
    0x7ffff7dfc5bd <fake+1>:    mov    %rsp,%rbp
    0x7ffff7dfc5c0 <fake+4>:    sub    $0x10,%rsp
    0x7ffff7dfc5c4 <fake+8>:    mov    %rdi,-0x8(%rbp)
    0x7ffff7dfc5c8 <fake+12>:    mov    %rsi,-0x10(%rbp)
    0x7ffff7dfc5cc <fake+16>:    lea    0x73(%rip),%rax        # 0x7ffff7dfc646
    0x7ffff7dfc5d3 <fake+23>:    mov    -0x10(%rbp),%rdx
    0x7ffff7dfc5d7 <fake+27>:    mov    -0x8(%rbp),%rcx
    0x7ffff7dfc5db <fake+31>:    mov    %rcx,%rsi
    0x7ffff7dfc5de <fake+34>:    mov    %rax,%rdi
    0x7ffff7dfc5e1 <fake+37>:    mov    $0x0,%eax
    0x7ffff7dfc5e6 <fake+42>:    callq  0x7ffff7dfc4c0 <printf@plt>
    0x7ffff7dfc5eb <fake+47>:    mov    $0x1,%edi
    0x7ffff7dfc5f0 <fake+52>:    mov    $0x0,%eax
    0x7ffff7dfc5f5 <fake+57>:    callq  0x7ffff7dfc4e0 <sleep@plt>
    0x7ffff7dfc5fa <fake+62>:    jmp    0x7ffff7dfc5eb <fake+47>


在这段反汇编代码中，我们看到了2个函数:printf/sleep,有点像fake.c中的代码了。
由于，fake.so是源码编译的，可以在此看到源码，并下断点：  

    0x7ffff7dfc604 <__do_global_ctors_aux+4>:	push   %rbx
    ---Type <return> to continue, or q <return> to quit---q
    Quit
    (gdb) list
    1	#include <string.h>
    2	#include <stdio.h>
    3	
    4	int fake(const char* s1,const char* s2)
    5	{
    6		printf("s1:%s-s2:%s\n",s1,s2);
    7		
    8		while(1)
    9				sleep(1);
    10		return 0;
    (gdb) b 8
    Breakpoint 4 at 0x7ffff7dfc5eb: file fake.c, line 8.
    (gdb) 


当然，还支持查看变量：  

    
    $2 = 0x40072a "1"
    (gdb) p s2
    $3 = 0x400728 "2"

