## 变量声明 ##
定义的变量一定要用到
变量的作用域只有函数和包：  
      
      package 包名
      var a,b,c bool //初值各字节位均为0,指定的类型在后面
      var s1,s2 string = "hello","world"
      var (
        a=1
        s="kk"
        b=true
      )
      func ()  {
        aa,bb,cc:=true,3,"hello"//只能函数中使用
        var aaa,bbb,ccc =false,1,"world"//与上一句等价
        complex := 3 + 1i //1 i是complex类型
      }

## 内建变量类型 ##  
两个不同类型的整型数不能直接比较，比如int8类型的数和int类型的数不能直接比较，但各种类型的整型变量都可以直接与字面常量（literal）进行比较。  
      bool，string  
      //u是无符号类型，不规定长度的int根据操作系统长度来  
      (u)int,(u)int8,(u)int16,(u)int32,(u)int64  
      //指针，长度根据操作系统来  
      uintptr  
      //rune是char类型，但是是4字节，可以于整数混用 
      //Go语言中byte和rune实质上就是uint8和int32类型。byte用来强调数据是raw data，而不是数字；而rune用来表示Unicode的code point
      byte，rune  
      //float 类型不精确  
      float32，float64，complex64（两个float32），complex128（float64）  

## 强制类型转化 ##  
go只有强制类型转化  
c = int(math.Sqrt(float64(1+2\*8)))  

## 常量声明 ##  
常量不能大写，一定要有初值.  
Go语言预定义了这些常量：true、false和iota。  
iota比较特殊，可以被认为是一个可被编译器修改的常量，在每一个const关键字出现时被  
重置为0，然后在下一个const出现之前，每出现一次iota，其所代表的数字会自动增1。  


      const c int = 1
      const a,b = 3,4 //a,b没有明确类型
      const(
            ...
      )
      //枚举
      func enums(){
            const(
                  cpp=iota //iota自增，0，1<<(10 * iota)等都行
                  _//跳过
                  python 
            )
      }

      const (
       a = 1 << iota // a == 1 (iota在每个const开头被重设为0)
       b = 1 << iota // b == 2
       c = 1 << iota // c == 4
      )
      const (  
       u = iota * 42 // u == 0  
       v float64 = iota * 42 // v == 42.0 
       w = iota * 42 // w == 84
      ) 

  ## 数组类型 ##  
 
      package main
      import "fmt"
      func main() {
          var numbers2 [5]int
            numbers2[0] = 2
            numbers2[3] = numbers2[0] - 3
            numbers2[1] = numbers2[2] + 5
            numbers2[4] = len(numbers2)
      }

 ## 切片类型 ##  
切片本身已经是一个引用类型，所以它本身就是一个指针。  
数组切片的数据结构可以抽象为以下3个变量：  
   一个指向原生数组的指针；  
   数组切片中的元素个数；  
   数组切片已分配的存储空间。  
可以动态增加容量
      func main() {
            //创建一个初始元素个数为5的数组切片，元素初始值为0：
            mySlice1 := make([]int, 5)
            //创建一个初始元素个数为5的数组切片，元素初始值为0，并预留10个元素的存储空间：
            mySlice2 := make([]int, 5, 10)
            //直接创建并初始化包含5个元素的数组切片：
            mySlice3 := []int{1, 2, 3, 4, 5}
            //当然，事实上还会有一个匿名数组被创建出来，只是不需要我们来操心而已。
            
            //数组形式创建
            var numbers3 = [5]int{1, 2, 3, 4, 5}
            slice3 := numbers3[2 : len(numbers3)]
            length := (3)//切片长度
            capacity := (3)//切片值的容量即为它的第一个元素值在其底层数组中的索引值与该数组长度的差值的绝对值。
            fmt.Printf("%v, %v\n", (length == len(slice3)), (capacity == cap(slice3)))

            slice5 := numbers4[4:6:8]//5, 6, 7 ,8;//第三个参数代表索引上界可以把作为结果的切片值的容量设置得更小。
            length := (2)
            capacity := (4)
            fmt.Printf("%v, %v\n", length == len(slice5), capacity == cap(slice5))
            slice5 = slice5[:cap(slice5)]
            slice5 = append(slice5, 11, 12, 13)//5, 6, 7, 8, 11, 12, 13
            length = (7)
            fmt.Printf("%v\n", length == len(slice5))
            slice6 := []int{0, 0, 0}
            copy(slice5, slice6)//0, 0, 0, 8, 11, 12, 13
            e2 := (0)
            e3 := (8)
            e4 := (11)
            fmt.Printf("%v, %v, %v\n", e2 == slice5[2], e3 == slice5[3], e4 == slice5[4])
      }

