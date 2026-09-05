# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MiniCPM-o 4.5 全模态推理优化参赛仓库（赛道一·**子赛道 A: llama.cpp-omni**，核心指标 **RTF**，官方口径 = core 帧 pooled Σcompute/Σaudio）。运行/评测在**昇腾 910B4 单卡（32GB HBM，NPU id=3，NUMA node4→CPU 128-159）+ CANN 9.1.0-beta.3**（厂家授权替代 910C；aarch64；⚠️ 设备会被平台重新分配，跑评测前先 `npu-smi info` 探测，勿信本文硬件参数）。本机 = 910B 云机（`/workspace/minicpm-ascend-challenge`），**无公网入站，出站仅 github/pypi/modelscope 通（YouTube/HF 被封）**。当前进度与下一步见 `docs/session-2026-08-25.md`（最新交接）。

## 关键约束（红线，必读）

- **CANN 不支持 Q4_K_M 量化算子** → LLM 必须用 **F16**（Q4_K_M fallback CPU）。**Q8_0 实测不提速**（dequant-bound），量化对 910B 双工 decode 无收益，别再追。
- **单 compute NPU**：`npu-smi` `Total Count=1`；CANN 报 `dev_count=2` 是双 die 聚合假象，dev1 不可单独用。**npu-smi card id 因机器而异（先 `npu-smi info` 看 NPU 列表取 id）：旧机 1/5，新机（2026-08-14）= 7**（`-i 7`）。binary 用 dev0（逻辑 0 = die0）。
- **判断"NPU 是否在算"**：用 `npu-smi info -t usages -i 1` **细粒度（≤0.5s）采样**，看 `Aicore Usage Rate` + `HBM Bandwidth Usage Rate`（后者高=真在 NPU 算）。**不能看单次/粗均值**（曾因此误判"AICore 4%=没走 NPU"，实测 burst 60–84%）。
- **perf-duplex 的 exit 0/2/3 是本工具"双工实时交互"门槛，非官方排名指标**。官方性能只看 **SPEAK→WAV RTF**（基线 1.087，我方 0.83）。`analyze_perf.py` 的 `e2e RTF` = SPEAK 轮完整链路 RTF（≈官方口径）。
- 图模式 `USE_ACL_GRAPH`：**910B4 实测 CLOSED（2026-08-24）**——头文件存在（旧"头文件缺"结论推翻）、编译链接成功，但全量 on 运行时崩（TTS zero norm/whisper 每帧 re-capture/挂死，与官方 L320 警告一致）；受限版（per-backend `ggml_backend_cann_set_acl_graph`，只给 VPM 开）规避成功但 910B4 图执行不省时（aclmdlRIExecuteAsync 与 eager 相同）。接口保留供 910C，官方评测默认 `GGML_CANN_ACL_GRAPH=off`。
- **双die device 锁定**（2026-08-10 新设备 910B/beta.1 验证）：双 die 被 CANN 枚举为 device0+device1，**dev1（die1）不可用**。perf-duplex 双工流水线会跑到 dev1，在 `aclnn_repeat_interleave`（RoPE 用）崩溃 exit139。跑 perf/duplex 前**必须** `ASCEND_RT_VISIBLE_DEVICES=0 CUDA_VISIBLE_DEVICES=0`（→ aclrtGetDeviceCount=1，只看 die0）。npu-smi 查询用 `-i 5`，binary 用 dev0。详见 `docs/session-2026-08-10-newenv.md`。
- 优化**不得改推理数学**（仅流水线/调度层）→ 精度 = F16 基线，准入必过。
- **NUMA 亲和（易踩，机器相关）**：vocoder/推理进程**必须绑 NPU 同 NUMA node**。查法：`cat /sys/bus/pci/devices/<NPU_bus>/numa_node`（NPU bus 从 `npu-smi info` 取）。**当前 910B4：NPU 0000:82:00.0 → node4 → `taskset -c 128-159`**。一键：`scripts/numa-bind.sh`（自动探测）。绑核是运行稳定性必需（全核/跨 NUMA → BATCH_WORKER_FAILED），但 910B4+FA 下无额外性能收益（CPU 侧非瓶颈）。
- **🔴 RTF 新口径（2026-08-21 官方 b06198f）**：官方成绩 = **core 帧 pooled**（Σ compute/Σ audio，掐首帧冷启动+尾帧 flush），分子走 server 上报（SSE vpm_ms/apm_ms/llm_prefill_ms/cost_llm_ms + stage_timing.jsonl tts_ms/token2wav_ms）。**batch_validity 双 true（data_valid && realtime_eligible）才出成绩**：tts/t2w 事件必须带 src_cnt、非尾帧 TTS 恰 26 audio token、core 帧 wav 24000 samples@24kHz、t2w_dequeue 无跨 src 积压且 oldest_wait_ms<1s。perf-duplex/analyze_perf.py 旧口径数字不再可比。自测 = make_test_case.py + run_all.sh --smoke 2（任务顺序 rts 优先）。
- **🔴 官方不可改文件（2026-08-15 官方说明，正式评测会校验，修改=不计入成绩/校验失败）**：`evaluation/` 目录（**含 config.env**）、`tools/omni/omni-eval-cli.cpp`、`tools/omni/omni-eval-daily-cli.cpp`、`tools/omni/omni-tts-eval.cpp`、`tools/omni/CMakeLists.txt`。**一律不得改动**；本机路径/设备适配走 `EVAL_CONFIG` 覆盖（benchmark/*.env，不在清单内）。已回退 3 处违规（config.env 适配 + 2 eval-cli 的 image_seq_idx 归零）。改前先 `git diff official/bench/huawei -- <path>` 自查。官方分支：https://github.com/tc-mb/llama.cpp-omni/tree/bench/huawei（已加 remote `official`）。
- **🔴 NZ 纪律（2026-08-15 大反转，必读）**：官方要求 **`GGML_CANN_WEIGHT_NZ=off`**（否则空串/换行复读等异常输出；ggml-cann.cpp:1286/1554 默认 `value_or("on")`），off **只经 run_all.sh→run_eval.py 官方路径注入**。**一切直跑（eval_cpp_pipeline.py 直接起 / 诊断 binary）必须显式 `export GGML_CANN_WEIGHT_NZ=off`**，否则数据作废。08-14 晚"空响应=EOS 临界/缺 image_id"整套归因建立在 NZ=ON 直跑上，**作废**；NZ=off 下空响应≈0（99q 仅 1/99）。详见 `docs/nz-pollution-impact.md`。
- **Video-MME 最新认知（2026-08-21 更新）**：官方新增确定性分层采样（stratified_sampling.py，duration/domain/sub_category 等距，无随机）。**官方采样 ratio=0.1（90 视频/270 题）实测 72.9%（197/270）→ 达标（准入 67）**；旧 63.3%（手动 270 合池）是采样构造偏差（KB 域占比高），非代码问题。官方正式 VIDEOMME_SAMPLE_RATIO 未公开（0.1/0.5/全量未知）。协议对齐路线关闭（不启用，门控留作探针）。

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
  - `tools/omni/omni.cpp`：**双工流水线 + 归帧溯源（官方 b06198f）**。流水线 = 音频帧 → encoder(VPM/APM) → LLM decode(NPU) → TTS-model(NPU) → token2wav/T2W(NPU Flow + CPU vocoder) → wav。**性能主力 env（v6 提交，全部门控默认关=官方行为）**：`OMNI_FORCE_FA=1`（LLM Flash Attention，decode -59%）、`OMNI_VISION_FA=1`（VPM FA，encode -8.2%）、`OMNI_NPU_SERIAL=1`（NPU 提交串行化互斥，RTF -3.3%）、`OMNI_HEADCODE_THREADS=24`（TTS head_code 行间并行，logits 逐位一致，tts -34%）、`OMNI_T2W_THREADS=24`（token2wav CPU 线程）。其余旋钮：`OMNI_TTS_QUEUE` / `OMNI_TTS_GPU_LAYERS` / `OMNI_ETH_PROBE` / `OMNI_STEP_SIZE` / `OMNI_ASSISTANT_PROMPT` / `OMNI_T2W_PROFILE`(=1 打印 token2mel/vocoder 分段)。
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

- `docs/session-2026-08-26.md` —— ⭐最新会话交接（官方 910C 出分回写：v5 RTF 0.8357 精度 4/4 全过，v6 待出分；新会话先读）
- `docs/session-2026-08-25.md` —— 上一交接（赛事说明相符性核对 + v6 包哈希问题）
- `docs/competition-readiness.md` —— ⭐就绪度总览（§0 为 2026-08-25 最新状态，精度/性能/风险一表）
- `docs/ops-handoff.md` —— ⭐提交记录与凭证约定（v1-v6 全链路）
- `docs/eval-spec.md` —— 官方评测规范（基线/准入/Demo/提交物）
- `docs/announcement-2026-08-21-official-update.md` —— ⭐官方 8/21 更新（新 RTF 口径/SUBMISSION_GUIDE/不可改清单）
- `docs/cann-patches.md` —— CANN 补丁 + 已知问题（优化必读）
- `docs/experiments.md` / `docs/decisions.md` —— 实验记录 / 决策链（时间倒序）

### 文档时效地图（docs/ 65 篇分层）

- **活跃（当前主线，数字可信）**：session-2026-08-24/25/26、ops-handoff、competition-readiness（§0）、
  announcement-2026-08-21、experiments、decisions、env-scan、papers-p0-probe-2026-08-24、
  closed-optimizations-deep-analysis-2026-08-24、knowledge-map（8/26 已回写官方出分）、status-assessment（8/26 头部已覆盖）
- **历史（数字已被取代，仅查过程/决策背景）**：competition-readiness（§0 以下）、status-assessment、
  performance-report、submission-checklist、prep-roadmap、track1-*、workflow-overview、
  session-2026-08-04/05/10、organizer-inquiry-*、videomme-* 系列等 8/17 前文档
- **规则**：引用数字前先确认口径（机器/RTF 口径/NZ 状态）；拿不准查 session-2026-08-25 §一

## 工作流

- **方法论**：runtime 实测 > 静态推理（多次被 npu-smi+micro-probe 推翻静态误判）。每配置 ≥3 次取中位（RTF 差异 <0.03 视噪声）。优化闭环：plan→实测定位→修→三件套验证（npu-smi + 质量 + 同口径）→落盘。
- **同步通道**：本地↔910B = **Git**（`hujinnvshi/minicpm-ascend-challenge`，main）；大文件（权重/数据集）= ModelScope（YouTube/HF 被封）。
- **分支**：main=完整提交；`p2-duplex-exit0`=性能诊断（未 merge，信息性）。
- **CodeGraph** 已索引（`.codegraph/`）—— 查代码先用 `codegraph_explore`，别直接 grep。

## 当前进度（一句话，2026-08-26 晚更新）

**赛事已收官（8/26 用户确认）→ 铺路模式：无提交/排名压力，技术积累导向，可无时间压力移植验证竞品方案。**
收官前最终成绩：官方在册 v5 = RTF 0.8357（精度 4/4 准入全过）；910C 实测优化链 v6→v7→v8
（head 并行 → VPM batch → 图模式+t16）= **0.7237×5 轮**（纯优化 vs v6 ≈ -26%），v8 精度已验证
（LLM 逐字节一致 / tts 40 条 WER 0.947%=0.947% / 40/40 wav 逐字节一致），提交物 6 文件已就绪
（910c 分支 c7ec345，未提交）。
铺路候选：① 910C 特性补验（FP8/KV 量化/大 ctx/量化重扫）② **DFlash TTS 推测解码移植**
（⭐执行路线图 docs/dflash-port-roadmap-2026-09-05.md——CPU A/B 实测 1.75×、v8.7 基评估
0.48-0.50，P0-P4 分阶段就绪待执行；知识链 competitor-intel→probe→assets→roadmap）
③ t2w 步数修复（910C 最大段 0.238，v8.5 已用 1 步+conv_mm 解决——gitcode 后期已做）。
详细见 `docs/session-2026-08-26.md`（最新交接）+ `docs/competition-readiness.md` §0。
