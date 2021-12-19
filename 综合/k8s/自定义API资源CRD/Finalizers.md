https://kubernetes.io/zh/docs/concepts/overview/working-with-objects/finalizers/  

Finalizers
Finalizer 是带有命名空间的键，告诉 Kubernetes 等到特定的条件被满足后， 再完全删除被标记为删除的资源。 Finalizer 提醒控制器清理被删除的对象拥有的资源。

当你告诉 Kubernetes 删除一个指定了 Finalizer 的对象时， Kubernetes API 会将该对象标记为删除，使其进入只读状态。 此时控制平面或其他组件会采取 Finalizer 所定义的行动， 而目标对象仍然处于终止中（Terminating）的状态。 这些行动完成后，控制器会删除目标对象相关的 Finalizer。 当 metadata.finalizers 字段为空时，Kubernetes 认为删除已完成。

你可以使用 Finalizer 控制资源的垃圾收集。 例如，你可以定义一个 Finalizer，在删除目标资源前清理相关资源或基础设施。

你可以通过使用 Finalizers 提醒控制器 在删除目标资源前执行特定的清理任务， 来控制资源的垃圾收集。

Finalizers 通常不指定要执行的代码。 相反，它们通常是特定资源上的键的列表，类似于注解。 Kubernetes 自动指定了一些 Finalizers，但你也可以指定你自己的。

Finalizers 如何工作 
当你使用清单文件创建资源时，你可以在 metadata.finalizers 字段指定 Finalizers。 当你试图删除该资源时，管理该资源的控制器会注意到 finalizers 字段中的值， 并进行以下操作：

修改对象，将你开始执行删除的时间添加到 metadata.deletionTimestamp 字段。
将该对象标记为只读，直到其 metadata.finalizers 字段为空。
然后，控制器试图满足资源的 Finalizers 的条件。 每当一个 Finalizer 的条件被满足时，控制器就会从资源的 finalizers 字段中删除该键。 当该字段为空时，垃圾收集继续进行。 你也可以使用 Finalizers 来阻止删除未被管理的资源。

一个常见的 Finalizer 的例子是 kubernetes.io/pv-protection， 它用来防止意外删除 PersistentVolume 对象。 当一个 PersistentVolume 对象被 Pod 使用时， Kubernetes 会添加 pv-protection Finalizer。 如果你试图删除 PersistentVolume，它将进入 Terminating 状态， 但是控制器因为该 Finalizer 存在而无法删除该资源。 当 Pod 停止使用 PersistentVolume 时， Kubernetes 清除 pv-protection Finalizer，控制器就会删除该卷。

