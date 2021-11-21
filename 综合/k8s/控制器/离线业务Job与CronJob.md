 # job #  
 ## job的相关介绍 ##  
 Deployment、StatefulSet，以及 DaemonSet都是“在线业务”，及Long Running Task（长作业）。  
 应用一旦运行起来，除非出错或者停止，它的容器进程会一直保持在 Running 状态。    
 
 有一类作业显然不满足这样的条件，这就是“离线业务”，或者叫作 Batch Job（计算业
务）。这种业务在计算完成后就直接退出了。  

举个例子：  

      apiVersion: batch/v1
      kind: Job
      metadata:
       name: pi
      spec:
         template:
         spec:
           containers:
           - name: pi
             image: resouer/ubuntu-bc 
             command: ["sh", "-c", "echo 'scale=10000; 4*a(1)' | bc -l "]
         restartPolicy: Never   //离线计算的 Pod 永远都不应该被重启，否则它们会再重新计算一遍。 
                                //在 Job 对象里只允许被设置为 Never 和 OnFailure；  
                                //而在Deployment 对象里，restartPolicy 则只允许被设置为 Always。  
                                //restartPolicy=OnFailure，那么离线作业失败后，Job Controller 就不会去尝试创建新的 Pod。  
                                //但是，它会不断地尝试重启 Pod 里的容器。这也正好对应了 restartPolicy的含义
       backoffLimit: 4   //重试次数为 4  
                         //Job Controller 重新创建 Pod 的间隔是呈指数增加的，即下一次重新创建 Pod的动作会分别发生在 10 s、20 s、40 s …后
       activeDeadlineSeconds ： 100   //超过100s自动停止，可以不设置  

跟其他控制器不同的是，Job 对象并不要求你定义一个 spec.selector 来描述要控制哪些Pod

      $ kubectl create -f job.yaml   
 
      $ kubectl describe jobs/pi  
      
CronJob是定期产生新的Job，还是定期重启同一个Job任务？  

      Name: pi
      Namespace: default
      Selector: controller-uid=c2db599a-2c9d-11e6-b324-0209dc45a495  
      Labels: controller-uid=c2db599a-2c9d-11e6-b324-0209dc45a495  //保证了 Job 与它所管理的 Pod 之间的匹配关系  
       job-name=pi
      Annotations: <none>
      Parallelism: 1
      Completions: 1
      ..
      Pods Statuses: 0 Running / 1 Succeeded / 0 Failed
      Pod Template:
       Labels: controller-uid=c2db599a-2c9d-11e6-b324-0209dc45a495
       job-name=pi
       Containers:
       ...
       Volumes: <none>
      Events:
       FirstSeen LastSeen Count From SubobjectPath Type Reason 
       --------- -------- ----- ---- ------------- -------- ------ 
       1m 1m 1 {job-controller } Normal SuccessfulCreat 
可见Job 对象在创建后，它的 Pod 模板，被自动加上了一个 controller-uid=< 一
个随机字符串 > 这样的 Label。而这个 Job 对象本身，则被自动加上了这个 Label 对应的
Selector，从而 保证了 Job 与它所管理的 Pod 之间的匹配关系。  
Job Controller 之所以要使用这种携带了 UID 的 Label，就是为了避免不同 Job 对象所管理
的 Pod 发生重合。需要注意的是，这种自动生成的 Label 对用户来说并不友好，所以不太适合
推广到 Deployment 等长作业编排对象上。  



## Job Controller的工作原理##
在 Job 对象中，负责并行控制的参数有两个：  
1. spec.parallelism，它定义的是一个 Job 在任意时间最多可以启动多少个 Pod 同时运行；  
2. spec.completions，它定义的是 Job 至少要完成的 Pod 数目，即 Job 的最小完成数。  

**Job Controller 控制的对象，直接就是 Pod。**  
**其次，Job Controller 在控制循环中进行的调谐（Reconcile）操作，是根据实际在 Running
状态 Pod 的数目、已经成功退出的 Pod 的数目，以及 parallelism、completions 参数的值共
同计算出在这个周期里，应该创建或者删除的 Pod 数目，然后调用 Kubernetes API 来执行这
个操作。**  

