#!/usr/bin/env python3

import ast
import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SOURCES = {
    ROOT / "01-WMMA" / "代码实验" / "tensorop_gemm.py": {
        "source_path": "examples/python/CuTeDSL/cute/ampere/kernel/dense_gemm/tensorop_gemm.py",
        "logic_sha256": "2c9e7ded13462a60735e777fb977d5bcc31549660de6fbfa8abff2a5d55da358",
        "markers": (
            "TensorOpGemm",
            "warp.MmaF16BF16Op",
            "warp.LdMatrix",
            "cute.compile",
        ),
    },
    ROOT / "02-WGMMA" / "代码实验" / "dense_gemm.py": {
        "source_path": "examples/python/CuTeDSL/cute/hopper/kernel/dense_gemm/dense_gemm.py",
        "logic_sha256": "9854f590988d72fedac07f9a4ae46be4a82d72dd9a7d1773458d9bdb8c870b8f",
        "markers": (
            "HopperWgmmaGemmKernel",
            "warpgroup",
            "cute.compile",
            "PipelineTmaAsync",
        ),
    },
    ROOT / "03-TCGen05" / "代码实验" / "fp16_gemm_0.py": {
        "source_path": "examples/python/CuTeDSL/cute/blackwell/tutorial/tutorial_gemm/fp16_gemm_0.py",
        "logic_sha256": "b29780f3b79b5e2f14ae79c9d0053c0b2181ea31e94c80046ff1ecb5513cd493",
        "markers": (
            "tcgen05.MmaF16BF16Op",
            "TmemAllocator",
            "PipelineTmaUmma",
            "host_function(a_tensor, b_tensor, c_tensor, no_cache=True)",
        ),
    },
}

SHELL_SCRIPTS = (
    ROOT / "代码实验" / "run_wmma.sh",
    ROOT / "代码实验" / "run_wgmma.sh",
    ROOT / "代码实验" / "run_tcgen05.sh",
)


class StripStrings(ast.NodeTransformer):
    """忽略翻译允许修改的字符串和打印参数，仅校验计算代码结构。"""

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value="<字符串>"), node)
        return node

    def visit_Call(self, node: ast.Call):
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            node.args = []
            node.keywords = []
        return node


def validate_source(path: Path, spec: dict) -> None:
    data = path.read_bytes()
    source = data.decode("utf-8")
    tree = StripStrings().visit(ast.parse(source, filename=str(path)))
    logic_hash = hashlib.sha256(
        ast.dump(tree, include_attributes=False).encode("utf-8")
    ).hexdigest()
    if logic_hash != spec["logic_sha256"]:
        raise AssertionError(f"{path}：注释翻译之外的代码结构发生变化")

    expected_url = (
        "https://github.com/NVIDIA/cutlass/blob/"
        "098de2a652cf8f00fd70b2df54051c7eccbb855a/"
        f"{spec['source_path']}"
    )
    if expected_url not in source:
        raise AssertionError(f"{path}：缺少固定版本英文原版链接")

    for marker in spec["markers"]:
        if marker not in source:
            raise AssertionError(f"{path}：缺少必要标记 {marker!r}")


def main() -> None:
    for path, spec in SOURCES.items():
        validate_source(path, spec)
        print(f"源码检查通过：{path.relative_to(ROOT)}")

    for script in SHELL_SCRIPTS:
        subprocess.run(["bash", "-n", str(script)], check=True)
        print(f"脚本检查通过：{script.relative_to(ROOT)}")

    print("源码校验：通过")


if __name__ == "__main__":
    main()
