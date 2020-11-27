场景：如果有这样一个函数，通过返回值来判断计算结果是否有效，如果结果有效，才能使用结果 。

例如：计算a、b相除。b有可能为0，所以需要考虑相除结果是否有效。


    bool div_int(int a, int b, int &result) {
        if (b == 0) {
            return false;
        }
        result = a / b;
        return true;
    }

    TEST_F(before_optional) {
        int result = 0; // 接收结果
        auto ret = div_int(2, 1, result);
        ASSERT(ret);
        ASSERT_EQ(2, result); // 如果返回值为true, 结果才有效

        auto b = div_int(2, 0, result);
        ASSERT(!b);
    }

这样的使用方式很不方便，需要两个变量来描述结果。这种场景下应该使用c++17中的std::optional。我们用std::optional改写上面这个例子：

    //div_int可以通过optional优化：optional中，结果是否有效和结果都保存在其中
    std::optional<int> div_int(int a, int b) {
        if (b != 0) {
            return std::make_optional<int>(a / b);
        }
        return {};
    }

    TEST_F(optional) {
        auto ret = div_int(2, 1);
        ASSERT(ret);
        ASSERT_EQ(2, ret.value()); // 如果ret为true, 直接从ret中获取结果

        auto ret2 = div_int(2, 0);
        ASSERT(!ret2); // 结果无效

        // 如果ret2为false，获取访问value将会 抛出异常
        try {
            ret2.value();
        } catch (std::exception e) {
            std::cout << e.what() << std::endl;
        }
    }

如果开发项目中没有支持到c++17可以用boost库中的optional。
