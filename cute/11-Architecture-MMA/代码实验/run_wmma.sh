#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/../01-WMMA/代码实验/tensorop_gemm.py"
PYTHON_BIN="${PYTHON:-python3}"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "错误：未找到 nvidia-smi；需要 Ampere SM80 系列 GPU。" >&2
  exit 1
fi

compute_cap="$(
  nvidia-smi --query-gpu=compute_cap --format=csv,noheader |
    head -n 1 |
    tr -d '[:space:]'
)"
if [[ "$compute_cap" != 8.* ]]; then
  echo "错误：本教程面向 Ampere SM8x，检测到的计算能力为 $compute_cap。" >&2
  exit 1
fi

"$PYTHON_BIN" -c \
  'import cutlass, torch; import cuda.bindings.driver; print("CuTe DSL 依赖导入：通过")'

if [[ "$#" -eq 0 ]]; then
  set -- \
    --mnkl 256,256,512,1 \
    --atom_layout_mnk 2,2,1 \
    --ab_dtype Float16 \
    --c_dtype Float16 \
    --acc_dtype Float32 \
    --a_major m \
    --b_major n \
    --c_major n \
    --benchmark none \
    --warmup_iterations 0 \
    --iterations 1
fi

exec "$PYTHON_BIN" "$SOURCE" "$@"
