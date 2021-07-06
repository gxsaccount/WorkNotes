# Timer #  
** Timer **  

  timer := time.NewTimer(3*time.Hour + 36*time.Minute)//timer为×time.Timer类型，到期后向**通道**发送元素值  
  timer.Reset()//重置定时器  
  timer.Stop()//停止定时器  
  timer.C//获得定时器到期的通知，容量总是1  
  
  timer.AfterFunc(到期时间，需要执行函数)//返回新建的定时器，到期时启用一个goroutine执行函数    
  
  ** Ticker **  
  var ticker *time.Ticker = time.NewTicker(time.Second)//停止断续器    
