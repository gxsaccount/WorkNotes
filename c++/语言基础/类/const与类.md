## const与成员函数 ##
规则：只要成员函数不修改对象，就应该为const成员函数。**否则类实例为const时不能使用该函数**  
格式：
void function() const{}
避免如下情况出现：
const Class class {...}
class.function()//错误，因为function可能会修改class

## const成员变量 ##  
使用static const 关键字声明类的const成员变量  
直接使用const该成员变量只描述了该对象形式，没有创建对象，会没有用于存储值的空间。???  
