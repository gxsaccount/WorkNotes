## 基本属性 ##  
相当于一个struct  

## 基本使用 ##  

    #include <tuple>
    //1.2 、创建一个元组并初始化元组。　
    std::string str_second_1("_1");
    std::string str_second_2("_2");

    // 指定了元素类型为引用 和 std::string, 下面两种方式都是可以的，只不过第二个参数不同而已
    std::tuple<std::string, std::string> second_1(str_second_1, std::string("_2"));
    std::tuple<std::string, std::string> second_2(str_second_1, str_second_2);
    
    //1.3、创建一个元素是引用的元组
    //创建一个元组，元组的元素可以被引用, 这里以 int 为例
    int i_third = 3;
    std::tuple<int&> third(std::ref(i_third));
    
    //1.4、使用make_tuple创建元组
    int i_fourth_1 = 4;
    int i_fourth_2 = 44;
    std::tuple<int, int> forth_1    = std::make_tuple(i_fourth_1, i_fourth_2);
    
    //1.5、创建一个类型为引用的元组， 对元组的修改。 这里以 std::string为例
    std::string str_five_1("five_1");
    // 输出原址值
    std::cout << "str_five_1 = " << str_five_1.c_str() << "\n";

    std::tuple<std::string&, int> five(str_five_1, 5);
    // 通过元组 对第一个元素的修改，str_five_1的值也会跟着修改，因为元组的第一个元素类型为引用。
    // 使用get访问元组的第一个元素
    std::get<0>(five) = "five_2";

    // 输出的将是： five_2
    std::cout << "str_five_1 = " << str_five_1.c_str() << "\n";
    
    2、计算元组的元素个数
    1     std::tuple<char, int, long, std::string> first('A', 2, 3, "4");
2         // 使用std::tuple_size计算元组个数
3         int i_count = std::tuple_size<decltype(first)>::value;
4         std::cout << "元组个数=" << i_count << "\n";


  访问元组的元素，需要函数： std::get<index>(obj)。其中：【index】是元组中元素的下标，0 ，1 ， 2， 3， 4，....     【obj】-元组变量。 　　
  std::tuple<char, int, long, std::string> second('A', 2, 3, "4");
int index = 0;
std::cout << index++ << " = " << std::get<0>(second) << "\n";
std::cout << index++ << " = " << std::get<1>(second) << "\n";
std::cout << index++ << " = " << std::get<2>(second) << "\n";
std::cout << index++ << " = " << std::get<3>(second).c_str() << "\n";
【注意】元组不支持迭代访问， 且只能通过索引（或者tie解包：将元组的中每一个元素提取到指定变量中）访问， 且索引不能动态传入。上面的代码中，索引都是在编译器编译期间就确定了。 下面的演示代码将会在编译期间出错。
for (int i = 0; i < 3; i++)
        std::cout << index++ << " = " << std::get<i>(second) << "\n";　　// 无法通过编译

4、获取元素的类型  
std::tuple<int, std::string> third(9, std::string("ABC"));

// 得到元组第1个元素的类型，用元组第一个元素的类型声明一个变量
std::tuple_element<1, decltype(third)>::type val_1;

// 获取元组的第一个元素的值
val_1 = std::get<1>(third);
std::cout << "val_1 = " << val_1.c_str() << "\n";

5、使用 std::tie解包  
元组，可以看作一个包，类比结构体。 需要访问元组的元素时，2 种方法： A、索引访问，B、std::tie 。

　　元组包含一个或者多个元素，使用std::tie解包： 首先需要定义对应元素的变量，再使用tie。 比如，元素第0个元素的类型时 char, 第1个元素类型时int,  那么， 需要定义 一个 char的变量和int的变量， 用来储存解包元素的结果。  
  
  std::tuple<char, int, long, std::string> fourth('A', 2, 3, "4");

// 定义变量，保存解包结果
char tuple_0    = '0';
int tuple_1        = 0;
long tuple_2    = 0;
std::string tuple_3("");

// 使用std::tie, 依次传入对应的解包变量
std::tie(tuple_0, tuple_1, tuple_2, tuple_3) = fourth;

// 输出解包结果
std::cout << "tuple_0 = " << tuple_0 << "\n";
std::cout << "tuple_1 = " << tuple_1 << "\n";
std::cout << "tuple_2 = " << tuple_2 << "\n";
std::cout << "tuple_3 = " << tuple_3.c_str() << "\n";
 如果一个元组，只需要取出其中特定位置上的元素，不用把每一个元素取出来， 怎么做？ 

　　比如： 只要索引为 偶数的元素。

　　元组提供了类似占位符的功能： std::ignore 。满足上面的需求，只需要在索引为奇数的位置填上 std::ignore 。 一个例子：  
  std::tuple<char, int, long, std::string> fourth('A', 2, 3, "4");

// 定义变量，保存解包结果
char tuple_0    = '0';
int tuple_1        = 0;
long tuple_2    = 0;
std::string tuple_3("");

