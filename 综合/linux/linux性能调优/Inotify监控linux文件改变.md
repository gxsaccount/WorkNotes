Inotify 到底是什么？
Inotify 是一种文件变化通知机制，Linux 内核从 2.6.13 开始引入。在 BSD 和 Mac OS 系统中比较有名的是 kqueue ，它可以高效地实时跟踪 Linux 文件系统的变化。近些年来，以 fsnotify 作为后端，几乎所有的主流 Linux 发行版都支持 Inotify 机制。如何知道你的 Linux 内核是否支持 Inotify 机制呢？很简单，执行下面这条命令：

复制代码
 
% grep INOTIFY_USER /boot/config-$(uname -r)
CONFIG_INOTIFY_USER=y
如果输出 (‘CONFIG_INOTIFY_USER=y’)，那么你可以马上享受 Inotify 之旅了。

简单的文件变化通知样例：
好的开始是成功的一半，对于了解 Inotify 机制来说，让我们从使用 inotifywait 程序开始，它包含在 inotify-tools 工具包中。假如我们打算监控 /srv/test 文件夹上的操作，只需执行：

复制代码
 
% inotifywait -rme modify,attrib,move,close_write,create,delete,delete_self /srv/test
Setting up watches.  Beware: since -r was given, this may take a while!
Watches established.
上述任务运行的同时，我们在另一个 shell 里依次执行以下操作：创建文件夹，然后在新文件夹下创建文件，接着删除新创建的文件：

复制代码
 
% mkdir /srv/test/infoq
% echo TODO > /srv/test/infoq/article.txt
% rm /srv/test/infoq/article.txt
在运行 inotifywait 的 shell 中将会打印以下信息：

复制代码
 
/srv/test/ CREATE,ISDIR infoq
/srv/test/infoq/ CREATE article.txt
/srv/test/infoq/ MODIFY article.txt
/srv/test/infoq/ CLOSE_WRITE,CLOSE article.txt
/srv/test/infoq/ DELETE article.txt
显而易见，只要有变化我们就会收到相关的通知。如果想了解关于 Inotify 提供的事件 (如 modify, atrrib 等) 的详细信息，请参考 inotifywatch 的 manpage。实际使用时，如果并不想监控某个大文件夹，那么就可以使用 inotifywait 的 exclude 选项。例如：我们要忽略文件夹 /srv/test/large，那么就可以这样来建立监控:

复制代码
 
% inotifywait --exclude '^/srv/test/(large|ignore)/' -rme modify,attrib,move,close_write,create,delete,delete_self /srv/test
Setting up watches.  Beware: since -r was given, this may take a while!
Watches established.
上面的例子中，在 exclude 选项的匹配串中我们使用了正则表达式，因为我们不想将名称中含有 large 或 ignore 的文件也排除掉。我们可以测试一下：

复制代码
% echo test > /srv/test/action.txt
% echo test > /srv/test/large/no_action.txt
% echo test > /srv/test/ignore/no_action.txt
% echo test > /srv/test/large-name-but-action.txt
这里 inotifywait 应该只会报告’action.txt’和’large-name-but-action.txt’两个文件的变化，而忽略子文件夹’large’和’ignore’下的文件，结果也确实如此；

复制代码
 
/srv/test/ CREATE action.txt
/srv/test/ MODIFY action.txt
/srv/test/ CLOSE_WRITE,CLOSE action.txt
/srv/test/ CREATE large-name-but-action.txt
/srv/test/ MODIFY large-name-but-action.txt
/srv/test/ CLOSE_WRITE,CLOSE large-name-but-action.txt
另外，通过使用 -t 选项我们还可以定义 inotifywait 的监控时间，既可以让它执行一段时间，也可以让它一直运行。 util-linux-ng 的 logger 命令也可以实现此功能，不过得先把相关的消息事件发送到 syslog，然后从 syslog 服务器再分析整合。

Inotifywatch - 使用 inotify 来统计文件系统访问信息
Inotify-tools 中还有一个工具叫 inotifywatch，它会先监听文件系统的消息事件，然后统计每个被监听文件或文件夹的消息事件，之后输出统计信息。比如我们想知道某个文件夹上有那些操作：

复制代码
 
% inotifywatch -v -e access -e modify -t 120 -r ~/InfoQ
Establishing watches...
Setting up watch(es) on /home/mika/InfoQ
OK, /home/mika/InfoQ is now being watched.
Total of 58 watches.
Finished establishing watches, now collecting statistics.
Will listen for events for 120 seconds.
total  modify  filename
2      2       /home/mika/InfoQ/inotify/
很显然，这里我们监控的是~/InfoQ 文件夹，并且可以看到 /home/mika/InfoQ/inotify 上发生了两个事件。方法虽简单，但却很有效。

