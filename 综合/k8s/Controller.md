 kube-controller-manager 的组件,就是一系列控制器的集合  
 
    cd kubernetes/pkg/controller/ $ 
    ls -d */ 
    deployment/  job/ podautoscaler/ 
    cloud/ disruption/ namespace/ 
    replicaset/ serviceaccount/ volume/ 
    cronjob/ garbagecollector/ nodelifecycle/ ...  
    
    这个目录下面的每一个控制器，都以独有的方式负责某种编排功能。而我们的 Deployment，正是
这些控制器中的一种。它们都遵循 Kubernetes
项目中的一个通用编排模式，即：控制循环（control loop）。  


## 控制循环 ##  
控制循环主要逻辑：  

    for
    {
        实际状态:= 获取集群中对象 X 的实际状态（Actual State） 
        期望状态 : = 获取集群中对象 X 的期望状态（Desired State） 
        if 实际状态 == 期望状态 
            { 什么都不做 }
        else { 执行编排动作，将实际状态调整为期望状态 }
    }
