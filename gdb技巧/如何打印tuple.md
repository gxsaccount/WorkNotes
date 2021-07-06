    #include <tuple>
    #include <iostream>

     using namespace std;

     int main() {
         auto t = make_tuple(111, 222);
         cout << std::get<0>(t) << endl
              << std::get<1>(t) << endl;
         return 0;
     }

(gdb) p/r t
$3 = {<std::_Tuple_impl<0ul, int, int>> = {<std::_Tuple_impl<1ul, int>> = {<std::_Head_base<1ul, int, false>> = {
        _M_head_impl = 222}, <No data fields>}, <std::_Head_base<0ul, int, false>> = {_M_head_impl = 111}, <No data fields>}, <No data fields>}
在这里,您可以看到元组的“真实”结构,并直接访问字段：

(gdb) print ((std::_Head_base<1ul, int, false>) t)._M_head_impl
$7 = 222
