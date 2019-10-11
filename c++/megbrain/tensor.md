1.tensor有存储有两种方式,在cpu(host设备)上和在gpu(device设备)上  

以CPU为例:  
-TensorStorage<Trait> 类管理tensor的存储  
cpu的模板特化类:
-using HostTensorStorage = TensorStorage<HostTensorStorageTrait>;  

TensorStorage类主要功能:  
1.拷贝:copy_from  
2.重置:reset
3.管理comp_node,判断有效  
4.

TensorStorage的成员:
        
        template<class T> friend class TensorStorage;

        bool m_allow_realloc = true;
        CompNode m_comp_node;

        //! current logical size; may exceed m_capacity and in such case memory
        //! would be allocate when ptr() is called
        size_t m_size = 0;

        //! usable size until end of allocated data block, excluding offset
        size_t m_capacity = 0;

        //! offset on m_data
        size_t m_offset = 0;

        RawStorage m_data;
