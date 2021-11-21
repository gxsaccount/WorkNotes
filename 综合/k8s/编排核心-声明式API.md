 # 声明式API #  
 ## 定义 ##  
 **所谓“声明式”,指的就是我只需要提交一个定义好的 API 对象来“声明”,我所期望的状态是什么样子**  
 “声明式 API”允许有多个 API 写端,以**PATCH**的方式对 API 对象进行修改,而无需关心本地原始 YAML 文件的内容  
 Kubernetes 项目才可以基于对 API 对象的增、删、改、查，在完全无需外界干预的情况下,完成对“实际状态”和“期望状态”的调谐（Reconcile）过程  
 声明式 API,才是 Kubernetes 项目编排能力“赖以生存”的核心所在  
 
 ## 使用 ##  
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
apply），**一次能处理多个写操作，并且具备 Merge 能力**（类似与git merge）。  

由于要照顾到这样的 API 设计，做同样一
件事情，Kubernetes 需要的步骤往往要比其他项目多不少。

## merge功能实现接口 ##  
Kubernetes 的 API 库，为我们提供了一个方法，使得我们可以直接使用新旧两个 Pod 对象，
生成一个 TwoWayMergePatch：  

  func doSomething(pod) { 
   cm := client.Get(ConfigMap, "envoy-initializer")
   newPod := Pod{}
   newPod.Spec.Containers = cm.Containers
   newPod.Spec.Volumes = cm.Volumes
   // 生成 patch 数据
   patchBytes := strategicpatch.CreateTwoWayMergePatch(pod, newPod)
   // 发起 PATCH 请求，修改这个 pod 对象
   client.Patch(pod.Name, patchBytes)
  }  
  
# merge的重要性 #  
声明式api的merge功能在Initializer为pod初始化阶段自动添加配置（及热插拔Admission机制(Dynamic Admission)）时非常有用   

## AdmissionControl机制 ##  
在K8S中 当一个Pod或者任何一个API对象提交给APIServer之后 总需要做一些**初始化的工作** 比如在自动为Pod添加上某些标签。  
这些功能的实现依赖于一组Admission Controller来实现 可以选择性的编译到APIServer中 在API对象创建之后会被立即调用  
但是这样需要重新编译自己的APIServer添加自己的规则，比较麻烦  

## 热插拔Admission机制(Dynamic Admission)/Initializer ##  
### Istio实现机制
编写一个用来为所有Pod自动注入自己定义的容器的**Initializer**   
**Istio将一个编写好Initializer做为一个Pod运行在k8s集群中**     
这个Initializer的定义会以**ConfigMap**的方式进行保存在集群中  
在Initializer更新用户的Pod对象的时候，必须使用**PATCH API**来完成   
在Pod YAML文件提交给K8S之后 在创建好的Pod的API对象上自动添加**Envoy容器配置**（一个高性能c++网络代理）   

       
### Initializer控制器介绍  
Initializer可以是以一个Pod的形式运行在集群当中  
Initializer就是初始化器的意思，就是在任何一个API对象刚刚创建成功后马上调用初始化器给这个对象添加一些自定义的属性  

**envoy-initializer**是Envoy 容器本身的定义的configmap  

      apiVersion: v1
      kind: ConfigMap
      metadata:
         name: envoy-initializer
      data:
         config: |
             containers:
                  - name: envoy
                  image: lyft/envoy:845747db88f102c0fd262ab234308e9e22f693a1
                  command: ["/usr/local/bin/envoy"]
                  args:
                     - "--concurrency 4"
                     - "--config-path /etc/envoy/envoy.json"
                     - "--mode serve"
             ports:
                     - containerPort: 80
                     protocol: TCP
             resources:
                    limits:
                         cpu: "1000m"
                         memory: "512Mi"
                    requests:
                         cpu: "100m"
                         memory: "64Mi"
             volumeMounts:
                         - name: envoy-conf
                          mountPath: /etc/envoy
             volumes:
             - name: envoy-conf
             configMap:
             name: envoy  
 
这个 ConfigMap 的 data 部分，正是一个 Pod 对象的一部分定义。  
**Initializer为什么需要声明式api**  
Initializer 要做的工作,就是把这部分单独定义相关的字段,自动添加到用户提交的Pod的API对象里.可是,用户提交的 Pod 里本来就有containers字段和volumes字段  
所以Kubernetes 在处理这样的更新请求时,就必须使用类似于git merge 这样的操作,才能将这两部分内容合并在一起 最后按照合并后的结果创建容器和挂载卷等  
所以Initializer在更新用户pod对象的时候 必须使用PATCH API来完成，而PATCH API正是声明式API的最主要的能力  
**Initializer在istio的定义**  
Istio 将一个编写好的 Initializer，作为一个 Pod 部署在 Kubernetes 中。这个 Pod 的
定义非常简单，如下所示：  
   apiVersion: v1
   kind: Pod
   metadata:
    labels:
      app: envoy-initializer
    name: envoy-initializer
   spec:
    containers:
    - name: envoy-initializer
      image: envoy-initializer:0.0.1
      imagePullPolicy: Always  
