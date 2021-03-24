gcc/g++ 编译选项 march 引入的问题

问题说明：在core-i5主机上编译程序，并打包，放到 core-i3 的设备上出现段错误：
"xxx received signal SIGILL, Illegal instruction"

经查，是因为在编译时指定了 -march=native 选项，该选项使得编译器在生成目标文件时，针对当前编译主机（core-i5）进行了优化，导致在 core-i3 上无法正常执行。（前提：i5 和 i3 的系统版本、编译器版本、依赖库版本均完全相同）

march、mtune选项说明：
1、-march=cpu-type
优化选项。指定目标架构的名字，以及（可选的）一个或多个功能修饰符。 此选项的格式为:
-march = arch {+ [no] feature} *

gcc/g++在编译时，会生成针对目标架构优化的目标代码。

注意： -march=navite navite表示允许编译器自动探测目标架构（即：编译主机）并生成针对目标架构优化的目标代码。

例如：

-march=i686
-march=prescott
-march=armv8-a
-march=pentium4

2、-mtune=cpu-type
优化选项。指定目标处理器的名字。与march选项功能类似，但相对于march而言，mtune是一种"松约束"。mtune可以提供后向兼容性，即：mtune=pentium-nmx编译出来的程序，在pentium4处理器上也可以运行。
-mtune=native （与 -march=native 类似）

-mtune 允许值包括：native，generic, cortex-a53, cortex-a57, cortex-a72, exynos-m1, thunderx, xgene1 等

例如：-march=i686 -mtune=pentium4 编译出来的程序，是为奔腾4处理器优化过的，但是在任何i686上都可以运行。

若指定了 -march 而未指定 -mtune 或 -mcpu，则调整代码以确保在实现目标体系结构的一系列目标处理器上执行良好。

march、mtune选项类型
针对 march、mtune，可使用如下指令查看执行了哪些优化操作：
gcc -Q --help=target -march=native [xxx].c
