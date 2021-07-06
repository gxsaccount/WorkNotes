可以通过Tag来增强结构体的定义，Tag会带上一些meta信息  

## 反射获取Tag ##  

    //不管是raw string还是interpreted string都可以用来当tag。 如果field定义时候两个名字公用一个属性，那么这个tag会被附在两个名字上，像f4,f5一样。  
    type T struct{
      f1 string "f one"
      f2 string
      f3 string 'f three'
      f4,f5 int64 'f four and five'//and 为关键字
    }

    func main(){
      t:= reflect.TypeOf(T{})
      f1,_:=t.FieldByName("f1")
      fmt.Println(f1.Tag) // f one
      f4, _ := t.FieldByName("f4")
      fmt.Println(f4.Tag) // f four and five
      f5, _ := t.FieldByName("f5")
      fmt.Println(f5.Tag) // f four and five
    }

## tag的键值对形式 ##  
Tags可以由键值对来组成，通过空格符来分割键值 —key1:"value1" key2:"value2" key3:"value3"。  
如果Tags格式没问题的话，我们可以通过Lookup或者Get来获取键值对的值。  
Lookup回传两个值 —对应的值和是否找到  

    type T struct{
      f string `one:"1" two:"2"blank:""`
    }
    func main(){
      t := reflect.TypeOf(T{})
      f, _ := t.FieldByName("f")
      fmt.Println(f.Tag) // one:"1" two:"2"blank:""
      v, ok := f.Tag.Lookup("one")
      fmt.Printf("%s, %t\n", v, ok) // 1, true
      v, ok = f.Tag.Lookup("blank")
      fmt.Printf("%s, %t\n", v, ok) // , true
      v, ok = f.Tag.Lookup("five")
      fmt.Printf("%s, %t\n", v, ok) // , false
    } 
    //Get方法只是简单的包装了以下Lookup。但是丢弃了是否成功结果
    func (tag StructTag) Get(key string) string {
      v, _ := tag.Lookup(key)
      return v
    }

## marshaling使用 ##  

    import (
      "encoding/json"
      "fmt"
    )
    func main() {
        type T struct {
           F1 int `json:"f_1"`
           F2 int `json:"f_2,omitempty"`
           F3 int `json:"f_3,omitempty"`
           F4 int `json:"-"`
        }
        t := T{1, 0, 2, 3}
        b, err := json.Marshal(t)
        if err != nil {
            panic(err)
        }
        fmt.Printf("%s\n", b) // {"f_1":1,"f_3":2}
    }


