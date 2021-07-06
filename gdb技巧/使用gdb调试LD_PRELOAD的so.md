1.gdb --args env LD_PRELOAD=/home/gaoxiang/data/nvbit_release/tools/mytool/mytool.so   ./vectoradd   
2.         
    (gdb) set exec-wrapper env 'LD_PRELOAD=libtest.so'
    (gdb) run
