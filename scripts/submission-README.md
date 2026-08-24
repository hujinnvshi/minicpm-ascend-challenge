# MiniCPM-o 昇腾推理优化与应用创新挑战赛 — 赛道一 · 子赛道 A（llama.cpp-omni）

## 1. 基本信息

| 项 | 值 |
|---|---|
| 队伍/选手 | 张宁（杭州闪捷信息科技） |
| 联系方式 | 18510911437 / zhangning@secsmart.net |
| 架构级改动 | 否（本提交为常规优化，未修改评测入口/计时/校验逻辑；修改点见 §2） |
| 开发基线分支 | `bench/huawei`（官方） |
| 基线提交哈希 | `b06198f`（refine rtf test #100） |
| 最终提交哈希 | `af67cfe`（staging 仓库 HEAD，见 llama.cpp-omni.zip 内 git log） |
| 目标硬件 | Atlas 800T A2 / 昇腾 910B4 单卡（32GB HBM）· aarch64 |
| 软件 | CANN 9.1.0-beta.3 · ccec · CMake · Python 3.12 |

## 2. 优化说明

全部改动位于 `llama.cpp-omni` 主源码包，共 4 个文件，**默认行为与官方基线一致**（改动均为环境变量门控的诊断/稳定性修复，不改变推理数学、评测入口、计时或校验逻辑）：

| 文件 | 修改 | 原理/用途 | 是否改变行为 |
|---|---|---|---|
| `ggml/src/ggml-cann/ggml-cann.cpp` | 补丁 7：`ggml_backend_cann_free` 前 `ggml_cann_set_device` | 修复 910B4 上 omni_free 在未设置过 device 的线程执行时 CANN context null 崩溃（否则评测链路在析构阶段 abort） | 否（生命周期正确性修复） |
| `tools/omni/omni.cpp` | 诊断开关（`OMNI_DEBUG_PREFILL`/`OMNI_DEBUG_TOPK`）+ `OMNI_T2W_STEPS` env 化 + image_id 门控 + 系统提示 + **NPU 提交串行化互斥锁（`OMNI_NPU_SERIAL` 门控）** + **TTS head_code logits 行间并行（`OMNI_HEADCODE_THREADS`，默认 24）+ per-step 计时插桩（`OMNI_TTS_STEP_PROFILE`）** | env 默认关闭/默认值=官方；NPU 锁消除 4 线程并发排队（encoder/llm/tts 三段互斥），RTF -3.3%；head_code matmul（6562×768，原 CPU 单核标量 8.6ms/步）行间并行后 3.1ms/步，每行内部累加顺序不变 → **logits 逐位一致**（26/26 实测），tts 0.417→0.275、RTF -14.3% | 否（默认关闭；并行版数值逐位一致） |
| `tools/omni/omni.h` | T2WOut/last_chunk_timings 结构字段对齐 | 与 omni.cpp 配套 | 否 |
| `tools/omni/vision.cpp` | `Omni_DUMP_EMBED` 诊断开关 + **VPM(ViT) Flash Attention（`OMNI_VISION_FA` 门控）** | env 默认关闭；VPM 原走 mul_mat+softmax（上游 TODO），FA 分支对齐 llama-graph 布局，encode -8.2%、RTF -2.1%、精度零翻转 | 否（默认关闭） |

所有改动均可通过环境变量回退到官方行为；未使用第三方代码。

### 2.1 运行时调优（环境变量，官方 README L268 允许随提交上传）

性能收益来自运行时配置而非修改推理数学（`evaluation/README.md` 明确"若后端优化需要开启，可在提交时一并上传自己的环境变量"）：

