分段连续，使用上是感觉是连续的，和vector一样有扩充逻辑，当存储不够时，扩充一个固定大小  
deque是双端队列的数据结构，可以在队首和队尾高效的添加和删除元素，这是相对于vector的优势。  

deque内部采用分段连续的内存空间来存储元素，在插入元素的时候随时都可以重新增加一段新的空间并链接起来，因此虽然提供了随机访问操作，但访问速度和vector相比要慢。  

deque并没有data函数，因为deque的元素并没有放在数组中。  

deque不提供capacity和reserve操作。  

deque内部的插入和删除元素要比list慢。  
由于deque在性能上并不是最高效的，有时候对deque元素进行排序，更高效的做法是，将deque的元素移到vector再进行排序，然后在移到回来。  

deque为了实现整体连续的假象，导致其实现起来比较繁琐，尽量少使用它。  

双向队列  
分段连续
（1）map（vector）+N（buffer/array）  
迭代器走到边界跳到下一个buffer  
迭代器结构：
【cur，first，last，node】
cur：迭代器指向当前buffer的元素index  
first：buffer的起始  
last：buffer的结束  
node：buffer在map中位置  
