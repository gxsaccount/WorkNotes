![image](https://user-images.githubusercontent.com/20179983/132117659-38b5659f-0573-4d8d-b3d9-a6ad748adb5a.png)



brk  
brk系统调用，扩大或缩小进程堆空间。将数据段.data的最高地址指针_edata往高地址推；只分配虚拟空间，不对ing物理内存。第一次读、写数据时，引起内核缺页中断，然后虚拟地址空间建立映射关系。  
![image](https://user-images.githubusercontent.com/20179983/132118138-172e9679-60c7-4814-9746-ce0dd4951579.png)
brk系统调用源码：  
      
      https://elixir.bootlin.com/linux/v4.20.17/source/include/linux/mm_types.h#L416
      
      //堆的新边界
      newbrk = PAGE_ALIGN(brk);
      //堆的老边界
      oldbrk = PAGE_ALIGN(mm->brk);
      if (oldbrk == newbrk)
        goto set_brk;

       //释放堆内存
      /* Always allow shrinking brk. */
      if (brk <= mm->brk) {
        //do_munmap删除用户空间地址newbrk到oldbrk-newbrk的线性空间区，并删除vma线性区对应的页表项，释放相应的页。  
        if (!do_munmap(mm, newbrk, oldbrk-newbrk))
          goto set_brk;
        goto out;
      }
      
      //申请堆内存
      /* Check against existing mmap mappings. */
      if (find_vma_intersection(mm, oldbrk, newbrk+PAGE_SIZE))
        goto out;

      /* Ok, looks good - let it rip. */
      if (do_brk(oldbrk, newbrk-oldbrk) != oldbrk)
        goto out;
        
    //分配成功后更新堆当前边界  
    set_brk:
      mm->brk = brk;
      populate = newbrk > oldbrk && (mm->def_flags & VM_LOCKED) != 0;
      up_write(&mm->mmap_sem);
      if (populate)
        //mm_populate可能会使用mlokall()将进程中全部的虚拟空间加锁，防止内存被交换  
        //mm_populate会分配物理内存并建立映射关系  
        mm_populate(oldbrk, newbrk - oldbrk);
      return brk;

    out:
      retval = mm->brk;
      up_write(&mm->mmap_sem);
      return retval;
    }


mmap 
mmap申请大块（>128k）内存,匿名文件映射区  
将文件映射到堆和栈之间的虚拟内存，将IO变为读写内存操作，先从设备加载文件，建立address space（缓存），更新页表后返回虚拟地址。  
对于堆申请来讲，mmap是映射内存空间到物理内存。mmap是进程的虚拟地址空间中（堆和栈中间，文件映射区），找一块空闲的虚拟内存。  
一个进程映射一个文件到自己的虚拟内存空间，也要通过mmap银蛇内存空间到物理内存再到文件。  
mmap调用核心源码：  

      SYSCALL_DEFINE6(mmap_pgoff, unsigned long, addr, unsigned long, len,
          unsigned long, prot, unsigned long, flags,
          unsigned long, fd, unsigned long, pgoff)
      {
        struct file *file = NULL;
        unsigned long retval = -EBADF;

        if (!(flags & MAP_ANONYMOUS)) {//非匿名映射，文件映射到用户进程
          audit_mmap_fd(fd, flags);
          file = fget(fd);//通过fd获取file，从而获得inode信息，关联磁盘文件，后面关闭fd
          if (!file)
            goto out;
          if (is_file_hugepages(file))
            len = ALIGN(len, huge_page_size(hstate_file(file)));
          retval = -EINVAL;
          if (unlikely(flags & MAP_HUGETLB && !is_file_hugepages(file)))
            goto out_fput;
        } else if (flags & MAP_HUGETLB) {
          struct user_struct *user = NULL;
          struct hstate *hs;

          hs = hstate_sizelog((flags >> MAP_HUGE_SHIFT) & SHM_HUGE_MASK);
          if (!hs)
            return -EINVAL;

          len = ALIGN(len, huge_page_size(hs));
          /*
           * VM_NORESERVE is used because the reservations will be
           * taken when vm_ops->mmap() is called
           * A dummy user value is used because we are not locking
           * memory so no accounting is necessary
           */
          file = hugetlb_file_setup(HUGETLB_ANON_FILE, len,
              VM_NORESERVE,
              &user, HUGETLB_ANONHUGE_INODE,
              (flags >> MAP_HUGE_SHIFT) & MAP_HUGE_MASK);
          if (IS_ERR(file))
            return PTR_ERR(file);
        }

        flags &= ~(MAP_EXECUTABLE | MAP_DENYWRITE);
        
        //做完安全权限检查后，调用主要实现函数do_mmap_pgoff
        retval = vm_mmap_pgoff(file, addr, len, prot, flags, pgoff);
      out_fput:
        if (file)
          fput(file);
      out:
        return retval;
      }

      #ifdef __ARCH_WANT_SYS_OLD_MMAP
      struct mmap_arg_struct {
        unsigned long addr;
        unsigned long len;
        unsigned long prot;
        unsigned long flags;
        unsigned long fd;
        unsigned long offset;
      };
      
      
      
      
      
      unsigned long do_mmap_pgoff(struct file *file, unsigned long addr,
			unsigned long len, unsigned long prot,
			unsigned long flags, unsigned long pgoff,
			unsigned long *populate)
      {
        struct mm_struct *mm = current->mm;
        vm_flags_t vm_flags;

        *populate = 0;

        /*
         * Does the application expect PROT_READ to imply PROT_EXEC?
         *
         * (the exception is when the underlying filesystem is noexec
         *  mounted, in which case we dont add PROT_EXEC.)
         */
        if ((prot & PROT_READ) && (current->personality & READ_IMPLIES_EXEC))
          if (!(file && (file->f_path.mnt->mnt_flags & MNT_NOEXEC)))
            prot |= PROT_EXEC;

        if (!len)
          return -EINVAL;
        
        //对于非MAP_FIXED,addr不能小于mmap_min_addr大小，如果小于则使用mmap？？？
        if (!(flags & MAP_FIXED))
          addr = round_hint_to_min(addr);
        
        //检查len是否溢出
        /* Careful about overflows.. */
        len = PAGE_ALIGN(len);
        if (!len)
          return -ENOMEM;
        
        //offset 是否溢出
        /* offset overflow? */
        if ((pgoff + (len >> PAGE_SHIFT)) < pgoff)
          return -EOVERFLOW;
        
        /进程中mmap个数是否有限制   
        /* Too many mappings? */
        if (mm->map_count > sysctl_max_map_count)
          return -ENOMEM;
        
        //在创建的ma区域，寻找一块足够大小的空闲区域，返回空间的首地址  
        /* Obtain the address to map to. we verify (or select) it and ensure
         * that it represents a valid section of the address space.
         */
        addr = get_unmapped_area(file, addr, len, pgoff, flags);
        if (addr & ~PAGE_MASK)
          return addr;

        //根据prot/flags以及mm->flags来得到vm_flags
        /* Do simple checking here so the lower-level routines won't have
         * to. we assume access permissions have been handled by the open
         * of the memory object, so we don't do any here.
         */
        vm_flags = calc_vm_prot_bits(prot) | calc_vm_flag_bits(flags) |
            mm->def_flags | VM_MAYREAD | VM_MAYWRITE | VM_MAYEXEC;

        if (flags & MAP_LOCKED)
          if (!can_do_mlock())
            return -EPERM;

        if (mlock_future_check(mm, vm_flags, len))
          return -EAGAIN;
        
        //文件映射情况处理，主要更新vm_flags  
        if (file) {
          struct inode *inode = file_inode(file);

          switch (flags & MAP_TYPE) {
          case MAP_SHARED://共享文件映射
            if ((prot&PROT_WRITE) && !(file->f_mode&FMODE_WRITE))
              return -EACCES;

            /*
             * Make sure we don't allow writing to an append-only
             * file..
             */
            if (IS_APPEND(inode) && (file->f_mode & FMODE_WRITE))
              return -EACCES;

            /*
             * Make sure there are no mandatory locks on the file.
             */
            if (locks_verify_locked(file))
              return -EAGAIN;

            vm_flags |= VM_SHARED | VM_MAYSHARE;
            if (!(file->f_mode & FMODE_WRITE))
              vm_flags &= ~(VM_MAYWRITE | VM_SHARED);

            /* fall through */
          case MAP_PRIVATE://私有文件映射  
            if (!(file->f_mode & FMODE_READ))
              return -EACCES;
            if (file->f_path.mnt->mnt_flags & MNT_NOEXEC) {
              if (vm_flags & VM_EXEC)
                return -EPERM;
              vm_flags &= ~VM_MAYEXEC;
            }

            if (!file->f_op->mmap)
              return -ENODEV;
            if (vm_flags & (VM_GROWSDOWN|VM_GROWSUP))
              return -EINVAL;
            break;

          default:
            return -EINVAL;
          }
        } else {//匿名映射处理情况
          switch (flags & MAP_TYPE) {
          case MAP_SHARED://共享匿名映射
            if (vm_flags & (VM_GROWSDOWN|VM_GROWSUP))
              return -EINVAL;
            /*
             * Ignore pgoff.
             */
            pgoff = 0;
            vm_flags |= VM_SHARED | VM_MAYSHARE;
            break;
          case MAP_PRIVATE://私有匿名映射
            /*
             * Set pgoff according to addr for anon_vma.
             */
            pgoff = addr >> PAGE_SHIFT;
            break;
          default:
            return -EINVAL;
          }
        }

        /*
         * Set 'VM_NORESERVE' if we should not account for the
         * memory use of this mapping.
         */
        if (flags & MAP_NORESERVE) {
          /* We honor MAP_NORESERVE if allowed to overcommit */
          if (sysctl_overcommit_memory != OVERCOMMIT_NEVER)
            vm_flags |= VM_NORESERVE;

          /* hugetlb applies strict overcommit unless MAP_NORESERVE */
          if (file && is_file_hugepages(file))
            vm_flags |= VM_NORESERVE;
        }

        addr = mmap_region(file, addr, len, vm_flags, pgoff);
        if (!IS_ERR_VALUE(addr) &&
            ((vm_flags & VM_LOCKED) ||
             (flags & (MAP_POPULATE | MAP_NONBLOCK)) == MAP_POPULATE))
          *populate = len;
        return addr;
      }



mmap将新建的vma插入到进程空间vma红黑树当中，并且返回地址。如何实现。  
