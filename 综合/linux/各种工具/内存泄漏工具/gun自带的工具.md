GNU libc has built-in malloc debugging:

http://www.gnu.org/software/libc/manual/html_node/Allocation-Debugging.html

Use LD_PRELOAD to call mtrace() from your own .so:

#include <mcheck.h>
static void prepare(void) __attribute__((constructor));
static void prepare(void)
{
    mtrace();
}
Compile it with:

gcc -shared -fPIC dbg.c -o dbg.so
Run it with:

export MALLOC_TRACE=out.txt
LD_PRELOAD=./dbg.so ./my-leaky-program
Later inspect the output file:

mtrace ./my-leaky-program out.txt
And you will get something like:

Memory not freed:
-----------------
           Address     Size     Caller
0x0000000001bda460     0x96  at /tmp/test/src/test.c:7
Of course, feel free to write your own malloc hooks that dump the entire stack (calling backtrace() if you think that's going to help).

Lines numbers and/or function names will be obtainable if you kept debug info for the binary somewhere (e.g. the binary has some debug info built in, or you did objcopy --only-keep-debug my-leaky-program my-leaky-program.debug).
