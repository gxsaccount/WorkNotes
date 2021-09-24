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
        return 0;
    }
    
 ## definitely lost ##  
    
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

## indirectly ##  

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
