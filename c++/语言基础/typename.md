# typename #  

用于声明模板内的标识符是类型  

考虑如下例子:  


        template<typename T>
        class MyClass 
        {
        public:
            ...
            void fool()
            {
                typename T::SubType* ptr;
            }
        };

第二个typename用于声明SubType是类T内的类型，因此ptr是个指向类型T::SubType的指针。  

如果没有typename，SubType会被认为是个非类型成员（比如静态数据成员或者枚举常量），这样该表达式T::SubType* ptr将是类T的静态SubType成员和ptr相乘  

通常，typename在一个名字依赖于模板参数并且是个类型时必须使用。  
* typename的一个应用便是在泛型代码中声明标准容器的迭代器。  

        // basics/printcoll.hpp

        #include <iostream>

        // print elements of an STL container
        template<typename T>
        void printcoll(T const& coll)
        {
            typename T::const_iterator pos; // iterator to iterate over coll
            typename T::const_iterator end(coll.end()); // end position
            for(pos.coll.begin();  pos!=end; ++pos)
            {
                std::cout << *pos << ' ';
            }
            std::cout << '\n';
        }

