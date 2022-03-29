
class shape_wrapper {
public:
  explicit shape_wrapper(
    shape* ptr = nullptr)
    : ptr_(ptr) {}
  ~shape_wrapper()
  {
    delete ptr_;
  }
  shape* get() const { return ptr_; }

private:
  shape* ptr_;
};

template <typename T>
class common_wrapper {
public:
  explicit common_wrapper(
    T* ptr = nullptr)
    : ptr_(ptr) {}
  ~common_wrapper()
  {
    delete ptr_;
  }
  T* get() const { return ptr_; }

  T& operator*(){return *ptr_;} 
  T* operator->() const { return ptr_; }
  operator bool() const { return ptr_; }
private:
  T* ptr_;
};

//禁止拷贝,可防止double free 指针    

template <typename T>
class smart_ptr {
  …
  smart_ptr(const smart_ptr&) = delete;
  smart_ptr& operator=(const smart_ptr&) = delete;
  …
};

//拷贝时移交控制权,auto_ptr实现方案，c++17以废除，容易出现不小心拷贝导致原指针失效的问题    
template <typename T>
class smart_ptr {
  …
  smart_ptr(const smart_ptr& other) {
      ptr_ = other.release();
  };
  smart_ptr& operator=(const smart_ptr& rhs) {
    //   if(this==*smart_ptr) return *this;
      smart_ptr(rhs).swap(*this);//临时的smart_ptr最后拿到*this的ptr_,this拿到rhs的ptr_,函数结束时，释放smart_ptr，rhs的值为nullptr
      return *this;
  };
  T* release(){
      T* ptr = ptr_;
      ptr_ = nullptr;
      return ptr;
  }

  void swap(smart_ptr& rhs){
      using std::swap;
      swap(ptr_,rhs.ptr_);//copy and swap，提供异常安全性保证
  }
  …
};
// （1）当出现异常的时候，因为this参与了运算，所以不能够保证异常过程中this没有被修改，不能够保证this的完整性。 
// （2）上面的处理方法，先生成一个临时变量，在生成临时变量的时候出现异常，也是不会影响到原来赋值符号左边对象的。

//移动指针unique_ptr的基本行为  
template <typename T>
class smart_ptr {
  …
  smart_ptr(smart_ptr&& other) {//把拷贝构造函数中的参数类型 smart_ptr& 改成了 smart_ptr&&；现在它成了移动构造函数。  
      ptr_ = other.release();
  };
  smart_ptr& operator=(smart_ptr rhs) {//在接收参数的时候，会调用构造函数，如果调用的是拷贝构造，那赋值操作就是拷贝，如果调用的是移动构造，那么赋值操作就是移动。
      rhs.swap(*this);
      return *this;
  };

  //实现子类指针向基类指针的转换,这个构造函数不被编译器看作移动构造函数，因而不能自动触发删除拷贝构造函数的行为,因为万能引用  
  template <typename U>
  smart_ptr(smart_ptr<U>&& other) //在函数模板中，如果参数列表是带“&&”的模板参数，那么这个参数的类型不是右值引用，而是万能引用  
  {
    ptr_ = other.release();//不正确的转换(U到T)会在代码编译时直接报错
  }  
  …
};
//如果我提供了移动构造函数而没有手动提供拷贝构造函数，那后者自动被禁用,但是建议全部补齐，设置delete，增加可读性  

//可以得到如下结果  
smart_ptr<shape> ptr1{create_shape(shape_type::circle)};
smart_ptr<shape> ptr2{ptr1};             // 编译出错
smart_ptr<shape> ptr3;
ptr3 = ptr1;                             // 编译出错
ptr3 = std::move(ptr1);                  // OK，可以
smart_ptr<shape> ptr4{std::move(ptr3)};  // OK，可以


//shared_ptr   

