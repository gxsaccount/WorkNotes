

int values[]{1,2,3};

编译器看到{t1,t2,...,tn}，便做出一个initalizer_list<T>,它关联至一个array<T,n>,调用函数时编译器可以逐一的传给函数  
例如：
    P(int a,int b){}
    P{1,2}
    
如果函数的参数是initalizer_list<T>，就不会逐一的传给函数，而是整个过去   
 
 
 
 
 
     template<class _E>
    class initializer_list
    {
    public:
      typedef _E value_type;
      typedef const _E& reference;
      typedef const _E& const_reference;
      typedef size_t size_type;
      typedef const _E* iterator;
      typedef const _E* const_iterator;

    private:
      iterator _M_array;
      size_type _M_len;

      // The compiler can call a private constructor.
      constexpr initializer_list(const_iterator __a, size_type __l)
      : _M_array(__a), _M_len(__l) { }

    public:
      constexpr initializer_list() noexcept
      : _M_array(0), _M_len(0) { }

      constexpr size_type size() const noexcept { return _M_len; }
      constexpr const_iterator begin() const noexcept { return _M_array; }
      constexpr const_iterator end() const noexcept { return begin() + size(); }
    };
    
    
    可以看到initializer_list内部存储了两个变量：_M_array(迭代器变量)和_M_len(长度)。当调用构造函数的时候，就会将这两个变量进行初始化赋值。那这两个变量是怎么来的呢？

其实，**当用{}进行初始化的时候，首先会创建一个array，并将初始化元素存放起来。然后，调用initializer_list的构造函数，用array首元素的迭代器和array的元素个数，进行初始化。**

如果仔细看会发现，initializer_list构造函数是private类型的，按道理来说，是没有办法外部调用的！但是，在源码中也注明了，编译器可以调用该private构造函数。  


除此之外，还有如下几个注意点：

initializer_list是一个轻量级的容器类型，内部定义了iterator等容器必需的概念。其中有3个成员接口：size()、begin()和end()。遍历时取得的迭代器是只读的，无法修改其中的某一个元素的值；
对于initializer_list而言，它可以接收任意长度的初始化列表，但要求元素必须是同种类型T(或可转换为T)；
Initializer_list内部并不负责保存初始化列表中的元素拷贝，仅仅是列表中元素的引用而己。因此，通过过拷贝构造对象与原对象共享列表中的元素空间。也就是说，initializer_list的内部并没有内含该array的内容，仅仅是拥有指向array的迭代器。如果拷贝构造或者拷贝赋值的话，array的内容只有一份，但有两份迭代器指向。如果对initializer_list对象copy一个副本，默认是浅拷贝，此时两个对象指向同一个array。这是危险的。  

也就是说，下面的情形是不允许的：

std::initializer_list<int> func(void)
{
  int a = 1, b = 2;
  return {a, b};      //由于initializer_list保存的是对象的引用，但a与b是局部变量在
                      //func返回后会被释放，initializer_list内部会存在空悬指针！危险！
                      //正确的做法可以将返回值改为保存副本的容器，如vector<int>
}

//注意下面s1、 s2、s3和s4均共享元素空间
initializer_list<string> s1 = { "aa", "bb", "cc", "dd" };
initializer_list<string> s2 = s1;
initializer_list<string> s3(s1);
initializer_list<string> s4;
s4 = s1;


其他
之前版本的C++，min、max只可以进行两个数之间的比较，但是有了initializer_list之后，现在支持如下的比较：

std::max({4, 3, 5, 7});
std::min({4, 3, 5, 7});
1
2
这是因为，源码中增加了如下的定义：

template<typename _Tp>
inline _Tp max(initializer_list<_Tp> __l)
{ return *std::max_element(__l.begin(), __l.end()); }

template<typename _Tp>
inline _Tp min(initializer_list<_Tp> __l)
{ return *std::min_element(__l.begin(), __l.end()); }
