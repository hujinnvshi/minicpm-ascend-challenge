# 复现说明(2026-08-05 版)

目标:评审人员在官方昇腾环境(单卡 910B4 + CANN 9.1.0-beta.3,厂家授权替代 910C)按本文档复现本方案的全部结果(SPEAK→WAV RTF + 可运行 Demo)。

> 配套:[cann-patches.md](cann-patches.md)(6 补丁详)、[experiments.md](experiments.md)(P0–P1.7 优化链)、[performance-report.md](performance-report.md)、[demo-server-notes.md](demo-server-notes.md)。

## 1. 环境

- 硬件:昇腾 910B4 单卡(64GB HBM,20 AICore)+ 鲲鹏 920 256 核 + 2TB 内存,aarch64(openEuler)。
- 软件:CANN 9.1.0-beta.3(官方指定 beta1,向上兼容);`ASCEND_TOOLKIT_HOME` 已配置;`npu-smi` 可用。
- 预置权重(只读,免下载):`/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/`。
- 依赖:cmake ≥3.24、g++ ≥11、python3(分析脚本)、`npu-smi`。

## 2. 代码与本方案改动

代码库:`code/llama.cpp-omni/`(llama.cpp-omni fork)。本方案改动两类:

**A. ggml-cann 后端 6 处补丁**(`code/llama.cpp-omni/ggml/src/ggml-cann/ggml-cann.cpp`,详见 [cann-patches.md](cann-patches.md)):
- 补丁 1–4:`set_tensor_async` / `get_tensor_async` / `event_record` / `event_wait` 前加 `ggml_cann_set_device`(CANN 多线程 per-thread device 绑定,修 T2W 线程 aclrt 崩)。
- 补丁 5:`GGML_OP_SQR` 断言放宽。
- 补丁 6:`device_get_props` 的 `host_buffer` 默认 false(让 LLM 权重上 device buffer,非 host buffer/CPU)。

**B. P1.7 双工 LLM↔TTS 队列解耦**(`code/llama.cpp-omni/tools/omni/omni.cpp`):
- `omni_init` 中 `TTSThreadInfo` 队列容量 1 → 16(env `OMNI_TTS_QUEUE` 可覆盖)—— 解除 LLM 与 TTS-model 1:1 锁步(主 RTF 杠杆)。
- (诊断)micro-probe `eval_tokens_with_hidden` 计时,env `OMNI_ETH_PROBE` 开(默认静默);`OMNI_TTS_GPU_LAYERS` env 旋钮。

## 3. 构建

```bash
cd code/llama.cpp-omni
# ⚠️ 必须用 CANN bisheng clang(ccec),系统 gcc 12.3.1 build 不了(COMDAT/binding/symtab 异常,
#   bfd/lld/gold 三 linker 全失败,见 memory 910b-cann-gotchas 第10条)。
#   简单方式: bash scripts/build-cann.sh(已固化 ccec);或显式:
CCEC=$ASCEND_TOOLKIT_HOME/tools/bisheng_compiler/bin/ccec   # CANN 自带 clang 15.0.5
cmake -B build-cann -DCMAKE_BUILD_TYPE=Release -DGGML_CANN=ON -DCANN_INSTALL_DIR=$ASCEND_TOOLKIT_HOME \
  -DCMAKE_C_COMPILER=$CCEC -DCMAKE_CXX_COMPILER=$CCEC \
  -DCMAKE_EXE_LINKER_FLAGS="-lstdc++ -lm -lpthread -ldl" \
  -DCMAKE_SHARED_LINKER_FLAGS="-lstdc++ -lm" -DCMAKE_MODULE_LINKER_FLAGS="-lstdc++ -lm"
cmake --build build-cann --target llama-omni-cli llama-omni-perf-duplex llama-omni-server -j$(nproc)
# 产物:build-cann/bin/{llama-omni-cli,llama-omni-perf-duplex,llama-omni-server}
# (eval target llama-omni-eval-cli/-eval-daily-cli: CookBook 官方评测 pipeline,见 benchmark/video-mme-cookbook/ + docs/asv-official-plan.md)
```

