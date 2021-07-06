整体与java类似  
# 互斥锁 #  


    var mutex sync.Mutex
    func write(){
      mutex.Lock()
      defer mutex.Unlock()//保证释放锁
      ...
    }
  
# 读写锁 #  

    func main(){
        var rwm sync.RWMutex
        for i:= 0; i<3; i++{
          go func(i int){
            rwm.RLock()//读锁上锁
            fmt.Printf("Try to unlock for reading.. [%d]\n",i)
            ...
            rwm.RUNlock()//读锁解锁
          }(i)
        }
        fmt.Printf("Try to unlock for writing.. [%d]\n",i)  
        rwm.Lock()//写锁上锁  
      }

# 条件表量 #  
sync.Cond类型  

    var locker = new(sync.Mutex)
    var cond = sync.NewCond(locker)
    cond.L.Lock() //获取锁
    cond.Wait()//等待通知  暂时阻塞
    cond.L.Unlock()//释放锁
    cond.Signal()   // 下发一个通知给已经获取锁的goroutine
    cond.Broadcast()//下发广播给所有等待的goroutine

# 原子操作 #  
sync/atomic包  
用于增或减的原子操作函数名都以“Add”为前缀，后跟针对具体类型的名称。  
AddInt32、AddInt64、AddUint32、AddUint64、AddUintptr等。  
    
    newi32 := atomic.AddInt32(&i32,3)//让i32增加3，由于原子操作需要在源地址操作，所以需要第一个参数为指针。且第二个参数类型必须对应。    

# 比较交换 #  
CAS操作,并发更新值时优先使用  
CompareAndSwapInt32、CompareAndSwapInt64、CompareAndSwapPointer、CompareAndSwapUint32、CompareAndSwapUint64、CompareAndSwapUintptr  

    func CompareAndSwapInt32(addr *int32,old ,new int32)(swappd bool)

# 载入 #  
原子读操作时使用  
LoadInt32、LoadInt64、LoadPointer、LoadUint32、LoadUint64、LoadUintptr
    
    func addValue(delta int32){
        for{
            v:=atomic.LoadInt32(&value)
            if atomic.CompareAndSwapInt32(&value,v,(v+delta)){
                break
            }
        }
     }
 
 # 存储 #  
 原子存操作时使用，直接覆盖，不关心旧值。  
 StoreInt32等  
 
 # 交换 #  
 原子交换操作  
 与CAS操作不同的是，它不关心旧值,还会返回被操作的旧值。比CAS约束少，但比原子载入操作功能更强。    
 
    SwapInt32(int1 *int32,int2 int32)
    
 # 原子值 #
sync/atomic.Value,原子值类型，用于存储需要原子读写的值,被接受的操作值类型不限。  
    
    func main(){
        var countVal atomic.Value//声明得到实例，不应该用于复制，赋值或者通道等操作都不应该使用它
        countVal.Load()//原子读取原子值实例重存储的值，返回一个interface{}类型，此时为nil，因为没有值  
        countVal.Store([]int{1,3,5,7})//原子存储一个值，接受一个interface{}类型参数，不能为nil，且类型必须一样
        anotherStore(countVal)
    }
    func anotherStore(countVal atomic.Value){//出错，不能这样使用
        countVal.Store([]int{2,4,6,8})
    }
 
 需要检测程序事都出现竞态条件：
 
    go test -race

# 只执行一次 #  
适用于数据库连接池建立、全局变量的延迟初始化等等。由互斥锁和原子操作实现。包括卫述语句、双重检查锁定、共享标记的原子读写操作。  
    
    count:=0
    var once sync.Once//once
    once.Do(func(){count++})//就算在for循环中调用多次，count依然是1
    
 # WaitGroup #  
 sync.WaitGroup结构体类型的值是并发安全的。用于多个goroutine的wait,wait的计数不能为0  
 
    
例如g1要等待3个g2,g3,g4完成后执行： 
    
    //g1
    sign := make(chan byte,3)
    go func(){//g2
        ...
        sign<-2
    }()
    go func(){//g3
        ...
        sign<-3
    }()
    go func(){//g4
        ...
        sign<-4
    }()
    for i:=0;i<3;i++{
        fmt.Printf("g%d is ended.\n",<-sign)
    }

使用sync.WaitGroup：
    
    //g2
    var wg sync.WaitGroup
    wg.Add(3)
    go func(){//g2
        ...
        wg.Done()
    }()
    go func(){//g3
        ...
        wg.Done()
    }()
    go func(){//g4
        ...
        wg.Done()
    }()
    wg.Wait()
    fmt.Println("g2,g3 and g4 are ended.")
    
# 临时对象池 #  
sync.Pool类型值看作存放临时值的容器。  
## 特征一 ##
**临时对象池可以把由其中的对象值产生的存储压力进行分摊。**  
它会专门为每一个与操作它的gotoutine相关联的P建立本地池。  
**GET**  
在临时对象池Get方法被调用时，会先从本地P对应的私有池和本地共享池中获取一个对象值，  
如果获取失败，从其他P的本地共享池头一个对象值返给调用方。   
如果还不行，调用临时对象池的对象值生成函数。生成值直接返给调用方，不存。  
**PUT**  
PUT方法把它的参数值存放到本地P的本地池中。  
每个相关P的本地共享池重的所有对象值，都在当前临时对象池的范围内共享。  
## 特征二 ##  
对垃圾回收友好。  
垃圾回收时会将临时对象池重的对象值全部移除。  

    func main(){
        //禁用GC，并保证在main函数执行结束前恢复GC  
        defer debug.SetGCPercent(debug.SetGCPercent(-1))
        var count int32
        newFunc := func() inteface{}{
            return atomic.AddInt32(&count,1)
        }
        pool := sync.Pool{New:newFunc}
        v1 := pool.Get()
        fmt.Println("Value 1: %v\n",v1)//1

        //临时对象池的存取
        pool.Put(10)
        pool.Put(11)
        pool.Put(12)
        v2:=pool.Get()
        fmt.Printf("Value 2:%v\n",v2)//10,与顺序毫无关系
        
        //垃圾回收对临时对象池的影响
        debug.SetGCPrecent(100)
        runtime.GC()
        v3:=pool.Get()//2
        fmt.Printf("Value 3:%v\n",v3)
        pool.New = nil
        v4:=pool.Get()
        fmt.Printf("Value 4:%v\n",v4)//<nil>
    }
