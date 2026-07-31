#!/bin/bash
# capture-env.sh - 推理测试环境/资源使用采集（4090 nvidia-smi / 910C npu-smi 通用）
# 用法:
#   bash capture-env.sh before [标签]   # 测试前采集环境快照
#   bash capture-env.sh monitor [秒数] [标签]  # 测试期间监控资源曲线
#   bash capture-env.sh after [标签]    # 测试后采集（含日志摘要）
# 输出: output/<标签>/ 目录，报告用字段名对齐 performance-report.md 八字段
set -euo pipefail

OUT="${2:-env}"
DUR="${2:-60}"   # monitor 模式下的监控时长（秒）
LABEL="${3:-run}"
DIR="resource-$LABEL"
mkdir -p "$DIR"

# 检测 NPU 类型
if command -v npu-smi >/dev/null 2>&1; then
    NPU_TYPE="Ascend"
elif command -v nvidia-smi >/dev/null 2>&1; then
    NPU_TYPE="NVIDIA"
else
    NPU_TYPE="none"
fi
echo "$NPU_TYPE" > "$DIR/npu-type.txt"

snapshot() {
    local tag="$1"
    {
        echo "=== $tag $(date '+%F %T') ==="
        echo "--- host ---"
        hostname; uname -r; nproc; free -h | head -2
        echo "--- cpu ---"
        uptime
        echo "--- disk ---"
        df -h /workspace /user_data /tmp 2>/dev/null || df -h
        echo "--- npu ---"
        case "$NPU_TYPE" in
            Ascend) npu-smi info 2>/dev/null || echo "npu-smi 不可用" ;;
            NVIDIA) nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu --format=csv ;;
            *) echo "无 NPU" ;;
        esac
    } > "$DIR/$tag.txt"
    echo "saved $DIR/$tag.txt"
}

monitor() {
    local dur="$1" label="$2" out="$DIR/monitor-$label.csv"
    echo "time,npu_type,util,mem_used_mb,mem_total_mb,cpu_load" > "$out"
    local end=$((SECONDS + dur))
    while [ $SECONDS -lt $end ]; do
        local line
        case "$NPU_TYPE" in
            Ascend)
                line=$(npu-smi info 2>/dev/null | awk '/HBM/ {print $3","$4}' | head -1)
                ;;
            NVIDIA)
                line=$(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | tr -d ' %' | head -1 | awk -F, '{print $1","$2","$3}')
                ;;
            *) line="0,0,0" ;;
        esac
        echo "$(date +%T),${NPU_TYPE},${line},$(cut -d' ' -f1 /proc/loadavg)" >> "$out"
        sleep 2
    done
    echo "saved $out ($dur s)"
}

case "${1:-}" in
    before)  snapshot "before-${LABEL}" ;;
    after)   snapshot "after-${LABEL}" ;;
    monitor) monitor "$DUR" "$LABEL" ;;
    *) echo "用法: $0 before|after [标签] | monitor [秒数] [标签]" ;;
esac
