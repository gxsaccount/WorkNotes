stack和queue性质上不属于容器，是容器的装饰器adpter  
底层默认使用deque实现  
不提供遍历和迭代器实现，会破坏它们的特性  

stack可以使用deque和list实现
queue可以使用deque和list，不能使用vector(编译可通过，调用pop()报错，vector没有pop_front)  
set和map都不行
stack<string,list<string>> c;

为什么 stack（或 queue）的 pop 函数返回类型为 void，而不是直接返回容器的 top（或 front）成员？  
异常安全性，为什么会有异常安全性。 场景： C++是值语义，以前返回对象只能是拷贝，可能发生异常。一旦发生异常，对象已经被弹出，那它就彻底“丢失”了  

