## new handler ##
当operator new没有能力为你分配出申请的memory(大部分情况是没有足够的内存)，会抛出std::bad_alloc exception。某些编译器返回0；  
抛出异常之前会先**多次**调用由使用者设定的handler。  

  typedef void(*new handler)();
  new_handler set_new_handler(new_handler p) throw();  
  
new_handler只有两种选择：  
1.让更多的memory可用  
2.调用abort()或exit()  

实例：  

void noMoreMemory(){
  cerr<<"out of memory";
  abort();//不调用abort(),这个函数会被不断地调用
}

void main(){
  set_new_handler(noMoreMemory);
  int* p = new int[100000000000000000000000000000000];
  assert()p;
  
}
