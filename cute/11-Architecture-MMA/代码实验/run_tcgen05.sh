#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/../03-TCGen05/代码实验/fp16_gemm_0.py"
PYTHON_BIN="${PYTHON:-python3}"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "错误：未找到 nvidia-smi；需要 Blackwell SM100 GPU。" >&2
  exit 1
fi

compute_cap="$(
  nvidia-smi --query-gpu=compute_cap --format=csv,noheader |
    head -n 1 |
    tr -d '[:space:]'
)"
if [[ "$compute_cap" != 10.* ]]; then
  echo "错误：TCGen05 示例需要 Blackwell SM100，检测到的计算能力为 $compute_cap。" >&2
  exit 1
fi

"$PYTHON_BIN" -c \
  'import cutlass, torch; import cuda.bindings.driver; print("CuTe DSL 依赖导入：通过")'

if [[ "$#" -eq 0 ]]; then
  set -- --mnk 256,256,64
fi

exec "$PYTHON_BIN" "$SOURCE" "$@"
