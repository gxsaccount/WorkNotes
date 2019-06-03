一致性协议： ETCD使用**Raft**协议， ZK使用ZAB（类**PAXOS协议**），前者容易理解，方便工程实现；
运维方面：ETCD**方便运维**，ZK难以运维；
项目活跃度：ETCD社区与开发活跃，ZK已经快死了；
API：ETCD提供**HTTP+JSON**, **gRPC接口**，跨平台跨语言，ZK需要使用其客户端；
访问安全方面：ETCD**支持HTTPS访问**，ZK在这方面缺失；
