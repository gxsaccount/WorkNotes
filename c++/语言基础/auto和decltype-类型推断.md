# auto #  

自动类型推断，顾名思义，就是编译器能够根据表达式的类型，自动决定变量的类型（从 C++14 开始，还有函数的返回类型），不再需要程序员手工声明,由编译帮助填充。  


不使用auto：  


        template <typename T>
        void foo(const T& container)
        {
          for (typename T::const_iterator   //不使用typename，const_iterator会被当作一个type（常量。静态变量等）  
                 it = v.begin(),
            …
        }

使用auto：  

        template <typename T>
        void foo(const T& container)
        {
          for (auto&   //不使用typename，const_iterator会被当作一个type（常量。静态变量等）  
                 it = v.begin(),
            …
        }

如果我们的遍历函数要求支持 C 数组的话，不用自动类型推断的话，就只能使用两个不同的重载，因为begin 返回的类型不是该类型的 const_iterator 嵌套类型      


        template <typename T, std::size_t N>
        void foo(const T (&a)[N])
        {
          typedef const T* ptr_t;
          for (ptr_t it = a, end = a + N;
               it != end; ++it) {
            // 循环体
          }
        }

        template <typename T>
        void foo(const T& c)
        {
          for (typename T::const_iterator
                 it = c.begin(),
                 end = c.end();
               it != end; ++it) {
            // 循环体
          }
        }

使用auto：  


        template <typename T>
        void foo(const T& c)
        {
          using std::begin;
          using std::end;
          // 使用依赖参数查找（ADL）；
          for (auto it = begin(c),
               ite = end(c);
               it != ite; ++it) {
            // 循环体
          }
        }

当你写了一个含 auto 的表达式时，相当于把 auto 替换为模板参数的结果  

* auto a = expr; 意味着用 expr 去匹配一个假想的 template f(T) 函数模板，结果为值类型。  
* const auto& a = expr; 意味着用 expr 去匹配一个假想的 template f(const T&) 函数模板，结果为常左值引用类型。  
* auto&& a = expr; 意味着用 expr 去匹配一个假想的 template f(T&&) 函数模板，万能引用，结果是一个跟 expr 值类别相同的引用类型。  

总结：**auto 是值类型，auto& 是左值引用类型，auto&& 是转发引用（可以是左值引用，也可以是右值引用）**    

# decltype #  
decltype 的用途是获得一个表达式的类型，结果可以跟类型一样使用  

一般用法：  
* decltype(变量名) 可以获得变量的精确类型。  
* decltype(表达式) （表达式不是变量名，但包括 decltype((变量名)) 的情况）可以获得表达式的引用类型；除非表达式的结果是个纯右值（prvalue），此时结果仍然是值类型。  


如果我们有 int a;，那么：  
* decltype(a) 会获得 int（因为 a 是 int）。  
* decltype((a)) 会获得 int&（因为 a 是 lvalue）。  
* decltype(a + a) 会获得 int（因为 a + a 是 prvalue）。


# decltype(auto) # 
使用 auto 不能通用地根据表达式类型来决定返回值的类型。不过，decltype(expr) 既可以是值类型，也可以是引用类型。  


    decltype(expr) a = expr;
    decltype(auto) a = expr; //添加auto，更为简洁
**decltype(auto) 可以根据返回表达式通用地决定返回的是值类型还是引用类型。**    
这种代码主要用在通用的转发函数模板中：你可能根本不知道你调用的函数是不是会返回一个引用。这时使用这种语法就会方便很多。  


从 C++14 开始，函数的返回值也可以用 auto 或 decltype(auto) 来声明了。  
**同样的，用 auto 可以得到值类型，用 auto& 或 auto&& 可以得到引用类型；而用 decltype(auto) 可以根据返回表达式通用地决定返回的是值类型还是引用类型。**  




元编程应用  

  template<typename T1,typename T2>  
  decltype(x+y) add(T1 x,T2 y);//编译错误，因为x+y在T1 x,T2 y声明之前引用  
  //采用auto，和->指定函数返回类型
  auto add(T1 x,T2 y)->decltype(x+y)  
  

lamda 表达式的类型
auto cmp = [const P p1,const P p2]{
    return ...;
}

typyof功能  
需要调用容器有比较函数的构造函数  
std::set<P,decltype(cmp)> coll() 编译报错，因为lambda没有构造函数和赋值操作，
std::set<P,decltype(cmp)> coll(cmp);

