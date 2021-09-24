valgrind:   
valgrind --tool=memcheck --leak-check=full --show-leak-kinds=all    
 
g++ -g 编译简单例子还行，适合观察单元测试的小程序     


# 不同lost例子与理解 #
## still reachable ##  

    void *g_p1;
    int  fun1(void)
    {
        g_p1=malloc(20);  //付给了全局变量, 内存可以访问
        return 0;
    }
    int main(int argc, char *argv[])
    {

        int p=fun1();
        //free(g_p1);  //如果不free, 将会有 still reachable 内存泄露
        return 0;
    }

## possibly lost ##  
可能丢失。大多数情况下应视为与"definitely lost"一样需要尽快修复，除非你的程序让一个指针指向一块动态分配的内存（但不是这块内存起始地址），然后通过运算得到这块内存起始地址，再释放它。当程序结束时如果一块动态分配的内存没有被释放且通过程序内的指针变量均无法访问这块内存的起始地址，但可以访问其中的某一部分数据，则会报这个错误。

    void *g_p2;
    int  fun1(void)
    {
        g_p2=malloc(30);
        g_p2++;            //付给了全局变量, 内存可以访问,但是指针被移动过,为可能丢失
        return 0;
    }
    int main(int argc, char *argv[])
    {
        int p=fun1();
        //free(--g_p2);
        return 0;
    }
    
 ## definitely lost ##  
 确认丢失。程序中存在内存泄露，应尽快修复。当程序结束时如果一块动态分配的内存没有被释放且通过程序内的指针变量均无法访问这块内存则会报这个错误。  
    int  fun1(void)
    {
        int **p=(int **)malloc(16);
        // free(p);     //如果不free, 将会有 definitely lost内存泄露
        return 0;
    }
    int main(int argc, char *argv[])
      {

          int p=fun1();
          return 0;
      }

## indirectly lost ##  
间接丢失。当使用了含有指针成员的类或结构时可能会报这个错误。这类错误无需直接修复，他们总是与"definitely lost"一起出现，只要修复"definitely lost"即可。例子可参考我的例程。  
     
     int  fun1(void)
     {
         int **p=(int **)malloc(16);
         p[1]=(int *)malloc(40); //如果p丢失了,则p[1]为间接丢失.
         // free(p[1]);  //如果不free, 将会有 indirectly lost 内存泄露
         // free(p);     //如果不free, 将会有 definitely lost内存泄露
         return 0;
     }
     int main(int argc, char *argv[])
     {

         int p=fun1();
         return 0;
     }
