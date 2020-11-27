定义在any头文件中：#include\<any\>  
是一个可用于任何类型单个值的类型安全的容器.
使用方法

    #include <iostream>
    #include <optional>
    #include <string>

    // convert string to int if possible:
    std::optional<int> asInt(const std::string& s)
    {
        try 
        {
            return std::stoi(s);
        }
        catch (...) 
        {
            return std::nullopt;
        }
    }
    int main()
    {
        for (auto s : { "42", " 077", "hello", "0x33" }) 
        {
            // convert s to int and use the result if possible:
            std::optional<int> oi = asInt(s);
            if (oi) {
                std::cout << "convert '" << s << "' to int: " << *oi << "\n";
            }
            else {
                std::cout << "can't convert '" << s << "' to int\n";
            }
        }
    }

总结：

    std::any a = 1;: 声明一个any类型的容器，容器中的值为int类型的1
    a.type(): 得到容器中的值的类型
    std::any_cast<int>(a);: 强制类型转换, 转换失败可以捕获到std::bad_any_cast类型的异常
    has_value(): 判断容器中是否有值
    reset(): 删除容器中的值
    std::any_cast<int>(&a): 强制转换得到容器中的值的地址
