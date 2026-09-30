"""最小 DSL GPU kernel 冒烟测试。

目的：验证 nvidia-cutlass-dsl 4.8.0 能在本机 MIG 切片(sm_80) + CUDA 12.2 上
真正 JIT 编译并在 GPU 上执行一个 kernel，而不只是 import 成功。

做一件最简单的事：把输入张量每个元素 +1，拷回 host 校验。
跑通即证明「DSL → JIT → PTX → GPU 执行」整条链路在本机可用。
"""
import cutlass
import cutlass.cute as cute
import cutlass.torch as _  # noqa: 触发运行时初始化（若需要）
from cutlass.cute.runtime import from_dlpack
import numpy as np


@cute.kernel
def add_one_kernel(gT: cute.Tensor):
    tidx, _, _ = cute.arch.thread_idx()
    bidx, _, _ = cute.arch.block_idx()
    bdim, _, _ = cute.arch.block_dim()
    i = bidx * bdim + tidx
    if i < cute.size(gT):
        gT[i] = gT[i] + 1.0


@cute.jit
def launch(gT: cute.Tensor):
    n = cute.size(gT)
    threads = 128
    blocks = (n + threads - 1) // threads
    add_one_kernel(gT).launch(grid=[blocks, 1, 1], block=[threads, 1, 1])


def main():
    import torch  # DSL 自带的 torch？若无则退回 numpy 路径
    x = torch.arange(256, dtype=torch.float32, device="cuda")
    gT = from_dlpack(x)
    launch(gT)
    torch.cuda.synchronize()
    expected = torch.arange(256, dtype=torch.float32, device="cuda") + 1
    ok = torch.allclose(x, expected)
    print(f"[smoke] add_one on GPU: {'PASS' if ok else 'FAIL'}  x[:4]={x[:4].tolist()}")


if __name__ == "__main__":
    main()
