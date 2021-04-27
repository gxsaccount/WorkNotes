1.一般用于回调函数  
    
    struct A {
    void func() {
        // only have "this" ptr ?
      }
    };

    int main() {
      A* a;
      std::shared_ptr<A> sp_a(a);
    }
    当A* a被shared_ptr托管的时候,如何在func获取自身的shared_ptr成了问题.  
    
    这里就需要用enable_shared_from_this改写:struct A : public enable_shared_from_this {
    void func() {
        std::shared_ptr<A> local_sp_a = shared_from_this();
        // do something with local_sp
      }
    };
    
3.实现（简化）：从weak_ptr安全的生成一个自身的shared_ptr.
    
    mutable weak_ptr<_Ty> _Wptr;
    _NODISCARD shared_ptr<_Ty> shared_from_this() {
        return shared_ptr<_Ty>(_Wptr);
    }
    
3.原理：  
  
    在异步调用中，存在一个保活机制，异步函数执行的时间点我们是无法确定的，然而异步函数可能会使用到异步调用之前就存在的变量。为了保证该变量在异步函数执期间一直有效，我们可以传递一个指向自身的share_ptr给异步函数，这样在异步函数执行期间share_ptr所管理的对象就不会析构，所使用的变量也会一直有效了（保活）
