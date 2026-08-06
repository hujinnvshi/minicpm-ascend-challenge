#!/usr/bin/env bash
# 跑 SPEAK→WAV RTF 性能基准(perf-duplex 36 帧 + analyze)— 官方性能排名指标
# 用法: ./scripts/benchmark.sh [out_json_path]
set -euo pipefail
cd "$(dirname "$0")/.."
source /workspace/venv-g23/bin/activate
cd code/llama.cpp-omni
MODEL=/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf
PREFIX=$PWD/tools/omni/assets/test_case/duplex_omni_test_case/duplex_omni_test_case_
REF=$PWD/tools/omni/assets/default_ref_audio/default_ref_audio.wav
OUT=${1:-tools/omni/output/perf.json}
build-cann/bin/llama-omni-perf-duplex -m "$MODEL" -c 4096 -ngl 99 --ref-audio "$REF" \
  --test "$PREFIX" 36 -o tools/omni/output --out-json "$OUT"
python3 tools/omni/perf/analyze_perf.py "$OUT" --interval-ms 1000