**计算方法**  
以创建 Pod 为例。在上面计算 Pi 值的这个例子中，当 Job 一开始创建出来时，实际处于
Running 状态的 Pod 数目 =0，已经成功退出的 Pod 数目 =0，而用户定义的 completions，
也就是最终用户需要的 Pod 数目 =4。
所以，在这个时刻，需要创建的 Pod 数目 = 最终需要的 Pod 数目 - 实际在 Running 状态
Pod 数目 - 已经成功退出的 Pod 数目 = 4 - 0 - 0= 4。也就是说，Job Controller 需要创建 4
个 Pod 来纠正这个不一致状态。
可是，我们又定义了这个 Job 的 parallelism=2。也就是说，我们规定了每次并发创建的 Pod
个数不能超过 2 个。所以，Job Controller 会对前面的计算结果做一个修正，修正后的期望创
建的 Pod 数目应该是：2 个。
这时候，Job Controller 就会并发地向 kube-apiserver 发起两个创建 Pod 的请求。
类似地，如果在这次调谐周期里，Job Controller 发现实际在 Running 状态的 Pod 数目，比
parallelism 还大，那么它就会删除一些 Pod，使两者相等。
综上所述，Job Controller 实际上控制了，作业执行的并行度，以及总共需要完成的任务数这两
个重要参数。而在实际使用时，你需要根据作业的特性，来决定并行度（parallelism）和任务
数（completions）的合理取值。  

## 常用的、使用 Job 对象的方法 ##  
### 外部管理器 +Job 模板 ###  
把 Job 的 YAML 文件定义为一个“模板”，然后用一个外部工具控制
这些“模板”来生成 Job。  

    apiVersion: batch/v1
      kind: Job
      metadata:
       name: process-item-$ITEM
       labels:
       jobgroup: jobexample
      spec:
       template:
       metadata:
       name: jobexample
       labels:
       jobgroup: jobexample
       spec:
       containers:
       - name: c
       image: busybox
       command: ["sh", "-c", "echo Processing item $ITEM && sleep 5"]
       restartPolicy: Never  
  在这个 Job 的 YAML 里，定义了 $ITEM 这样的“变量”。
所以，在控制这种 Job 时，我们只要注意如下两个方面即可：
1. 创建 Job 时，替换掉 $ITEM 这样的变量；
2. 所有来自于同一个模板的 Job，都有一个 jobgroup: jobexample 标签，也就是说这一组
Job 使用这样一个相同的标识。
而做到第一点非常简单。比如，你可以通过这样一句 shell 把 $ITEM 替换掉：   

    $ mkdir ./jobs  
    $ for i in apple banana cherry
    do
     cat job-tmpl.yaml | sed "s/\$ITEM/$i/" > ./jobs/job-$i.yaml
    done  
    $ kubectl create -f ./jobs  
    
 ### 拥有固定任务数目的并行 Job ###  
 这种模式下，我只关心最后是否有指定数目（spec.completions）个任务成功退出。至于执行
时的并行度是多少，我并不关心。
比如，我们这个计算 Pi 值的例子，就是这样一个典型的、拥有固定任务数目
（completions=4）的应用场景。 它的 parallelism 值是 2；或者，你可以干脆不指定
parallelism，直接使用默认的并行度（即：1）。
此外，你还可以使用一个工作队列（Work Queue）进行任务分发。这时，Job 的 YAML 文件
定义如下所示：  

    apiVersion: batch/v1
    kind: Job
    metadata:
     name: job-wq-1
    spec:
     completions: 8
     parallelism: 2
     template:
       metadata:
          name: job-wq-1
       spec:
         containers:
           - name: c
           image: myrepo/job-wq-1
           env:
           - name: BROKER_URL
            value: amqp://guest:guest@rabbitmq-service:5672
           - name: QUEUE
            value: job1
       restartPolicy: OnFailure
 在这个实例中，我选择充当工作队列的是一个运行在 Kubernetes 里的 RabbitMQ。所以，我
们需要在 Pod 模板里定义 BROKER_URL，来作为消费者。
所以，一旦你用 kubectl create 创建了这个 Job，它就会以并发度为 2 的方式，每两个 Pod 一
组，创建出 8 个 Pod。每个 Pod 都会去连接 BROKER_URL，从 RabbitMQ 里读取任务，然后
各自进行处理。这个 Pod 里的执行逻辑，我们可以用这样一段伪代码来表示：   

    /* job-wq-1 的伪代码 */
    queue := newQueue($BROKER_URL, $QUEUE)
    task := queue.Pop()
    process(task)
    exit
    
 每个 Pod 只需要将任务信息读取出来，处理完成，然后退出即可。而作为用户，我
