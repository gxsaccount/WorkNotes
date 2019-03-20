## hashmap1.7与hashmap1.8区别 ##
**基础实现的改进：**
JDK1.7中  
使用一个Entry数组来存储数据，使用**数组+链表**，put和transer等函数插入链表用**头插法**  
JDK1.8中  
使用一个Node数组来存储数据，使用**数组+链表/红黑树**，所以key的对象，必须正确的实现了Compare接口，put和transer等函数插入链表用**尾插法**  
尾插法可以避免两（多）个线程扩容时出现环。  
hashmap的容量为2，hash值为1的链表上3->7(mod2),扩容后hashmap的容量为4，3和7都应该在hash值为3上(mod4)，线程1先准备插入3，但是被线程2抢先插入7->3,线程1再插入则：3->7->3  
**resize的改进：**  
JDK1.7中  
遍历所有元素，重新计算所有元素的的位置（**hash & (length - 1)** ），使用头插法插入，所以链表元素会倒置  
JDK1.8中  
原理：因为使用2次幂扩展（x2扩展），所以元素要么在原位置，要么在原位置移动2次幂的位置。  
如0101=5，  
原位置= **0**0101 = 5      
新位置= **1**0101 = 21 = 5+**16** = 原位置 + 原来的size  
所以不需要重新计算hash，只需要看原来的hash值新增的那个bit是1还是0，0的话索引不变，1的话索引变为“原索引+原来的size”，  

## ConcurrentHashMap1.7与Hashtable ##
Hashtable使用**synchornich**保证线程安全，在大小过大时性能急剧下降。因为迭代时需要锁定很长时间。
ConcurrentHashMap1.7使用**分段锁**，只会锁定某个部分，所以效率不会明显下降。
Hashtable是**强一致性**的
ConcurrentHashMap1.7是**弱一致性**，如get,clear,iterator，解释如下。
put：

	V put(K key, int hash, V value, boolean onlyIfAbsent) {  
		lock();  
		try {  
			int c = count;  
			if (c++ > threshold) // ensure capacity  
				rehash();   
			HashEntry[] tab = table;  
			int index = hash & (tab.length - 1);  
			HashEntry first = tab[index];  
			HashEntry e = first;  
			while (e != null && (e.hash != hash || !key.equals(e.key)))  
				e = e.next;  
			V oldValue;  
			if (e != null) {  
				oldValue = e.value;  
				if (!onlyIfAbsent)  
					e.value = value;  
			}  
			else {  
				oldValue = null;  
				++modCount;  
				tab[index] = new HashEntry(key, hash, first, value);  
				count = c; // write-volatile  
			}  
			return oldValue;  
		} finally {  
			unlock();  
		}  
	}

get：

	V get(Object key, int hash) {
		if (count != 0) { // read-volatile
			HashEntry e = getFirst(hash);
			while (e != null) {
				if (e.hash == hash && key.equals(e.key)) {
					V v = e.value;
					if (v != null)
						return v;
					return readValueUnderLock(e); // recheck
				}
				e = e.next;
			}
		}
		return null;
	}
因为get是没有加锁的，而put是加了锁的,使得一个segment上的put和get可以同时进行，只能保证get看到已完成的put操作。
如果某个Segment实例中的put将一个Entry加入到了table中，在未执行count赋值操作之前有另一个线程执行了同一个Segment实例中的get，来获取这个刚加入的Entry中的value，那么是有可能取不到的！ 
clear：

	public void clear() {
		for (int i = 0; i < segments.length; ++i)
			segments[i].clear();
	}
因为没有全局的锁，在清除完一个segments之后，正在清理下一个segments的时候，已经清理segments可能又被加入了数据，因此clear返回的时候，ConcurrentHashMap中是可能存在数据的。因此，clear方法是弱一致的。   
迭代器：
ConcurrentHashMap中的迭代器主要包括entrySet、keySet、values方法。它们大同小异，这里选择entrySet解释。当我们调用entrySet返回值的iterator方法时，返回的是EntryIterator，在EntryIterator上调用next方法时，最终实际调用到了HashIterator.advance()方法。
这个方法在遍历底层数组。在遍历过程中，如果已经遍历的数组上的内容变化了，迭代器不会抛出ConcurrentModificationException异常。如果未遍历的数组上的内容发生了变化，则有可能反映到迭代过程中。这就是ConcurrentHashMap迭代器弱一致的表现。
**ConcurrentHashMap的弱一致性主要是为了提升效率，是一致性与效率之间的一种权衡。要成为强一致性，就得到处使用锁，甚至是全局锁，这就与Hashtable和同步的HashMap一样了。** 