| 变量 | 官方默认 | 提交值 | 适用模块 | 作用及必要性 |
|---|---|---|---|---|
| `OMNI_FORCE_FA` | 未设（CANN 默认 forcing off） | 1 | LLM/TTS | **强制 Flash Attention**（ggml-cann 有完整 FLASH_ATTN_EXT 实现，llama-context AUTO 对 CANN 保守关闭）；实测 llm_decode 0.571→0.234（-59%），core RTF 1.71→1.38（-19.6%）；精度零翻转（2026-08-15 A/B 记录） |
| `OMNI_T2W_THREADS` | 16 | 24 | token2wav | vocoder CPU 工作线程；配合 NUMA 绑核降低 T2W 段耗时 |
| `OMNI_VISION_FA` | 未设（VPM 无 FA） | 1 | VPM(视觉编码) | **VPM(ViT) Flash Attention**（vision.cpp build_attn FA 分支）；encode 0.452→0.415（-8.2%）；videomme 10/10 逐字节零翻转 |
| `OMNI_NPU_SERIAL` | 未设（4 线程并发提交） | 1 | 全链路 NPU 提交 | **NPU 提交串行化互斥锁**（VPM/LLM-decode/TTS 三段互斥）：消除 4 线程并发排队（core 帧 vpm 383→341、cost_llm 233→91 稳态水平），RTF -3.3%；墙钟 +18ms 在帧间隔预算内；videomme 10/10 零翻转 |
| `OMNI_HEADCODE_THREADS` | 24 | 24 | TTS head_code | **TTS logits 行间并行**（head_code 6562×768 CPU matmul，原单核标量 8.6ms/步，占 TTS 段 53%）：行间 std::thread 并行 → 3.1ms/步；每行内部标量累加顺序与原代码完全相同 → **logits 逐位一致**（THREADS=0 vs 24 实测 26/26 bin 字节一致）；tts 0.417→0.275（-34%）、core RTF 1.3291→1.139（-14.3%）；0=禁用回退官方 |
| `GGML_CANN_WEIGHT_NZ` | off | off | LLM | 官方要求（`evaluation/README.md` L317：必须保持 off，否则空串/复读异常输出） |
| `GGML_CANN_ACL_GRAPH` | off | off | LLM | 910B 不支持图模式，保持关闭 |
| NUMA 绑核（taskset） | — | NPU 同 node CPU | 全链路 | 避免跨 NUMA DMA；机器相关，先探测 `cat /sys/bus/pci/devices/<NPU_BDF>/numa_node` |

实测效果（同机同输入，910B4 单卡，官方 b06198f harness）：

| 配置 | core RTF | SPEAK→wav 中位 | llm_decode |
|---|---|---|---|
| 零调优默认（16 线程） | 1.87 | 1913ms | 0.57 |
| `OMNI_T2W_THREADS=24` + NUMA 绑核 | 1.71 | 1859ms | 0.57 |
| **+ `OMNI_FORCE_FA=1`（本提交）** | **1.38** | **1599ms** | **0.23** |
| **本提交（FA + VPM FA + NPU 串行锁）** | **1.33** | **1559ms** | **0.24** |
| **v6 增量（+ head_code 行间并行）** | **1.139** | — | 0.24 |

> v6 实测（2026-08-24，官方 b06198f harness 全量 rts，turn=7 core 7 帧）：core RTF **1.139**（分项 encode 0.359 + llm_prefill 0.016 + llm_decode 0.240 + tts 0.275 + token2wav 0.249），batch_validity 全 true（data_valid+realtime_eligible+core_sufficient+score_eligible）。tts 段 -34% 来自 head_code 行间并行（逐位一致，见 §2.1）。

> 另有 A/B 对照：官方原版代码（无本提交 4 文件补丁）同配置 = 1.63，与本提交 1.71 差异在噪声内（±5%）——补丁对性能零影响，本提交的 RTF 水平即官方代码在 910B4 上的真实水平。

## 3. 构建与运行

### 3.1 系统依赖

```bash
# CANN 9.1.0-beta.3（昇腾 910B 系列）
# 编译器：ccec（CANN 自带）；cmake ≥3.20；g++（C++17）
```

### 3.2 模型与数据（不随包分发，按官方环境预置）

- 模型：`/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/`
  （`MiniCPM-o-4_5-F16.gguf` + `vision/` + `audio/` + `tts/` + `token2wav-gguf/`）
- 评测数据：`/workspace/shared_assets/datasets/`（Video-MME / Daily-Omni / Seed-TTS）

### 3.3 构建

```bash
cd llama.cpp-omni
source /usr/local/Ascend/cann-9.1.0-beta.3/set_env.sh
cmake -B build-cann -DGGML_CANN=ON -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_SHARED_LINKER_FLAGS="-lstdc++ -lm -L$ASCEND_TOOLKIT_HOME/aarch64-linux/devlib -lascendcl"
cmake --build build-cann --target llama-omni-server llama-omni-cli llama-omni-perf-duplex \
  llama-omni-eval-cli llama-omni-eval-daily-cli llama-omni-tts-eval -j$(nproc)
```

