#!/usr/bin/env bash
# 启动 llama-omni-server 单进程(:22500,F16)— benchmark 与 Demo 的统一后端
# 用法: ./scripts/serve.sh   (环境变量 MODEL 可覆盖默认权重)
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH=/usr/local/bin:$PATH   # 确保 ffmpeg 在 PATH(extract 需要)
MODEL=${MODEL:-/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf}
exec code/llama.cpp-omni/build-cann/bin/llama-omni-server \
  -m "$MODEL" -ngl 99 --host 127.0.0.1 --port 22500 -c 8192 --no-mmap "$@"
