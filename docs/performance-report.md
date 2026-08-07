# 性能测试报告 — MiniCPM-o 4.5 双工推理优化(赛道一·子赛道 A: llama.cpp-omni)

> 状态:2026-08-07 版。SPEAK→WAV RTF 已实测(0.57 调优 / 0.68 默认);精度 benchmark 现状见 §10(Daily-Omni/VideoMME 框架视觉限制,已向组委会发问 `docs/organizer-inquiry-email.md`)。
> 北极星指标:**SPEAK→WAV 完整链路 RTF**(单并发 F16),官方基线 **1.087**。
> 赛事:MiniCPM & 昇腾推理优化与应用创新挑战赛 · 赛道一 · 子赛道 A(llama.cpp-omni)。

## 1. RTF(核心指标 + 统计口径)

- **指标定义**:SPEAK→WAV 完整链路 RTF = (一轮 SPEAK 从首帧 push 到末 wav 落盘的墙钟时间) / (该轮生成音频时长)。单并发、F16。<1 表示快于实时。
- **口径对齐**:与官方"主要优化目标 = SPEAK 生成阶段 RTF(非全 chunk 平均)"一致 —— 本指标按 SPEAK 轮计,不对 LISTEN 帧平均。
- **实测结果(perf-duplex 36 帧,F16)**:

| 配置 | SPEAK→WAV RTF(e2e) | 官方基线 | 结论 |
|---|---|---|---|
| **24 线程 + NUMA 绑核**(调优最优,5 次中位 0.55–0.62) | **0.57** | **1.087** | ✅ **beat ~48%** |
| **16 线程默认**(最可复现,3 次 0.84/0.68/0.58) | **0.68** | **1.087** | ✅ **beat ~37%** |

> 报告口径:**0.68**(16 线程默认,零手动配置、最可复现)为主线;**0.57**(`OMNI_T2W_THREADS=24 + taskset -c 192-223` NUMA)为调优最优,见 `reproduce-guide.md`。均红线内(仅 CPU 线程 + NUMA 绑核,不改推理数学)。
- TTS RTF(TTS 段,参考)0.80–0.82;LLM 判定 P50(参考)977ms(<1000,实时)。
- 优化链:P1.7(队列解耦)→ P3(vocoder 8→16 线程)→ P4(24 线程 + NUMA)。详见 `experiments.md`。

## 2. 测试环境

- **硬件**:昇腾 910B3 单卡(64GB HBM,20 AICore;厂家授权替代 910C,"1 颗 910C = 2 颗 910B")+ 鲲鹏 920 256 核 + 2TB 内存。
- **软件**:CANN 9.1.0-beta.3(官方指定 beta1,向上兼容);aarch64(openEuler)。
- **框架**:llama.cpp-omni(build-cann,GGML_CANN=ON),6 处 ggml-cann 补丁 + P1.7 队列解耦。
- **权重**:MiniCPM-o-4_5-**F16**.gguf(CANN 不支持 Q4_K_M 量化算子 → 用 F16)+ vision/audio/tts/projector F16 + token2wav-gguf(官方预置只读)。

## 3. 测试数据

- **工具**:`tools/omni/perf/perf-duplex`(perf-duplex,全双工模拟,1s 推帧节奏)+ `analyze_perf.py`。
- **输入**:`duplex_omni_test_case_`(36 帧:32 SPEAK / 4 LISTEN,音视频)。
- **配置**:F16 / n_ctx 4096 / ngl 99 / use_mmap=false(双工上 device)/ stream-interval 1000ms / LLM→TTS 队列 16(P1.7)。

## 4. 测试次数

- 多次复跑取中位:16 线程默认(P8,3 次)0.84/0.68/0.58 → 中位 **0.68**;24 线程+NUMA(P4,5 次)0.55–0.62 → 中位 **0.57**。均稳定 <1.087。
- **P8 复测(2026-08-06,fix 分支含 P3 vocoder 16)**:3 次 e2e RTF = 0.84 / 0.68 / 0.58,**中位 0.68**(冷启动→热机波动,均 <1.087)。原始日志 `tools/omni/output/perf_p8_{1,2,3}.{json,log}`(gitignored)。
- 方法论:每配置 ≥3 次,RTF 差异 <0.03 视噪声(experiments 016);P8 三次波动 0.26 系冷启动/系统负载,取中位 0.68 报告。

## 5. 统计方式

