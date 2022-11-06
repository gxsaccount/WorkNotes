linux下time命令可以获取到一个程序的执行时间，包括程序的实际运行时间(real time)，以及程序运行在用户态的时间(user time)和内核态的时间(sys time)。  

    time ./test
    real    0m0.020s
    user    0m0.000s
    sys     0m0.018s
    
    
/usr/bin/time  和 time 不一定是同一个time   
/usr/bin/time --verbose test 可以查看更多信息

        Command being timed: "test 1"
        User time (seconds): 0.00
        System time (seconds): 0.00
        Percent of CPU this job got: ?%
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:00.00
        Average shared text size (kbytes): 0
        Average unshared data size (kbytes): 0
        Average stack size (kbytes): 0
        Average total size (kbytes): 0
        Maximum resident set size (kbytes): 2304
        Average resident set size (kbytes): 0
        Major (requiring I/O) page faults: 0
        Minor (reclaiming a frame) page faults: 80
        Voluntary context switches: 1
        Involuntary context switches: 0
        Swaps: 0
        File system inputs: 0
        File system outputs: 0
        Socket messages sent: 0
        Socket messages received: 0
        Signals delivered: 0
        Page size (bytes): 4096
        Exit status: 0