## 4. 权重

- 来源:官方预置只读 `/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/`。
- 主模型:**MiniCPM-o-4_5-F16.gguf**(CANN 不支持 Q4_K_M 量化算子 → 用 F16)。
- 子模块(自动从 LLM 目录解析):`vision/MiniCPM-o-4_5-vision-F16.gguf`、`audio/...-audio-F16.gguf`、`tts/...-tts-F16.gguf`、`tts/...-projector-F16.gguf`、`token2wav-gguf/`。

## 5. 性能评测(SPEAK→WAV RTF)

```bash
cd code/llama.cpp-omni
BIN=build-cann/bin/llama-omni-perf-duplex
MODEL=/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf
PREFIX=$PWD/tools/omni/assets/test_case/duplex_omni_test_case/duplex_omni_test_case_
REF=$PWD/tools/omni/assets/default_ref_audio/default_ref_audio.wav
# [P3+P4] 推荐: vocoder 24 threads + NUMA 绑 NPU 同 node → RTF 0.58-0.59 (默认 16 不绑核 0.68-0.69)
# ★ 必须先查 NPU 的 NUMA node 再绑对应 CPU（不同机器 node 不同！旧机 node6=192-223，本机 node2=64-95）:
#   NPU bus 从 `npu-smi info` 取（本机 0000:42:00.0）→ cat /sys/bus/pci/devices/<NPU_bus>/numa_node
#   照抄 192-223 到 NPU 在 node2 的机器 = 跨 NUMA DMA, RTF 退化到 0.68
taskset -c 64-95 env OMNI_T2W_THREADS=24 $BIN -m "$MODEL" -c 4096 -ngl 99 --ref-audio "$REF" --test "$PREFIX" 36 \
  -o tools/omni/output --out-json tools/omni/output/perf_report.json
python3 tools/omni/perf/analyze_perf.py tools/omni/output/perf_report.json --interval-ms 1000
```

**预期结果(本方案, 2026-08-14 新机实测口径)**:
- **SPEAK→WAV e2e RTF ≈ 0.58-0.59**(推荐 24 vocoder threads + NUMA 绑 NPU 同 node) / 0.68–0.69(默认 16 不绑核)(官方基线 1.087,beat ~46%/37%)。
- RTF 0.57(2026-08-12 旧机 node6 配置实测)为旧机参考值;换机器必先查 numa_node(见上)。
- TTS RTF ≈ 0.58-0.59;LLM 判定 P50 ≈ 977ms。
- 多次跑取中位(RTF 差异 <0.03 视噪声)。
- 并发采样(证 compute 在 NPU):`while sleep 0.5; do npu-smi info -t usages -i 1 | grep -i 'Aicore\|HBM Bandwidth'; done` → decode 期 AICore burst 60–84%、HBM 带宽 50%。

## 6. Demo 复现(3 进程裸机部署)

```bash
# venv(pip 装依赖:见 docs/demo-server-notes.md;ffmpeg 用 imageio-ffmpeg)
cd code/MiniCPM-o-Demo
VENV=/workspace/venv-g23/bin/python  # 或自建 venv
SERVER=../llama.cpp-omni/build-cann/bin/llama-omni-server
MODEL=/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf
# 1) gateway(https :8006 + internal :8007)
$VENV gateway.py --port 8006 --internal-port 8007 --host 0.0.0.0 --https \
  --ssl-certfile certs/cert.pem --ssl-keyfile certs/key.pem &
# 2) backend(llama-omni-server,:22500)
$SERVER -m "$MODEL" -ngl 99 --host 127.0.0.1 --port 22500 -c 8192 --no-mmap &
# 3) worker(:22400,转发 backend,注册 gateway)
$VENV worker.py --host 0.0.0.0 --port 22400 --gpu-id 0 \
  --backend-server-url http://127.0.0.1:22500 &
# 4) 注册 worker
curl -X PUT -H "content-type: application/json" \
  --data '{"endpoint":"127.0.0.1:22400","gpu_group":"gpu-0"}' \
  http://127.0.0.1:8007/internal/workers/cpp-worker-1
```

