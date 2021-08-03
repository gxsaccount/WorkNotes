[...](...)mutable(opt) throeSpec(opt)->retType(opt){...}    
[=] 所有outer scope变量使用值传递    
[&] 所有outer scope变量使用引用传递  
[&a,b] a引用传递，b值传递  
mutable关键字，表示可以修改按值传入的变量的副本（不是值本身），类似于不带const关键字的形参。使用mutable关键字后对按值传入的变量进行的修改，不会将改变传递到Lambda表达式之外。
throw(类型)表达式，表示Lambda表达式可以抛出指定类型的异常。
->返回值类型，指示Lambda表达式定义的匿名函数的返回值类型。
函数语句，跟常规函数的函数语句相同，如果指定了函数的返回值类型，函数实现语句中一定需要return来返回相应的类型的值。
1.函数对象：auto tmp = []{}  ； 直接调用[]{}()
2.[]{}

## 关于mutable ##
    int main()
    {

        //by value
        int id = 0;
        auto f = [id]() mutable{
            std::cout<<"id = "<<id<<std::endl;
            ++id; 
        };
        id = 42;
        f();//0
        f();//1
        f();//2
        return 0;
    }
输出结果0，1，2因为传入的外界变量方式是by value,所以外界的id改变 不会改变lambda内的 id  
/* 不加mutable改变值传递值会报错，因为read-only */
    
    #include <iostream>

    int main()
    {
        //by reference
        int id = 0;
        auto g = [&id]() mutable{
            std::cout<<"id = "<<id<<std::endl;
            id++;
        };
        id = 10;
        g();//10
        g();//11
        g();//12
        return 0;
    }
输出结果随外界值改变而改变  



2. 对于lambda，编译器会产生怎样的代码？

   
        int tobefound = 5;
        auto lambda1 = [tobefound](int val){
            return val == tobefound;
        };
 
//编译器会将其装换为一个类似这样的对象
       
        int tobefound = 5;
        auto lambdal = [tobefound](int val) {return val == tobefound;};
        class UnNamedLocalFunction
        {
        private:
            int localVar;

        public:
            UnNamedLocalFunction(int var) : localVar(var) { }
            bool operator()(int val)
            {
                return val == localVar;
            }
        };
capture的对象会变成这个class的成员(当然不是完全一样的，因为lambda的捕获还有一些规则，这个class并没有体现出来。)

