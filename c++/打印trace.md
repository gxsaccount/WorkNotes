    #include <cxxabi.h>
    #include <execinfo.h>

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
