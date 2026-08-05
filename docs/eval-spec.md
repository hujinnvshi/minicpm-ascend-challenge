# 官方评测规范（2026-08-05 发布）— 赛道一·高性能推理优化

> 来源：官方通知《MiniCPM 昇腾挑战赛 · 高性能推理优化赛道 — 评测规范说明》
> 我们 = **子赛道 A（llama.cpp-omni，核心指标 RTF）**。子赛道 B（vLLM-Omni）独立排名，不相关。

## 一、精度准入（全部满足才进性能排名，两子赛道标准相同）

| Benchmark | 基线(F16) | 准入阈值 | 我们的口径 |
|---|---|---|---|
| **VideoMME** | 69.0 | ≥ 67.0（降幅 ≤2pp） | F16 不改模型 → 应 = 69.0，过 |
| **Daily-Omni** | 79.5 | ≥ 77.5（降幅 ≤2pp） | F16 → 应 = 79.5，过（注：非公开 leaderboard 的 Qwen 61.82，那是另一框架） |
| **TTS-Seed ASV**（说话人相似度） | 0.709 | ≥ 0.689（降幅 ≤0.02） | WavLM 算 SIM；F16 → 应 = 0.709 |
| **TTS-Seed WER** | 1.414 | ≤ 1.56（增幅 ≤10%） | Whisper 算 WER；F16 → 应 = 1.414 |

**关键认知**：基线是 **llama.cpp-omni 框架自身的 F16 基线**。我们的优化（P1.7 队列解耦/host_buffer/use_mmap）是**流水线/调度层，不改推理数学** → 推理输出 = F16 数学等价 → **精度 = 基线，准入必过**（只要把 4 个数跑出来）。精度风险 ≈ 0，工作量 = 跑通 4 个评测。

## 二、性能基线（单并发，F16）— 子赛道 A

- **指标 = SPEAK→WAV 完整链路 RTF**，基线 **1.087**。
- ⚠️ **官方明确**：主要优化目标是 **SPEAK 生成阶段的 RTF**，**不是全部 chunk 的平均 RTF**。
- 含义：RTF = (SPEAK→WAV 处理时间) / (音频时长)；<1 = 快于实时。基线 1.087（略慢于实时）。**我们要 beat 1.087（越低越好）。**
- 我方现状（P1.7）：perf-duplex e2e RTF ~0.81 / TTS RTF 0.80（SPEAK chunk）—— **已低于 1.087**。但需按官方"SPEAK→WAV 完整链路"口径**重测确认**（当前 e2e RTF 与官方口径的对齐待确认）。

### 实测（2026-08-05，P1.7 config，36 帧 perf-duplex）
- **SPEAK→WAV 完整链路 RTF = 0.83**（e2e wall 44.44s / 音频 53.84s）；TTS RTF 0.82。
- vs 官方基线 **1.087 → beat ~24%**。✅ 性能排名指标通过且领先。
- ⚠️ 澄清：perf-duplex 的 `exit 2`（LLM P95/首响 <1000ms）是**本工具更严的"双工实时交互"门槛，非官方排名指标**。官方性能只看 SPEAK→WAV RTF。P2 死磕 exit-0/首响 是超纲（低延迟对 Demo 体验有益但不影响 RTF 排名）。

## 三、Demo 准入（硬门槛）

- ⚠️ "仅能跑 Benchmark 但**无法接入官方 Demo** 的方案，不满足准入条件"。
- 我方：G3 Demo 已端到端跑通（gateway+worker+backend，P1.7 build，中文提问→连贯流式回复）。✅ 基本满足。

## 四、最终提交内容（5 块）

1. 完整代码与配置（llama.cpp-omni 6 补丁 + P1.7 队列解耦 + build-cann）
2. 三项 Benchmark 评测结果（VideoMME / Daily-Omni / TTS-Seed ASV+WER）
3. 性能测试报告（SPEAK→WAV RTF，含口径/环境/数据/次数/前后对比）
4. 可运行 Demo（+ 演示视频）
5. 优化与复现说明

## 五、对我们策略的确认与调整

- **方向确认正确**：P1.7（perf）+ G2（benchmarks）+ G3（demo）正是三大准入/排名项。
- **性能**：RTF 已 beat 基线 1.087（~0.81）；需按官方口径重测 SPEAK→WAV。
- **精度**：4 数 = F16 基线（P1.7 不改数学）→ 跑通即过；**风险在工程（数据+跑通），不在精度**。
- **数据现状**：TTS-Seed 本地全齐（seed-tts-eval testset + WavLM，只缺 Whisper）；VideoMME 平台下载中；Daily-Omni 需用户下 Videos.tar。
- **执行序**：① 按 SPEAK→WAV 口径重测 RTF（确认 beat 1.087）→ ② 跑 TTS-Seed（本地，出第一个精度数）→ ③ Daily-Omni（用户数据到位）→ ④ VideoMME（平台下载完）→ ⑤ G5 提交材料。
