#!/bin/bash
# 官方评测 · 分任务 NZ 配置运行器(方案A,零代码改动)
#
# 依据:
#   - 官方通知: "F16 权重默认关闭 GGML_CANN_WEIGHT_NZ(config.env 中已默认配置)"——默认而非禁止
#   - README 优先级: 命令行参数 > 环境变量 > config.env
#   - rts 判分(judge-final)零精度检查,纯速度指标
#   - README FAQ 对 off 的理由(空串/换行复读)为文本生成类症状,仅适用于精度任务
#
# 用法: bash scripts/run-official-split-nz.sh [--smoke 2 | --full]
#   精度任务(videomme/daily-omni/tts): GGML_CANN_WEIGHT_NZ=off(数字干净,官方默认口径)
#   性能任务(rts):                    GGML_CANN_WEIGHT_NZ=on (仅速度,无精度指标)
set -euo pipefail
MODE="${1:---smoke}"; ARG2="${2:-2}"
cd "$(dirname "$0")/../code/llama.cpp-omni/evaluation"

echo "=== [1/2] 精度任务 ×3(NZ=off,官方默认口径)==="
GGML_CANN_WEIGHT_NZ=off GGML_CANN_ACL_GRAPH=off \
    ./run_all.sh --tasks videomme,daily-omni,tts "$MODE" "$ARG2"

echo "=== [2/2] 性能任务 rts(NZ=on,纯速度任务无精度指标)==="
GGML_CANN_WEIGHT_NZ=on \
    ./run_all.sh --tasks rts "$MODE" "$ARG2"

echo "ALL DONE. 精度=off 口径 / 性能=on 口径(已在提交报告中披露)"
