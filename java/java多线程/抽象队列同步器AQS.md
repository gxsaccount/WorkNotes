抽象队列同步器用来构建锁或者其他同步组件的基础框架，它使用一个整型的volatile变量（命名为state）来维护同步状态，通过内置的FIFO队列来完成资源获取线程的排队工作。   
https://www.cnblogs.com/zaizhoumo/p/7749820.html 
<table><tbody>
    <tr>
        <th>高层类</th>
        <td>Lock</td>
        <td>同步器</td>
        <td>阻塞队列</td>
        <td>Executor</td>
        <td>并发容器</td>
    </tr>
    <tr>
        <th>基础类</th>
        <td >
                <td >AQS</td>
                <td >非阻塞数据结构</td>
                <td >原子变量类</td>
        </td>
    </tr>
    <tr>
        <td></td>
        <td colspan="2.5">volatile变量的读/写</td>
        <td colspan="2.5">CAS</td>
    </tr>
</table>  

AQS的域和方法  
域:  
1 private transient volatile Node head; //同步队列的head节点  
2 private transient volatile Node tail; //同步队列的tail节点  
3 private volatile int state; //同步状态  

方法：AQS提供的可以修改同步状态的3个方法  
1 protected final int getState();　　//获取同步状态  
2 protected final void setState(int newState);　　//设置同步状态  
3 protected final boolean compareAndSetState(int expect, int update);　　//CAS设置同步状态  

1）独占式获取和释放同步状态  
1 public final void acquire(int arg) //独占式获取同步状态，如果不成功会进入同步队列等待。  
2 public final void acquireInterruptibly(int arg) //与acquire不同的是，能响应中断  
3 public final boolean tryAcquireNanos(int arg, long nanosTimeout) //增加超时机制  
4 public final boolean release(int arg) //独占式释放同步状态，该方法会调用重写的tryRelease(int arg)。  
2）共享式获取和释放同步状态  
1 public final void acquireShared(int arg) //共享式获取同步状态，如果不成功会进入同步队列等待。与独占式不同的是，同一时刻可以有多个线程获取到同步状态。   
2 public final void acquireSharedInterruptibly(int arg) //可响应中断  
3 public final boolean tryAcquireSharedNanos(int arg, long nanosTimeout) //超时机制  
4 public final boolean releaseShared(int arg) //共享式释放同步状态，该方法会调用重写的tryReleaseShared(int arg)。  
3）查询同步队列中的等待线程情  
1 publicfinalCollection<Thread>getQueuedThreads()   
2 publicfinalbooleanhasQueuedThreads()//返回包含可能正在等待获取的线程列表，需要遍历链表。返回的只是个估计值，且是无序的。这个方法的主要是为子类提供的监视同步队列措施而设计。   

AQS提供的自定义方法  
protected boolean tryAcquire(int arg) //独占式获取同步状态，此方法应该查询是否允许它在独占模式下获取对象状态，如果允许，则获取它。返回值语义：true代表获取成功，false代表获取失败。  
protected boolean tryRelease(int arg) //独占式释放同步状态   
protected int tryAcquireShared(int arg) //共享式获取同步状态，返回值语义：负数代表获取失败、0代表获取成功但没有剩余资源、正数代表获取成功，还有剩余资源。   
protected boolean tryReleaseShared(int arg) //共享式释放同步状态  
protected boolean isHeldExclusively() //AQS是否被当前线程所独占  

AQS的使用:在Mutex类中组合一个AbstractQueuedSynchronizer的实现类，Mutex将操作代理到AQS的实现类。
独占锁：   
class Mutex implements Lock, java.io.Serializable {
 
    //静态内部类，自定义同步器
    private static class Sync extends AbstractQueuedSynchronizer {
    
        // 释放处于占用状态（重写isHeldExclusively）Report whether in locked state
        protected boolean isHeldExclusively() { 
            return getState() == 1; 
        }

        // 独占式获取锁（重写tryAcquire） Acquire the lock if state is zero
        public boolean tryAcquire(int acquires) {
            assert acquires == 1; // Otherwise unused
            if (compareAndSetState(0, 1)) {    //CAS设置状态为1。
                setExclusiveOwnerThread(Thread.currentThread());
                return true;
            }
            return false;
        }

        // 独占式释放锁（重写tryRelease） Release the lock by setting state to zero
        protected boolean tryRelease(int releases) {
            assert releases == 1; // Otherwise unused
            if (getState() == 0) //获取状态
                throw new IllegalMonitorStateException();
            setExclusiveOwnerThread(null);
            setState(0);    //设置状态为0
            return true;
        }
       
        // Provide a Condition
        //每个Condition都包含一个队列
        Condition newCondition() { return new ConditionObject(); }

        // Deserialize properly
        private void readObject(ObjectInputStream s) throws IOException, ClassNotFoundException {
            s.defaultReadObject();
            setState(0); // reset to unlocked state
        }
    }

    // The sync object does all the hard work. We just forward to it.
    private final Sync sync = new Sync();
    
    //仅需要将操作代理到sync
    public void lock()                { sync.acquire(1); }    //调用AQS的模板方法，
    public boolean tryLock()          { return sync.tryAcquire(1); }
    public void unlock()              { sync.release(1); }
    public Condition newCondition()   { return sync.newCondition(); }
    public boolean isLocked()         { return sync.isHeldExclusively(); }
    public boolean hasQueuedThreads() { return sync.hasQueuedThreads(); }
    public void lockInterruptibly() throws InterruptedException { 
        sync.acquireInterruptibly(1);
    }
    public boolean tryLock(long timeout, TimeUnit unit) throws InterruptedException {
        return sync.tryAcquireNanos(1, unit.toNanos(timeout));
    }
}  
共享锁  
class BooleanLatch {  

    private static class Sync extends AbstractQueuedSynchronizer {
        boolean isSignalled() { return getState() != 0; }

        protected int tryAcquireShared(int ignore) {
            return isSignalled()? 1 : -1;
        }
        
        protected boolean tryReleaseShared(int ignore) {
            setState(1);
            return true;
        }
    }

    private final Sync sync = new Sync();
    public boolean isSignalled() { return sync.isSignalled(); }
    public void signal()         { sync.releaseShared(1); }
    public void await() throws InterruptedException {
        sync.acquireSharedInterruptibly(1);
    }
}