## ConcurrentHashMap1.7与ConcurrentHashMap1.8 ##
**JDK1.7分析**  
ConcurrentHashMap采用了分段锁的设计，只有在同一个分段内才存在竞态关系，不同的分段锁之间没有锁竞争。相比于对整个Map加锁的设计，分段锁大大的提高了高并发环境下的处理能力。但同时，由于不是对整个Map加锁，导致一些需要扫描整个Map的方法（如size(), containsValue()）需要使用特殊的实现，另外一些方法（如clear()）甚至放弃了对一致性的要求 
其包含两个核心静态内部类 Segment和HashEntry。  
Segment继承ReentrantLock用来充当锁的角色，每个 Segment 对象守护每个散列映射表的若干个桶。  
HashEntry 用来封装映射表的键 / 值对；  
每个桶是由若干个 HashEntry 对象链接起来的链表。  
一个 ConcurrentHashMap 实例中包含由若干个 Segment 对象组成的数组  
ConcurrentHashMap中的HashEntry相对于HashMap中的Entry有一定的差异性：**HashEntry中的value以及next都被volatile修饰，这样在多线程读写过程中能够保持它们的可见性**  
HashEntry实现：

	static final class HashEntry<K,V> {
		final int hash;
		final K key;
		volatile V value;
		volatile HashEntry<K,V> next;
	}
**get实现**  
get不需要加锁。get里面的共享变量都是volatile。不会读到过期的值。  
**put实现**  
方法通过加锁机制插入数据  
当执行put方法插入数据时，根据key的hash值，在Segment数组中找到相应的位置，如果相应位置的Segment还未初始化，则通过CAS进行赋值，接着执行Segment对象的put通过**加锁机制**插入（segment**初始化CAS，插入锁**）
线程A和线程B同时执行相同Segment对象的put方法：  
1、线程A执行tryLock()方法成功获取锁，则把HashEntry对象插入到相应的位置；  
2、线程B获取锁失败，则执行scanAndLockForPut()方法，在scanAndLockForPut方法中，会通过重复执行tryLock()方法尝试获取锁，在多处理器环境下，重复次数为64，单处理器重复次数为1，当执行tryLock()方法的次数超过上限时，则执行lock()方法挂起线程B；  
3、当线程A执行完插入操作时，会通过unlock()方法释放锁，接着唤醒线程B继续执行；  
**size实现**  
先采用不加锁的方式，连续计算元素的个数，最多计算3次：  
1、如果前后两次计算结果相同，则说明计算出来的元素个数是准确的；  
2、如果前后两次计算结果都不同，则给每个Segment进行加锁，再计算一次元素的个数；  
  
**JDK1.8分析**    
1.8的实现已经抛弃了Segment分段锁机制，利用**Node+CAS+Synchronized**来保证并发更新的安全，底层采用**数组+链表+红黑树**的存储结构。  
**put实现**  
Node节点，一个hash值的头节点，它的value和next是用volatile修饰的。  
TreeNode继承于Node，TreeBin是红黑树具体的节点，组合了一个TreeNode节点（头节点）。  
当执行put方法插入数据时，根据key的hash值，在Node数组中找到相应的位置  
1、如果相应位置的Node还未初始化，则通过CAS插入相应的数据；  
2、如果相应位置的Node不为空，则对Node头节点加synchronized锁，更新或插入节点；  
3、如果该节点是TreeBin类型的节点，说明是红黑树结构，则通过putTreeVal方法往红黑树中插入节点；  
4、如果当前链表的个数达到8个，则通过treeifyBin方法转化为红黑树  
5、如果插入的是一个新节点，则执行addCount()方法尝试更新元素个数baseCount；  
  
**GET方法**  
计算出该节点的hash值，并算出该node在table中的位置 e = tabAt(tab, (n - 1) & h)。  
判断首节点是不是要找的节点，是，直接返回。  
如果该节点hash值小于0 则可能是forwadingNode也可能是Treebin节点,直接调用forwadingNode.find或者Treebin节点的find方法。  
如果该节点hash值大于等于0，则是普通节点，通过遍历链表查到要找的节点。  

