 1.使用info register查看栈上点用函数信息  
 2.使用info register $rbp查看栈顶指针的地址XXX
 3.使用x/128ag XXX查看栈的调用信息，查看相关函数    
 4.rbp地址可能被改了，啥都没有，就看rsp。rsp不会被改，但是得知道局部变量有哪些，然后rsp地址+offset(所有局部变量大小)得到调用栈，一般不管用
 



程序core掉,要去debug,但是函数堆栈乱掉了,很恶心.....经过Google/wiki一番,找到两种解决办法.

1. 手动还原backtrace

　　手动还原其实就是看栈里面的数据,自己还原函数栈,听起来很复杂其实也比较简单.手头上没有比较好的例子,所以大家就去看

　　http://devpit.org/wiki/x86ManualBacktrace 上面的例子.那个例子很好,是x86下面的,amd64下面也是类似.

　　amd64下面,无非就是寄存器变成rbp,字长增加了一倍.当然这边选择了手动寻找函数返回地址,然后info symbol打印出函数名,其实还可以通过gdb格式化来直接打印函数名:

　　gdb>x/128ag　rbp内的内容

　　所以手动还原的办法就变得很简单:

　　gdb>info reg rbp　　　　　　　　　　　　*x86换成info reg ebp

　　gdb>x/128ag  rbp内的内容　　　　　　　 *x86换成 x/128aw ebp的内容

　　这样就能看到函数栈.如果你想解析参数是啥,也是可以的,只是比较麻烦,苦力活儿....想解析参数,就要知道栈的布局,可以参考这篇文章:

　　http://blog.csdn.net/liigo/archive/2006/12/23/1456938.aspx

　　这个办法比较简单,很容易实践,但是有一个前提,如果栈的内容被冲刷干净了,你连毛都看不到(事实就是这样).所以你需要开始栈保护...至少你还能找到栈顶的函数...

　　gcc有参数: -fstack-protector 和 -fstack-protector-all,强烈建议开启....

2. 手动记录backtrace

　　开启了栈保护,这样至少会看到一个函数栈....如果想要知道更多的信息,对不起,没的...后来看公司内部的wiki,外加上google,得知很多人通过trace的办法来debug.:-D

　　简单的说,在gcc2时代,提供了两个接口函数:

　　void __cyg_profile_func_enter (void *this_fn, void *call_site)
　　void __cyg_profile_func_exit  (void *this_fn, void *call_site)

　　方便大家伙做profile,然后很多人用这俩函数来调试代码.:-D

　　函数功能很简单,第一个就是函数入栈,第二就是函数出栈.所以你只要自己维护一个栈,然后在他入栈的时候你也入栈(只记录函数地址),出栈的时候你也出栈.等程序挂了,你去看你自己维护的栈,这样就能搞到第二手的函数栈(第一手的可能被破坏了).然后在去info symbol或者x/num ag格式化打印也可以的.

　　需要注意的是,编译需要加上参数-finstrumnet-function,而且这里函数的声明需要加上__attribute__ ((no_instrument_function))宏,否则他会无限递归调用下去,:-)

　　如果是单线程,就搞一个栈就行了,如果多个线程,一个线程一个栈~~~

参考:

http://devpit.org/wiki/x86ManualBacktrace

http://blogold.chinaunix.net/u3/111887/showart_2182373.html

http://blog.csdn.net/liigo/archive/2006/12/23/1456938.aspx