## 字典类型 ##  
HashMap()  
      
      func main() {
            myMap = make(map[string] PersonInfo)
            //也可以选择是否在创建时指定该map的初始存储能力，下面的例子创建了一个初始存储能力为100的map:
            myMap = make(map[string] PersonInfo, 100) 
            //
            delete(myMap, "1234") 
            
            mm2 := map[string]int{"golang": 42, "java": 1, "python": 8}
            mm2["scala"]=25
            mm2["erlang"]=50
            mm2["python"]=0
            fmt.Printf("%d, %d, %d \n", mm2["scala"], mm2["erlang"], mm2["python"])
      }
      遍历
      for k, v := range mm2 {mt.Printf("%s=%d;", k, v)}
 ## 通道类型 ##  
 通道（Channel）可用于在不同Go程序之间传递类型化的数据，**先进先出**，**并发安全**，类型关键字**chan**。  
 初始化：用make函数初始化一个通道，make第一个参数是代表了通道的传递的类型，而第二个参数则是可以缓存的个数。
 传递值：用**操作符<-** 进行取值和放值
 指定方向：make初始化的是双向通道，需要用到单向通道时，用如下语句：
 
      type Receiver <-chan int //类型Receiver代表了一个只可从中接收数据的单向通道类型。
      type Sender chan<- int //传递通道
      
 注意：
 1.对通道值的重复关闭会引发运行时恐慌
 2.通道缓存满时阻塞放入
 3.通道为空时取出操作阻塞
 4.与切片和字典类型相同，通道类型属于引用类型。它的零值即为nil
 5.单向通道可以被赋值为双向通道，双向通道不能赋值为单向通道
 6.发送时，通道获取的是值的副本，不是原值  
 7.可以用range获取通道中的数据，通道关闭后
 
      type Sender chan<- int
      type Receiver <-chan int
      func main() {
            var myChannel = make(chan int, 0)//无缓冲通道
            var number = 6
            go func() {
                  var sender Sender = myChannel
                  sender <- number//传递值后阻塞
                  fmt.Println("Sent!")
            }()
            go func() {
                  var receiver Receiver = myChannel
                  fmt.Println("Received!", <-receiver)
            }()
            // 让main函数执行结束的时间延迟1秒，
            // 以使上面两个代码块有机会被执行。
            time.Sleep(time.Second)
      }
      //以上代码打印顺序为 “Received! 6 Sent”，因为Sent之前被阻塞，“<-receiver”之后才能执行
      
      
      func main(){
	var myChannel = make(chan int,1)
	var temp int
	go func() {
		var count int
		count =0
		for{
			count++
			myChannel<-1
			if count>10{
				close(myChannel)
				break//没有break会造成重复关闭恐慌
			}

		}
	}()

	for temp = range myChannel{//如果chan不关闭将会一直执行下去
		fmt.Print(temp)
	}

 

  ## 结构体 ##
  结构体类型属于值类型。它的零值并不是nil，而是其中字段的值均为相应类型的零值的值。
      
      //声明
      type Person struct {
            Name   string
            Gender string
            Age    uint8
      }   
      //实例化
      Person{Name: "Robert", Gender: "Male", Age: 33}
      Person{"Robert", "Male", 33}
      //结构体函数，(person *Person)为接收者声明
      func (person *Person) Grow() {
          person.Age++
      } 
      //使用
      p := Person{"Robert", "Male", 33}
      p.Grow() 
      
      //匿名结构体，匿名结构体是不可能拥有方法的
      p := struct {
            Name   string
            Gender string
            Age    uint8
      }{"Robert", "Male", 33}
      
      
 ## strcut的继承 ##
一个结构体嵌到另一个结构体，称作组合  
匿名和组合的区别  
如果一个struct嵌套了另一个匿名结构体，那么这个结构可以直接访问匿名结构体的方法，从而实现继承  
如果一个struct嵌套了另一个【有名】的结构体，那么这个模式叫做组合  
如果一个struct嵌套了多个匿名结构体，那么这个结构可以直接访问多个匿名结构体的方法，从而实现多重继承  
  
  ## 指针 ##
  go 语言的指针不能运算，只有值传递，调用函数都需要拷贝一份参数  
  用指针实现引用传递效果  
      
      var pa \*int = &a
   
  基底类型：\*类型 是 类型的基底类型  
  一个指针类型拥有以它以及以它的基底类型为接收者类型的所有方法，而它的基底类型却只拥有以它本身为接收者类型的方法。  
  即指针类型拥有拥有值方法和指针方法。  
  
  
  ## 函数 ##
函数是一等（first-class）类型，类名func。这意味着，我们可以把函数作为值来传递和使用。
Go语言中函数可以返回多个结果。
      
      //函数声明
      type MyFunc func(input1 string ,input2 string) string
      //函数实现
      func myFunc(part1 string, part2 string) string {
          return part1 + part2
      }  
      //函数类型变量
      var splice func(string, string) string // 等价于 var splice MyFunc
      splice = myFunc
      
      //普通形式
      func 函数名(变量名 变量类型) (返回类型1,...){
            ...
      }
      //函数参数
      func apply(op func(int,int) int , a,b int) int {
            //通过反射获得方法名字
            p:= reflect.ValueOf(op).Pointer()
            opName := runtime.FuncForPC(p).Name()
            fmt.Printf("Calling function %s with args "+"(%d,%d)opName,a,b")
            return op(a,b)
      }
      
     //匿名函数
     fmt.Println(apply(
            func(a int,b int) int {
                  return int(math.Pow(
                        float64(a),float64(b)))
            },3,4))
      //可变参数列表
      func sum(numbers ...int) int{
            s:=0
            for i:= range numbers{
                  s+= numbers[i]
            }
            return s
      }
      
 # 接口 #
 无需在一个数据类型中声明它实现了哪个接口。只要满足了“方法集合为其超集”的条件，即接口对应的函数某结构体都有，就建立了“实现”关系。  
 这是典型的无侵入式的接口实现方法。  
 空接口类型即是不包含任何方法声明的接口类型，用interface{}表示，常简称为空接口。  
 Go语言中的包含预定义的任何数据类型都可以被看做是空接口的实现。  
 只要两个接口拥有相同的方法列表，那么它们就是等同的，可以相互赋值。  
 
 声明：
  
      type Animal interface {
            Grow()
            Move(string) string//Move(new string) (old string)简化
      }
      
使用：
      
      type Animal interface {
            Grow()
            Move(string) string
      }

      type Cat struct{
            Name string
            Age uint8
            Location  string
      }

      func (cat *Cat) Move(new string) string {
            old := cat.Location
            cat.Location = new
            return old
      }

      func (cat *Cat) Grow(){
            cat.Age++
      }

      func main() {
            //初始化一个结构体
            myCat := Cat{"Little C", 2, "In the house"}
            //将结构体转化为空接口
            animal, ok := interface{}(&myCat).(Animal)
            //类型断言
            fmt.Printf("%v, %v\n", ok, animal)
      }
       
       
  ## 条件语句 ##
 if语句中可以赋值，作用于在if中
      
      if contents,err := ioutil.ReadDile(filename);err == nil {
            fmt.Println(string(contents))
      } else{
            fmt.Println("can not print file contents:",err)
      }
 ## switch ##  
 switch会自动break，除非使用fallthrough
      
      import (
          "fmt"
            "math/rand"
            "time"
      )

      func main() {
            //随机数种子
            rand.Seed(time.Now().Unix())
            //空接口数组
            ia := []interface{}{byte(6), 'a', uint(10), int32(-4)}
            switch v := ia[rand.Intn(2)]; interface{}(v).(type) {
            case int32 :
                  fmt.Printf("Integer")
            case byte :
                  fmt.Printf("Byte")
            case uint:
                fmt.Printf("uint")
      // 	case rune://rune就是int32，类型重复
      // 	    fmt.Printf("rune")
            default:
                  fmt.Println("Unknown!")
            }
      }
## 循环 ## 
      sum:=0
      for i := 1; i<= 100 ; i++{
            sum+=i
      }
      //死循环
      for{}
## select ##
select语句属于条件分支流程控制方法，不过它只能用于通道。  
它可以包含若干条case语句，并根据条件选择其中的一个执行。  
进一步说，select语句中的case关键字只能后跟用于通道的发送操作的表达式以及接收操作的表达式或语句。  

      ch1 := make(chan int, 1)
      ch2 := make(chan int, 1)
      // 省略若干条语句
      select {
      case e1 := <-ch1:
          fmt.Printf("1th case is selected. e1=%v.\n", e1)
      case e2 := <-ch2:
          fmt.Printf("2th case is selected. e2=%v.\n", e2)
      default:
          fmt.Println("No data!")
      } 
如果该select语句被执行时通道ch1和ch2中都没有任何数据，那么肯定只有default case会被执行。但是，只要有一个通道在当时有数据就不会轮到default case执行了。显然，对于包含通道接收操作的case来讲，其执行条件就是通道中存在数据（或者说通道未空）。如果在当时有数据的通道多于一个，那么Go语言会通过一种伪随机的算法来决定哪一个case将被执行。  
break语句也可以被包含在select语句中的case语句中。它的作用是立即结束当前的select语句的执行，不论其所属的case语句中是否还有未被执行的语句。  

## defer ##  
defer语句仅能被放置在函数或方法中。  
defer语句影响的代码块在函数执行即将结束的前一时刻执行  
当一个函数中存在多个defer语句时，它们携带的表达式语句的执行顺序一定是它们的出现顺序的**倒序**。  
使用：

      func readFile(path string) ([]byte, error) {
          file, err := os.Open(path)
          if err != nil {
              return nil, err
          }
          defer file.Close()
          return ioutil.ReadAll(file)
      }
      
 倒序：  
 
      func deferIt3() {
            f := func(i int) int {
              fmt.Printf("%d ",i)
              return i * 10
            }
            for i := 1; i < 5; i++ {
              defer fmt.Printf("%d ", f(i))
            }
      }
      
      包含匿名函数：  
      func deferIt4() {
            for i := 1; i < 5; i++ {
                    defer func() {
                        fmt.Print(i)
                    }()
            }
      }    
      //输出5555，原因是defer语句携带的表达式语句中的那个匿名函数包含了对外部（确切地说，是该defer语句之外）的变量的使用。
      func deferIt4() {
            for i := 1; i < 5; i++ {
                    defer func(n int) {
                        fmt.Print(n)
                    }(i)
            }
      }
      //输出4321
      
 ## Go语言异常处理——error ##  
 error是Go语言内置的一个接口类型。只要一个类型的方法集合包含了名为Error、无参数声明且仅声明了一个string类型的结果的方法，就相当于实现了error接口。  
它的声明是这样的：

      type error interface { 
          Error() string
      }
 
可以用errors.New创建一个错误，如
      
      errors.New("The parameter is invalid!

## Go语言异常处理——panic ##  
panic用于产生运行时恐慌，该函数可接受一个interface{}类型的值作为其参数。也就是说，可以在调用panic函数的时候可以传入任何类型的值。建议只传入error类型的值。这样它表达的语义才是精确的。    
recover用于“恢复”panic，函数会返回一个interface{}类型的值，recover函数必须要在defer语句中调用才有效。  

      import (
          "errors"
            "fmt"
      )

      func innerFunc() {
            fmt.Println("Enter innerFunc")
            //panic使用
            panic(errors.New("Occur a panic!"))
            fmt.Println("Quit innerFunc")
      }

      func outerFunc() {
            fmt.Println("Enter outerFunc")
            innerFunc()
            fmt.Println("Quit outerFunc")
      }

      func main() {
            //recover使用
          defer func() {
              if p := recover(); p != nil {
                  fmt.Printf("Fatal error: %s\n", p)
              }
          }()
            fmt.Println("Enter main")
            outerFunc()
            fmt.Println("Quit main")
      }

【注】引用类型初始化用make函数
