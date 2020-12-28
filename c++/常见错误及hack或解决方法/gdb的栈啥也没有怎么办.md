 1.使用info register查看栈上点用函数信息  
 2.使用info register $rbp查看栈顶指针的地址XXX
 3.使用x/128ag XXX查看栈的调用信息，查看相关函数  
 4.rbp地址可能被改了，啥都没有，就看rsp。rsp不会被改，但是得知道局部变量有哪些，然后rsp地址+offset(所有局部变量大小)得到调用栈，一般不管用
 
