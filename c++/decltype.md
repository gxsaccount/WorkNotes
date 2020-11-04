推断参数的类型  

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
