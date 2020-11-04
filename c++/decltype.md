推断参数的类型  

元编程应用  

  template<typename T1,typename T2>  
  decltype(x+y) add(T1 x,T2 y);//编译错误，因为x+y在T1 x,T2 y声明之前引用  
  //采用auto，和->指定函数返回类型
  auto add(T1 x,T2 y)->decltype(x+y)  
  

auto cmp = [const P p1,const P p2]{
    return ...;
}

typyof功能  
std::set<P,decltype(cmp)> coll(cmp);
