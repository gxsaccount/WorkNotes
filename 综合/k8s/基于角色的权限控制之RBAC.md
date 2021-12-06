# 序 #  
Kubernetes 中所有的 API 对象，都保存在 Etcd 里。可是，对这些 API 对象的操
作，却一定都是通过访问 kube-apiserver 实现的。其中一个非常重要的原因，就是你需要
APIServer 来帮助你做授权工作。  
而在 Kubernetes 项目中，负责完成授权（Authorization）工作的机制，就是 RBAC：基于角
色的访问控制（Role-Based Access Control）。   

RBAC核心：  

1. Role：角色，它其实是一组规则，定义了一组对 Kubernetes API 对象的操作权限。
2. Subject：被作用者，既可以是“人”，也可以是“机器”，也可以使你在 Kubernetes 里
定义的“用户”。
3. RoleBinding：定义了“被作用者”和“角色”的绑定关系。  

# Role和RoleBinding #
## Role ##   
Role 本身就是一个 Kubernetes 的 API 对象，是一个namespace对象，是 PolicyRule 分组，可以RoleBinding 作为一个单元引用。     
通过kubectl explain roles --recursive查看解释      

    KIND:     Role
    VERSION:  rbac.authorization.k8s.io/v1
    DESCRIPTION:
         Role is a namespaced, logical grouping of PolicyRules that can be
         referenced as a unit by a RoleBinding.
    FIELDS:
       apiVersion   <string>
       kind <string>
       metadata     <Object>
          annotations       <map[string]string>
          clusterName       <string>
          creationTimestamp <string>
          deletionGracePeriodSeconds        <integer>
          deletionTimestamp <string>
          finalizers        <[]string>
          generateName      <string>
          generation        <integer>
          labels    <map[string]string>
          managedFields     <[]Object>
             apiVersion     <string>
             fieldsType     <string>
             fieldsV1       <map[string]>
             manager        <string>
             operation      <string>
             time   <string>
          name      <string>
          namespace <string>
          ownerReferences   <[]Object>
             apiVersion     <string>
             blockOwnerDeletion     <boolean>
             controller     <boolean>
             kind   <string>
             name   <string>
             uid    <string>
          resourceVersion   <string>
          selfLink  <string>
          uid       <string>
       rules        <[]Object>
          apiGroups <[]string>
          nonResourceURLs   <[]string>
          resourceNames     <[]string>
          resources <[]string>
          verbs     <[]string>
  
  实例  
    
    kind: Role
    apiVersion: rbac.authorization.k8s.io/v1
    metadata:
      namespace: mynamespace
      name: example-role
    rules:
    - apiGroups: [""]  # "" indicates the core API group
      resources: ["pods"]
      verbs: ["get", "watch", "list"]  

这个 Role 对象指定了它能产生作用的 Namepace 是：mynamespace。
Namespace 是 Kubernetes 项目里的一个逻辑管理单位。不同 Namespace 的 API 对象，在
通过 kubectl 命令进行操作的时候，是互相隔离开的。   

这个 Role 对象的 rules 字段，就是它所定义的权限规则。在上面的例子里，这条规则的
含义就是：允许“被作用者”，对 mynamespace 下面的 Pod 对象，进行 GET、WATCH 和
LIST 操作。  


 ## RoleBinding ##  
 RoleBinding也是一个api对象，是一个namespace对象。RoleBinding 对象里定义了一个 subjects 字段，即“被作用者”，  
 通过roleRef 字段，RoleBinding 对象可以通过名字来引用我们前面定义的 Role 对象（example-role），从而定义了“被作用者
