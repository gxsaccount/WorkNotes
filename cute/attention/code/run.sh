#!/usr/bin/env bash
# 一键跑通 Flash Attention 对拍流水线（CPU golden，无需 GPU）。
#
# 数据流：golden/ 生成对拍真值，learn/ 放学习实操代码，产物统一写到 artifacts/。
#   1. golden/gen_inputs.py   生成固定 Q/K/V + dims.txt
#   2. golden/golden_numpy.py numpy 真值 -> O_numpy.bin
#   3. golden/golden.cpp      C++ 真值   -> O_cpp.bin （在 artifacts/ 内编译运行，按 CWD 读写 .bin）
#   4. learn/fa_reference.py  FA 分块参考（v0/v1）自对拍 golden -> O_v0/v1.bin
#   5. golden/check.py        逐元素对拍 O_numpy vs O_cpp
#
# 用法：bash code/run.sh   （从任意目录调用均可）
set -euo pipefail

CODE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOLDEN="$CODE_DIR/golden"
LEARN="$CODE_DIR/learn"
ART="$CODE_DIR/artifacts"
PY="${PYTHON:-python3}"
mkdir -p "$ART"

echo "==> [1/5] 生成输入"
"$PY" "$GOLDEN/gen_inputs.py"

echo "==> [2/5] numpy golden"
"$PY" "$GOLDEN/golden_numpy.py"

echo "==> [3/5] C++ golden（在 artifacts/ 内编译运行）"
g++ -O2 -std=c++17 "$GOLDEN/golden.cpp" -o "$ART/golden"
( cd "$ART" && ./golden )

echo "==> [4/5] FA 分块参考自对拍"
"$PY" "$LEARN/fa_reference.py"

echo "==> [5/5] numpy vs C++ 对拍"
"$PY" "$GOLDEN/check.py" O_numpy.bin O_cpp.bin
