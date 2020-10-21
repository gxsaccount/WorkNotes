    
   ## 万用的hashfunc ##
   //计算种子数值
    template<typename T>
    inline void hash_combine(size_t& seed, const T& val)
    {
      seed ^= std::hash<T>()(val) + 0x9e3779b9 + (seed << 6) + (seed >> 2);//黄金比例1.9e3779b9 -1
    }

    //递归调用出口
    template<typename T>
    inline void hash_val(size_t& seed, const T& val)
    {
      hash_combine(seed, val);
    }

    template<typename T, typename... Types>
    inline void hash_val(size_t& seed, const T& val, const Types&... args)
    {
      //重新计算种子值
      hash_combine(seed, val);
      //递归调用
      hash_val(seed, args...);
    }
    
    //一般起始
    template<typename... Types>
    inline size_t hash_val(const Types&... args)
    {
      size_t seed = 0;
      hash_val(seed, args...);
      return seed;
    }

## struct hash 偏特化 ##  

    hash<T>
