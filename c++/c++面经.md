## 迭代器失效  
## 工厂模式的好处  
## 虚函数表  
## static  
## move 
## 编译链接过程  
## 

## 1.零碎知识点 ##  

  int *p1 = new int[10];   
  int *p2 = new int[10]();  
  
  编译器有可能将两者都初始化。
  内置类型，new只分配内存，后面加(),相当于调用它的构造函数，所以值全部初始化为0；
  自定义类型，只要调用new，那么编译器不仅仅给它分配内存，还调用它的默认构造函数初始化，即使后面没有加()
  
  
    enum string{    
      x1,    
      x2,    
      x3=10,    
      x4,    
      x5,    
    } x;  
    
    全局变量时初始化为0，局部变量时初始化为随机值  
    
    
    void Func(char str_arg[100])
    {
           printf("%d\n",sizeof(str_arg));
    }
    int main(void)
    {
         char str[]="Hello";
         printf("%d\n",sizeof(str));
        printf("%d\n",strlen(str));
        char*p=str;
        printf("%d\n",sizeof(p));
        Func(str);
    }
    str是复合类型数组char[6]，维度6是其类型的一部分，sizeof取其 维度*sizeof(char)，故为6；
    strlen 求c类型string 的长度，不含尾部的'\0'，故为5；
    p只是个指针，32位机上为4；
    c++中不允许隐式的数组拷贝，所以Func的参数会被隐式地转为char*，故为4；

    note：若Func的原型为void Func(char (&str_arg) [6])（若不为6则调用出错），则结果为6.  
    
    
    
    若char是一字节，int是4字节，指针类型是4字节，代码如下：
    class CTest
    {
        public:
            CTest():m_chData(‘\0’),m_nData(0)
            {
            }
            virtual void mem_fun(){}
        private:
            char m_chData;
            int m_nData;
            static char s_chData;
    };
    char CTest::s_chData=’\0’;
    问：
    （1）若按4字节对齐sizeof(CTest)的值是多少？
    （2）若按1字节对齐sizeof(CTest)的值是多少？
    请选择正确的答案。
    
    1 先找有没有virtual 有的话就要建立虚函数表，+4
    2 static的成员变量属于类域，不算入对象中      +0
    3 神马成员都没有的类，或者只有成员函数        +1
    4 对齐法则
    
    
    
    class A
    {
    public:
     void FuncA()
     {
         printf( "FuncA called\n" );
     }
     virtual void FuncB()
     {
         printf( "FuncB called\n" );
     }
    };
    class B : public A
    {
    public:
     void FuncA()
     {
         A::FuncA();
         printf( "FuncAB called\n" );
     }
     virtual void FuncB()
     {
         printf( "FuncBB called\n" );
     }
    };
    void main( void )
    {
     B  b;
     A  *pa;
     pa = &b;
     A *pa2 = new A;
     pa->FuncA(); （ 3）
     pa->FuncB(); （ 4）
     pa2->FuncA(); （ 5）
     pa2->FuncB();
     delete pa2;
    }
    选B
     B  b; 
     A  *pa;
     pa = &b;
     A *pa2 = newA;
     pa->FuncA(); （ 3）//pa=&b动态绑定但是FuncA不是虚函数，所以FuncA called,**pa是一个A*指针，这个函数编译时就确定了**
     pa->FuncB(); （ 4）//FuncB是虚函数所以调用B中FuncB，FuncBB called  
     pa2->FuncA(); （ 5）//pa2是A类指针，不涉及虚函数，调用的都是A中函数，所以FuncA called FuncB called
     pa2->FuncB()
     
     
     
     
	Test t1;
 
	// 拷贝
	Test t2(t1);
	Test t3 = t1;//在进行赋值时 t3还没有构造完成，所以调用拷贝
 
	// 赋值
	Test t4, t5;
	t5 = t4 = t1;
	
	return 0;
