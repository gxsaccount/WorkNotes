#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/../03-TCGen05/代码实验/fp16_gemm_0.py"
PYTHON_BIN="${PYTHON:-python3}"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found; Blackwell SM100 GPU is required." >&2
  exit 1
fi

compute_cap="$(
  nvidia-smi --query-gpu=compute_cap --format=csv,noheader |
    head -n 1 |
    tr -d '[:space:]'
)"
if [[ "$compute_cap" != 10.* ]]; then
  echo "ERROR: TCGen05 example requires Blackwell SM100; detected compute capability $compute_cap." >&2
  exit 1
fi

"$PYTHON_BIN" -c \
  'import cutlass, torch; import cuda.bindings.driver; print("CuTe DSL imports: PASS")'

if [[ "$#" -eq 0 ]]; then
  set -- --mnk 256,256,64
fi

exec "$PYTHON_BIN" "$SOURCE" "$@"
