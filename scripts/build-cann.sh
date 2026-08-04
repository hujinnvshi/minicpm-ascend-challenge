#!/bin/bash
# build-cann.sh - 昇腾 910C 构建脚本（官方统一环境）
# 用法: bash build-cann.sh [--graph]
#   --graph  启用 USE_ACL_GRAPH（图模式，910C 最大优化杠杆）
set -euo pipefail

REPO="${1:-$PWD/llama.cpp-omni}"
BUILD_DIR="${BUILD_DIR:-$REPO/build-cann}"
JOBS="$(nproc)"

echo "[1/3] 检查 CANN 环境..."
# CANN 版本检查：优先用 ASCEND_TOOLKIT_HOME（实测 /usr/local/Ascend/cann-9.1.0-beta.3）
#   注：旧版用 /usr/local/Ascend/ascend-toolkit/latest/version.cfg，新版镜像该文件可能缺失
CANN_HOME="${ASCEND_TOOLKIT_HOME:-/usr/local/Ascend/ascend-toolkit/latest}"
VERSION_CFG="$CANN_HOME/version.cfg"
if [ -f "$VERSION_CFG" ]; then
    echo "    当前 CANN: $(grep -i version "$VERSION_CFG" | head -1)"
else
    # version.cfg 缺失时从目录名推断（如 cann-9.1.0-beta.3）
    echo "    当前 CANN(路径推断): $(basename "$CANN_HOME")"
fi
echo "    架构: $(uname -m)"
# 升级方法（如需 9.0.0→9.1.0-beta1，见 docs/hidevlab-faq.md）:
#   https://www.hiascend.com/developer/download/community/result?module=cann&cann=9.0.0 下载 run 包
#   chmod +x xxx.run && ./xxx.run --upgrade && python -c "import acl; print('ACL OK')"

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
    # ⚠️ 910B3 实测：acl_graph 头文件缺失，图模式大概率不支持（编不过或 FATAL_ERROR）
    #     910C 才完整支持图模式。910B 上默认编译即可，--graph 仅作验证性尝试。
    echo "    启用 USE_ACL_GRAPH（图模式）—— 910B 可能不支持，编译失败属预期"
    CMAKE_ARGS+=(-DUSE_ACL_GRAPH=ON)
fi

echo "[3/3] 构建 llama-omni-cli / llama-omni-perf-duplex"
cmake -S "$REPO" "${CMAKE_ARGS[@]}"
cmake --build "$BUILD_DIR" --target llama-omni-cli llama-omni-perf-duplex -j"$JOBS"

echo "DONE: $BUILD_DIR/bin/llama-omni-cli"
echo "验证: $BUILD_DIR/bin/llama-omni-cli -h"
