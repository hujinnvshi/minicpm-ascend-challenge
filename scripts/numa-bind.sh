#!/bin/bash
# numa-bind.sh - 把命令绑定到 NPU 同 NUMA node 的 CPU（自动探测，无需手查核号）
#
# 背景: 910B 机型之间 NPU 的 NUMA 归属不同（旧机 node6→192-223，新机 node2→64-95），
#       写死核号会跨 NUMA DMA 使 RTF 从 0.58 退化到 0.68（experiments.md 2026-08-14）。
# 用法:
#   scripts/numa-bind.sh env OMNI_T2W_THREADS=24 <binary> [args...]
#   # 或单独查看: scripts/numa-bind.sh --print
# 原理: npu-smi info 取 NPU PCI BDF → /sys/bus/pci/devices/<bdf>/numa_node → nodeN/cpulist → taskset
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

get_npu_bdf() {
    # npu-smi info 中任一含 PCI BDF(0000:XX:00.0) 的行, 取第一个 BDF。兼容不同列序。
    npu-smi info 2>/dev/null | awk -F'|' '
        /[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]/ {
            for (i=1;i<=NF;i++) if ($i ~ /[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]/) { gsub(/^ +| +$/,"",$i); print $i; exit }
        }'
}

if [ "${1:-}" = "--print" ]; then
    BDF="$(get_npu_bdf)"
    [ -z "$BDF" ] && { echo "FATAL: 未从 npu-smi info 解析到 NPU BDF" >&2; exit 1; }
    NODE="$(cat "/sys/bus/pci/devices/$BDF/numa_node" 2>/dev/null || echo unknown)"
    echo "NPU_BDF=$BDF NUMA_NODE=${NODE:-unknown}"
    [ -f "/sys/devices/system/node/node$NODE/cpulist" ] && \
        echo "CPUS=$(cat "/sys/devices/system/node/node$NODE/cpulist")"
    exit 0
fi

BDF="$(get_npu_bdf)"
[ -z "$BDF" ] && { echo "FATAL: 未从 npu-smi info 解析到 NPU BDF（先确认 npu-smi 可用）" >&2; exit 1; }
NODE="$(cat "/sys/bus/pci/devices/$BDF/numa_node" 2>/dev/null || true)"
if [ -z "$NODE" ] || [ ! -f "/sys/devices/system/node/node$NODE/cpulist" ]; then
    echo "WARN: 无法解析 NUMA（BDF=$BDF），不绑核直接执行" >&2
    exec "$@"
fi
CPULIST="$(cat "/sys/devices/system/node/node$NODE/cpulist")"
echo "[numa-bind] NPU $BDF → NUMA node$NODE → CPU $CPULIST （taskset -c $CPULIST）" >&2
exec taskset -c "$CPULIST" "$@"