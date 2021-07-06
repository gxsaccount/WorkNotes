1.红黑树  
rb_tree  
有insert_uique和insert_equal两种方式  
rb_tree的元素的值可以改变  
2.hashmap  
拉链法  
容量为M，元素的key值为K，对应位置为K%M  
当元素数量大于M时，M扩容后rehash，扩容大小为（53，97，193，389...），素数扩容，素数可以减小冲突概率   

    template<class Value,class Key,class HashFun,class ExtractKey,class EqualKey,class Alloc =alloc>
    //ExtractKey从pair里获取key的函数，EqualKey key相等的方法  
    class hashtable{
      ....
    }

迭代器  
在一个bucket的node上顺序遍历，到链表尾部，回到buckets的vectoer上的下一node  

    template<class Value,class Key,class HashFun,class ExtractKey,class EqualKey,class Alloc>
    struct __hashtable_iterator{
      ...
      node* cur;//当前链表元素
      hashtable* ht;//hashtable本身，可以回去
    }

hashtable
3.set/multiset 也可以算是个container adapter  
底层使用rb_tree  
元素的值无法改变，使用const 迭代器，保证无法改变  

