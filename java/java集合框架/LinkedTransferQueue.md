BlockingQueue：用synchronized全局锁。  
SynchronousQueue：只能放一个物件，要么有一个物件在等人拿，要么有一个空等人放  
LinkedBlockingQueue：  
TransferQueue接口继承了BlockingQueue接口，并进行了扩充，自己又定义了一些LinkedTransferQueue类需要用到的方法。  
BlockingQueue当生产者向队列添加元素但队列已满时，生产者会被阻塞；当消费者从队列移除元素但队列为空时，消费者会被阻塞。  
  
  
TransferQueue  
TransferQueue是一个继承了BlockingQueue的接口，并且增加若干新的方法。LinkedTransferQueue是TransferQueue接口的实现类，其定义为一个无界的队列，具有先进先出(FIFO)的特性。  
TransferQueue是ConcurrentLinkedQueue、SynchronousQueue (公平模式下)、无界的LinkedBlockingQueues等的超集。  
原理  
LinkedTransferQueue采用的一种预占模式。  
意思就是消费者线程取元素时，如果队列为空，那就生成一个节点（节点元素为null）入队，然后消费者线程park住，后面生产者线程入队时发现有一个元素为null的节点，生产者线程就不入队了，直接就将元素填充到该节点，唤醒该节点上park住线程，被唤醒的消费者线程拿货走人。  
  
这就是预占的意思：有就拿货走人，没有就占个位置等着，等到或超时。  
  
TransferQueue队列中的节点都是Node节点类型。  
  
static final class Node{  
    // 如果是消费者请求的节点，则isData为false，否则该节点为生产（数据）节点为true  
    final boolean isData;   // false if this is a request node  
    // 数据节点的值，若是消费者节点，则item为null  
    volatile Object item;   // initially non-null if isData; CASed to match  
    // 指向下一个节点  
    volatile Node next;  
    // 等待线程  
    volatile Thread waiter; // null until waiting  
    //item，next节点的都用CAS操作  
}  
  
重要函数：  
LinkedTransferQueue实现了一个重要的接口TransferQueue，该接口含有下面几个重要方法：  
transfer(E e)：若当前存在一个正在等待获取的消费者线程，即立刻移交之；否则，会插入当前元素e到队列尾部，并且等待进入阻塞状态，到有消费者线程取走该元素。  
tryTransfer(E e)：若当前存在一个正在等待获取的消费者线程（使用take()或者poll()函数），使用该方法会即刻转移/传输对象元素e；若不存在，则返回false，并且不进入队列。这是一个不阻塞的操作。  
tryTransfer(E e, long timeout, TimeUnit unit)：若当前存在一个正在等待获取的消费者线程，会立即传输给它;否则将插入元素e到队列尾部，并且等待被消费者线程获取消费掉；若在指定的时间内元素e无法被消费者线程获取，则返回false，同时该元素被移除。  
hasWaitingConsumer()：判断是否存在消费者线程。  
getWaitingConsumerCount()：获取所有等待获取元素的消费线程数量。  
size()：因为队列的异步特性，检测当前队列的元素个数需要逐一迭代，可能会得到一个不太准确的结果，尤其是在遍历时有可能队列发生更改。  
批量操作：类似于addAll，removeAll, retainAll, containsAll, equals, toArray等方法，API不能保证一定会立刻执行。因此，我们在使用过程中，不能有所期待，这是一个具有异步特性的队列。  
  
  
LinkedTransferQueue采用一种**预占模式**。意思就是消费者线程取元素时，如果队列不为空，则直接取走数据，若队列为空，那就生成一个节点（节点元素为null）入队，  
然后消费者线程被等待在这个节点上，后面生产者线程入队时发现有一个元素为null的节点，生产者线程就不入队了，直接就将元素填充到该节点，并唤醒该节点等待的线  
程，被唤醒的消费者线程取走元素，从调用的方法返回。我们称这种节点操作为“匹配”方式。  
  
数据节点，则匹配前item不为null且不为自身，匹配后设置为null。  
占位请求节点，匹配前item为null，匹配后自连接。  
  
LinkedTransferQueue类的入队、出队方法都调用一个xfer方法。transfer和tryTransfer也用xfer  
  
xfer方法  
xfer(E e,boolean haveData,int how,long nanos)  
e:data数据（havedata时不能为null）  
haveData:是否有数据（有入队，无出对）  
how:ASYNC（入队异步）/SYNC（出队同步）/TIMED（超时控制）  
nanos:  
  
put线程：  
先看head是不是take类型，如果是存入数据。  
如果不是遍历链表做同样操作  
遍历到尾节点如果不是，则入队，立即返回  
get线程：  
先看head是不是put类型，如果是直接取出数据，  
如果不是遍历链表做同样操作  
遍历到尾节点如果不是，则入队，并阻塞  
先看head  