**size的实现**  
1.8中使用一个**volatile**类型的变量baseCount记录元素的个数，当插入新数据或则删除数据时，会通过addCount()方法（CAS实现）更新baseCount  
counterCells存储的都是value为1的CounterCell对象，而这些对象是因为在CAS更新baseCounter值时，由于高并发而导致失败，最终将值保存到CounterCell中，放到counterCells里。  
1、初始化时counterCells为空，在并发量很高时，如果存在两个线程同时执行CAS修改baseCount值，则失败的线程会继续执行方法体中的逻辑，使用CounterCell记录元素个数的变化；  
2、如果CounterCell数组counterCells为空，调用fullAddCount()方法进行初始化，并插入对应的记录数，通过CAS设置cellsBusy字段，只有设置成功的线程才能初始化CounterCell数组  
3、如果通过CAS设置cellsBusy字段失败的话，则继续尝试通过CAS修改baseCount字段，如果修改baseCount字段成功的话，就退出循环，否则继续循环插入CounterCell对象  
所以在1.8中的size实现比1.7简单多，因为元素个数保存baseCount中，部分元素的变化个数保存在CounterCell数组中  
通过累加baseCount和CounterCell数组中的数量，即可得到元素的总个数  
性能大大优于jdk1.7中的size()方法。  
**扩容实现**  
1.当有线程进行put操作时，如果正在进行扩容，可以通过helpTransfer()方法加入扩容。也就是说，ConcurrentHashMap支持多线程扩容，多个线程处理不同的节点。   
2.开始扩容，首先计算步长，也就是每个线程分配到的扩容的节点数(默认是16)。这个值是根据当前容量和CPU的数量来计算(stride = (NCPU > 1) ? (n >>> 3) / NCPU : n)，最小是16。   
3.接下来初始化临时的Hash表nextTable，如果nextTable为null，初始化nextTable长度为原来的2倍；   
4.通过计算出的步长开始遍历Hash表，其中坐标是通过一个原子操作(compareAndSetInt)记录。通过一个while循环，如果在一个线程的步长内便跳过此节点。否则转下一步；   
5.如果当前节点为空，之间将此节点在旧的Hash表中设置为一个ForwardingNodes节点，表示这个节点已经被处理过了。   
6.如果当前节点元素的hash值为MOVED(f.hash == -1)，表示这是一个ForwardingNodes节点，则直接跳过。否则，开始重新处理节点；   
7.对当前节点进行加锁，在这一步的扩容操作中，重新计算元素位置的操作与HashMap中是一样的，即当前元素键值的hash与长度进行&操作，如果结果为0则保持位置不变，为1位置就是i+n。其中进行处理的元素是最后一个符合条件的元素，所以扩容后可能是一种倒序，但在Hash表中这种顺序也没有太大的影响。 
最后如果是链表结构直接获得高位与低位的新链表节点，如果是树结构，同样计算高位与低位的节点，但是需要根据节点的长度进行判断是否需要转化为树的结构。   

### 改进原因 ###   
**锁的粒度**   
首先锁的粒度并没有变粗，甚至变得更细了。每当扩容一次，ConcurrentHashMap的并发度就扩大一倍。  
**Hash冲突**   
红黑树可以较有效的防止hash冲突效率下降，get的效率会上升很快  
**扩容**   
JDK1.8中，在ConcurrentHashmap进行扩容时，其他线程可以通过检测数组中的节点决定是否对这条链表（红黑树）进行扩容，减小了扩容的粒度，提高了扩容的效率。 
 

**为什么是synchronized，而不是可重入锁** 
1. 减少内存开销 
假设使用可重入锁来获得同步支持，那么每个节点都需要通过继承AQS来获得同步支持。但并不是每个节点都需要获得同步支持的，只有链表的头节点（红黑树的根节点）需要同步，这无疑带来了巨大内存浪费。 
2. 获得JVM的支持 
可重入锁毕竟是API这个级别的，后续的性能优化空间很小。 
synchronized则是JVM直接支持的，JVM能够在运行时作出相应的优化措施：锁粗化、锁消除、锁自旋等等。这就使得synchronized能够随着JDK版本的升级而不改动代码的前提下获得性能上的提升。

**为什么扩容是2的倍数**  
加快取余运算的计算，当容量一定是2^n时，h & (length - 1) == h % length
