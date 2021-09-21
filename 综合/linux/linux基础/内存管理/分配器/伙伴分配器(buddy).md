https://zhuanlan.zhihu.com/p/73562347  
https://blog.csdn.net/u012142460/article/details/107433754    
https://zhuanlan.zhihu.com/p/105589621  
# 伙伴定义 #  
* 两个内存大小相同  
* 两个内存地址连续
* 两个内存从同一块大内存分离出来  

# 原理 #   
buddy分配系统在普通内存池的基础上，允许两个大小相同且相邻的内存块合并，合并之后的内存块的「尺寸」增大，因而将被移动到另一个内存池的free list上。  
来看下面这个例子，  
内存共有1024字节，  
由32, 64, 128, 256, 512字节为「尺寸」的5个free list组织起来，最小分配单位为32字节（对应位图中的1个bit）。  
假设现在0到448字节的内存已使用，448到1024字节的内存为空闲（字母编号从A开始，表示分配顺序）。     

![image](https://user-images.githubusercontent.com/20179983/132301800-d39526d4-2e3e-43a5-a649-0438fe159168.png)


现在我们要申请128字节的内存，那么首先应该查看「尺寸」为128字节的free list，但很可惜没有，那再看看256字节的free list，还是没有，只能再往上找，到512字节的free list这儿，终于有了一个空闲的内存块A'。  
那么将A'划分为256字节的E和E'，再将内存块E划分成128字节的F和F'，内存块F即是我们需要的内存。之后，在此过程中产生的E'和F'将分别被挂接到「尺寸」为256字节和128字节的free list上，位图中bits的值也会相应变化。  

![image](https://user-images.githubusercontent.com/20179983/132301970-1adb5392-5fe4-40e3-a2d9-e7b9ede32756.png)

接下来释放128字节的内存块C，由于C相邻的两个内存块都不是空闲状态，因此不能合并，之后C也将被挂接到「尺寸」为128字节的free list上。  

![image](https://user-images.githubusercontent.com/20179983/132302017-de5a5e43-de68-4165-942a-247847c4be3a.png)
然后释放64字节的内存块D，分配器根据位图可知，右侧的D'也是空闲的，且D和D'的大小相同，因此D和D'将合并。按理合并后的空闲内存块C'为128字节，应该被添加到「尺寸」为128字节的free list上，但因为左侧的C也是空闲的，且C和C'的大小相同，因此C和C'还将合并形成B'，合并后的空闲内存块将被挂接到「尺寸」为256字节的free list上。  

![image](https://user-images.githubusercontent.com/20179983/132302076-b8d2ff07-1778-4a01-9a4b-d5588fe4ae50.png)

在buddy分配系统中，从物理上，内存块按地址从小到大排列；从逻辑上，内存块通过free list组织。通过对相邻内存块的合并，增加了内存使用的灵活性，减少了内存碎片。  

但是实现合并有一个前提，就是内存块的尺寸必须是2的幂次方（称为"order"），这也是buddy系统划分内存块的依据。此外，每次内存释放都要查找左右的buddy是否可以合并，还可能需要在free list之间移动，也是一笔不小的开销。  

# 实现 #  
**Linux中物理内存分配的最小粒度为page frame，而属性相同的page被划分到了同一个zone中**。    
在"struct zone"的定义中，包含了一个"struct free_area"的数组（代码位于"/include/linux/mmzone.h"），这个数组就是用于实现buddy系统的。  

    struct zone {
        /* free areas of different sizes */
        struct free_area    free_area[MAX_ORDER];
        ...
    }

    #define MAX_ORDER 11
    #define MAX_ORDER_NR_PAGES (1 << (MAX_ORDER - 1))
    
"MAX_ORDER"的值默认为11，一次分配可以请求的page frame数目为1, 2, 4……最大为1024，**即order越大，page frame的空间越大**。    

## 复合页 ##  
如果"order"的值大于0，那么同一个free list中的一个节点上的page frames不只一个，它们构成了一个"compound pages"，其中的第一个page frame被称为"head page"（如下图蓝色部分所示），其余的page frame被称为"tail page"（如下图黄色部分所示）。  
![image](https://user-images.githubusercontent.com/20179983/132304791-f90935d8-a46f-4276-9526-21e149116068.png)
一个page是否属于compound page可通过PageCompound()函数判断，依据是flag为"PG_Head"或者"PG_Tail"。  
在compound page中，"order"的值记录在第二个page的描述符中    
![image](https://user-images.githubusercontent.com/20179983/132309584-b8aa4d72-962c-4078-82d0-a0a67cc5a414.png)


    int PageCompound(struct page *page)
    {
        return test_bit(PG_head, &page->flags) || PageTail(page);
    }

    set_compound_order(struct page *page, unsigned int order)
    {
        page[1].compound_order = order;
    }

内核并没有为描述compound page而单独定义结构体，一个compound page的相关信息（比如order）是「塞」在组成这个compound page的页面的"struct page"中的，而"struct page"又是对所占内存限制极为严苛的，很多「位域」都是复用，这使得存储compound page的信息显得非常的不直观。  
加之"struct page"中的「位域」也是在不断演进和变化中，因此本文就不展开讲解这块了，需要深入了解的请参考文末的两个链接。  

## 迁移类型 - pageblock ##  
**每个"free_area"包含不只一个free list，而是一个free list数组（形成二维数组），包含了多种"migrate type"，以便将具有相同「迁移类型」的page frame尽可能地分组（同一类型的所有order的free list构成一组"pageblocks"），这样可以使包括memory compaction在内的一些操作更加高效**。  

    struct free_area {
        struct list_head    free_list[MIGRATE_TYPES];
        unsigned long       nr_free;
    };

比如，"MIGRATE_MOVABLE"表示page frame可移动，"MIGRATE_UNMOVABLE"与之相反，而"MIGRATE_CMA"则是专用于CMA区域。  

![image](https://user-images.githubusercontent.com/20179983/132310019-c84b65e4-4f73-4a5b-88f8-2eaa12bd8427.png)

分配的时候会首先按照请求的migrate type从对应的pageblocks中寻找，如果不成功，其他migrate type的pageblocks中也会考虑（类似于https://zhuanlan.zhihu.com/p/81961211 中zone之间的fallback），在一定条件下，甚至有可能改变pageblock的migrate type。   

![image](https://user-images.githubusercontent.com/20179983/132310191-9babac89-dc5d-4ab2-8fff-61a432b5ae0c.png)
可以通过"/proc/buddyinfo"查看各个zones中不同migrate type的page frame数目。    
![image](https://user-images.githubusercontent.com/20179983/132310228-7a7f4ad6-81a3-41da-98cf-19be0f4fd3da.png)  
通过查看"/proc/pagetypeinfo"可进一步获取同一migrate type中不同order的compound page数目。  

![image](https://user-images.githubusercontent.com/20179983/132310270-d4e92f25-f8a2-407f-ae45-e54a89c82ae6.png)

## buddy内存释放 ##  
释放page frame的基本函数是free_pages()：  

void free_pages(unsigned long addr, unsigned int order)  
其实现流程大致如下图所示：  
![image](https://user-images.githubusercontent.com/20179983/132310416-2609ae5d-ebf3-430a-9f90-e1d2ceedd6ab.png)  
其实single page可以视作是compoud pages中"order"为0的特例，但single page在分配和释放时多了一层机制。在计算机领域，从硬件到软件，可谓“无处不cache”，  内存分配这么重要的环节自然也是少不了cache的。Linux中对应的实现为per-CPU的page frame cache（简称pcp http://jake.dothome.co.kr/per-cpu-page-frame-cache/ ）。   
如果是single page，那么分配时会先从pcp获取，pcp为空再从buddy系统批量申请；释放时也是先回到pcp，pcp溢满再批量回归到buddy系统。  
对于compound page，在__free_pages_ok()中，获得了物理页面号"pfn"和"migratetype"，准备好了核心函数__free_one_page()所需的各项参数。  

    static void __free_pages_ok(struct page *page, unsigned int order)
    {
        unsigned long pfn = page_to_pfn(page);
        int migratetype = get_pfnblock_migratetype(page, pfn);

        free_one_page(page_zone(page), page, pfn, order, migratetype);
        ...
    }
  
"\_\_free_one_page()"的名字有一定的误导性，它其实既可以处理single page的释放，也可以处理compound page的释放，  
其功能是：在一个single/compound page释放后，查询相邻的buddy是否是空闲的，如果是就需要合并成一个更大的compound page。合并可能会进行多次，直到不再满足合并的条件为止，在次过程中，"order"的值不断增大。  
![image](https://user-images.githubusercontent.com/20179983/132311061-381dec63-57c1-4fa8-bcd9-e7e77456a314.png)
具体的函数实现如下：  

      static inline void __free_one_page(struct page *page, unsigned long pfn,
                                        struct zone *zone, unsigned int order, int migratetype)
      {
          unsigned long uninitialized_var(buddy_pfn);
          struct page *buddy;

      continue_merging:
          while (order < max_order - 1) {
              buddy_pfn = __find_buddy_pfn(pfn, order);
              buddy = page + (buddy_pfn - pfn);

              // 不能合并
              if ((!pfn_valid_within(buddy_pfn))||(!page_is_buddy(page, buddy, order)))
                  goto done_merging;

              // 可以合并，从哪当前free area[]中移除
              del_page_from_free_area(buddy, &zone->free_area[order]);
              order++;

              // 继续合并
              if (max_order < MAX_ORDER) {
                  ...
                  max_order++;
                  goto continue_merging;
          }

      done_merging:
          // 添加到新的free_area[]中对应的free list上
          add_to_free_area(page, &zone->free_area[order], migratetype);
      }

首先是根据"pfn"查找buddy page，因为一个page和它的buddy在物理内存上是连续的，确定"order"之后，就可以根据其中一个的物理页面号，计算出另一个的。比如一个compound page的起始pfn是8，order是1，那么它的其中一个buddy的pfn就是10。  

  Buddy = 8 ^ (1 << 1) = 8 ^ 2 = 10  
  
**要成为buddy，除了两者的大小（即order）相同，还必须属于同一个zone。**  
Buddy系统是以page frame为粒度分配的，这并不能直接满足Linux的应用需求，下文要介绍的slab分配器将可以实现更小粒度的内存分配。  




 