**Initializer的本质和**  
这个 envoy-initializer 使用的 envoy-initializer:0.0.1 镜像，就是一个事先编写好的“**自定义控制器**”（Custom Controller）   
Initializer 的控制器，不断获取到的“实际状态”，就是用户新创建的 Pod。而它的“期望状态”，则是：这个 Pod 里被添加了 Envoy 容器的定义。  

     for {
      // 获取新创建的 Pod
      pod := client.GetLatestPod()
      // Diff 一下，检查是否已经初始化过
      if !isInitialized(pod) {
      // 没有？那就来初始化一下
      doSomething(pod)
      }
     }
**Initializer逻辑流程**  
       1.首先从ConfigMap中拿到相关数据创建一个空的Pod对象
       2.使用新旧两个Pod对象做为参数调用k8s中TwoWayMergePatch返回patch数据
       3.通过client发起PATCH请求更新原来的Pod API对象,此时Pod还只是个API对象 没有被真正的创建出来
       4.根据Merge后的Pod对象定义 创建出Pod

API对象都有revision所以apiserver处理merge的流程跟git Server是一样的
Initializer和Preset的关系：
       Initializer和Preset都能注入Pod配置
       preset相当于initializer的子集,比较适合在发布流程里处理比较简单的情况，initializer是要开发代码
       Initializer与新的pod在git merge冲突时就不会出入成功
kubectl apply是通过mvcc实现的并发写

## 声明式 API 的工作原理 ##  

API对象在Etcd里的完整路径由**Group/Version\/Resource**组成，整个 Kubernetes 里的所有 API 对象，实际上就可以用如下的树形结构表示
出来：      
![image](https://user-images.githubusercontent.com/20179983/142756592-4fe915d8-d3cf-4683-96ee-4c30e07dee9b.png)

    apiVersion: batch/v2alpha1
    kind: CronJob
    ...  
在这个yaml文件中，“CronJob”就是这个 API 对象的资源类型（Resource），“batch”就是它的组（Group），v2alpha1 就是它的版本（Version）  

## Kubernetes 如何对 Resource、Group 和 Version 进行解析 ##  

 **1. 首先匹配API对象**  
* 匹配组  
Pod  Node等核心API对象是不需要Group的 它们的Group是"" 直接从/api开始查找    
而对于 CronJob 等非核心 API 对象来说，Kubernetes 就必须在 /apis 这个层级里查找它对应的 Group，进而根据“batch”这个 Group 的名字，找到 /apis/batch    
这些 API Group 的分类是以对象功能为依据的，比如 Job 和 CronJob 就都属于“batch” （离线业务）这个 Group    
* 匹配对应的vision
然后，Kubernetes 会进一步匹配到 API 对象的版本号。   
**同一种API对象可以有多个Version k8s进行API版本化的重要手段**  
* 匹配资源类型  
 **2. 根据完整路径找到k8s的类型定义后使用用户提交的YAML文件中的字段创建一个实例**  
     ![image](https://user-images.githubusercontent.com/20179983/142756885-f9364dff-4e9d-446e-a1d7-8e80c2a62be5.png)
* 当我们发起了创建 CronJob 的 POST 请求之后，我们编写的 YAML 的信息就被提交给了 APIServer。
* APIServer 的第一个功能，就是过滤这个请求，并完成一些前置性的工作，比如授权、超时处理、审计等。
* 请求会进入 MUX 和 Routes 流程MUX 和Routes 是 APIServer 完成 URL 和 Handler 绑定的场所。而 APIServer 的 Handler 要做的事情，就是按照我刚刚介绍的匹配过程，找到对应的 CronJob 类型定义  
* 根据这个 CronJob 类型定义，使用用户提交的 YAML文件里的字段，创建一个 CronJob 对象。  
    - 在这个过程中，APIServer 会进行一个 Convert 工作，即：把用户提交的 YAML 文件，转换成一个叫作 **Super Version** 的对象，它正是该 API 资源类型所有版本的字段全集。这样用户提交的不同版本的 YAML 文件，就都可以用这个 Super Version 对象来进行处理了。  
    - 接下来，APIServer 会先后进行 Admission() （例如initializer）和 Validation() (检验合法性)操作。  
    - **这个被验证过的 API 对象，都保存在了 APIServer 里一个叫作 Registry 的数据结构中**。也就是说，只要一个 API 对象的定义能在 Registry 里查到，它就是一个有效的 Kubernetes API 对象。  
* APIServer 会把验证过的 API 对象转换成用户最初提交的版本，进行序列化操作，并调用 Etcd 的 API 把它保存起来  




思考题
你是否对 Envoy 项目做过了解？你觉得为什么它能够击败 Nginx 以及 HAProxy 等竞品，成为
Service Mesh 体系的核心？
   **补充envoy和nginx比的优点**   
      envoy的设计支持热更新和热重启很适合声明式规则的开发范式
      envoy提供了api形式的配置入口,更方便做流量治理
      envoy编程友好的api,方便容器化,配置方便
      nginx的reload需要把worker进程退出比较面向命令
