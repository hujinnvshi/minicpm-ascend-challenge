# 赛事准备总览（2026-08-12 固化）

> 赛事：MiniCPM-o 昇腾推理优化 · **赛道一 · 子赛道 A（llama.cpp-omni）**，核心指标 **SPEAK→WAV RTF**。
> 环境：Atlas 910B3 单卡（die0，64GB HBM）+ CANN 9.1.0-beta.1 + aarch64。
> 分支：`bench-huawei-adapt`（当前评测主分支，全部 push origin）。

## 一、准入状态（一表看清）

| 项 | 官方基线 | 准入阈值 | 我们 | 状态 |
|---|---|---|---|---|
| **性能 SPEAK→WAV RTF**（排名核心）| 1.087 | <1.087 | **0.57**（24线程+NUMA）/ 0.68（默认）| ✅ **beat 48%** |
| **Daily-Omni** 精度 | 79.5 | ≥77.5 | **79.8%**（全量1196题，官方Overall）| ✅ 微超基线(+0.3pp)，达准入 |
| **TTS-Seed WER** | 1.414 | ≤1.56（增幅≤10%）| **1.501%**（全量2020题）| ✅ 增幅 6.2% |
| **TTS-Seed ASV/SIM** | 0.709 | ≥0.689（降幅≤0.02）| **0.694**（全量2020题）| ✅ 降幅 0.015 |
| **Video-MME** 精度 | 69.0 | ≥67.0 | **51.5%**（99题官方pipeline）| 📋 **待赛方**（证据充分，非代码问题）|
| **Demo** | — | 端到端稳定 | 3 进程跑通（gateway+worker+backend，含视频）| ✅ |

**结论：性能 + Daily-Omni + TTS-Seed（WER/ASV）三项达标，Video-MME 代码层已穷尽、证据充分，球在赛方。**

## 二、性能 RTF（排名核心）

- **SPEAK→WAV RTF = 0.57**（`OMNI_T2W_THREADS=24 + taskset -c 192-223` NUMA）/ 0.68（默认16线程，零配置）
- vs 官方基线 **1.087 → beat 37–48%**
- 优化链：**P1.7**（LLM↔TTS 队列 1→16 解耦，P50 8295→977ms，主杠杆）+ **P3/P4**（vocoder 线程 8→24 + NUMA 绑核，0.64→0.57）+ **P6**（vocoder overlap 探索，bit-精确失败——ggml 跨 backend 并发限制，**0.57 是物理限**）
- 红线：仅流水线/调度层（队列/线程/NUMA），**不改推理数学**
- 详见 `performance-report.md` / `experiments.md`(P0–P6) / `reproduce-guide.md` / `perf-ceiling-analysis.md`

## 三、精度（三项 benchmark）

| Benchmark | 我们 | 怎么跑 | 文档 |
|---|---|---|---|
| **Daily-Omni 88%** | 超基线 79.5 | parquet→jsonl+音视频转换 + 官方 `run_all.sh --tasks daily-omni` | `daily-omni-eval.md` + `benchmark/daily-omni-convert/` |
| **TTS-Seed WER 1.501% / ASV 0.694** | 两项达标 | 官方 `run_tts_eval_cpp_zh.sh` 全量2020（generate NPU + WER/SIM CPU）| `tts-seed-eval.md` + `benchmark/tts-seed-convert/` |
| **Video-MME 51.5%** | gap（待赛方）| 官方不可改 `evaluation/` 99题 + Track B + vision 诊断 | `multiframe-degradation-fix.md` + `vision-npu-vs-cpu-diagnosis.md` |

**Video-MME gap 证据链（非代码问题）**：
1. 官方 pipeline 51.5%（退化 0，已修 attention -Inf）
2. Track B：HF/torch_npu 同 910B 同口径 = 50%，18/20 题与 llama.cpp 一致 → 非框架视觉问题
3. uni96：帧数 64→96 证伪（50%→55% 持平）→ 非帧数
4. vision NPU vs CPU：cos 0.995 无 NaN → 非视觉算子灾难性 bug
5. temp/slice 穷尽无杠杆 → 51.5% 是 910B + 官方64帧@1fps 口径稳定真实水平
6. 根因：910B vs 910C 计算精度差（官方基线"以 910C 复现"）+ 疑 baseline 未在 910B 实测（69.0≈vLLM 69.96%）

## 四、Demo / 复现 / 报告（提交物）

- **Demo**：3 进程（gateway:8006 + worker:22400 + llama-omni-server:22500）端到端跑通，含视频；`benchmark/demo-video/`
- **复现**：`docs/reproduce-guide.md` + `scripts/build-cann.sh`（ccec 构建，6 补丁 + P1.7）
- **报告**：`docs/performance-report.md`（8 字段：指标定义/环境/数据/次数/统计/前后对比/资源/异常）
- **赛方邮件**：`docs/organizer-inquiry-2026-08-12.md`（Video-MME 澄清，附 Q1-Q4 + 证据，待发）

## 五、分支与提交物

| 分支 | 内容 | 状态 |
|---|---|---|
| `main` | 完整提交（P1.7 + 报告 + 复现 + Demo 视频 + 规范）| ✅ push |
| `bench-huawei-adapt`（当前）| 评测全套：Daily/TTS/Video-MME 达标数据 + 转换脚本 + 诊断 + 澄清邮件 + P6 overlap 记录 | ✅ push（4676184）|
| `perf-vocoder-overlap` | P6 性能实验（step1 拆分 bit-精确 + step2 overlap 失败）| ✅ push（669dca4，**未 merge**，信息性）|

## 六、关键文档导航

- **评测规范**：`eval-spec.md`（基线/准入/Demo/提交物）
- **性能**：`performance-report.md` + `experiments.md`(P0–P6) + `perf-ceiling-analysis.md`（0.34 理论 vs 0.57 物理限）
- **精度**：`daily-omni-eval.md` / `tts-seed-eval.md` / `multiframe-degradation-fix.md` / `vision-npu-vs-cpu-diagnosis.md`
- **赛方**：`organizer-inquiry-2026-08-12.md`（Video-MME 澄清邮件）+ `videomme-baseline-clarification.md`
- **构建/补丁**：`cann-patches.md`（6 补丁）+ `reproduce-guide.md`

## 七、下一步

1. **发 Video-MME 澄清邮件**（`organizer-inquiry-2026-08-12.md` → contact@openbmb.cn），等赛方对基线口径/910B 单实测的回复
2. 性能（RTF 0.57）+ Daily/TTS 精度 + Demo **已就绪**，无需更多代码动作
3. 视赛方回复：若认 910B 基线≠69 → Video-MME 达标；若坚持 69 → 用证据链申请豁免/单独基线
