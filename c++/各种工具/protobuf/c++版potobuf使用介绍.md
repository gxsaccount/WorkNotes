## proto例子 ##  

    syntax = "proto2";
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
    在反序列化的时候，protobuf会从输入流中读取出字段编号，然后再设置message中对应的值。    
    如果读出来的字段编号是message中没有的，就直接忽略，  
    如果message中有字段编号是输入流中没有的，则该字段不会被设置。  
    但是如果两端同一编号的字段规则或者字段类型不一样，就会影响反序列化。  
    **所以一般调整proto文件的时候，尽量选择加字段或者删字段，而不是修改字段编号或者字段类型。**  
