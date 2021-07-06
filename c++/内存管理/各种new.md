## new/operator new/malloc 和析够delete ##   
本质上new调用operator new,而operator new调用malloc.  
析够/delete本质上调用free
        
        /*new*/
        Complex *pc = new Complex(1,2);  
        
        //编译器转化为类似如下代码
        Complex *pc;
        try{
            void* mem = operator new(sizeof(Complex));
            pc = static_cast<Complex*> mem;
            pc->Complex::Complex(1,2);//只有编译器可以用 ,若希望直接用ctor,只能用 new(p)Complex(1,2)
        }
        catch(std::bad_alloc){
            //
        }
        
        // operater new源码
        void * operater new(size_t size,const std::nothrow_t&)
                        _THROW0()
        {
            void* p;
            while((p=malloc(size))==0)//底层调用malloc
            {
                _TRY_BEGIN
                    if(_callnewh(size)==0) break;//_callnewh自己设定函数,通过自己释放一些内存来malloc
                _CATCH(std::bad_alloc) return(0);
                _CATCH_END
            }
        }
        
        
        /*delete*/
        Complex *pc = new Complex(1,2);
        ...
        delete pc;
        
        //编译器转化为如下代码  
        pc->~Complex();//先析够
        operator delete(pc);//然后释放内存  
        
        // operater delete源码
        void _cdecl operator delete(void *p)_THROW0()
        {
            free(p);
        }
        
   ## array new,array delete ##  
        
        Complex *pca = new Complex[3]; //构造顺序1,2,3
        //唤起三次ctor
        //无法调用有参数的构造函数即,必须有Complex()
        ...
        delete[] pca;//唤起三次dtor,释放顺序3,2,1,长度由内存块记录长度,见malloc的内存块结构解析  
        
   **delete[]如果不加[],释放没有指针的类不会内存泄漏,有指针时因为只会调用一次析够,会有指针无法施放,造成内存泄漏. 写的话运行时会直接报错**  
   **new[]和new内存布局不一样,见malloc的内存块结构解析**
   
## placement new ##  
允许我们将object创建与allocated memory中.  

       #include<new>  
       char* buf = new char[sizeof(Complex)*3];
       Complex* pc = new(buf) Complex(1,2);
       ...
       delete[]buf;
        
        //编译器转化为
        Complex *pc;
        try{
            void* mem = operator new(sizeof(Complex),buf);//与直接new不同,增加了buf输入  
            pc = static_cast<Complex*>(mem);
            pc->Complex::Complex(1,2);
        }
        catch(std::bad_alloc){
            ...
        }
    
    
## 重载 ##   
**::operator new是全局的函数,需要慎重重载** 
    
        //重载::operator new/::operator delete  
        inline void* operator new(size_t size){...}
        inline void* operator new[](size_t size){...}
        inline void* operator delete(size_t size){...}
        inline void* operator delete[](size_t size){...}
        
        //重载operator new/operator delete  
        class Foo{
            public:
            void* operator new(size_t);
            void operator delete(void*,size_t);//size_t 是optional
            void* operator new[](size_t);
            void operator delete[](void*,size_t);//size_t 是optional  
            //实际上,这四个函数必须是static,因为new对象时并没有实例化函数,却要用成员函数,但是c++自己优化了,默认隐式的static
        }
        
##重载new()/delete()##  
重载class member operator new()，**其中第一参数必须为size_t，其余参数是以new指定的placement arguments为初值**    
重载class member operator delete(),**只有构造函数抛出异常**，才会调用对应重载的operator delete，**主要功能是用来归还未能创建成功的object所占用的memory。**   
不重载也行，默认放弃处理ctor抛出的异常。  
    class Foo{
        public:
        Foo() {};
        Foo(int){};
        //1.一般的operator new() /delete重载
        void* operator new(size_t size){
            return malloc(size);
        }
        void operator delete(void*,size_t size){}

        //2.placement new()的重载
        void* operator new(size_t size,void* start){
            return start;
        }
        void operator delete(void*,void* ){}  

        //3.新的palcement new
        void* operator new(size_t size,long extra){
            return malloc(size+extra);
        }
        void operator delete(void*,long){}  

        //4.新的palcement new2
        void* operator new(size_t size,long extra,char init){
            return malloc(size+extra);
        }
        void operator delete(void*,long,char){}  
    }
    
    
    
    
operator new()/delete() 可以使用=delete，=defalut不行  
