break _Unwind_RaiseException

gcc5 在处理异常时catch(...),然而又处理不了所有异常，异常抛出时，栈销毁，导致什么也看不到
