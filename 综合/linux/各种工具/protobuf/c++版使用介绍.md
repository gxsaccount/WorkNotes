# proto语法 #
## proto例子 ##  
    
    //tutorial.poto
    syntax = "proto2";//声明使用poto的版本,默认poto3
    package tutorial; //package声明,防止不同项目定义冲突

    message Person {
      required string name = 1;
      required int32 id = 2;
      optional string email = 3;

      enum PhoneType {
        MOBILE = 0;
        HOME = 1;
        WORK = 2;
      }

      message PhoneNumber {
        required string number = 1;
        optional PhoneType type = 2 [default = HOME];
      }

      repeated PhoneNumber phones = 4;
    }

    message AddressBook {
      repeated Person people = 1;
    }

## 语法解释 ##
**message**  
消息是包含一组类型字段的聚合  
**类型使用**  
类型包括bool, int32, float, double, and string  
类型还包括其他message和enum  
**字段规则**  
required:必需设置的字段  
optional:可以不设值,使用默认值.可以使用defalut设置默认值  
repeated:该字段可以重复任意次（包括零次),重复值的顺序将保留在协议缓冲区中,将重复字段视为动态大小的数组。  
**字段编号**  
为了向前及向后兼容设计，   
字段编号用于标识消息二进制格式中的字段，并且在使用消息类型后不应更改。
在反序列化的时候，protobuf会从输入流中读取出字段编号，然后再设置message中对应的值。    
如果读出来的字段编号是message中没有的，就直接忽略，  
如果message中有字段编号是输入流中没有的，则该字段不会被设置。  
但是如果两端同一编号的字段规则或者字段类型不一样，就会影响反序列化。 
范围1到15中的字段编号需要一个字节进行编码,包括字段编号和字段类型。  
范围16至2047中的字段编号需要两个字节。  **???**
所以需要保留数字1到15作为非常频繁出现的消息元素。  
请记住为将来可能添加的频繁出现的元素留出一些空间。
可以指定的最小字段编号为1，最大字段编号为2^29^-1。  
也不能使用数字 19000 到 19999（FieldDescriptor :: kFirstReservedNumber 到 FieldDescriptor :: kLastReservedNumber），因为它们是为 Protocol Buffers实现保留的。
如果在 .proto 中使用这些保留数字中的一个，Protocol Buffers 编译的时候会报错。
同样，您不能使用任何以前 Protocol Buffers 保留的一些字段号码。
**所以一般调整proto文件的时候，尽量选择加字段或者删字段，而不是修改字段编号或者字段类型。**  

**保留字段**  
如果您通过完全删除某个字段或将其注释掉来更新消息类型，那么未来的用户可以在对该类型进行自己的更新时重新使用该字段号。  
如果稍后加载到了的旧版本 .proto 文件，则会导致服务器出现严重问题，例如数据混乱，隐私错误等等。  
确保这种情况不会发生的一种方法是指定删除字段的字段编号（或名称，这也可能会导致 JSON 序列化问题）为 reserved。  
如果将来的任何用户试图使用这些字段标识符，Protocol Buffers 编译器将会报错。  

    message Foo {
      reserved 2, 15, 9 to 11;
      reserved "foo", "bar";
    }

注意，不能在同一个 reserved 语句中混合字段名称和字段编号。如有需要需要像上面这个例子这样写。  

# 在C++中使用 #  
## 编译potobuf ##  
使用poto编译器编译
    
    protoc -I=$SRC_DIR --cpp_out=$DST_DIR $SRC_DIR/tutorial.poto  
命令生成两个文件:
    
    lm.helloworld.pb.h ， 定义了 C++ 类的头文件
    lm.helloworld.pb.cc ， C++ 类的实现文件

## 编写writer和Reader ##  
