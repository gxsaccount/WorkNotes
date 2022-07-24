# shared_ptr #  
https://zhuanlan.zhihu.com/p/448376125
# unique_ptr #  
# weak_ptr #  

## shared_ptr与unique_ptr析构的区别 ##  
现象：  
      
      class Sub:public Base;
      std::shared_ptr<Base> a = std::make_shared<Sub>(Sub());  
      std::unique_ptr<Base> b = std::make_unique<Sub>(Sub());  
      
      a析构调用~Sub()（~Sub()接着调用~Base()）;  
      b析构调用~Base();
    
unique_ptr<Base>只保存了Base类型信息和对应的析构函数；  
虽然shared_ptr<Base>也是只保存了Base的类型信息，但shared_ptr构造的时候能够拿到具体类型信息Derived*，并存到引用计数块去，  
引用计数块析构的时候调用的就是子类的析构函数了。  
unique_ptr<Base>和手动new/delete管理对象内存方式相比无任何额外开销，实现零成本抽象，不保存额外信息；  
而shared_ptr因为引用计数的原因导致额外开销，那么可以存储具体类型。  
相关细节如下：先看看std::unique_ptr<Base>，其模板定义和对应的构造函数如下：  
      
    template <typename _Tp, typename _Dp = default_delete<_Tp>>
      class unique_ptr {
          template<typename _Del = _Dp, typename = _DeleterConstraint<_Del>>
          explicit unique_ptr(_Tp* __p) noexcept
          : _M_t(__p)
          { }
      };
  
通过构造函数可以发现Derived*被隐式转化成_Tp = Base类型，也就是类型擦除了。而std::shared_ptr<Base>，其模板定义和对应的构造函数如下：
    
    template<typename _Tp>
    class shared_ptr : public __shared_ptr<_Tp>
    {
        template<typename _Yp, typename = _Constructible<_Yp*>>
        explicit shared_ptr(_Yp* __p) : __shared_ptr<_Tp>(__p) { }
    }

  通过构造函数可以发现Derived*类型信息被保留到了_Yp = Derived，最终析构的时候就能调用_Yp的构造函数了。
