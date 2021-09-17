https://www.cnblogs.com/xuewangkai/p/11158576.html    
http://www.pandademo.com/2016/11/linux-kernel-epoll-source-dissect/
1.基本使用  
          int epoll_create(int size);  
          int epoll_ctl(int epfd, int op, int fd, struct epoll_event *event);  
          int epoll_wait(int epfd, struct epoll_event *events,int maxevents, int timeout);   
          
首先调用epoll_create建立一个epoll fd。参数size是内核保证能够正确处理的最大文件描述符数目（现在内核使用红黑树组织epoll相关数据结构，不再使用这个参数）。    
epoll_ctl可以操作上面建立的epoll fd，例如，将刚建立的socket fd加入到epoll中让其监控，或者把 epoll正在监控的某个socket fd移出epoll，不再监控它等等。    
epoll_wait在调用时，在给定的timeout时间内，当在监控的这些文件描述符中的某些文件描述符上有事件发生时，就返回用户态的进程。    
另：用epoll和select监听普通文件会报错，因为文件一直可以写一直可读。一般使用stdin,socket,pipe,timefd...  
linux对文件的操作做了很高层的抽象vfs，它并不知道每种具体的文件(如NTFS，FAT32，EXT4等)应该怎么打开，读写，linux让每种设备自定义struct   file_operations结构体的各种函数    

     1518 struct file_operations {
     1519     struct module *owner;
     1520     loff_t (*llseek) (struct file *, loff_t, int);
     1521     ssize_t (*read) (struct file *, char __user *, size_t, loff_t *);
     1522     ssize_t (*write) (struct file *, const char __user *, size_t, loff_t *);
     1523     ssize_t (*aio_read) (struct kiocb *, const struct iovec *, unsigned long, loff_t);
     1524     ssize_t (*aio_write) (struct kiocb *, const struct iovec *, unsigned long, loff_t);
     1525     int (*readdir) (struct file *, void *, filldir_t);
     1526     unsigned int (*poll) (struct file *, struct poll_table_struct *);
              ......
     1546 };
     
     
  **只有实现了poll接口的文件才能使用select和epoll**   
poll函数常见作用：    
将当前线程（task）**睡眠**并加入到设备驱动等队列，**并设置回调函数**，这样设备发生时才知道唤醒哪些线程，调用这些线程什么方法    
当有事件、数据来唤醒task时，就会继续执行，将自己移除等待队列，放入readlist。  
检查此刻已经发生的事件，POLLIN，POLLOUT，POLLERR等，以掩码形式返回    


## 等待队列： ##  
双向循环链表实现    



![image](https://user-images.githubusercontent.com/20179983/133466420-96850c9d-2b48-422a-b0e0-b4cf03908917.png)

## epoll_wait ##   
**调用epoll_wait时，entry中的private被加入task_struct(有栈帧和ip等context保存，激活后可以继续执行),这里的private即为wait_queue**   
epoll_wait是的task_struct对应的线程让出cpu  


![image](https://user-images.githubusercontent.com/20179983/133628530-6ccb49be-09ba-4fa4-a3cc-828e85c2e147.png)
![image](https://user-images.githubusercontent.com/20179983/133628584-fae0fbe3-750b-4659-9adb-9ad69c638fb0.png)
![image](https://user-images.githubusercontent.com/20179983/133628660-a563c472-5824-4fe3-a6e3-7ee8eff17f32.png)



![image](https://user-images.githubusercontent.com/20179983/133630625-19628b00-ce34-47c9-9076-70b2e2c43915.png)

![image](https://user-images.githubusercontent.com/20179983/133631490-4e4fd00a-23db-43f1-adc5-0ce715c157e6.png)

epoll比select好的地方：  
select需要遍历一遍知道哪些fd就绪  
epoll直接返回就绪队列rdllist，不用再遍历。  

epi==epitem  
对fd的包装  
多了可读可写事件，指向红黑树节点的rbn，pwqlist回调list，epoll——filefd  ，
![image](https://user-images.githubusercontent.com/20179983/133644058-6e117489-eefa-420a-97c5-230e688dab21.png)

task==task_struct  

## 红黑树 ##  
红黑树用来存在所有要监听的fd  
红黑树按照？？？排序  
红黑树用？什么区分不同的epitem？    
![image](https://user-images.githubusercontent.com/20179983/133644695-f886542d-dc87-454f-92c7-5bed2cdae980.png)
为什么fd和file对应，为什么要都要在这个结构体中  
![image](https://user-images.githubusercontent.com/20179983/133644931-9e16fc5f-c862-4ca5-87c8-8b0fff14bdcd.png)

![image](https://user-images.githubusercontent.com/20179983/133643920-a2ce09e1-37c8-44cc-a1f6-096a939fc383.png)



## 事件通知 ##  
事件发生，需要将对应的epi拷贝到rdllist   
如何做到？软中断机制？？？

## epoll create ##  
![image](https://user-images.githubusercontent.com/20179983/133642435-775679a2-2e46-4fe9-9083-7f025827a660.png)
epoll create 主要创建这个struct，fd，  
![image](https://user-images.githubusercontent.com/20179983/133642515-51bb18f1-f695-46f6-aacb-53ae4529816d.png)

操作系统的fd有上限，需要用get——unused——fd——flags获得  
![image](https://user-images.githubusercontent.com/20179983/133642713-14cbd468-bd19-4338-a1b4-f7637ec761ea.png)
![image](https://user-images.githubusercontent.com/20179983/133643209-91d02e72-bdba-4e0e-8606-898e53bbd8cd.png)
## epoll contral ## 
### add ###     
**将fd添加到关注列表（加入到红黑树中），同时设置一些回调函数**  
**从private中找到epi，加入红黑树中**  
![image](https://user-images.githubusercontent.com/20179983/133643250-3e2631d9-35d9-4f94-b129-472a0dd75db3.png)

  
  



## 水平触发，边缘触发 ##   
linux通知你有event，要是处理不完  
水平触发：处理不完的再通知   
边缘触发：有新的数据再通知  


