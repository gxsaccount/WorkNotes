#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/../02-WGMMA/代码实验/dense_gemm.py"
PYTHON_BIN="${PYTHON:-python3}"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found; Hopper SM90 GPU is required." >&2
  exit 1
fi

compute_cap="$(
  nvidia-smi --query-gpu=compute_cap --format=csv,noheader |
    head -n 1 |
    tr -d '[:space:]'
)"
if [[ "$compute_cap" != 9.* ]]; then
  echo "ERROR: WGMMA example requires Hopper SM90/SM90a; detected compute capability $compute_cap." >&2
  exit 1
fi

"$PYTHON_BIN" -c \
  'import cutlass, torch; import cuda.bindings.driver; print("CuTe DSL imports: PASS")'

if [[ "$#" -eq 0 ]]; then
  set -- \
    --mnkl 256,256,256,1 \
    --tile_shape_mn 128,128 \
    --cluster_shape_mn 1,1 \
    --a_dtype Float16 \
    --b_dtype Float16 \
    --c_dtype Float16 \
    --acc_dtype Float32 \
    --a_major k \
    --b_major k \
    --c_major n \
    --warmup_iterations 1 \
    --iterations 1
fi

exec "$PYTHON_BIN" "$SOURCE" "$@"
