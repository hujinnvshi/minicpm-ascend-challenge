# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MiniCPM-o 4.5 全模态推理优化参赛仓库（赛道一·**子赛道 A: llama.cpp-omni**，核心指标 **SPEAK→WAV RTF**）。运行/评测在**昇腾 910B3 单卡 + CANN 9.1.0-beta.3**（厂家授权替代 910C；aarch64）。本机 = 910B 云机（`/workspace/minicpm-ascend-challenge`），**无公网入站，出站仅 github/pypi/modelscope 通（YouTube/HF 被封）**。当前进度与下一步见 `docs/session-2026-08-05.md`。

## 关键约束（红线，必读）

- **CANN 不支持 Q4_K_M 量化算子** → LLM 必须用 **F16**（Q4_K_M fallback CPU）。**Q8_0 实测不提速**（dequant-bound），量化对 910B 双工 decode 无收益，别再追。
- **单 compute NPU**：`npu-smi` `Total Count=1`；CANN 报 `dev_count=2` 是双 die 聚合假象，dev1 不可单独用。**npu-smi card id 因机器而异（先 `npu-smi info` 看 NPU 列表取 id）：旧机 1/5，新机（2026-08-14）= 7**（`-i 7`）。binary 用 dev0（逻辑 0 = die0）。
- **判断"NPU 是否在算"**：用 `npu-smi info -t usages -i 1` **细粒度（≤0.5s）采样**，看 `Aicore Usage Rate` + `HBM Bandwidth Usage Rate`（后者高=真在 NPU 算）。**不能看单次/粗均值**（曾因此误判"AICore 4%=没走 NPU"，实测 burst 60–84%）。
- **perf-duplex 的 exit 0/2/3 是本工具"双工实时交互"门槛，非官方排名指标**。官方性能只看 **SPEAK→WAV RTF**（基线 1.087，我方 0.83）。`analyze_perf.py` 的 `e2e RTF` = SPEAK 轮完整链路 RTF（≈官方口径）。
- 图模式 `USE_ACL_GRAPH` 在 910B **不支持**（头文件缺）。
- **双die device 锁定**（2026-08-10 新设备 910B/beta.1 验证）：双 die 被 CANN 枚举为 device0+device1，**dev1（die1）不可用**。perf-duplex 双工流水线会跑到 dev1，在 `aclnn_repeat_interleave`（RoPE 用）崩溃 exit139。跑 perf/duplex 前**必须** `ASCEND_RT_VISIBLE_DEVICES=0 CUDA_VISIBLE_DEVICES=0`（→ aclrtGetDeviceCount=1，只看 die0）。npu-smi 查询用 `-i 5`，binary 用 dev0。详见 `docs/session-2026-08-10-newenv.md`。
- 优化**不得改推理数学**（仅流水线/调度层）→ 精度 = F16 基线，准入必过。
- **NUMA 亲和（2026-08-14 新机纠正，易踩）**：vocoder/推理进程**必须绑 NPU 同 NUMA node**，不能照抄 `taskset -c 192-223`。查法：`cat /sys/bus/pci/devices/<NPU_bus>/numa_node`（NPU bus 从 `npu-smi info` 取，本机 `0000:42:00.0`）→ 绑该 node 的 CPU。**旧机 NPU 在 node6 → `192-223`；新机（npu id=7）NPU 在 node2 → `taskset -c 64-95`**。照抄 192-223 会跨 NUMA DMA，使 RTF 退化到 0.68（正确绑核 0.57-0.59）。详见 `docs/experiments.md` 2026-08-14 节。一键：`scripts/numa-bind.sh`（自动探测）。
- **🔴 官方不可改文件（2026-08-15 官方说明，正式评测会校验，修改=不计入成绩/校验失败）**：`evaluation/` 目录（**含 config.env**）、`tools/omni/omni-eval-cli.cpp`、`tools/omni/omni-eval-daily-cli.cpp`、`tools/omni/omni-tts-eval.cpp`、`tools/omni/CMakeLists.txt`。**一律不得改动**；本机路径/设备适配走 `EVAL_CONFIG` 覆盖（benchmark/*.env，不在清单内）。已回退 3 处违规（config.env 适配 + 2 eval-cli 的 image_seq_idx 归零）。改前先 `git diff official/bench/huawei -- <path>` 自查。官方分支：https://github.com/tc-mb/llama.cpp-omni/tree/bench/huawei（已加 remote `official`）。
- **🔴 NZ 纪律（2026-08-15 大反转，必读）**：官方要求 **`GGML_CANN_WEIGHT_NZ=off`**（否则空串/换行复读等异常输出；ggml-cann.cpp:1286/1554 默认 `value_or("on")`），off **只经 run_all.sh→run_eval.py 官方路径注入**。**一切直跑（eval_cpp_pipeline.py 直接起 / 诊断 binary）必须显式 `export GGML_CANN_WEIGHT_NZ=off`**，否则数据作废。08-14 晚"空响应=EOS 临界/缺 image_id"整套归因建立在 NZ=ON 直跑上，**作废**；NZ=off 下空响应≈0（99q 仅 1/99）。详见 `docs/nz-pollution-impact.md`。
- **Video-MME 最新认知（2026-08-15）**：NZ=off 下 image_id/去系统提示/FA 四杠杆 45 题**逐字节零翻转**（63%±6pp = 本机规则内天花板）；270 题合池实测 **63.3%±5.7pp**（准入 67 在区间上沿，全量 2700 仍为唯一裁决）；51.5-53.5% 是 99q KB 域历史口径（KB 视频异质性极大 78/44/52）。协议对齐路线正式关闭（不启用，门控留作探针）。

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
  - `tools/omni/omni.cpp`：**双工流水线 + P1.7 队列解耦**。流水线 = 音频帧 → encoder(CPU) → LLM decode(NPU, `duplex_do_decode`/`stream_decode`) → TTS-model(NPU, `ctx_tts_llama`) → token2wav/T2W(NPU Flow + CPU vocoder) → wav，多线程 + 队列。**LLM↔TTS 队列**（`TTSThreadInfo` cap，`omni_init` ~4296，env `OMNI_TTS_QUEUE` 默认 16）= 主吞吐杠杆（P1.7：1→16 使 LLM P50 8295→977ms）。环境旋钮：`OMNI_TTS_QUEUE` / `OMNI_TTS_GPU_LAYERS` / `OMNI_ETH_PROBE`(micro-probe) / `OMNI_STEP_SIZE` / `OMNI_ASSISTANT_PROMPT` / `OMNI_T2W_THREADS`(P3+P4:token2wav CPU 线程,默认 16;**推荐 24 + NUMA 绑 NPU 同 node** → RTF 0.57-0.59;**先查 `cat /sys/bus/pci/devices/<NPU_bus>/numa_node`**(NPU bus 从 `npu-smi info` 取)→ 绑该 node CPU：旧机 node6→`taskset -c 192-223`,**新机(npu id=7)node2→`taskset -c 64-95`**,照抄 192-223 跨 NUMA 使 RTF 退化到 0.68;不绑核 24 反慢至 0.72) / `OMNI_T2W_PROFILE`(=1 打印 token2mel/vocoder 分段)。
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

性能(SPEAK→WAV RTF **0.58-0.59**<1.087)✅ + Demo(3 进程+视频)✅ + Daily 79.8%✅ + TTS 1.501/0.694✅（**NZ=on 下生成，待 NZ=off 复核**）+ Video-MME 51.5-53.5%（99q KB）/ 270 题合池 **63.3%±5.7pp**（NZ=off，准入 67 在区间上沿，待赛方基线口径）✅/⚠️；**NZ 污染大反转已闭环**（08-14 晚空响应归因作废，协议对齐路线关闭，NZ 纪律见红线）。提交物打包流程已重写并跑通（`scripts/package-submission.sh`）。分支：`review-optimize`（评审改进 + 全部最新实验）。详见 `docs/nz-pollution-impact.md` + `docs/experiments.md` 08-14/15 节。
