#!/usr/bin/env python3

import ast
import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SOURCES = {
    ROOT / "01-WMMA" / "代码实验" / "tensorop_gemm.py": {
        "sha256": "ed7eca473c66a3a3ded741eb4ee30757b4b944d5d360e4023ad6be7ba225b21c",
        "markers": (
            "TensorOpGemm",
            "warp.MmaF16BF16Op",
            "warp.LdMatrix",
            "cute.compile",
        ),
    },
    ROOT / "02-WGMMA" / "代码实验" / "dense_gemm.py": {
        "sha256": "bb7b76d893219757e2f3701abf1a7c8c819b9966e38aaed30a768596a55aca9f",
        "markers": (
            "HopperWgmmaGemmKernel",
            "warpgroup",
            "cute.compile",
            "PipelineTmaAsync",
        ),
    },
    ROOT / "03-TCGen05" / "代码实验" / "fp16_gemm_0.py": {
        "sha256": "a15471df9a2a9c80a6a772416210ea256a58b142aa4b6358ca01851f6f02362a",
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


def validate_source(path: Path, spec: dict) -> None:
    data = path.read_bytes()
    actual_hash = hashlib.sha256(data).hexdigest()
    if actual_hash != spec["sha256"]:
        raise AssertionError(
            f"{path}: SHA-256 mismatch: expected {spec['sha256']}, got {actual_hash}"
        )

    source = data.decode("utf-8")
    ast.parse(source, filename=str(path))

    for marker in spec["markers"]:
        if marker not in source:
            raise AssertionError(f"{path}: missing required marker {marker!r}")


def main() -> None:
    for path, spec in SOURCES.items():
        validate_source(path, spec)
        print(f"PASS source: {path.relative_to(ROOT)}")

    for script in SHELL_SCRIPTS:
        subprocess.run(["bash", "-n", str(script)], check=True)
        print(f"PASS shell: {script.relative_to(ROOT)}")

    print("SOURCE_VALIDATION: PASS")


if __name__ == "__main__":
    main()
