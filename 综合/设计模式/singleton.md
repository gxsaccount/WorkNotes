class Singleton_Lazy
{
private:
	Singleton_Lazy()
	{
		cout << "我是懒汉式,在别人需要我的时候，我才现身。" << endl;
	}
	static Singleton_Lazy* singleton;
public:
	static Singleton_Lazy* getInstance()
	{
 
		if (NULL == singleton)
		{
			
			mu.lock();//关闭锁
			if (NULL == singleton)
			{
				singleton = new Singleton_Lazy;
			}
			mu.unlock();//打开锁
		}
		return singleton;
	}
};
Singleton_Lazy* Singleton_Lazy::singleton = NULL;



class Singleton_Hungry
{
private:
	Singleton_Hungry()
	{
		cout << "我是饿汉式，在程序加载时，我就已经存在了。" << endl;
	}
	static Singleton_Hungry* singleton;
public:
	static Singleton_Hungry* getInstace()
	{
		return singleton;
	}
 
};
//静态属性类外初始化
Singleton_Hungry* Singleton_Hungry::singleton = new Singleton_Hungry;
