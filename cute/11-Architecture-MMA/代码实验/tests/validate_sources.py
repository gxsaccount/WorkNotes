#!/usr/bin/env python3

import ast
import hashlib
import io
import subprocess
import tokenize
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SOURCES = {
    ROOT / "01-WMMA" / "代码实验" / "tensorop_gemm.py": {
        "source_path": "examples/python/CuTeDSL/cute/ampere/kernel/dense_gemm/tensorop_gemm.py",
        "logic_sha256": "1687dafbe7c8b4b76200b173f695f06eeb247238ee0d1f7a52ee6af1578ba05d",
        "comment_count": 200,
        "doc_newlines": [48, 20, 20, 23, 37],
        "markers": (
            "TensorOpGemm",
            "warp.MmaF16BF16Op",
            "warp.LdMatrix",
            "cute.compile",
        ),
    },
    ROOT / "02-WGMMA" / "代码实验" / "dense_gemm.py": {
        "source_path": "examples/python/CuTeDSL/cute/hopper/kernel/dense_gemm/dense_gemm.py",
        "logic_sha256": "12ee74cca506116966e1b6aca62fce1b3348e67362a4456f0f6cb5c5bbedc54d",
        "comment_count": 166,
        "doc_newlines": [51, 38, 31, 12, 11, 15, 25, 16, 25, 11, 11, 13, 18, 24],
        "markers": (
            "HopperWgmmaGemmKernel",
            "warpgroup",
            "cute.compile",
            "PipelineTmaAsync",
        ),
    },
    ROOT / "03-TCGen05" / "代码实验" / "fp16_gemm_0.py": {
        "source_path": "examples/python/CuTeDSL/cute/blackwell/tutorial/tutorial_gemm/fp16_gemm_0.py",
        "logic_sha256": "173380dc4ccad7f54288733fc8cee6b1469d1d2399f6a2b10d3ddb4643a4c9bd",
        "comment_count": 98,
        "doc_newlines": [15],
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
    """忽略翻译允许修改的字符串，仅校验计算代码结构。"""

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value="<字符串>"), node)
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

    comment_count = sum(
        token.type == tokenize.COMMENT
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
    )
    if comment_count != spec["comment_count"]:
        raise AssertionError(
            f"{path}：注释数量发生变化，期望 {spec['comment_count']}，"
            f"实际 {comment_count}"
        )

    doc_newlines = [
        node.value.value.count("\n")
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    if doc_newlines != spec["doc_newlines"]:
        raise AssertionError(f"{path}：文档字符串的行数或数量发生变化")

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