访问 `https://127.0.0.1:8006/` → Turn-based Chat / Omni Full-Duplex / Audio Full-Duplex。验证:发文本 → 模型流式回复(中文连贯,非乱码;Total ~925ms)。

## 7. 精度评测（三项 Benchmark，2026-08-12/08-14 实测）

- **Daily-Omni**: 全量 **1196 题 79.8%**(官方 Overall, output/20260812_132304;基线 79.5,准入 ≥77.5)✅ 持平基线。数据: `shared_assets/datasets/MTEB/Daily-Omni/` parquet(内嵌 video+audio) → `benchmark/daily-omni-convert/convert.py` 转 jsonl+落盘 → 官方 `run_all.sh --tasks daily-omni --full --no-build`。命令行与结果: `docs/daily-omni-eval.md`。
- **TTS-Seed**: 全量 **2020 题 WER 1.501%**(基线 1.414,准入 ≤1.56)✅ / **ASV 0.694**(基线 0.709,准入 ≥0.689)✅。生成走 NPU + WER/SIM 走 CPU(不改官方 evaluation/)。显式链路: `docs/tts-seed-eval.md`;ASV 权重准备: `scripts/setup-tts-asv.sh`(wavlm 1.2GB, 从 hf-mirror)。
- **Video-MME**: 99 题子集 **51.5–53.5%**(官方不可改 evaluation/, 64帧@1fps;官方基线 69.0 为全量 2700 口径,不可直接比)。多帧退化已根治(attention 掩码 -Inf F16 修复)。2026-08-14 深入排查: 空响应根因 = C++ prefill 缺 `<image_id>` 帧编号(协议层, 与 HF 参考实现 diff 坐实), env `OMNI_IMAGE_ID=1` + `OMNI_TEXT_CHAT_SYS=1` 可消除退化模式(协议对齐, 不会改推理数学); 99q 完整对齐 A/B 见 `benchmark/video-mme-cookbook/diag/eval-99q-review.env` 与 experiments.md 2026-08-14 节。基线口径问题(910B 单 die 真实基线 / 69.0 出处)已整理待发组委会: `docs/organizer-inquiry-2026-08-12.md`。
- 复现基准: 官方全量视频 900 个在 `videos_chunked_*.zip`, 按需解压用 `scripts/setup-videomme-videos.py`; 单卡适配用 EVAL_CONFIG 覆盖(dev0=die0 锁, NUM_GPUS=1), 见 `benchmark/video-mme-cookbook/diag/eval-99q-review.env`。

## 8. 复现检查清单

- [ ] build-cann 无报错,产物 3 个 binary 齐。
- [ ] perf-duplex 出报告,**SPEAK→WAV RTF ≈ 0.58-0.59**(24线程+NUMA 绑 NPU 同 node)/ **0.68-0.69**(默认16)(<基线 1.087)。
- [ ] NUMA 绑核先查 `cat /sys/bus/pci/devices/<NPU_bus>/numa_node`(勿照抄核号)。
- [ ] 精度评测走官方 `run_all.sh` 路径(NZ=off 自动注入);**直跑必须 `export GGML_CANN_WEIGHT_NZ=off`**(NZ=on 致空串/换行复读,数据作废,见 nz-pollution-impact.md)。
- [ ] npu-smi 采样 decode 期 AICore burst >60%(证 compute 在 NPU)。
- [ ] `llm_debug/llm_text.txt` 输出正常(防乱码)。
- [ ] 3 进程 Demo 启动,前端可访问,文本→流式回复正常。
- [ ] 精度 benchmark: Daily-Omni 全量 1196(79.8%) / TTS-Seed 全量 2020(WER 1.501% / ASV 0.694)达准入;Video-MME 以官方 910B 独立基线口径判定(待赛方)。