// 使用占位符
std::tie(tuple_0, std::ignore, tuple_2, std::ignore) = fourth;

// 输出解包结果
std::cout << "tuple_0 = " << tuple_0 << "\n";
std::cout << "tuple_1 = " << tuple_1 << "\n";
std::cout << "tuple_2 = " << tuple_2 << "\n";
std::cout << "tuple_3 = " << tuple_3.c_str() << "\n";
  
6、元组连接（拼接）
　　使用 std::tuple_cat 执行拼接

　　一个例子：

复制代码
 1 std::tuple<char, int, double> first('A', 1, 2.2f);
 2 
 3 // 组合到一起, 使用auto， 自动推导
 4 auto second = std::tuple_cat(first, std::make_tuple('B', std::string("-=+")));
 5 // 组合到一起，可以知道每一个元素的数据类型时什么 与 auto推导效果一样
 6 std::tuple<char, int, double, char, std::string> third = std::tuple_cat(first, std::make_tuple('B', std::string("-=+")));
 7 
 8 // 输出合并后的元组内容
 9 int index = 0;
10 std::cout << index++ << " = " << std::get<0>(second) << "\n";
11 std::cout << index++ << " = " << std::get<1>(second) << "\n";
12 std::cout << index++ << " = " << std::get<2>(second) << "\n";
13 
14 std::cout << index++ << " = " << std::get<3>(second) << "\n";
15 std::cout << index++ << " = " << std::get<4>(second).c_str() << "\n";

7、遍历
　　这里将采用的时 递归遍历，需要注意，考虑爆栈的情况。其实，tuple也是基于模板的STL容器。 因为其可以容纳多个参数，且每个参数类型可不相同，遍历输出则涉及到参数展开的情况，这里以递归的方式实现遍历， 核心代码：

复制代码
 1 template<typename Tuple, size_t N>
 2 struct tuple_show
 3 {
 4     static void show(const Tuple &t, std::ostream& os)
 5     {
 6         tuple_show<Tuple, N - 1>::show(t, os);
 7         os << ", " << std::get<N - 1>(t);
 8     }
 9 };
10 
11 
12 // 偏特性，可以理解为递归的终止
13 template<typename Tuple>
14 struct tuple_show < Tuple, 1>
15 {
16     static void show(const Tuple &t, std::ostream &os)
17     {
18         os <<  std::get<0>(t);
19     }
20 };
21 
22 
23 
24 // 自己写个函数，调用上面的递归展开，
25 template<typename... Args>
26 std::ostream& operator << (std::ostream &os, const std::tuple<Args...>& t)
27 {
28     os << "[";
29     tuple_show<decltype(t), sizeof...(Args)>::show(t, os);
30     os << "]";
31 
32     return os;
33 }
复制代码
　　调用示例：

1     auto t1 = std::make_tuple(1, 'A', "-=+", 2);
2     std::cout << t1;




## 实现 ##   

#include <iostream>
using namespace std;
 
 
template<typename... Values>class Tuple;
template<>class Tuple<> {}; //偏特化，中止条件
template<typename Head, typename... Tail>
class Tuple<Head, Tail...>
	:private Tuple<Tail...>	// 私有继承自Tuple<Tail...>
{
	using inherited = Tuple<Tail...>; //定义inherited 为 基类类型
public:
	Tuple(){}  
	Tuple(Head v, Tail... vtail) // 将第一个元素 赋值给m_head, 其余传给基类
		:m_head(v), inherited(vtail...)
	{}
 
	Head head() { return m_head; }  // 返回元组的第一个元素
	inherited& tail() { return *this; } // 返回该元组的基类引用
protected:
	Head m_head;
};
 
 
template<typename Head, typename... Tail> //typename... Tail 多个类型
ostream& operator<<(ostream& os, Tuple<Head, Tail...>& tpe) // 当元素个数大于1时调用该方法
{
	os <<  tpe.head() << ",";
	operator<<(os, tpe.tail()); // 将tpe的基类作为输出的对象 递归调用输出函数
	return os;
}
 
template<typename T>
ostream& operator<<(ostream& os, Tuple<T>& tpe) // 当元素个数为 1 是调用该方法
{
	os  << tpe.head();
	return os;
}
 
 
int main(void)
{
	Tuple<int, string, float> mt(10, "fsdf", 23.);
	cout << mt.head() << endl; // 输出: 10
	cout << (mt.tail()).head() << endl; // 输出: fsdf
	cout << ((mt.tail()).tail()).head() << endl; //输出: 23
 
	cout << "--------------------" << endl;
 
	cout << "Tuple<" << mt << ">" << endl; //输出: Tuple<10, fsdf, 23>
 
	system("pause");
	return 0;
}
  Tuple<int, string, float> 继承自 Tuple<string, float>

  Tuple<string, float> 继承自 Tuple<float>

  Tuple<float> 继承自 Tuple<>
