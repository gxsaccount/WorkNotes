    注意在for循环中使用并发，变量作为参数传入较好
    func main(){
      names:= []string {"One","Two","Three"}
      // for _,name := range names{
      // 	go func() {
      // 		fmt.Printf("%s.\n",name)
      // 	}()
      // }
      //打印结果是Three，Three，Three
      //因为此处for循环较简单很快执行完，name值变为Three
      for _,name := range names{
        go func(who string) {
          fmt.Printf("%s.\n",who)
        }(name)
      }
      //打印结果是One，Two，Three
      //name作为参数传入
      runtime.Gosched()//为啥Windows下没用？
      time.Sleep(time.Millisecond)//替代runtime.Gosched()
    }
    
## Gotoutine的线程模型 ##
go语言提倡用通信（Channel）来共享内存，而少使用共享方式来通讯，减少因为并发访问的控制的复杂性。  
go语言在操作系统提供的内核线程上搭建了一个两级线程模型。  
go语言线程模型实现核心元素MPG：  
    M：Machine，内核线程，与一个内核调度实体KSE**一一对应**  
    P：Processor，M的上下文  
    G：Goroutine，Go代码  
一个G的执行需要M和P的支持，一个M在与一个P关联之后形成G的运行环境。  
每一个P都会包含一个可运行的G队列。  
[MPG与KES的关系]  
**M**  
M中主要存放：正在运行的G的指针，M关联的P，M的起始函数，与当前M有潜在关系的P（预联）等信息。  
M本身并无状态，处在调度器的空闲M列表就为空闲。  
可以在全局M列表中查找  
**P**  
P的最大数量相当于可以被并发的用户级别G的数量。（默认为1，即所有G都会被方法一个P的可运行G队列中）    
可以在全局P列表中查找  
P本身有状态：
-Pidle：未与任何M关联  
-Prunning：与某个M关联  
-Psyscall：P对应的G正在进行系统调用  
-Pgcstop：系统正在进行垃圾回收（全局P都会处于此状态，初始的P也处在此状态）  
-Pdead：P不会再使用（调用runtime.GOMAXPROCS减少P数量时，多余P状态，多余P上的队列G会被转移到调度器对应G队列上）  
[P的状态转化图]  
P重要结构：可运行G队列和自由G队列  
**G**  
G本身有状态：  
Gidle：被创建还未被初始化  
Grunnable：等待被运行  
Grunning：正在被运行  
Gsyscall：G正在进行系统调用  
Gwaitting：等待状态  
Gdead：被运行完成，被放入本地P或调度器的自由G列表，**可以被重用**，区别于Pdead状态  
[G的生命周期]  
核心元素容器：
[核心元素容器]  
从Gsyscall到Ggcstop的G会被放在调度器可运行G队列。  
被运行时初始化的G会被放到本地P可运行G队列。  
从Gwaiting转出的G，会被放到本地可运行G队列。  
调度器和本地P的可运行队列中的G被运行机会均等。**（why？）**  
G转入Gdead后会首先被放入本地P的自由G列表，运行时系统需要用自由G封装go函数时，也会尝试从本地P的自由G列表获取。  
**调度器**  
调度器的重要字段（帮助垃圾回收“stop the word”）：  

| 字段名称 | 数据类型 | 用途简述 |  
| ------ | ------ | ------ |  
| gcwaiting | uint32 | 为1，垃圾回收器开始准备回收，调度器陆续停止调度 |  
| stopwait | int32 | 还未被停止调度的P进行计数，为0时调度工作停止（开始垃圾回收） |  
| stopnote | Note |  垃圾回收利用此字段阻塞自身，等待调度器停止调度工作 |  
| sysmonwait | uint32 |  未被停止系统监测任务进行计数，为1时系统监测任务暂停（开始垃圾回收） |  
| sysmonnote | Note | 系统监测器利用此字段阻塞自身  |  

