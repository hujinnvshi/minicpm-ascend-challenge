# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MiniCPM-o 4.5 全模态推理优化参赛仓库（赛道一·**子赛道 A: llama.cpp-omni**，核心指标 **SPEAK→WAV RTF**）。运行/评测在**昇腾 910B3 单卡 + CANN 9.1.0-beta.3**（厂家授权替代 910C；aarch64）。本机 = 910B 云机（`/workspace/user_data/temp_project/minicpm-ascend-challenge`），**无公网入站，出站仅 github/pypi/modelscope 通（YouTube/HF 被封）**。当前进度与下一步见 `docs/session-2026-08-05.md`。

## 关键约束（红线，必读）

- **CANN 不支持 Q4_K_M 量化算子** → LLM 必须用 **F16**（Q4_K_M fallback CPU）。**Q8_0 实测不提速**（dequant-bound），量化对 910B 双工 decode 无收益，别再追。
- **单 compute NPU**：`npu-smi` `Total Count=1`；CANN 报 `dev_count=2` 是双 die 聚合假象，dev1 不可单独用。NPU id = **1**（`/dev/davinci1`）。
- **判断"NPU 是否在算"**：用 `npu-smi info -t usages -i 1` **细粒度（≤0.5s）采样**，看 `Aicore Usage Rate` + `HBM Bandwidth Usage Rate`（后者高=真在 NPU 算）。**不能看单次/粗均值**（曾因此误判"AICore 4%=没走 NPU"，实测 burst 60–84%）。
- **perf-duplex 的 exit 0/2/3 是本工具"双工实时交互"门槛，非官方排名指标**。官方性能只看 **SPEAK→WAV RTF**（基线 1.087，我方 0.83）。`analyze_perf.py` 的 `e2e RTF` = SPEAK 轮完整链路 RTF（≈官方口径）。
- 图模式 `USE_ACL_GRAPH` 在 910B **不支持**（头文件缺）。
- 优化**不得改推理数学**（仅流水线/调度层）→ 精度 = F16 基线，准入必过。

## 常用命令

```bash
# venv（torch/transformers/jiwer/playwright+chromium/opencv/imageio-ffmpeg 已装）
source /workspace/venv-g23/bin/activate

# 构建（增量；改了 ggml-cann.cpp 或 omni.cpp 后）
cmake --build code/llama.cpp-omni/build-cann --target llama-omni-cli llama-omni-perf-duplex llama-omni-server -j$(nproc)
# 全新构建：bash scripts/build-cann.sh

# 跑 SPEAK→WAV RTF（官方性能指标）
cd code/llama.cpp-omni
MODEL=/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf
PREFIX=$PWD/tools/omni/assets/test_case/duplex_omni_test_case/duplex_omni_test_case_
REF=$PWD/tools/omni/assets/default_ref_audio/default_ref_audio.wav
build-cann/bin/llama-omni-perf-duplex -m "$MODEL" -c 4096 -ngl 99 --ref-audio "$REF" --test "$PREFIX" 36 \
  -o tools/omni/output --out-json tools/omni/output/perf.json
python3 tools/omni/perf/analyze_perf.py tools/omni/output/perf.json --interval-ms 1000

# NPU 监测（decode 期 AICore/HBMbw）
npu-smi info -t usages -i 1

# 起 Demo 3 进程（详见 docs/reproduce-guide.md §6）
# gateway(8006) + backend llama-omni-server(22500) + worker(22400) + 注册 worker
```

## 架构（big picture）

三个代码子树 + 文档/工具知识库：

- **`code/llama.cpp-omni/`** —— llama.cpp fork（本赛框架）。优化的两处落点：
  - `ggml/src/ggml-cann/ggml-cann.cpp`：**6 处 CANN 补丁**（`set/get_tensor_async`+`event_record/wait` 加 per-thread `ggml_cann_set_device`；SQR 断言放宽；`host_buffer` 默认 false 让权重上 device）。详见 `docs/cann-patches.md`。
  - `tools/omni/omni.cpp`：**双工流水线 + P1.7 队列解耦**。流水线 = 音频帧 → encoder(CPU) → LLM decode(NPU, `duplex_do_decode`/`stream_decode`) → TTS-model(NPU, `ctx_tts_llama`) → token2wav/T2W(NPU Flow + CPU vocoder) → wav，多线程 + 队列。**LLM↔TTS 队列**（`TTSThreadInfo` cap，`omni_init` ~4296，env `OMNI_TTS_QUEUE` 默认 16）= 主吞吐杠杆（P1.7：1→16 使 LLM P50 8295→977ms）。环境旋钮：`OMNI_TTS_QUEUE` / `OMNI_TTS_GPU_LAYERS` / `OMNI_ETH_PROBE`(micro-probe) / `OMNI_STEP_SIZE` / `OMNI_ASSISTANT_PROMPT` / `OMNI_T2W_THREADS`(P3+P4:token2wav CPU 线程,默认 16;**推荐 24 + `taskset -c 192-223`(NUMA node6)→RTF 0.57**,不绑核 24 反慢至 0.72) / `OMNI_T2W_PROFILE`(=1 打印 token2mel/vocoder 分段)。
