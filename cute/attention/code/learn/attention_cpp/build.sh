#!/usr/bin/env bash
# 编译一份 attention 实现：harness.cpp + 指定的 impl_*.cpp -> 对应可执行。
#
# 用法：
#   bash build.sh impl_template.cpp          # -> attention_template
#   bash build.sh impl_naive.cpp             # -> attention_naive
#   bash build.sh impl_xxx.cpp attention_foo # 第二个参数自定义可执行名
#
# 可执行名默认由 impl_<name>.cpp 取 <name>，前缀 attention_。
# 编译产物统一放到 ../artifacts/（已 gitignore），不污染源码目录。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART="$HERE/../../artifacts"
mkdir -p "$ART"

if [[ $# -lt 1 ]]; then
    echo "用法: bash build.sh <impl_xxx.cpp> [可执行名]" >&2
    echo "现有实现:" >&2
    ls "$HERE"/impl_*.cpp 2>/dev/null | xargs -n1 basename >&2 || echo "  (无)" >&2
    exit 1
fi

IMPL="$1"
if [[ ! -f "$HERE/$IMPL" ]]; then
    echo "找不到实现文件: $HERE/$IMPL" >&2
    exit 1
fi

# 默认可执行名：impl_naive.cpp -> attention_naive
DEFAULT_NAME="attention_$(basename "$IMPL" .cpp | sed 's/^impl_//')"
OUT="${2:-$DEFAULT_NAME}"

g++ -O2 -std=c++17 "$HERE/harness.cpp" "$HERE/$IMPL" -o "$ART/$OUT"
echo "已生成: $ART/$OUT"
echo "运行:   $ART/$OUT $ART     （或 cd $ART && ./$OUT）"