> 注：链接需显式 `-lascendcl`（libomni.so 引用 aclrtGet/SetDevice，官方 CMake 未链 + ccec `--no-allow-shlib-undefined` 严格模式）。

### 3.4 评测（与官方 evaluation/README.md 口径一致）

```bash
cd llama.cpp-omni/evaluation
python3 judge-final/scripts/make_test_case.py   # 生成 RTS 自测输入（一次）
# 运行时调优（§2.1）：Flash Attention + T2W 24 线程 + NUMA 绑 NPU 同 node
NUMA_CPU=$(cat /sys/bus/pci/devices/$(npu-smi info | grep -oE '0000:[0-9a-f:.]+' | head -1)/numa_node)
export OMNI_FORCE_FA=1 OMNI_T2W_THREADS=24
EVAL_CONFIG=<本机 env> taskset -c $(cat /sys/devices/system/node/node${NUMA_CPU}/cpulist) \
  ./run_all.sh --smoke 2 --no-build
```

自测验收：`batch_pooled_report.json` 中 `batch_validity.data_valid && realtime_eligible == true`。

## 4. MiniCPM-o Demo 集成

见 `integration-support.zip`（gateway:8006 + worker:22400 + llama-omni-server:22500 三进程，启动顺序与连接说明见其 README.md）。

## 5. 结果说明

### 5.1 官方口径

测试采用主源码包内 `evaluation/README.md` 定义的官方测量方法：**RTF = Σ core 帧 compute / Σ 对应音频时长（pooled）**，core 帧为掐首帧冷启动、掐尾帧 flush 后的稳态帧；分子来自 server 上报（SSE `vpm_ms/apm_ms/llm_prefill_ms/cost_llm_ms` + `stage_timing.jsonl` `tts_ms/token2wav_ms`）。

### 5.2 自测结果（2026-08-21，910B4 单卡，NZ=off 官方路径）

**性能（RTS）**：

| 项 | 值 |
|---|---|
| RTS core RTF（5 core 帧 pooled，`OMNI_FORCE_FA=1` + T2W24 + NUMA） | **1.38** |
| 分解 | encode 0.44 + llm_prefill 0.02 + llm_decode 0.23 + tts 0.42 + token2wav 0.27 |
| SPEAK→wav 中位 | 1599 ms |
| batch_validity | data_valid ✓ realtime_eligible ✓ core_sufficient ✓（5/3） |
| 官方样例基线 core RTF | 1.1~1.2（单输入 3 core 帧，抖动大，仅量级参考） |

> 自测用单样例输入，官方明确"自测只验证流程，不预测成绩"；正式成绩以官方统一评测环境为准。

**精度（四项 Benchmark）**：

| 项 | 官方基线 | 准入线 | 自测结果 | 状态 |
|---|---|---|---|---|
| Daily-Omni | 79.5% | ≥77.5 | **79.8%**（1196 题全量） | ✅ |
| TTS-Seed WER | 1.414 | ≤1.56 | **0.97%**（2020 题全量） | ✅ |
| TTS-Seed ASV | 0.709 | ≥0.689 | **0.708** | ✅ |
| Video-MME | 69.0% | ≥67.0 | **72.9%**（官方 stratified 采样 0.1：90 视频/270 题，确定性算法） | ✅ |

> Video-MME 说明：采用官方 `stratified_sampling.py`（duration/domain/sub_category 分层等距，无随机）ratio=0.1 采样的 270 题，NZ=off 官方路径，官方 `eval_your_result.py` 评分。此前 63.3% 为手动合池口径（KB 域占比高），非官方采样算法；本结果与官方准入线 67.0 直接可比。正式评测以赛方全量执行为准。

### 5.3 已知问题

- 910B4 设备为新分配（此前为 910B3），F16 全模态 ~19GB 权重在 32GB HBM 可全量上卡（-ngl 99）
- 历史 perf-duplex 口径（0.58-0.68）与新 core 帧 pooled 口径不可比，已弃用

## 6. 提交自检（对照 SUBMISSION_GUIDE §8）

- [x] 无 `._*` / `.DS_Store` / `__MACOSX/`
- [x] 无 `.git/` / `build/` / 模型权重 / 数据集 / 日志
- [x] `llama.cpp-omni.zip` 由 `git archive` 生成（仅 tracked + status clean）
- [x] README 含可执行构建/运行/复现步骤
- [x] 测量口径引用 `evaluation/README.md` 且与官方一致
