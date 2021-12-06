查看所有api资源  
kubectl api-resources  
查看api的版本  
kubectl api-versions  
查看api字段(一级、递归)  
kubectl explain <资源名对象名>
kubectl explain <资源名对象名> --recursive   
kubectl explain svc    
kubectl explain svc --recursive   

查看具体字段  
kubectl explain <资源对象名称.api名称>
kubectl explain svc.spec.ports  
