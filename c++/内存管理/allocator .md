## per_class_allocator ##
1.避免类型new时多次调用malloc
2.malloc每次new的内存有cookie，会多用内存，  
3.使用内存池，减少malloc次数  

## 方法一 ##  
原理：在类中定义一个指针，形成单向链表，减少malloc的次数，即也是减少cookie
缺点：指针会多占用4个字节，且每次使用完的内存没有还给操作系统，占用内存会一直增加，每次新加类都需要重载一个operator new、delete  
实现： 
    namespace per_class_allocator {

    class Screen {
        public:
          Screen(int x) : i(x) {};
          int get() { return i; }
          void*  operator new(size_t);
          void operator delete(void*, size_t);
        private:
          Screen * next;  //又多申请4个字节，膨胀百分百，降低malloc的次数，去除cookie,第一版多耗用一个next指针
          static Screen* freeStore;
          static const int screenChunk;
        private:
          int i;
        };
      }

      namespace per_class_allocator {
        Screen* Screen::freeStore = 0;
        const int Screen::screenChunk = 24;
          void* Screen::operator new(size_t size){
              Screen *p;
              if(!freeStore){
                  //linked list是空的，所以申请一大块
                  size_t chunk = screenChunk * size;
                  freeStore = p = reinterpret_cast<Screen*>(new char[chunk]);
                  //将一大块分割片片，当做linked list串接起来
                  for(;p!=&freeStore[screenChunk-1];++p){
                      p->next=p+1;
                  }
                  p->next=0;
              }
          }
          //重载Screen类的operator delete
        void Screen::operator delete(void *p, size_t) {
          //将deleted object插回free list前端
          (static_cast<Screen*>(p))->next = freeStore;
          freeStore = static_cast<Screen*>(p);
        }
      }

      //开始测试
      void per_class_allocator_function() {
          std::cout << sizeof(Screen) << std::endl; //8
          size_t const N = 10;
          Screen* p[N];

          for (int i = 0; i < N; ++i)
              p[i] = new Screen(i);

          //输出前10个pointers，比较其间隔
          for (int i = 0; i < 10; ++i)
              std::cout << p[i] << std::endl;

          for (int i = 0; i < N; ++i)
              delete p[i];
      }


## 方法二 ##   
原理：使用**union**，分配前是next指针，分配后变为对应class  
缺点：使用完的内存并没有还给操作系统，占用内存会一直增加，每次新加类都需要重载一个operator new、delete  
实现： 

    namespace per_class_allocator_two {
        void per_class_allocator_two_function();

        class Airplane {
        private:
            struct AirplaneRep {
                unsigned long miles;
                char type;
            };
        private:
            union { 
                AirplaneRep rep;
                Airplane* next; //借用同一个东西的前四个字节作为指针来用
            };
        public:
            unsigned long getMiles() { return rep.miles; }
            char getType() { return rep.type; }
            void set(unsigned long m, char t) {
                rep.miles = m; 
                rep.type = t;
            }
        public:
            static void* operator new(size_t size);
            static void operator delete(void* deadObject, size_t size);
        private:
            static const int BLOCK_SIZE;
            static Airplane* headOfFreeList;
        };
    }

    Airplane* Airplane::headOfFreeList;
    const int Airplane::BLOCK_SIZE = 512;

    //重载Airplane的operator new
    void* Airplane::operator new(size_t size) {
        //如果大小有误，转交给operator new()，继承时size变化会引起错误  
        if (size != sizeof(Airplane))
            return ::operator new(size);
        Airplane* p = headOfFreeList;
        if(p)//如果p有效，就把list的头部下移一个元素
            headOfFreeList = p->next;
        else{
            //free list 已空，申请分配一个大块内存
            Airplane* newBlock = static_cast<Airplane*>(::operator new(BLOCK_SIZE * sizeof(Airplane)));

            //再将每个小块串成一个free list,但是要跳过#0,它被传回，作为本次成果
            for(int i=1;i<BLOCK_SIZE-1;++i){
                newBlock[i].next = &newBlock[i+1];
            }
            newBlock[BLOCK_SIZE - 1].next = 0; //结束list
            p = newBlock;
            headOfFreeList = &newBlock[1];
        }
        return p;

    }   
    //重载Airplane类的operator delete
    //并没有还给操作系统，还是在这个自由链表中
    void Airplane::operator delete(void* deadObject, size_t size) { 
        if (deadObject == 0) return;
        if (size != sizeof(Airplane)) {
            ::operator delete(deadObject);
            return;
        }
        Airplane* carcass = static_cast<Airplane*>(deadObject);
        carcass->next = headOfFreeList;
        headOfFreeList = carcass;
    }


    void per_class_allocator_two_function() {
        std::cout  << sizeof(Airplane) << std::endl;
        size_t const N = 10;
        Airplane* p[N];

        for (int i = 0; i < N; ++i)
            p[i] = new Airplane;
        //随机测试object是否正常
        p[1]->set(1000, 'A');
        p[5]->set(2000, 'B');
        p[8]->set(500000, 'C');

        //输出10个pointers
        for (int i = 0; i < N; ++i)
            std::cout << p[i] << std::endl;
        for (int i = 0; i < N; ++i)
            delete p[i];
    }
    // 8
    // 007312C8
    // 007312D0
    // 007312D8
    // 007312E0
    // 007312E8
    // 007312F0
    // 007312F8
    // 00731300
    // 00731308
    // 00731310
    // 请按任意键继续. . .

    

