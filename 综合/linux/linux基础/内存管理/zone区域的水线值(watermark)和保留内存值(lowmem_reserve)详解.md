https://blog.csdn.net/u010923083/article/details/115975292  
# 1 watermark简介  
linux物理内存中的每个zone都有自己独立的3个档位的watermark值：  

最低水线(WMARK_MIN)：如果内存区域的空闲页数小于最低水线，说明该内存区域的**内存严重不足**  
低水线(WMARK_LOW)：空闲页数小数低水线，说明该内存区域的**内存轻微不足**。默认情况下，该值为WMARK_MIN的125%  
高水线(WMARK_HIGH)：如果内存区域的空闲页数大于高水线，说明该**内存区域水线充足**。默认情况下，该值为WMARK_MAX的150%  

![image](https://user-images.githubusercontent.com/20179983/134799606-a693d823-111f-45a7-aae4-bb8efb5c744f.png)



## 内存轻微不足
判断依据:在进行内存分配的时候，如果分配器（比如buddy allocator）发现当前空余内存的值低于”low”但高于”min”，说明现在内存面临一定的压力。  
回收方法：那么在此次内存分配完成后，kswapd将被唤醒，以执行内存回收操作。  
在这种情况下，内存分配虽然会触发内存回收，但不存在被内存回收所阻塞的问题，两者的执行关系是**异步**的。    
对于kswapd来说，要回收多少内存才算完成任务呢？只要把空余内存的大小恢复到”high”对应的watermark值就可以了。  
”low”可以被认为是一个警戒水位线，而”high”则是一个安全的水位线。  

## 内存严重不足  
判断依据:如果内存分配器发现空余内存的值低于了”min”，说明现在内存严重不足。  
回收方法：这里要分两种情况来讨论，一种是默认的操作，此时分配器将同步等待内存回收完成，再进行内存分配，也就是direct reclaim。  
还有一种特殊情况，如果内存分配的请求是带了PF_MEMALLOC标志位的，并且现在空余内存的大小可以满足本次内存分配的需求，那么也将是先分配，再回收。  

# 2 watermark相关结构体  
每个zone如何记录各个档位的水线和如何获取每个zone各个档位的水线值？？？
        
        struct zone {  
            /* Read-mostly fields */  

            /*
             *水位值，WMARK_MIN/WMARK_LOV/WMARK_HIGH，页面分配器和kswapd页面回收中会用到,访问用	 
             *_wmark_pages(zone) 宏
           */ 
            unsigned long watermark[NR_WMARK];    
            unsigned long nr_reserved_highatomic;
           //zone内存区域中预留的内存
            long lowmem_reserve[MAX_NR_ZONES];  
            ...
            ...
            ...
            }

        #define min_wmark_pages(z) (z->watermark[WMARK_MIN])
        #define low_wmark_pages(z) (z->watermark[WMARK_LOW])
        #define high_wmark_pages(z) (z->watermark[WMARK_HIGH])

        enum zone_watermarks {
          WMARK_MIN,
          WMARK_LOW,
          WMARK_HIGH,
          NR_WMARK
        };
# 3 watermark初始化  
每个zone对应的3个档位的水线值是如何计算出来的呢？  
在计算之前我们需要了解内核中几个全局变量值对应的意义  
## 3.1 managed_pages，spanned_pages，present_pages三个值对应的意义    
      
      /*
       * spanned_pages is the total pages spanned by the zone, including
       * holes, which is calculated as:
       *  spanned_pages = zone_end_pfn - zone_start_pfn;
       *
       * present_pages is physical pages existing within the zone, which
       * is calculated as:
       *  present_pages = spanned_pages - absent_pages(pages in holes);
       *
       * managed_pages is present pages managed by the buddy system, which
       * is calculated as (reserved_pages includes pages allocated by the
       * bootmem allocator):
       *  managed_pages = present_pages - reserved_pages;
       */
      unsigned long       managed_pages;
      unsigned long       spanned_pages;
      unsigned long       present_pages;
      
spanned_pages: 代表的是这个zone中所有的页，包含空洞，计算公式是: zone_end_pfn - zone_start_pfn  
present_pages： 代表的是这个zone中可用的所有物理页，计算公式是：spanned_pages-hole_pages  
managed_pages： 代表的是通过buddy管理的所有可用的页，计算公式是：present_pages - reserved_pages  
三者的关系是： spanned_pages > present_pages > managed_pages

## 3.2 什么是min_free_kbytes  
      min_free_kbytes:

      This is used to force the Linux VM to keep a minimum number
      of kilobytes free.  The VM uses this number to compute a
      watermark[WMARK_MIN] value for each lowmem zone in the system.
      Each lowmem zone gets a number of reserved free pages based
      proportionally on its size.

      Some minimal amount of memory is needed to satisfy PF_MEMALLOC
      allocations; if you set this to lower than 1024KB, your system will
      become subtly broken, and prone to deadlock under high loads.

      Setting this too high will OOM your machine instantly.
      
由上可知  
min_free_kbyes代表的是系统保留空闲内存的最低限  
watermark[WMARK_MIN]的值是通过min_free_kbytes计算出来的  
内核是在函数init_per_zone_wmark_min中完成min_free_kbyes的初始化，这里的min_free_kbytes值有个下限和上限，就是最小不能低于128KiB，最大不能超过65536KiB。  
在实际应用中，通常建议为不低于1024KiB  


    //计算DMA_ZONE和NORAML_ZONE中超过高水位页的个数
    lowmem_kbytes = nr_free_buffer_pages() * (PAGE_SIZE >> 10);           
    min_free_kbytes = int_sqrt(lowmem_kbytes * 16);  
