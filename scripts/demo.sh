#!/usr/bin/env bash
# 启动 Demo 3 进程(gateway + backend server + worker)+ 注册 worker
# 详见 docs/reproduce-guide.md §6。访问:https://127.0.0.1:8006/
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH=/usr/local/bin:$PATH
source /workspace/venv-g23/bin/activate
VENV=/workspace/venv-g23/bin/python
SERVER=code/llama.cpp-omni/build-cann/bin/llama-omni-server
MODEL=/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf
cd code/MiniCPM-o-Demo
$VENV gateway.py --port 8006 --internal-port 8007 --host 0.0.0.0 --https \
  --ssl-certfile certs/cert.pem --ssl-keyfile certs/key.pem &
$SERVER -m "$MODEL" -ngl 99 --host 127.0.0.1 --port 22500 -c 8192 --no-mmap &
$VENV worker.py --host 0.0.0.0 --port 22400 --gpu-id 0 \
  --backend-server-url http://127.0.0.1:22500 &
sleep 12   # 等 server 懒加载就绪
curl -sS -X PUT -H "content-type: application/json" \
  --data '{"endpoint":"127.0.0.1:22400","gpu_group":"gpu-0"}' \
  http://127.0.0.1:8007/internal/workers/cpp-worker-1
echo
echo "Demo ready: https://127.0.0.1:8006/  (playwright 录像见 benchmark/demo-video)"
wait