Inotify 的配置选项
使用 Inotify 时，要特别注意内核中关于它的两个配置。首先 /proc/sys/fs/inotify/max_user_instances 规定了每个用户所能创建的 Inotify 实例的上限；其次 /proc/sys/fs/inotify/max_user_watches 规定了每个 Inotify 实例最多能关联几个监控 (watch)。你可以很容易地试验在运行过程中达到上限，如：

复制代码
 
% inotifywait -r /
Setting up watches.  Beware: since -r was given, this may take a while!
Failed to watch /; upper limit on inotify watches reached!
Please increase the amount of inotify watches allowed per user via `/proc/sys/fs/inotify/max_user_watches'.
如果要改变这些配置，只要向相应的文件写入新值即可，如下所示：

复制代码
 
# cat /proc/sys/fs/inotify/max_user_watches
8192
# echo 16000 > /proc/sys/fs/inotify/max_user_watches
# cat /proc/sys/fs/inotify/max_user_watches
16000
使用 Inotify 的一些工具
近一段时间出现了很多基于 Inotify 的超炫的工具，如 incron ，它是一个类似于 cron 的守护进程 (daemon)，传统的 cron 守护进程都是在规定的某个时间段内执行，而 incron 由于使用了 Inotify，可以由事件触发执行。同时 incron 的安装简单而直观，比如在 debian 上，首先在 /etc/incron.allow 中添加使用 incron 的用户 (debian 默认不允许用户使用 incron，因为如果 incron 使用不慎的话，例如形成死循环，则会导致系统宕机)：

复制代码
 
# echo username > /etc/incron.allow
然后调用”incrontab -e“, 在弹出的编辑器中插入我们自己的规则，例如下面的这条简单的规则，文件一变化 incron 就会发邮件通知我们：

复制代码
 
/srv/test/ IN_CLOSE_WRITE mail -s "$@/$#\n" root
从现在开始，一旦 /src/test 文件夹中的文件被修改，就会发送一封邮件。但是注意不要让incron 监控整个子目录树，因为Inotify 只关注inodes，而不在乎是文件还是文件夹，所以基于Inotify 的软件都需要自己来处理/ 预防递归问题。关于incontab 详细使用，请参考incrontab 的manpage。

如果你还要处理incoming 文件夹，那么你可能需要 inoticoming 。当有文件进入 incoming 文件夹时 Inoticoming 就会执行某些动作，从而可以用 inoticoming 来管理 debian 的软件仓库 (例如软件仓库中一旦有上传源码包或是新添加的二进制包就立刻自动进行编译)，另外，还可以用它来监控系统是否有新上传文件，如果有就发送通知。类似的工具还有 (它们都各有专长)： inosync (基于消息通知机制的文件夹同步服务)， iwatch (基于 Inotify 的程序，对文件系统进行实时监控)，以及 lsyncd (一个守护进程 (daemon)，使用 rsync 同步本地文件夹)。

Inotify 甚至对传统的 Unix 工具也进行了改进，例如 tail。使用 inotail ，同时加上 -f 选项，就可以取代每秒轮询文件的做法。此外，GNU 的 coreutils 从版本 7.5 开始也支持 Inotify 了，我们可以运行下面的命令来确认：

复制代码
 
# strace -e inotify_init,inotify_add_watch tail -f ~log/syslog
[...]
inotify_init()                          = 4
inotify_add_watch(4, "/var/log/syslog", IN_MODIFY|IN_ATTRIB|IN_DELETE_SELF|IN_MOVE_SELF) = 1
从现在开始，通过轮询来确实文件是否需要重新读取的方法应该作为古董了。

在脚本中使用 Inotify
Inotify 机制并不局限于工具，在脚本语言中也完全可以享受 Inotify 的乐趣，如 Python 中可以使用 pyinotify 和 inotifyx ，Perl 中有 Filesys-Notify-Simple 和 Linux-Inotify2 ，Inotify 的 Ruby 版有 ruby-inotifyrb-inoty 和 fssm 。

总结
综上所述，Inotify 为 Linux 提供了一套高效监控和跟踪文件变化的机制，它可以实时地处理、调试以及监控文件变化，而轮询是一种延迟机制。对于系统管理员，关于实现事件驱动的服务如系统备份，构建服务以及基于文件操作的程序调试等，Inotify 无疑提供了强大的支持。
