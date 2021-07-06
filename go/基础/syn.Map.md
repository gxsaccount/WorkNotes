sync.Map1.9的实现有几个优化点:  
1.空间换时间。 通过冗余的两个数据结构(read、dirty),实现加锁对性能的影响。  
2.使用只读数据(read)，避免读写冲突。  
3.动态调整，miss次数多了之后，将dirty数据提升为read。  
4.double-checking。  
5.延迟删除。 删除一个键值只是打标记，只有在提升dirty的时候才清理删除的数据。  
6.优先从read读取、更新、删除，因为对read的读取不需要锁。  
## 数据结构 ##  

**map的数据结构**  
它的很简单，值包含四个字段：read、mu、dirty、misses。  
它使用了冗余的数据结构read、dirty。dirty中会包含read中为删除的entries，新增加的entries会加入到dirty中。  
   
    type Map struct {
      // 当涉及到dirty数据的操作的时候，需要使用这个锁
      mu Mutex
      // 一个只读的数据结构，因为只读，所以不会有读写冲突。
      // 所以从这个数据中读取总是安全的。
      // 实际也会更新这个数据的entries,如果entry是未删除的(unexpunged), 并不需要加锁。如果entry已经被删除了，需要加锁，以便更新dirty数据。
      read atomic.Value // readOnly
      // dirty数据包含当前的map包含的entries,它包含最新的entries(包括read中未删除的数据,虽有冗余，但是提升dirty字段为read的时候非常快，不用一个一个的复制，而是直接将这个数据结构作为read字段的一部分),有些数据还可能没有移动到read字段中。
      // 对于dirty的操作需要加锁，因为对它的操作可能会有读写竞争。
      // 当dirty为空的时候， 比如初始化或者刚提升完，下一次的写操作会复制read字段中未删除的数据到这个数据中。
      dirty map[interface{}]*entry
      // 当从Map中读取entry的时候，如果read中不包含这个entry,会尝试从dirty中读取，这个时候会将misses加一，
      // 当misses累积到 dirty的长度的时候， 就会将dirty提升为read,避免从dirty中miss太多次。因为操作dirty需要加锁。
      misses int
    }
    
**read的数据结构**  
amended指明Map.dirty中有readOnly.m未包含的数据，所以如果从Map.read找不到数据的话，还要进一步到Map.dirty中查找。
对Map.read的修改是通过原子操作进行的。
虽然read和dirty有冗余数据，但这些数据是通过指针指向同一个数据，所以尽管Map的value会很大，但是冗余的空间占用还是有限的。
readOnly.m和Map.dirty存储的值类型是*entry,它包含一个指针p, 指向用户存储的value值。

    type readOnly struct {
      m       map[interface{}]*entry
      amended bool // 如果Map.dirty有些数据不在中的时候，这个值为true
    }
    
**entry**  
p有三种值：
nil: entry已被删除了，并且m.dirty为nil  
expunged: entry已被删除了，并且m.dirty不为nil，而且这个entry不存在于m.dirty中  
其它： entry是一个正常的值  

    type entry struct {
      p unsafe.Pointer // *interface{}
    }
    
**Load**  
提供一个键key,查找对应的值value,如果不存在，通过ok反映。  

      func (m *Map) Load(key interface{}) (value interface{}, ok bool) {
          // 1.首先从m.read中得到只读readOnly,从它的map中查找，不需要加锁
          read, _ := m.read.Load().(readOnly)
          e, ok := read.m[key]
          // 2. 如果没找到，并且m.dirty中有新数据，需要从m.dirty查找，这个时候需要加锁
          if !ok && read.amended {
              m.mu.Lock()
              // 双检查，避免加锁的时候m.dirty提升为m.read,这个时候m.read可能被替换了。
              read, _ = m.read.Load().(readOnly)
              e, ok = read.m[key]
              // 如果m.read中还是不存在，并且m.dirty中有新数据
              if !ok && read.amended {
                  // 从m.dirty查找
                  e, ok = m.dirty[key]
                  // 不管m.dirty中存不存在，都将misses计数加一
                  // missLocked()中满足条件后就会提升m.dirty
                  m.missLocked()
              }
              m.mu.Unlock()
          }
          if !ok {
              return nil, false
          }
          return e.load()
      }

