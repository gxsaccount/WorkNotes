# 编译工具链 #  
Figure 2.1: A Typical Compiler Toolchain  
## preprocessor、cpp ##   
处理#开头的语句，生成源码  
## compiler、ccl ##  
对源码进行扫面和解析，进行typechecking，semantic routines, 优化，生成汇编代码
## assembler、as ##  
将汇编代码生成object code（机器指令生成，相比于可执行文件，此时变量和函数的虚拟地址还未分配）  
## linker、ld ##  
将多个object code合并成一个可执行文件（分配好各个符号的虚拟地址）  

# 编译器 #  
Figure 2.2: The Stages of a Unix Compiler  
## scanner ##  
扫描源代码，将单个字符组合成完整的tokens，
## Parser ##  
将tokens组合成语句和表达式（statements and expressions），生成抽象语法树abstract syntax tree (AST)  
## Semantic routines ##    
从AST和语法和元素之间关系，获得额外的语义（x的类型是float，会使得x+10的结果是一个float）。  
Semantic routines将AST转化为中间表示（intermediate representation，IR），是适合详细分析的汇编代码的简化形式    
## optimizers ##   
多个优化器应用于IR结果，优化程序的大小，性能。因为他们输入是IR格式和输出都是IR格式，所以优化器的顺序可以是任意的且独立的  

## code generator ##  
最后，代码生成器使用优化的 IR 并将其转换为具体的汇编语言程序。通常，因为寄存器数量有限代码生成器必须执行**寄存器分配**，以及指令选择和排序，以便以最有效的形式对汇编指令进行排序  

## Example ## 

源语句：height = (width+56) * factor(foo);  
id:height = ( id:width + int:56 ) * id:factor ( id:foo ) ;

假设有如下语法：  
1. expr → expr + expr
2. expr → expr * expr
3. expr → expr = expr
4. expr → id ( expr )
5. expr → ( expr )
6. expr → id
7. expr → int

语法的每一行都称为规则，它解释了语言的各个部分是如何构成的  
语法的每一行都称为规则，并解释了语言的各个部分是如何构造的。  
规则 1-3 表明可以通过用运算符连接两个表达式来形成一个表达式。  
规则 4 描述了一个函数调用。  
规则 5 描述了括号的使用。  
最后，规则 6 和 7 表明标识符和整数是原子表达式。   




Figure 2.3: Example AST  

