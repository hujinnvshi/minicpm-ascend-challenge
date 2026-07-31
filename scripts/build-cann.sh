#!/bin/bash
# build-cann.sh - 昇腾 910C 构建脚本（官方统一环境）
# 用法: bash build-cann.sh [--graph]
#   --graph  启用 USE_ACL_GRAPH（图模式，910C 最大优化杠杆）
set -euo pipefail

REPO="${1:-$PWD/llama.cpp-omni}"
BUILD_DIR="${BUILD_DIR:-$REPO/build-cann}"
JOBS="$(nproc)"

echo "[1/3] 检查 CANN 环境..."
# CANN 安装目录：镜像预装则 ASCEND_TOOLKIT_HOME 已设；否则手动指定
if [ -z "${CANN_INSTALL_DIR:-}" ]; then
    if [ -n "${ASCEND_TOOLKIT_HOME:-}" ]; then
        CANN_INSTALL_DIR="$ASCEND_TOOLKIT_HOME"
        echo "    使用 ASCEND_TOOLKIT_HOME=$CANN_INSTALL_DIR"
    else
        # 常见路径探测
        for p in /usr/local/Ascend/ascend-toolkit/latest /usr/local/Ascend/ascend-toolkit; do
            if [ -d "$p" ]; then CANN_INSTALL_DIR="$p"; echo "    探测到 $p"; break; fi
        done
        [ -n "${CANN_INSTALL_DIR:-}" ] || { echo "ERROR: 未找到 CANN，设置 CANN_INSTALL_DIR"; exit 1; }
    fi
fi

# 环境变量（CANN 运行时必需）
export ASCEND_TOOLKIT_HOME="${ASCEND_TOOLKIT_HOME:-$CANN_INSTALL_DIR}"
export LD_LIBRARY_PATH="$CANN_INSTALL_DIR/lib64:${LD_LIBRARY_PATH:-}"
export PATH="$CANN_INSTALL_DIR/bin:${PATH:-}"

echo "[2/3] 验证 NPU..."
npu-smi info 2>/dev/null | head -3 || { echo "WARN: npu-smi 不可用（容器内可能无权限，跳过）"; }

CMAKE_ARGS=(-B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release -DGGML_CANN=ON -DCANN_INSTALL_DIR="$CANN_INSTALL_DIR")
if [ "${1:-}" = "--graph" ]; then
    echo "    启用 USE_ACL_GRAPH（图模式）"
    CMAKE_ARGS+=(-DUSE_ACL_GRAPH=ON)
fi

echo "[3/3] 构建 llama-omni-cli / llama-omni-perf-duplex"
cmake "${CMAKE_ARGS[@]}"
cmake --build "$BUILD_DIR" --target llama-omni-cli llama-omni-perf-duplex -j"$JOBS"

echo "DONE: $BUILD_DIR/bin/llama-omni-cli"
echo "验证: $BUILD_DIR/bin/llama-omni-cli -h"