[一轮调度的总体流程.png]
停止P：  
调度器断开P与当前M的关联，将P置为Pgcstop。  
检擦所有P是否被停止，是用stopnode字段想回收器发送通知。  
停止M：  
重置M一些属性。  
把当前M放入调度器的空闲M列表。  
阻塞当前M。  
[启动或停止M.png]
在运行m7中的调度器找不到可运行G时，会把m7放入调度器空闲列表中，阻塞它。  
在m3中运行的调度程序将找到的可运行G放入调度器可运行G队列。  
在有空闲P的前提下从调度器的空闲M取出一个M，预联这个M和那个空闲P。  
利用通知机制唤醒取出的M。  
若M是m7，m3的调度器向们发送通知唤醒它。  
m7被唤醒，调度程序会关联m7和在m3中已与它预联的那个空闲P。  
m7有了新的P，m7的调度程序重新查找可运行G。  
[启动或停止被锁定的M.png]
从stop the world中恢复：  
调度器从它的空闲M列表中唤醒M，被唤醒的M会立即与一个可运行G队列不为空的P进行关联。  
调度器在本地P或自己的可运行G列表中查找可以被运行的G。  
找不到可运行的G，进入全力查找可运行G的子流程。  
找到了可运行G，检查是否需要必须让某个M执行（一般cgo时，调用LockOSThread锁住）  
全力查找可运行G的子流程：  
-从本地P的可运行G队列获取G  
-从调度器的可运行G队列获取G  
-从网络I/O轮询器（netpoller）处查找就绪的G来当作可运行G。  
-在条件允许下从另一个P偷取可运行G  
-再次尝试从调度器的可运行G队列获取G  
-尝试从所有P的可运行G队列中获取G  
-再次尝试从网络I/O轮询器（netpoller）处查找就绪的G。  
系统检测任务  
系统检测任务做了如下四件事：  
-抢夺符合条件的P和G。  
-在必要时候，进行调度器跟踪打印相关信息。 
-再需要时进行强制GC  
-在需要时清扫堆  
-系统检测任务在一个单独的M中被运行，会一直执行下去  
[系统检测任务的总体流程.png]  
变量idle和delay决定了监测任务的间隔时间。  
idle代表了有连续多少次监测任务未能夺取P，delay代表了睡眠时间。
[抢夺P和G的流程.png]  
P的状态为Psyscall，程序会检查其syscalltick和系统监测程序中描述该P的结构体中的syscalltick字段是否相同。  
不同，更新此备份。相同判断是否可以抢夺。    
P的状态处于Prunning且处于改状态超过10毫秒，程序会尝试停止正在该P代表的上下文环境上运行的那个G。阻止一个G占用M时间过长。  

## g0和m0 ##  
运行时系统在初始化M期间会创建特殊的Goroutine（系统G），g0。g0包含了各种调度、垃圾回收和栈管办理等程序。  
每个M都有自己的g0。  
除了g0之外还有一个runtime.g0他被用用于执行引导程序。他是Go程序所简介拥有的第一个内核线程中运行的。这个内核线程被称为runtime.m0  
runtime.m0和runtime.g0都是静态分配的，引导程序无需为他们分配内存。  

## 调度器锁和原子操作 ##  

## Goroutine的运行过程 ##  
runtime.m0运行runtime.g0引导程序  
然后runtime.m0再运行主Goroutine（封装了main函数）
主Goroutine：
-设定栈空间  
-启动系统检测器  
-进行初始化工作（此期间与runtime.m0锁定）  
--创建defer语句，用于主Goroutine退出时解锁  
--检查当前M是否为runtime.m0。不是抛出异常  
--创建一个Goroutine来封装定时回收器（scavenger）  
--执行包的init函数  
--检查和设置之前的defer   
--执行main函数  

## runtime包 ##  
runtime.GOMAXPROCS:设置运行时系统中P的最大数量，会引起stop the world。  
runtime.Goexit:执行defer语句，并停止调用的Goroutine。  
runtime.Gosched:调用它的Goroutine置于Grunable状态，并放入调度器的可运行G队列。让其他Goroutine有运行机会  
runtime.NumGorutine:返回所有处于活跃或争渡调度的Goroutine数量  
runtime.LockOSThread/runtime.UnLockOSThread:将Gotoutine与M锁住/解锁  
runtime/debug.SetMaxStack:约束单个Goroutine所能申请的栈空间最大值  
runtime/debug.SetMaxThreads:设置运行时内核线程数量（M的数量）  
**与垃圾回收相关函数**
runtime.GC：强制进行垃圾收集  
runtime/debug.SetGCPercent：设置一个比率，垃圾回收的对内存单元增量相对于之前的堆内存单元总数量百分比???  
