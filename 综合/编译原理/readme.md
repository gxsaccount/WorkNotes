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

1. 扫描器,将逐个字符地读入源代码的文本，识别符号之间的边界，产生一系列标记  

    源语句：height = (width+56) * factor(foo);  
    id:height = ( id:width + int:56 ) * id:factor ( id:foo ) ;

这个阶段符号的意义是不知道的，例如factor和foo是函数还是变量是不知道的

2. parser在语句中查找符合语法的模式匹配，生成AST    

假设有如下语法：  

        1. expr → expr + expr
        2. expr → expr * expr
        3. expr → expr = expr
        4. expr → id ( expr )
        5. expr → ( expr )
        6. expr → id
        7. expr → int

语法的每一行都称为规则，它解释了语言的各个部分是如何构成的  
规则 1-3 表明可以通过用运算符连接两个表达式来形成一个表达式。  
规则 4 描述了一个函数调用。  
规则 5 描述了括号的使用。  
最后，规则 6 和 7 表明标识符和整数是原子表达式。   

解析器在我们的语法中寻找可以被规则左侧替换的标记序列。  
每次应用规则时，解析器都会在树中创建一个节点，并将子表达式连接到抽象语法树 (AST)

AST 显示了每个符号之间的结构关系：对宽度和 56 执行加法，而对因子和 foo 应用函数调用  

Figure 2.3: Example AST  


3. 有了AST后，接着分析程序的语义。semantic routines会遍历AST树，  
这个阶段会做typechecking,会确定每个表达式的类型，并检查与程序其他部分的一致性。  
为了生成IR代码，我们对 AST 进行后序遍历，并为树中的每个节点生成一条 IR 指令。  
典型的 IR 看起来像一种抽象的汇编语言，具有加载/存储指令、算术运算和无限数量的寄存器。  
例如，这是我们示例程序的一个可能的 IR 表示：  


        LOAD $56 -> r1
        LOAD width -> r2
        IADD r1, r2 -> r3
        ARG foo
        CALL factor -> r4
        IMUL r3, r4 -> r5
        STOR r5 -> height

许多优化发生在IR的表达过程中。dead code会被删除；生成的code会简化减少文件体积；common operations are combined   


4. 最后IR会被转化为汇编代码，请注意，汇编指令不一定与 IR 指令一一对应。  

        MOVQ width, %rax # load width into rax
        ADDQ $56, %rax # add 56 to rax
        MOVQ %rax, -8(%rbp) # save sum in temporary
        MOVQ foo, %edi # load foo into arg 0 register
        CALL factor # invoke factor, result in rax
        MOVQ -8(%rbp), %rbx # load sum into rbx
        IMULQ %rbx # multiply rbx by rax
        MOVQ %rax, height # store result into height

其他：  
编译器为了适配不同语言，可以有不同的scanners and parsers,可以生成相同的IR  
不同的优化器都可以应用在IR上，可以随时开启和禁用  
编译器可以包含多个代码生成器，因此相同的 IR可以在不同微处理器上生成对应的代码。  


2.4 Exercises
1. Determine how to invoke the preprocessor, compiler, assembler, and
linker manually in your local computing environment. Compile a
small complete program that computes a simple expression, and examine the output at each stage. Are you able to follow the flow of
the program in each form?
2. Determine how to change the optimization level for your local compiler. Find a non-trivial source program and compile it at multiple
levels of optimization. How does the compile time, program size,
and run time vary with optimization levels?
3. Search the internet for the formal grammars for three languages that
you are familiar with, such as C++, Ruby, and Rust. Compare them
side by side. Which language is inherently more complex? Do they
share any common structures?




# scanning #  
## token的类型 ##  

Keywords：while ，true 等  
Identifiers：变量、函数、类等的名字    
Numbers：  integers, float, fractions等
Strings：char序列   
Comments/whitespace：语言的format，甚至可以影响python的语义  

## 自制的scanner ##  

        token_t scan_token(FILE* fp) {
            int c = fgetc(fp);
            if (c == ’ * ’) {
                return TOKEN_MULTIPLY;
            }
            else if (c == ’!’) {
                char d = fgetc(fp);
                if (d == ’ = ’) {
                    return TOKEN_NOT_EQUAL;
                }
                else {
                    ungetc(d, fp);
                    return TOKEN_NOT;
                }
            }
            else if (isalpha(c)) {
                do {
                    char d = fgetc(fp);
                } while (isalnum(d));
                ungetc(d, fp);
                return TOKEN_IDENTIFIER;
            }
            else if (. . .) {
                . . .
            }
        }


## 正则表达式regular expressions ##  

我们可以使用regular expressions（RE）来匹配表达式。  

## 有限自动机finite automata ##  

Every RE can be written as an FA  


