1.查看cache miss  
perf stat -e L1-dcache-load-misses ./a.out  

2.查看  
sudo perf  record -g -a -p pid ;   perf report  
perf diff [oldfile] [newfile]  