- `analyze_perf.py`:按时间戳匹配 SPEAK 轮 ↔ 音频轮;e2e RTF = (末 wav − 首帧 push) / 音频时长。
- 辅助:npu-smi `info -t usages -i 1` 细粒度(0.5s)采样 AICore + HBM 带宽(证 compute 真在 NPU)。

## 6. 优化前后对比

| 优化项 | 前 | 后 | 机制 |
|---|---|---|---|
| **LLM↔TTS 队列解耦(P1.7)** | 队列 cap=1(锁步)→ LLM P50 8295ms | cap=16 → **P50 977ms(8.5×)** | 解除 LLM 与 TTS-model 1:1 锁步,LLM 可 burst 不每 chunk 阻塞 |
| 双工 model 上 device(P1.6) | host_buffer/use_mmap 致 model 在 CPU | use_mmap=false + 补丁6 → model 上 NPU(HBM 24G) | 强制 eager copy 权重到 device |
| cann 6 补丁(P0–P1.5) | T2W 线程 device 未绑定崩 | set/get_tensor + event +device 绑定 + host_buffer 默认 false | per-thread aclrtSetDevice + 权重上 device |

- **RTF 提升主杠杆**:队列解耦(消除单 NPU 上 LLM+TTS 串行等待)。

## 7. 资源使用

- **HBM**:推理期 ~24G(model 全上 device,稳定不释放)。
- **AICore**:decode 活跃窗 burst 60–84%、HBM 带宽 50%(证 LLM compute 真在 NPU,非 CPU fallback);窗口均值 ~23%(batch=1 自回归 decode 天然 memory-bound 的低 util,非故障)。

## 8. 异常情况说明

- **CANN 不支持 Q4_K_M 量化算子** → LLM 用 F16(4090 的"量化最优"在 910B 失效;Q8_0 实测不提速,dequant-bound)。非异常,平台约束。
- **P1.6 曾误判"AICore 4% = compute 没走 NPU"** → P1.7 npu-smi 细粒度采样澄清为时间均值伪影(实际 burst 60–84%),offload 一直正常。
- 910B3 替代 910C:算力约为半颗 910C,RTF 绝对值偏高但口径统一即公平。

## 9. 复现(摘要)

- 构建:`build-cann.sh`(GGML_CANN=ON)+ ggml-cann 6 补丁 + P1.7(`omni.cpp` 队列 cap 16,env `OMNI_TTS_QUEUE`)。
- 跑:`tools/omni/perf/run_perf.sh -m <F16> --test <duplex_omni_test_case_> 36` → `analyze_perf.py`。
- 详见 [reproduce-guide.md](reproduce-guide.md)、优化链 [experiments.md](experiments.md)(P0–P1.7)、补丁 [cann-patches.md](cann-patches.md)。

## 10. 精度 benchmark 现状(2026-08-07,详见 experiments.md P7 重验/P8 + organizer-inquiry-email.md)

- **Daily-Omni**:单帧/低帧(2 帧)约 6.7%–12.5%;**多帧(实测 8 帧)稳定触发模型退化**(重复不可打印 token)。已实现两处真实修复(交错打包 + whisper KV 跨段清理,commit `c9d9499`,gated/红线内),**均验证生效但未解 8 帧崩溃**——真因在更深的 turn_based 多图视觉路径(官方《910C 指南》亦注明"视觉模态未验证")。**基线 79.5 真实可达**(vLLM-Omni 同模型实测 78.28%),子赛道 A 卡在视觉路径,非基线虚高。
- **Video-MME**:未跑通 —— server 处理较大视频静默崩溃(无栈、非资源)。官方 `minicpm-frames` 配方同模型可达 69.96%。
- **TTS-Seed**:WER 0.20(官方同口径 paraformer/Whisper + jiwer,**达标** ≤1.56)✅;ASV SIM 0.84(本机 WavLM base-plus 口径;官方 UniSpeech SV 口径需 `wavlm_large_finetune.pth` + UniSpeech 模型代码——平台有权重但代码 GitHub 受限,已问组委会 Q5)。
- **认知更正**:"F16 不改数学→精度=基线"对多模态 benchmark 不成立——精度受框架视觉/音频路径严重影响。
- **已向组委会发问**:`docs/organizer-inquiry-email.md`(多帧视觉配置 + 准入刚性 + 基线口径 + VideoMME 崩溃 + ASV SV 口径),等回复。
- Demo 演示视频:`benchmark/demo-video/demo_turnchat.webm` + 8 项证据 `benchmark/demo-evidence/`。
