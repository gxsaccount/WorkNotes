## LinkedList ##
链表，实现了Deque, Queue, List三个接口  
## ArrayDeque ##
循环数组，https://www.cnblogs.com/wxd0108/p/7366234.html
## PriorityQueue ##  
数组形式的小根堆，

上浮函数：不断的为新节点找位置，最后找到位置后，才赋值一次。
 private void siftUpComparable(int k, E x) 
{//父亲节点N,孩子节点2*N+1,2(N+1),则孩子节点编号k,父亲节点为(k - 1) >>> 1。0位置
//也是存数据的
    Comparable<? super E> key = (Comparable<? super E>) x;
    while (k > 0) {
        int parent = (k - 1) >>> 1;
        Object e = queue[parent];
        if (key.compareTo((E) e) >= 0)
            break;
        queue[k] = e;
        k = parent;
    }
    queue[k] = key;
}

offer方法： 
比较简单，因为priorityQueue是无界队列，所以，添加元素不会抛出illegalStateException异常。如果当前数组已满，则会直接扩容。 
过程： 
a：安全性检查，不运行插入null元素 
b：容量检查，如果容量不够，则扩容。扩容原则：如果当前基层数组较小，则扩容时，每次扩展一倍。之后每次扩容时，每次扩展0.5倍 
c.如果当前队列为空，则直接插入到queue[0]位置，不需要调整。否则，将元素直接“放到”一个有效位置上，然后调整，不断上浮。
 
    public boolean offer(E e) 
    {
        if (e == null)
            throw new NullPointerException();
        modCount++;
        int i = size;
        if (i >= queue.length)
            grow(i + 1);
        size = i + 1;
        if (i == 0)
            queue[0] = e;
        else
            siftUp(i, e);
        return true;
    }

poll函数：   
主要步骤：   
a.容量检查   
b.size标志减一，同时保存堆顶元素。   
c.将最后一个元暂时提到堆顶位置，然后将堆顶元素调整，下移。  
    
    public E poll() 
    {
        if (size == 0)
            return null;
        int s = --size;
        modCount++;
        E result = (E) queue[0];
        E x = (E) queue[s];
        queue[s] = null;
        if (s != 0)
            siftDown(0, x);
        return result;
    }
    private void siftDownComparable(int k, E x) 
    {
        Comparable<? super E> key = (Comparable<? super E>)x;
        int half = size >>> 1;        // loop while a non-leaf
        while (k < half) 
        {
            int child = (k << 1) + 1; // assume left child is least
            Object c = queue[child];
            int right = child + 1;
            //C为左右孩子中最小的
            if (right < size &&
                ((Comparable<? super E>) c).compareTo((E) queue[right]) > 0)
                c = queue[child = right];
            //如果key小于孩子，则不用调整的，否则，需要下移，孩子上移
            if (key.compareTo((E) c) <= 0)
                break;
            //孩子上移
            queue[k] = c;
            k = child;
        }
        queue[k] = key;
    }

## BlockingQueue ##
## ArrayBlockingQueue ##
## DelayQueue ##  
## LinkedBlockingQueue ##
## PriorityBlockingQueue ##
## SynchronousQueue ##
## BlockingDeque ##
## LinkedBlockingDeque ##
## LinkedTransferQueue ##
## ConcurrentLinkedQueue ##
