non-explicit-one-argument ctor
argument指的是实参

    class Fraction
    {
    public:
        Fraction(int num,int den=1)  //此构造函数有两个参数，但只需要一个实参，所以可以做隐式转换
          : m_numerator(num),m_denominator(den)  {  }
        Fraction operator+(const Fraction& f)  {
            return Fraction(......);
        }
    private:
        int m_numerator;
        int m_denominator;
    };
    Fraction f(3,5);
    Fraction d2=f+4;  //调用non-explicit ctor将4转为Fraction(4,1)
                      //然后调用operator+

此时编译器是将其他类型，转化为我们定义的类。
此时要注意调用函数时二义性的问题。
explicit-one-argument ctor
关键字explicit90%用在构造函数这儿，如这个例子

    class Fraction
    {
    public:
        explicit Fraction(int num,int den=1)
          : m_numerator(num), m_denominator(den)  {  }
        operator double() const  {
          return (double)(m_numerator/m_denominator);
        Fraction operator+(const Fraction& f)  {
          return Fraction(......);
        }
    private:
        int m_numerator;
        int m_denominator;
    };

    Fraction f(3,5);

当构造函数前加了explicit就不允许编译器暗度陈仓式的类型转换了。
conversion function，转换函数
