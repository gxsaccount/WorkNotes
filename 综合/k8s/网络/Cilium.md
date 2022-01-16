Flannel 常见采取 UDP  Overlay 方案，VxLAN 性能比 TUN 强一点，一个是内核态一个是用户态  
Calico 是一个纯三层的方案，不需要 Overlay，基于 Etcd 维护网络准确性，也基于 Iptables 增加了策略配置
Cilium 就厉害了，基于 eBPF 和 XDP 的方案，eBPF/XDP 处理数据包的速度可以和 DPDK 媲美，零拷贝直接内核态处理，缺点就是用户不太容易进行配置，
而 cilium 解决了这个问题，毕竟 yaml 开发工程师都会写 yaml。。。可以支持 L3/L4/L7 的策略
