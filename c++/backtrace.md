/* need to add gcc compile option -rdynamic(or -export-dynamic) to extract symbols. */
 
           
           
        //
        #ifdef UNUSED
        #elif defined(__GNUC__)
        #define UNUSED(x) UNUSED_##x __attribute__((unused))
        #elif defined(__LCLINT__)
        #define UNUSED(x) /*@unused@*/ x
        #else
        #define UNUSED(x) x
        #endif
           
 
        #pragma once
        #ifdef MGV_DEBUG
        #include <cxxabi.h>
        #include <execinfo.h>
        #include <signal.h>
        #include <string.h>
        #include <iostream>
        #include <string>
        #include "base.h"

        namespace mgsdk {
        namespace common {
        struct sigaction oldact = {};
        //打印当前stack_depth深度的调用栈
        static void printBackTrace(int stack_depth) {
            if (stack_depth <= 0 || stack_depth > 32) return;

            void *pptrace_raw[stack_depth];
            char **pptrace_str = nullptr;
            int trace_num = backtrace(pptrace_raw, stack_depth);
            pptrace_str = backtrace_symbols(pptrace_raw, trace_num);
            if (pptrace_str == nullptr) return;

            for (int i = 1; i < trace_num; i++) {
                std::string symbol = pptrace_str[i];
                size_t left_bracket_pos = symbol.find_first_of("(");
                if (left_bracket_pos == std::string::npos) {
                    std::cout << "#" << i - 1 << " " << symbol << std::endl;
                    continue;
                }
                size_t plus_pos = symbol.find_first_of("+", left_bracket_pos);
                if (plus_pos == std::string::npos) {
                    std::cout << "#" << i - 1 << " " << symbol << std::endl;
                    continue;
                }
                size_t right_bracket_pos = symbol.find_first_of(")", plus_pos);
                if (right_bracket_pos == std::string::npos) {
                    std::cout << "#" << i - 1 << " " << symbol << std::endl;
                    continue;
                }
                std::string lib_name = symbol.substr(0, left_bracket_pos);
                std::string func_name = symbol.substr(left_bracket_pos + 1,
                                                      plus_pos - left_bracket_pos - 1);
                std::string pc_address = symbol.substr(right_bracket_pos + 1);
                std::string offset =
                    symbol.substr(plus_pos + 1, right_bracket_pos - plus_pos - 1);
                int status;
                char *ret = abi::__cxa_demangle(func_name.c_str(), 0, 0, &status);
                std::string function;
                if (!status)
                    function = ret;
                else
                    function = func_name.empty() ? "UNKNOWN" : func_name;
                std::cout << "#" << i - 1 << " (" << lib_name << ") " << function
                          << " + " << offset << pc_address << std::endl;
                delete ret;
            }
            delete pptrace_str;
        }

        static void printBackTraceInSigErr(int signum, siginfo_t *sig_info,
                                           void *ucontext) {
            sigaction(signum, &oldact, NULL);
            std::cout << "System Receives a " << signum << "(" << strsignal(signum)
                      << ", sig_code: " << sig_info->si_code
                      << ", sig_errno: " << sig_info->si_errno << ")"
                      << " Interrupt, Fault Address : " << sig_info->si_addr
                      << std::endl;
            printBackTrace(32);
        }

        static void catchSignalErr(int signum) {
            struct sigaction act;
            sigemptyset(&act.sa_mask);
            act.sa_flags = SA_SIGINFO | SA_ONESHOT | SA_ONSTACK;
            act.sa_sigaction = printBackTraceInSigErr;
            struct sigaction *pOldAct = NULL;
            if (NULL == oldact.sa_sigaction && NULL == oldact.sa_handler)
                pOldAct = &oldact;
            if (0 != sigaction(signum, &act, pOldAct))
                std::cout << "Register user signal handler for signal " << signum
                          << " fail." << std::endl;
        }

        static void catchSIGILL() { catchSignalErr(SIGILL); }

        static void catchSIGSEGV() { catchSignalErr(SIGSEGV); }

        static void catchSIGABRT() { catchSignalErr(SIGABRT); }

        static int catchAllSigErrs() {
            catchSIGSEGV();
            catchSIGILL();
            catchSIGABRT();
            return 0;
        }

        int UNUSED(backtrace_tmp) = catchAllSigErrs();
        }  // namespace common
        }  // namespace mgsdk

        #endif
