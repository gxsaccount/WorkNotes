## ArrayList ##  
动态数组，读快写慢  
## LinkedList ##  
链表，读慢写快  
## Vector ##
  public class Vector<E>
      extends AbstractList<E>
      implements List<E>, RandomAccess, Cloneable, java.io.Serializable {...}
用synchronize保证线程安全

## CopyOnWriteArrayList ##  
### CopyOnWrite容器 ###
CopyOnWrite容器即**写时复制**的容器。容器添加元素的时候，不直接往当前容器添加，而是先将当前容器进行Copy，复制出一个新的容器，然后新的容器里添加元素，添加完元素之后，再将原容器的引用指向新的容器。这样做可以对CopyOnWrite容器进行并发的读，而不需要加锁，因为当前容器不会添加任何元素。所以CopyOnWrite容器也是一种读写分离的思想，读和写不同的容器。  
CopyOnWrite并发容器用于**读多写少**的并发场景，只能保证数据的**最终一致性**，不能保证数据的实时一致性。所以如果你希望写入的的数据，马上能读到，请不要使用CopyOnWrite容器。  
**add实现**  

    public boolean add(E e) {
      final ReentrantLock lock = this.lock;
      lock.lock();
      try {
          Object[] elements = getArray();
          int len = elements.length;
          Object[] newElements = Arrays.copyOf(elements, len + 1);
          newElements[len] = e;
          setArray(newElements);
          return true;
      } finally {
          lock.unlock();
      }
    }
**get实现**
    
    public E get(int index) {
      return get(getArray(), index);
    }
