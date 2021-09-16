1.基本使用  
int epoll_create(int size);  
int epoll_ctl(int epfd, int op, int fd, struct epoll_event *event);  
int epoll_wait(int epfd, struct epoll_event *events,int maxevents, int timeout);  
首先调用epoll_create建立一个epoll fd。参数size是内核保证能够正确处理的最大文件描述符数目（现在内核使用红黑树组织epoll相关数据结构，不再使用这个参数）。    
epoll_ctl可以操作上面建立的epoll fd，例如，将刚建立的socket fd加入到epoll中让其监控，或者把 epoll正在监控的某个socket fd移出epoll，不再监控它等等。    
epoll_wait在调用时，在给定的timeout时间内，当在监控的这些文件描述符中的某些文件描述符上有事件发生时，就返回用户态的进程。    
另：用epoll和select监听普通文件会报错，因为文件一直可以写一直可读。一般使用stdin,socket,pipe,timefd...  
linux对文件的操作做了很高层的抽象vfs，它并不知道每种具体的文件(如NTFS，FAT32，EXT4等)应该怎么打开，读写，linux让每种设备自定义struct   file_operations结构体的各种函数    

poll函数常见作用：    
将当前线程（task）加入到设备驱动等队列，并设置回调函数。这样设备发生时才知道唤醒哪些线程，调用这些线程什么方法    
检查此刻已经发生的事件，POLLIN，POLLOUT，POLLERR等，以掩码形式返回    


等待队列：  
双向循环链表实现    
![image](https://user-images.githubusercontent.com/20179983/133466420-96850c9d-2b48-422a-b0e0-b4cf03908917.png)


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
  
  
    #define MAXLINE  1024
    #define OPEN_MAX  16 //一些系统会定义这些宏
    #define SERV_PORT  10001

    int main()
    {
        int i , maxi ,listenfd , connfd , sockfd ,epfd, nfds;
        int n;
        char buf[MAXLINE];
        struct epoll_event ev, events[20];  
        socklen_t clilen;
        struct pollfd client[OPEN_MAX];

        struct sockaddr_in cliaddr , servaddr;
        listenfd = socket(AF_INET , SOCK_STREAM , 0);
        memset(&servaddr,0,sizeof(servaddr));
        servaddr.sin_family = AF_INET;
        servaddr.sin_port = htons(SERV_PORT);
        servaddr.sin_addr.s_addr = htonl(INADDR_ANY);

        bind(listenfd , (struct sockaddr *) & servaddr, sizeof(servaddr));
        listen(listenfd,10);
        
        //******
        epfd = epoll_create(256);
        ev.data.fd=listenfd; 
        ev.events=EPOLLIN|EPOLLET;
        epoll_ctl(epfd,EPOLL_CTL_ADD,listenfd,&ev);

        for(;;)
        {
            nfds=epoll_wait(epfd,events,20,500); 
            for(i=0; i<nfds; i++)
            {
                if (listenfd == events[i].data.fd)
                {
                    clilen = sizeof(cliaddr);
                    connfd = accept(listenfd , (struct sockaddr *)&cliaddr, &clilen);
                    if(connfd < 0)  
                    {  
                        perror("connfd < 0");  
                        exit(1);  
                    }
                    ev.data.fd=connfd; 
                    ev.events=EPOLLIN|EPOLLET;
                    
                    //******  添加感兴趣的事件
                    epoll_ctl(epfd,EPOLL_CTL_ADD,connfd,&ev);                
                }
                else if (events[i].events & EPOLLIN)
                {
                    if ( (sockfd = events[i].data.fd) < 0)  
                        continue;  
                    n = recv(sockfd,buf,MAXLINE,0);
                    if (n <= 0)   
                    {    
                        close(sockfd);  
                        events[i].data.fd = -1;  
                    }
                    else
                    {
                        buf[n]='\0';
                        printf("Socket %d said : %s\n",sockfd,buf);
                        ev.data.fd=sockfd; 
                        ev.events=EPOLLOUT|EPOLLET;
                        epoll_ctl(epfd,EPOLL_CTL_MOD,connfd,&ev);
                    }
                }
                else if( events[i].events&EPOLLOUT )
                {
                    sockfd = events[i].data.fd;  
                    send(sockfd, "Hello!", 7, 0);  

                    ev.data.fd=sockfd;  
                    ev.events=EPOLLIN|EPOLLET;  
                    epoll_ctl(epfd,EPOLL_CTL_MOD,sockfd,&ev); 
                }
                else 
                {
                    printf("This is not avaible!");
                }
            }
        }
        close(epfd);  
        return 0;
    }
