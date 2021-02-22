# 分块法增加cache命中 #  

    DO I = 1, N
      DO J = 1, M
        A(I) = A(I) + B(J)  
      END DO
    END DO  


//A(I)在每一轮J循环中被重用
//B(J)在每一轮I循环中会被重用  
//当前由于I是外层循环，所以当B(J)在J层循环中的跨度太大时（无法fit in the cache），则在被下一次I重用时数据已被清出缓存  
//计算cache miss。假设每个cache line能容纳b个数组元素，associativity是fully associative，则可计算出A的cache miss次数是N/b，B的cache miss次数是N*M/b。  


    DO J = 1, M, T
      DO I = 1, N
        DO jj = J, min(J+T-1, M)
          A(I) = A(I) + B(jj)
        END DO
      END DO
    END DO

//tile的本质当总的数据量无法fit in cache的时候，把数据分成一个一个tile，让每一个tile的数据fit in the cache。
//所以tiling一般从最内层循环开始（tile外层循环的话一个tile就包括整个内层循环，这样的tile太大）
//注意当我们tile J层循环的时候，tile以后J层循环就跑到了外层（loop interchange），这样又会影响A的缓存命中率。
//该变换又称为strip-mine-and-interchange。我们可以计算此时A的cache miss次数是(M/T) * (N/b)，B的cache miss次数是T/b * M/T = M/b（每一轮J层循环miss一次），
//所以总共的cache miss是MN/(bT) + M/b，tile之前是N/b+N*M/b。所以在M和N的大小也相当的情况下做tiling大约能将cache miss缩小T倍

    DO I = 1, N, T
      DO J = 1, M
        DO ii = I, min(I+T-1, N)
          A(ii) = A(ii) + B(J)
        END DO
      END DO
    END DO
//此时A的cache miss次数是T/b * N/T，B的cache miss次数是M/b*(N/T)，加起来就是(MN)/(bT)+N/b，而tile J层循环得到的cache miss是(MN)* (bT)+M/b，
//所以对于该循环到底应该tile I层循环还是J层循环更好其实取决于M和N的相当大小。