只关心最终一共有 8 个计算任务启动并且退出，只要这个目标达到，我就认为整个 Job 处理完
成了。所以说，这种用法，对应的就是“任务总数固定”的场景。   


### 指定并行度（parallelism），但不设置固定的completions 的值。###  

此时，你就必须自己想办法，来决定什么时候启动新 Pod，什么时候 Job 才算执行完成。在这
种情况下，任务的总数是未知的，所以你不仅需要一个工作队列来负责任务分发，还需要能够判断工作队列已经为空（即：所有的工作已经结束了）。  

Job 的定义基本上没变化，只不过是不再需要定义 completions 的值了而已  

而对应的 Pod 的逻辑会稍微复杂一些，我可以用这样一段伪代码来描述：  

    /* job-wq-2 的伪代码 */
    for !queue.IsEmpty($BROKER_URL, $QUEUE) {
     task := queue.Pop()
     process(task)
    }
    print("Queue empty, exiting")
    exit  

由于任务数目的总数不固定，所以每一个 Pod 必须能够知道，自己什么时候可以退出。比如，
在这个例子中，我简单地以“队列为空”，作为任务全部完成的标志。所以说，这种用法，对应
的是“任务总数不固定”的场景。  

不过，在实际的应用中，你需要处理的条件往往会非常复杂。比如，任务完成后的输出、每个任
务 Pod 之间是不是有资源的竞争和协同等等。  

# CronJob #  
CronJob 描述的，正是定时任务。它的 API 对象，如下所示：  
    
    apiVersion: batch/v1beta1
    kind: CronJob
    metadata:
     name: hello
    spec:
     schedule: "*/1 * * * *"
     jobTemplate:
       spec:
         template:
           spec:
           containers:
           - name: hello
             image: busybox
             args:
             - /bin/sh
             - -c
             - date; echo Hello from the Kubernetes cluster
           restartPolicy: OnFailure  
     
     
 在这个 YAML 文件中，最重要的关键词就是jobTemplate。看到它，你一定恍然大悟，**原来
CronJob 是一个 Job 对象的控制器（Controller）！**     

CronJob 与 Job 的关系，正如同 Deployment 与 Pod 的关系一样。CronJob 是一个专
门用来管理 Job 对象的控制器。只不过，它创建和删除 Job 的依据，是 schedule 字段定义
的、一个标准的Unix Cron格式的表达式。
比如，"*/1 * * * *"。
这个 Cron 表达式里 */1 中的 * 表示从 0 开始，/ 表示“每”，1 表示偏移量。所以，它的意思
就是：从 0 开始，每 1 个时间单位执行一次。
那么，时间单位又是什么呢？
Cron 表达式中的五个部分分别代表：分钟、小时、日、月、星期。
所以，上面这句 Cron 表达式的意思是：从当前开始，每分钟执行一次。
而这里要执行的内容，就是 jobTemplate 定义的 Job 了。   


由于定时任务的特殊性，很可能某个 Job 还没有执行完，另外一个新 Job 就产
生了。这时候，你可以通过 spec.concurrencyPolicy 字段来定义具体的处理策略。比如：
1. concurrencyPolicy=Allow，这也是默认情况，这意味着这些 Job 可以同时存在；
2. concurrencyPolicy=Forbid，这意味着不会创建新的 Pod，该创建周期被跳过；
3. concurrencyPolicy=Replace，这意味着新产生的 Job 会替换旧的、没有执行完的 Job。
而如果某一次 Job 创建失败，这次创建就会被标记为“miss”。当在指定的时间窗口内，miss
的数目达到 100 时，那么 CronJob 会停止再创建这个 Job。
这个时间窗口，可以由 spec.startingDeadlineSeconds 字段指定。比如
startingDeadlineSeconds=200，意味着在过去 200 s 里，如果 miss 的数目达到了 100 次，
那么这个 Job 就不会被创建执行了。   

思考题
根据 Job 控制器的工作原理，如果你定义的 parallelism 比 completions 还大的话，比如：  
 parallelism: 4
 completions: 2  
 那么，这个 Job 最开始创建的时候，会同时启动几个 Pod 呢？原因是什么？  

CronJob是定期产生新的Job，还是定期重启同一个Job任务？  

 
