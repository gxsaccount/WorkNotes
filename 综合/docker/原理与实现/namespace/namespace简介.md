https://ty-chen.github.io/linux-kernel-docker/    
https://blog.csdn.net/tdaajames/article/details/107520153
# NameSpace #  
namespace是实现“看起来”隔离的关键技术，其作用主要是**修改进程的视图**，使其看起来仿佛是一个新的操作系统进程树。  
docker使用namespace通常可以通过命令行或者程序调用的方式执行。对应到容器技术，为了隔离不同类型的资源，Linux 内核里面实现了以下几种不同类型的 namespace。  

* UTS，对应的宏为 CLONE_NEWUTS，表示不同的 namespace 可以配置不同的 hostname。
* User，对应的宏为 CLONE_NEWUSER，表示不同的 namespace 可以配置不同的用户和组。
* Mount，对应的宏为 CLONE_NEWNS，表示不同的 namespace 的文件系统挂载点是隔离的
* PID，对应的宏为 CLONE_NEWPID，表示不同的 namespace 有完全独立的 pid，也即一个 namespace 的进程和另一个 namespace 的进程，pid 可以是一样的，但是代表不同的进程。
* Network，对应的宏为 CLONE_NEWNET，表示不同的 namespace 有独立的网络协议栈。
## 命令行 ##  
操作 namespace 的常用指令 nsenter，可以用来运行一个进程，进入指定的 namespace。  
另一个常用指令是unshare，可以用于离开当前的namespace、创建并加入新的namespacce，然后执行参数中指定的命令。  

    # nsenter --target 58212 --mount --uts --ipc --net --pid -- env --ignore-environment -- /bin/bash
    # unshare --mount --ipc --pid --net --mount-proc=/proc --fork /bin/bash
## 系统调用 ##  
常用的系统调用函数包括clone()，setns()和unshare()，clone()是创建新的进程，通过标记位的形式将其加入新的namespace，setns()是将当前进程加入到已有的namespace之中。  
unshare()则是退出当前namespace并加入到创建的新namespace之中。  

    int clone(int (*fn)(void *), void *child_stack, int flags, void *arg);
    int setns(int fd, int nstype);
    int unshare(int flags);
下面是一个实际使用clone()创建新的进程并将该进程置于新的namespace的例子

    #define _GNU_SOURCE
    #include <sys/wait.h>
    #include <sys/utsname.h>
    #include <sched.h>
    #include <string.h>
    #include <stdio.h>
    #include <stdlib.h>
    #include <unistd.h>
    #define STACK_SIZE (1024 * 1024)

    static int childFunc(void *arg)
    {
        printf("In child process.\n");
        execlp("bash", "bash", (char *) NULL);
        return 0;
    }

    int main(int argc, char *argv[])
    {
        char *stack;
        char *stackTop;
        pid_t pid;

        stack = malloc(STACK_SIZE);
        if (stack == NULL)
        {
            perror("malloc"); 
            exit(1);
        }
        stackTop = stack + STACK_SIZE;

        pid = clone(childFunc, stackTop, CLONE_NEWNS|CLONE_NEWPID|CLONE_NEWNET|SIGCHLD, NULL);  //关键生效函数再此处！！！
        if (pid == -1)
        {
            perror("clone"); 
            exit(1);
        }
        printf("clone() returned %ld\n", (long) pid);

        sleep(1);

        if (waitpid(pid, NULL, 0) == -1)
        {
            perror("waitpid"); 
            exit(1);
        }
        printf("child has terminated\n");
        exit(0);
    }
执行之前，可以通过echo看到进程号，而运行后，再次echo会发现进程号已经变成了1，即通过namespace伪装成了1号进程。  


**clone参数解释**    
        CLONE_NEWNS
        CLONE_NEWPID
        CLONE_NEWNET
        SIGCHLD
## 源码实现 ##  
namespace的结构体定义于task_struct中的nsproxy，在创建进程时，**调用链执行到copy_process()时，会执行copy_namesapces()进行复制和设置。**  

    struct task_struct {
    ......
      /* Namespaces: */
      struct nsproxy      *nsproxy;
    ......
    }

    /*
     * A structure to contain pointers to all per-process
     * namespaces - fs (mount), uts, network, sysvipc, etc.
     *
     * The pid namespace is an exception -- it's accessed using
     * task_active_pid_ns.  The pid namespace here is the
     * namespace that children will use.
     */
    struct nsproxy {
      atomic_t count;
      struct uts_namespace *uts_ns;
      struct ipc_namespace *ipc_ns;
      struct mnt_namespace *mnt_ns;
      struct pid_namespace *pid_ns_for_children;
      struct net        *net_ns;
      struct cgroup_namespace *cgroup_ns;
    };
copy_namespace()源码如下，可见其中如果没有CLONE_NEWNS | CLONE_NEWUTS | CLONE_NEWIPC | CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWCGROUP，就返回原来的 namespace，调用 get_nsproxy，否则调用create_new_namespace()创建新的名字空间。

    /*
     * called from clone.  This now handles copy for nsproxy and all
     * namespaces therein.
     */
    int copy_namespaces(unsigned long flags, struct task_struct *tsk)
    {
      struct nsproxy *old_ns = tsk->nsproxy;
      struct user_namespace *user_ns = task_cred_xxx(tsk, user_ns);
      struct nsproxy *new_ns;

      if (likely(!(flags & (CLONE_NEWNS | CLONE_NEWUTS | CLONE_NEWIPC |
                CLONE_NEWPID | CLONE_NEWNET |
                CLONE_NEWCGROUP)))) {
        get_nsproxy(old_ns);
        return 0;
      }

      if (!ns_capable(user_ns, CAP_SYS_ADMIN))
        return -EPERM;
    ......
      new_ns = create_new_namespaces(flags, tsk, user_ns, tsk->fs);

      tsk->nsproxy = new_ns;
      return 0;
    }
create_new_namespaces()函数进行namespace的复制，根据众多标记位分别判断是复制还是需要重新建立新的相应namesapce。由此就实现了namespace的创建工作。

    /*
     * Create new nsproxy and all of its the associated namespaces.
     * Return the newly created nsproxy.  Do not attach this to the task,
     * leave it to the caller to do proper locking and attach it to task.
     */
    static struct nsproxy *create_new_namespaces(unsigned long flags,
      struct task_struct *tsk, struct user_namespace *user_ns,
      struct fs_struct *new_fs)
    {
      struct nsproxy *new_nsp;

      new_nsp = create_nsproxy();
    ......
      new_nsp->mnt_ns = copy_mnt_ns(flags, tsk->nsproxy->mnt_ns, user_ns, new_fs);
    ......
      new_nsp->uts_ns = copy_utsname(flags, user_ns, tsk->nsproxy->uts_ns);
    ......
      new_nsp->ipc_ns = copy_ipcs(flags, user_ns, tsk->nsproxy->ipc_ns);
    ......
      new_nsp->pid_ns_for_children =
        copy_pid_ns(flags, user_ns, tsk->nsproxy->pid_ns_for_children);
    ......
      new_nsp->cgroup_ns = copy_cgroup_ns(flags, user_ns,
                  tsk->nsproxy->cgroup_ns);
    ......
      new_nsp->net_ns = copy_net_ns(flags, user_ns, tsk->nsproxy->net_ns);
    ......
      return new_nsp;
    ......
    }
