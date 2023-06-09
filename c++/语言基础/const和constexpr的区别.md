对于修饰Object来说，  
const并未区分出编译期常量和运行期常量  
constexpr限定在了编译期常量  


constexpr修饰的函数，简单的来说，如果其传入的参数可以在编译时期计算出来，那么这个函数就会产生编译时期的值。  
但是，传入的参数如果不能在编译时期计算出来，那么constexpr修饰的函数就和普通函数一样了。  
检测constexpr函数是否产生编译时期值的方法很简单，就是利用std::array需要编译期常值才能编译通过的小技巧。  
这样的话，即可检测你所写的函数是否真的产生编译期常值了。  

    #include <iostream>
    #include <array>
    using namespace std;

    constexpr int foo(int i)
    {
        return i + 5;
    }

    int main()
    {
        int i = 10;
        std::array<int, foo(5)> arr; // OK

        foo(i); // Call is Ok

        // But...
        std::array<int, foo(i)> arr1; // Error

    }


constexpr可以修饰的变量类型：  
LiteralType变量，文本类型是可在编译时确定其布局的类型：  
http://en.cppreference.com/w/cpp/concept/LiteralType     
https://learn.microsoft.com/zh-cn/cpp/cpp/trivial-standard-layout-and-pod-types?view=msvc-170#example    

* void  
* 标量类型  
* 引用  
* Void、标量类型或引用的数组  
* 具有普通析构函数以及一个或多个 constexpr 构造函数且不移动或复制构造函数的类。此外，其所有非静态数据成员和基类必须是文本类型且不可变。  

        #include <array>
        #include <iostream>
        using namespace std;

        class Test2 {
        public:
          int i = 0;
          constexpr Test2(){};
          constexpr void f(){};
          Test2(const Test2 &t) { i = t.i; };
          Test2(const Test2 &&t) { i = t.i; };
          //   ~Test2(); // can not have this !!!
        };

        constexpr int i = 0;
        constexpr int const &r1 = i;
        constexpr std::array<int, 2> array = {1, 2};
        constexpr Test2 t2{};

