 ## 声明式API ##
 **所谓“声明式”,指的就是我只需要提交一个定义好的 API 对象来“声明”,我所期望的状态是什么样子**  
 “声明式 API”允许有多个 API 写端,以**PATCH**的方式对 API 对象进行修改,而无需关心本地原始 YAML 文件的内容  
 Kubernetes 项目才可以基于对 API 对象的增、删、改、查，在完全无需外界干预的情况下,完成对“实际状态”和“期望状态”的调谐（Reconcile）过程  
 声明式 API,才是 Kubernetes 项目编排能力“赖以生存”的核心所在  
 
 ### kubectl apply ###   
 想要执行容器的更新操作时  
 **命名式做法**：  
     Docker Swarm：  
     $ docker service create --name nginx --replicas 2 nginx  //创建了这两个容器  
     $ docker service update --image nginx:1.7.9 nginx  //“滚动更新”为了一个新的镜像。
     


     本地编写一个 Deployment 的 YAML 文件,nginx.yaml   
     $ kubectl create -f nginx.yaml //创建原始控制器     
     修改nginx.yaml  
     $ kubectl replace -f nginx.yaml  //替换原始控制器  
 
 **声明式做法**  
     
     本地编写一个 Deployment 的 YAML 文件,nginx.yaml   
     $ kubectl apply -f nginx.yaml  //创建原始控制器     
     修改nginx.yaml  
     $ kubectl apply -f nginx.yaml    //patch原始控制器 
     
      kubectl set image 和 kubectl edit 命令，来直接修改 Kubernetes 里的API 对象   
      
      
 用kubectl apply 命令来使用声明式api  
*。  

**声明式vs命名式**    
 kubectl replace 的执行过程，是使用**新的 YAML 文件中的 API
对象，替换原有的 API 对象**；而 kubectl apply，则是执行了一个对原有 API 对象的 **PATCH 操
作**
更进一步地，这意味着 kube-apiserver 在响应命令式请求（比如，kubectl replace）的时候，
**一次只能处理一个写请求，否则会有产生冲突的可能**。而对于声明式请求（比如，kubectl
apply），**一次能处理多个写操作，并且具备 Merge 能力**。  

由于要照顾到这样的 API 设计，做同样一
件事情，Kubernetes 需要的步骤往往要比其他项目多不少。
 
## AdmissionControl机制 ##  
     在K8S中 当一个Pod或者任何一个API对象提交给APIServer之后 总需要做一些
     初始化的工作 比如在自动为Pod添加上某些标签
     这些功能的实现依赖于一组Admission Controller来实现 可以选择性的编译到
     APIServer中 在API对象创建之后会被立即调用
     需要重新编译自己的APIServer添加自己的规则 比较麻烦

## 热插拔Admission机制(Dynamic Admission)##  
### Istio实现机制
        编写一个用来为所有Pod自动注入自己定义的容器的Initializer
        这个Initializer的定义会以ConfigMap的方式进行保存在集群中
        在Initializer更新用户的Pod对象的时候，必须使用PATCH API来完成
        Istio将一个编写好Initializer做为一个Pod运行在k8s集群中
        在Pod YAML文件提交给K8S之后 在创建好的Pod的API对象上自动添加Envoy容器配置

### Initializer初始化器介绍

      Initializer可以是以一个Pod的形式运行在集群当中
      Initializer就是初始化器的意思，就是在任何一个API对象刚刚创建成功后马上调用初始化器给这个对象添加一些自定义的属性
      Initializer 要做的工作,就是把这部分单独定义相关的字段,自动添加到用户提交的Pod的API对象里.可是,用户提交的 Pod 里本来就有containers字段和volumes字段
      所以Kubernetes 在处理这样的更新请求时,就必须使用类似于git merge 这样的操作,才能将这两部分内容合并在一起 最后按照合并后的结果创建容器和挂载卷等
      Initializer在更新用户pod对象的时候 必须使用PATCH API来完成，而PATCH API正是声明式API的最主要的能力
      k8s能够对API对象进行在线更新的能力

   **Initializer逻辑流程**  
       1.首先从ConfigMap中拿到相关数据创建一个空的Pod对象
       2.使用新旧两个Pod对象做为参数调用k8s中TwoWayMergePatch返回patch数据
       3.通过client发起PATCH请求更新原来的Pod API对象,此时Pod还只是个API对象 没有被真正的创建出来

       4.根据Merge后的Pod对象定义 创建出Pod

    API对象都有revision所以apiserver处理merge的流程跟git Server是一样的
    Initializer和Preset都能注入Pod配置
       preset相当于initializer的子集,比较适合在发布流程里处理比较简单的情况  initializer是要开发代码
       Initializer与新的pod在git merge冲突时就不会出入成功
    kubectl apply是通过mvcc实现的并发写

   **envoy和nginx比的优点**   
      envoy的设计支持热更新和热重启很适合声明式规则的开发范式
      envoy提供了api形式的配置入口,更方便做流量治理
      envoy编程友好的api,方便容器化,配置方便
      nginx的reload需要把worker进程退出比较面向命令

   initializer步骤发生在Pod创建之前
      initializer发生在admission阶段,这个阶段完成后pod才会创建出来.并不是先创建好原始Pod然后再把initializer里面对原始Pod的修改进行滚动更新   
      
      
## 声明式API设计
      API对象在Etcd里的完整路径由Group/Version/Resource组成      
      同一种API对象可以有多个Version k8s进行API版本化的重要手段
     1.首先匹配API对象的组
        Pod  Node等核心API对象是不需要Group的 它们的Group是"" 直接从/api开始查找
     2.根据完整路径找到k8s的类型定义后使用用户提交的YAML文件中的字段创建一个实例
        在创建实例的过程中会进行一个Convert操作   把用户提交的YAML文件转成一个super version对象 
        它是API资源类型所有版本的字段全集    方便用户提交不同API版本的YAML
     3.进行API对象的Initializer操作和Validation操作
        validation操作验证对象中各个字段的合法性  验证后保存到Registry数据结构中  一个API对象的定义能在Registry里能查到 那么它就是一个有效的k8s API对象
     4.把super version对象转换成用户提交版本的对象  序列化后保存到etcd中