m.dirty是如何被提升的。 missLocked方法中可能会将m.dirty提升。

      func (m *Map) missLocked() {
          m.misses++
          if m.misses < len(m.dirty) {
              return
          }
          m.read.Store(readOnly{m: m.dirty})
          m.dirty = nil
          m.misses = 0
      }
      
 后三行代码就是提升m.dirty的，很简单的将m.dirty作为readOnly的m字段，原子更新m.read。提升后m.dirty、m.misses重置， 并且m.read.amended为false。  
 
 **Store**  
 这个方法是更新或者新增一个entry。  
 
    func (m *Map) Store(key, value interface{}) {
       // 如果m.read存在这个键，并且这个entry没有被标记删除，尝试直接存储。
       // 因为m.dirty也指向这个entry,所以m.dirty也保持最新的entry。
       read, _ := m.read.Load().(readOnly)
       if e, ok := read.m[key]; ok && e.tryStore(&value) {
           return
       }
       // 如果`m.read`不存在或者已经被标记删除
       m.mu.Lock()
       read, _ = m.read.Load().(readOnly)
       if e, ok := read.m[key]; ok {
           if e.unexpungeLocked() { //标记成未被删除
               m.dirty[key] = e //m.dirty中不存在这个键，所以加入m.dirty
           }
           e.storeLocked(&value) //更新
       } else if e, ok := m.dirty[key]; ok { // m.dirty存在这个键，更新
           e.storeLocked(&value)
       } else { //新键值
           if !read.amended { //m.dirty中没有新的数据，往m.dirty中增加第一个新键
               m.dirtyLocked() //从m.read中复制未删除的数据
               m.read.Store(readOnly{m: read.m, amended: true})
           }
           m.dirty[key] = newEntry(value) //将这个entry加入到m.dirty中
       }
       m.mu.Unlock()
      }
      func (m *Map) dirtyLocked() {
          if m.dirty != nil {
              return
          }
          read, _ := m.read.Load().(readOnly)
          m.dirty = make(map[interface{}]*entry, len(read.m))
          for k, e := range read.m {
              if !e.tryExpungeLocked() {
                  m.dirty[k] = e
              }
          }
      }
      func (e *entry) tryExpungeLocked() (isExpunged bool) {
          p := atomic.LoadPointer(&e.p)
          for p == nil {
              // 将已经删除标记为nil的数据标记为expunged
              if atomic.CompareAndSwapPointer(&e.p, nil, expunged) {
                  return true
              }
              p = atomic.LoadPointer(&e.p)
          }
          return p == expunged
      }
      

你可以看到，以上操作都是先从操作m.read开始的，不满足条件再加锁，然后操作m.dirty。  
Store可能会在某种情况下(初始化或者m.dirty刚被提升后)从m.read中复制数据，如果这个时候m.read中数据量非常大，可能会影响性能。  

**Delete**  
删除一个键值。

      func (m *Map) Delete(key interface{}) {
          read, _ := m.read.Load().(readOnly)
          e, ok := read.m[key]
          if !ok && read.amended {
              m.mu.Lock()
              read, _ = m.read.Load().(readOnly)
              e, ok = read.m[key]
              if !ok && read.amended {
                  delete(m.dirty, key)
              }
              m.mu.Unlock()
          }
          if ok {
              e.delete()
          }
      }
同样，删除操作还是从m.read中开始， 如果这个entry不存在于m.read中，并且m.dirty中有新数据，则加锁尝试从m.dirty中删除。
注意，还是要双检查的。 从m.dirty中直接删除即可，就当它没存在过，但是如果是从m.read中删除，并不会直接删除，而是打标记：

      func (e *entry) delete() (hadValue bool) {
          for {
              p := atomic.LoadPointer(&e.p)
              // 已标记为删除
              if p == nil || p == expunged {
                  return false
              }
              // 原子操作，e.p标记为nil
              if atomic.CompareAndSwapPointer(&e.p, p, nil) {
                  return true
              }
          }
      }
      
 **Range**  
 因为for ... range map是内建的语言特性，所以没有办法使用for range遍历sync.Map, 但是可以使用它的Range方法，通过回调的方式遍历。  
       
       func (m *Map) Range(f func(key, value interface{}) bool) {
          read, _ := m.read.Load().(readOnly)
          // 如果m.dirty中有新数据，则提升m.dirty,然后在遍历
          if read.amended {
              //提升m.dirty
              m.mu.Lock()
              read, _ = m.read.Load().(readOnly) //双检查
              if read.amended {
                  read = readOnly{m: m.dirty}
                  m.read.Store(read)
                  m.dirty = nil
                  m.misses = 0
              }
              m.mu.Unlock()
          }
          // 遍历, for range是安全的
          for k, e := range read.m {
              v, ok := e.load()
              if !ok {
                  continue
              }
              if !f(k, v) {
                  break
              }
          }
      }
      
      Range方法调用前可能会做一个m.dirty的提升，不过提升m.dirty不是一个耗时的操作。  
      
sync.Map没有Len方法，并且目前没有迹象要加上 (issue#20680),所以如果想得到当前Map中有效的entries的数量，需要使用Range方法遍历一次， 比较X疼。
LoadOrStore方法如果提供的key存在，则返回已存在的值(Load)，否则保存提供的键值(Store)。