（Subject）”和“角色（Role）”之间的绑定关系。  
 » sudo kubectl explain RoleBinding --recursive  

    KIND:     RoleBinding
    VERSION:  rbac.authorization.k8s.io/v1

    DESCRIPTION:
         RoleBinding references a role, but does not contain it. It can reference a
         Role in the same namespace or a ClusterRole in the global namespace. It
         adds who information via Subjects and namespace information by which
         namespace it exists in. RoleBindings in a given namespace only have effect
         in that namespace.

    FIELDS:
       apiVersion   <string>
       kind <string>
       metadata     <Object>
          annotations       <map[string]string>
          clusterName       <string>
          creationTimestamp <string>
          deletionGracePeriodSeconds        <integer>
          deletionTimestamp <string>
          finalizers        <[]string>
          generateName      <string>
          generation        <integer>
          labels    <map[string]string>
          managedFields     <[]Object>
             apiVersion     <string>
             fieldsType     <string>
             fieldsV1       <map[string]>
             manager        <string>
             operation      <string>
             time   <string>
          name      <string>
          namespace <string>
          ownerReferences   <[]Object>
             apiVersion     <string>
             blockOwnerDeletion     <boolean>
             controller     <boolean>
             kind   <string>
             name   <string>
             uid    <string>
          resourceVersion   <string>
          selfLink  <string>
          uid       <string>
       roleRef      <Object>
          apiGroup  <string>
          kind      <string>
            name      <string>
       subjects     <[]Object>
          apiGroup  <string>
          kind      <string>
          name      <string>
          namespace <string>
          
实例：  
    kind: RoleBinding
    apiVersion: rbac.authorization.k8s.io/v1
    metadata:
      name: example-rolebinding
      namespace: mynamespace
    subjects:
    - kind: User
      name: example-user
      apiGroup: rbac.authorization.k8s.io
    roleRef:
      kind: Role
      name: example-role
      apiGroup: rbac.authorization.k8s.io
这个 RoleBinding 对象里定义了一个 subjects 字段，即“被作用者”。它的类型是
User，即 Kubernetes 里的用户。这个用户的名字是 example-user。   

实际上，Kubernetes 里的“User”，也就是“用户”，只是一个授权系统里的逻辑概念。它需
要通过外部认证服务，比如 Keystone，来提供。或者，你也可以直接给 APIServer 指定一个用
户名、密码文件。那么 Kubernetes 的授权系统，就能够从这个文件里找到对应的“用户”了。
当然，在大多数私有的使用环境中，我们只要使用 Kubernetes 提供的内置“用户”，就足够
了。  


**Role 和 RoleBinding 对象都是 Namespaced 对象（Namespaced
Object），它们对权限的限制规则仅在它们自己的 Namespace 内有效，roleRef 也只能引用当
前 Namespace 里的 Role 对象。**  

# ClusterRole 和 ClusterRoleBinding #  
，对于非 Namespaced（Non-namespaced）对象（比如：Node），或者，某一个
Role 想要作用于所有的 Namespace 的时候，必须要使用 ClusterRole 和 ClusterRoleBinding  
这两个 API 对
象的用法跟 Role 和 RoleBinding 完全一样。只不过，它们的定义里，没有了 Namespace 字
段  

# k8s 默认用户介绍#  
Kubernetes 负责管理的“内置用户”，正是我们前面曾经提到过的：
ServiceAccount。   

ServiceAccount 分配权限的过程  
首先，我们要定义一个 ServiceAccount  

    apiVersion: v1
    kind: ServiceAccount
    metadata:
      namespace: mynamespace
      name: example-sa
RoleBinding  

kind: RoleBinding
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: example-rolebinding
  namespace: mynamespace
subjects:
- kind: ServiceAccount
  name: example-sa
  namespace: mynamespace
roleRef:
  kind: Role  
name: example-role
apiGroup: rbac.authorization.k8s.io  

在这个 RoleBinding 对象里，subjects 字段的类型（kind），不再是一个 User，
而是一个名叫 example-sa 的 ServiceAccount。而 roleRef 引用的 Role 对象，依然名叫
example-role，也就是我在这篇文章一开始定义的 Role 对象。   

来查看一下这个 ServiceAccount 的详细信息  

    $ kubectl get sa -n mynamespace -o yaml
    - apiVersion: v1
      kind: ServiceAccount
      metadata:
        creationTimestamp: 2018-09-08T12:59:17Z
        name: example-sa
        namespace: mynamespace
        resourceVersion: "409327"
        ...
      secrets:
      - name: example-sa-token-vmfg6  
      
      
      ，Kubernetes 会为一个 ServiceAccount 自动创建并分配一个 Secret 对象，即：上
述 ServiceAcount 定义里最下面的 secrets 字段。  
这个 Secret，就是这个 ServiceAccount 对应的、用来跟 APIServer 进行交互的授权文件，我
们一般称它为：**Token**。Token 文件的内容一般是证书或者密码，它以一个 Secret 对象的方式
保存在 Etcd 当中。  

