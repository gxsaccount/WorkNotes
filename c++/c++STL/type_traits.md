  下面是SGI中<type_traits.h>中的__type_traits,提供的一种机制，允许针对不同型别属性，在编译期完成函数派送决定（意思是在编译期就决定是采用快速的内存直接处理操作还是采用慢速的构造，析构，拷贝，赋值操作）  
  
        struct __true_type{};
        struct __false_type{};
        template<calss type>
        struct __type_traits{
            typedef __true_type this_dummy_must_be_first;
            typedef __false_type has_trivial_default_constructor;
            typedef __false_type has_trivial_copy_constructor;
            typedef __false_type has_trivial_assignment_operator;
            typedef __false_type has_trivial_destructor;
            typedef __false_type is_POD_type;
        };

    SGI把所有的内嵌型别都定义为__false_type，定义出最保守的值。c++11 有更多的typedef  
        
        
        char类型，因为对char类型进行初始化，删除，赋值，复制，都可以通过快速的内存直接处理操作，所以这里将__false_type改为__true_type不具备这些特性
        
        __STL_TEMPLATE_NULL struct __type_traits<char>{
            typedef __true_type has_trivial_default_constructor;
            typedef __true_type has_trivial_copy_constructor;
            typedef __true_type has_trivial_assignment_operator;
            typedef __true_type has_trivial_destructor;
            typedef __true_type is_POD_type;
        }
        
        
        
        STL库中的析构工具destory()，此函数设法找到元素的数值型别，进而利用__type_traits<>求取适当措施  
        当需要释放元素时，destory()利用value_type()获得迭代器所指对象的型别，在利用__type_traits<T>判断该型别的析构函数是否无关痛痒，
        如果是__true_type则什么都不做，系统会采用内存直接处理操作，如果是__false_type才采用循环方式对每个对象进行析构。  
        元素的量大时能节省可观的时间  
        例如自己写一个复数的类， 有实部虚部（都是基本类型），析构、复制拷贝、考拷贝赋值都不要（defalut就已够用），只有释放锁，释放指针等需要自行编写这些函数
        
        **旧版本需要手动写，新版本已经可以不用手动写了**
        
        
        基本使用：
            template <typename T>
    void type_traits_output(const T& x)
    {
        cout << "\ntype traits for type : " << typeid(T).name() << endl;//i

        cout << "is_void\t" << is_void<T>::value << endl;//0
        cout << "is_integral\t" << is_integral<T>::value << endl;//1
        cout << "is_floating_point\t" << is_floating_point<T>::value << endl;//0
        cout << "is_arithmetic\t" << is_arithmetic<T>::value << endl;//1
        cout << "is_signed\t" << is_signed<T>::value << endl;//1
        cout << "is_unsigned\t" << is_unsigned<T>::value << endl;//0
        cout << "is_const\t" << is_const<T>::value << endl;//0
        cout << "is_volatile\t" << is_volatile<T>::value << endl;//0
        cout << "is_class\t" << is_class<T>::value << endl;//0
        cout << "is_function\t" << is_function<T>::value << endl;//0
        cout << "is_reference\t" << is_reference<T>::value << endl;//0
    }

    int main(int argc, const char * argv[]) {

        int a = 5;
        type_traits_output<int>(a);
        return 0;
    }
    
    
    实现：
    以is_void为例子，用偏特化实现类似于枚举的能力  
  先做 remove_cv() 去掉 const 和 volatile（多线程关键字） 这这些无关的类型性质的影响。
丢给 helper，泛化情况下的所有类型回答 false， 符合偏特化的特定类型时才回答 true。  


//remove const
template<typename _Tp>
    struct remove_const
    { typedef _Tp    type; }                  //泛化，直接返回类型
 
 
template<typename _Tp>
    struct remove_const<_Tp const>
    { typedef _Tp    type; }                  //特化 const 时候的情况，返回去掉const 后的类型
    
 //remove voletile 类似  
 
 //remove cv 
 const + voletile  
 
 template< class T >
struct is_void : std::is_same<void, typename std::remove_cv<T>::type> {};
 
 
 是不是虚函数，引用等，是编译器相关提供的支持，源码无法找到。
    
