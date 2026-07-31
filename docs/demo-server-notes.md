# llama-omni-server 后端验证记录（2026-07-31）

## 结论

llama-omni-server（MiniCPM-o-Demo 的 C++ 后端）在 secs 4090 上构建 + 启动 + 全模块加载验证通过。
Demo 链路三阶段中"后端"环节确认可用；worker/gateway/前端阶段待 910C 或 secs 授权后验证。

## 构建（secs, /data/minicpm-omni/llama.cpp-omni）

- 目标：tools/server/llama-omni-server（-DLLAMA_BUILD_SERVER=ON）
- 增量构建：cmake -S . -B build-cuda -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_TESTS=OFF
- cmake --build build-cuda --target llama-omni-server -j 112
- 产物：build-cuda/bin/llama-omni-server（构建约 1 分钟增量）

## 启动

```bash
cd /data/minicpm-omni/llama.cpp-omni
CUDA_VISIBLE_DEVICES=1 ./build-cuda/bin/llama-omni-server \
  -m /data/minicpm-omni/weights/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
  -ngl 99 --host 127.0.0.1 --port 22500 -c 8192
```

- 模型懒加载：启动即 /health 可用，首个 omni_init 请求触发加载
- 与官方 entrypoint-cpp-worker-backend.sh 参数一致（-m/-ngl 99/--host/--port，LLAMA_SERVER_EXTRA_ARGS=-c 8192）

## 验证结果

1. GET /health → {"engine":"comni","status":"ok"}
2. POST /v1/stream/omni_init {"msg_type":2,"use_tts":true,"tts_gpu_layers":100,"token2wav_device":"gpu:0"} → {"success":true}
3. 加载后 GPU1 显存：4 MiB → 11334 MiB（Q4_K_M + 全模块，24.5G 卡余 ~13G）
4. 加载耗时约 30-60s

## API 端点（tools/server/server-omni.cpp）

- GET /health, GET /v1/health
- POST /v1/stream/omni_init       （加载/重置全模块，msg_type: 1=语音? 2=音频, use_tts, tts_gpu_layers, token2wav_device, output_dir, voice_audio）
- POST /v1/stream/prefill         （输入注入）
- POST /v1/stream/decode          （流式解码）
- POST /v1/stream/update_session_config
- POST /sessions/:id/close

## 权重目录布局要求（entrypoint 校验）

模型根目录下必须存在：
- vision/MiniCPM-o-4_5-vision-F16.gguf
- audio/MiniCPM-o-4_5-audio-F16.gguf
- tts/MiniCPM-o-4_5-tts-F16.gguf + tts/MiniCPM-o-4_5-projector-F16.gguf
- token2wav-gguf/（encoder/flow_matching/flow_extra/hifigan2/prompt_cache）
与 secs 现有权重布局一致，910C 同步时保持同样结构

## 对比赛的直接意义

1. Demo 准入三环节（server/worker/gateway）中 server 已验证——910C 上同参数构建 CANN 版即可
2. omni_init 参数（msg_type/use_tts/token2wav_device）即 Demo worker 转发协议，官方评测脚本大概率走同一接口
3. Daily-Omni 精度评测可走此 API（prefill 注入视频/音频 → decode 取文本答案）

## 待办

- [ ] worker.py + gateway.py 段验证（需 secs 部署授权或等 910C）
- [ ] prefill/decode 实测（文本问答 + 音频输入）
- [ ] 910C 上 CANN 版构建后同流程验证
