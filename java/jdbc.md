## JDBC常见接口和类介绍 ##  
**DriverManagar**：用于管理JDBC驱动的服务类。  
主要接口：  
public static synchronized getConnection(String url,String user,String password)  
**Connection**:数据库连接对象。每个Connection代表一个物理连接会话。  
主要接口：  
返回用于执行的SQL语句的Statement对象：  
Statement createStatement()  
PreparedStatement prepareStatement(String sql):将sql提交到数据库预编译  
CallableStatement prepareCall(String sql):返回CallableStatement用于调用存储过程。  
控制事务：  
1.创建保存点：  
Savepoint setSavepoint():  
Savepoint setSavepoint(String name):  
2.设置事务隔离级别：  
void setTransationIsolation(int level):  
3.回滚事务  
void rollback():  
void rollback(Savepoint savepoint):将事务回滚到指定的保存点  
4.关闭自动提交，打开事务  
void setAutoCommit(bollean autoCommit)  
void commit()    
**Statement**：用于执行SQL语句的工具接口：    
ResultSet executeQuery(String sql)  
int executeUpdate(String sql)  
boolean execute(String sql):可以执行任何sql语句，若执行第一个结果为ResultSet，返回true，否则false
**PreparedStatement**预编译的sql对象,继承于Statement接口  
每次只改变SQL命令参数，避免数据库每次都需要编译，性能更好。  
void setXxx(int parameterIndex,Xxx value)  
ResultSet executeQuery()    
int executeUpdate()    
boolean execute()  
**ResultSet**结果集对象  
close()
absolute()：i移动到第i行，-i移动到倒数第i行
beforeFirst()：相当于迭代器的开始。
first()
previous()
next()
last()
afterLast():将Statement指针定位到最后一行之后


JDBC编程步骤
1.加载数据库驱动
Class.forName(driverClass)//如Class.forName("com.mysql.Driver");
2.通过DriverMangaer获取数据库连接
DriverMangaer.getConnection(String url,String user,String pass)
3.通过Connection创建Statement对象
4.使用Statement对象执行SQL语句
5.操作结果集
6.回收数据库资源

使用连接池管理连接  
数据库的连接建立和关闭很耗时间，当应用程序启动时，系统主动建立足够的数据库连接，并组成一个连接池。javax.sql.DataSource
