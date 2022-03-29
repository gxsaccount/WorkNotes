数组，2倍扩容  

template<class T,Alloc = alloc>
class vector{
  public:
  typedef T value_type;
  typedef value_type* iteractor; //T*
  ...
};

因为内存连续，迭代器是指针，需要通过traits获得五种asociate_type（见迭代器介绍）