- **`code/MiniCPM-o-Demo/`** —— 官方 Demo。3 进程：`gateway.py`(Python,:8006/+8007) + `worker.py`(Python,:22400) + backend(`llama-omni-server`,:22500)。前端预构建在 `static/`（无需 bun）。WS 推理端点 `/v1/worker/{chat,duplex}`（runtime 协议）。
- **`code/daily-omni/`** —— Daily-Omni benchmark 代码（`test_model_api/`，API 测试 + `MODEL_FUNCTION_MAP` adapter 模式）。
- **`benchmark/seed-tts-eval/`** —— TTS-Seed 数据（`seedtts_testset/`，gitignored）+ 官方 eval 参考脚本（`eval_ref/`，自 vllm-omni 移植，含 TTS system prompt + WER/SIM 指标）。
- **`docs/`** —— 知识库（见下"文档导航"）。
- **`tools/omni/perf/`** —— `perf-duplex.cpp`（双工 perf 工具）+ `analyze_perf.py`（RTF/P95/首响 指标）+ `run_perf.sh`。`tools/omni/output/` = 日志/wav（gitignored）。

## 关键路径

- **模型（只读预置）**：`/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/` → 主 `MiniCPM-o-4_5-F16.gguf` + vision/audio/tts/projector F16 + `token2wav-gguf/`。
- **构建产物**：`code/llama.cpp-omni/build-cann/bin/{llama-omni-cli,llama-omni-perf-duplex,llama-omni-server,llama-bench}`。
- **venv**：`/workspace/venv-g23`（含 ffmpeg 二进制 `lib/.../imageio_ffmpeg/binaries/ffmpeg-linux-aarch64-*`）。
- **CANN**：`$ASCEND_TOOLKIT_HOME`（/usr/local/Ascend/cann-9.1.0-beta.3）；`npu-smi` 在 `/usr/local/bin/`。
- **Benchmark 数据（只读预置，三项全齐）**：`/workspace/shared_assets/datasets/` → Video-MME `lmms-lab/Video-MME/`（2700 题 parquet + 20 videos_chunked zip + subtitle）；Daily-Omni `MTEB/Daily-Omni/`（1196 条 parquet，video+audio 内嵌）；TTS-Seed `CowboyZ/seed-tts-eval/`。**不再缺数据，仅缺官方评测脚本**。
- **平台工程参考（只读）**：`/workspace/user_data/dev_info/` → `ascend_system_info.md`（硬件全貌：Atlas 800T A2 容器透传 1 卡 / 910B3 / 64GB / NUMA node6 CPU192-223 / PCI 0xD802）+ `inference_serving_observability.md`（msprof/mstx/npu-smi watch 观测命令模板 + Golden Signals 判读；摘要见 `docs/cann-patches.md`）。

## 文档导航（先读这些）

- `docs/session-2026-08-05.md` —— ⭐会话交接（当前状态/命令/账号/下一步，新会话先读）
- `docs/eval-spec.md` —— 官方评测规范（基线/准入/Demo/提交物）
- `docs/cann-patches.md` —— 6 补丁 + 已知问题（优化必读）
- `docs/experiments.md` —— 实验记录 P0–P1.7 + P2 诊断
- `docs/performance-report.md` / `docs/reproduce-guide.md` —— 提交物
- `docs/decisions.md` —— 决策链（时间倒序）
- `docs/optimization-methodology.md` —— RTF 优化方法论（北极星→定位→杠杆→验证→红线）

## 工作流

- **方法论**：runtime 实测 > 静态推理（多次被 npu-smi+micro-probe 推翻静态误判）。每配置 ≥3 次取中位（RTF 差异 <0.03 视噪声）。优化闭环：plan→实测定位→修→三件套验证（npu-smi + 质量 + 同口径）→落盘。
- **同步通道**：本地↔910B = **Git**（`hujinnvshi/minicpm-ascend-challenge`，main）；大文件（权重/数据集）= ModelScope（YouTube/HF 被封）。
- **分支**：main=完整提交；`p2-duplex-exit0`=性能诊断（未 merge，信息性）。
- **CodeGraph** 已索引（`.codegraph/`）—— 查代码先用 `codegraph_explore`，别直接 grep。

## 当前进度（一句话）

性能(SPEAK→WAV RTF 0.83<1.087)✅ + Demo(3 进程+视频)✅ + 报告/复现✅ 已 push main；**卡在等官方 llama.cpp-omni benchmark 脚本跑 3 项精度数**（F16 不改数学，预期=基线）。详见 `docs/session-2026-08-05.md`。
