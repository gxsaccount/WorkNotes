## 相关概念 ##  
[bitmap_allocator]  

    template<typename _Tp>
    class bitmap_allocator : private free_list{
        ...

        public:
        pointer allocate(size_type __n){
            if(__n>this->max_size())
                std::__throw_bad_alloc();
            if(__builtin_expect(__n==1,true))
                return this->_M_allocate_single_object();
            else{
                const size_type __b = __n*size_of(value_type);
                return reinterpret_cast<pointer>(::operator_new(__b));
            }
        }
        vois dealloccate(pointer __p,size_type __n)throw(){
            if(__builtin_expect(__p!=0,true)){
                if(__builtin_expect(__n==1,true))
                    this->M_deallocate_single_object(__p);
                else
                    ::operator delete()__p;
            }
        }
    }

适用与1次要1个元素的情况。几乎没有情况是不是一个。  
一个bitmap只能使用1中value_type  
第一次直接取64个区块，不够*2取内存取下去  
[bitmap的增长]  

**元素介绍**  
1.blocks  
一个小格为一个block    
2.super-blocks  
[super block size + use conut + bitmap + blocks]
3.bitmap  
bitmap的每一位代表每一个block的状态    
4.mini-vector  
控制所有的super-blocks    
mini-vector有控制单元
控制单元用start和finish两个指针标识一个super-blocks的开始和结束  
end_of_storage指向vector的尾部   
super-blocks不够时，mini-vector两倍成长

5.use conut（int）  
已使用的计数，方便回收,申请一个加1，释放一个减1  
6.super block size（int）   
 值为size_of(use conut) + size_of(bitmap) + size_of(blocks)  
        4+64+64*size_of(block)  

**申请过程**  


**回收过程**  
不曾做过全回收，分配规模不断倍增  
每次全回收，造成分配规模减半  
free_list(另一个mini_vecter),最多64个super block，超过便归还给os  
[全回收]  
1.super block第一次cnt为0时，将其放到free-list,在原mini-vector中国erase掉（vector元素一次前移）,且**分配规模减半**    
2.客户申请新的块时，优先从最大的super-blocks分配  
3.最大的spuer-blocks用完，会优先从前面的super-blocks中分配，而不会新建super-blocks  
4.当又1个super-blocks也需要全回收时，先执行1的操作，若free-list元素大于了64则，选一个最大的super-bloacks进行释放，未到则直接插入    
5.客户申请内存时，若需要新的super block，会优先从free-list中获取  


