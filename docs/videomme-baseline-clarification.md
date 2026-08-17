# Video-MME 精度基线澄清请求（子赛道 A · 2026-08-12）

> **用途**：发给组委会（contact@openbmb.cn）澄清 Video-MME 基线口径。修复多帧退化后，我队在官方 `evaluation/` pipeline 实测 **51.5%**，低于官方基线 69.0 / 准入 67.0。经充分调查，gap 非参赛代码问题（两个独立后端 + 帧数对照均佐证），疑为评测口径/环境差异，恳请赛方逐条澄清。
> 配套证据：`docs/multiframe-degradation-fix.md` §8-8.2（退化修复 + 帧数证伪）、`benchmark/video-mme-cookbook/diag/trackb_uni96.py` + `trackb_uni96_20q.csv`（Track B 对照）。

---

## 摘要

我队在**官方不可改 `evaluation/` pipeline**（`run_all.sh --tasks videomme`）实测 Video-MME **51.5%**（99 题分层子集，退化 0）。该配置（F16 / @1fps 均匀 64 帧 / temp 0 / seed 42）由官方 `evaluation/videomme/eval_cpp_config.py` 写死。为排查 51.5% vs 基线 69.0 的 gap，我队做了三项独立验证：

1. **Track B 对照**：同一台 910B 上换 HF/transformers（torch_npu）后端，同 @1fps 均匀 64 帧 = **50%**，且与 llama.cpp-omni **18/20 题答案一致** → 非 llama.cpp 视觉 encoder 质量问题。
2. **帧数证伪**：Track B 将帧数 64→96（对齐 vLLM ≤96 帧），精度 50%→55%（噪声内持平，逐题仅 3 变化）→ **gap 不是帧数**。
3. **配置穷尽**：temp 0/0.2、帧数 8/64、max_slice_nums 0/2 均无杠杆。

→ 51.5% 是 **910B + 官方 64帧@1fps 口径**的稳定真实水平（两个独立框架一致）。gap 根因疑为**官方基线 69.0 的口径/环境与子赛道 A 官方 evaluation/ 不一致**（69.0 疑似 vLLM-Omni 子赛道 B / minicpm-frames 96帧 / 910C 跑出）。请赛方澄清。

---

## 一、我队实测（官方不可改 pipeline）

**命令**：`cd evaluation && EVAL_CONFIG=<子集env> ./run_all.sh --tasks videomme --smoke 99 --no-build`（子集仅替换 `PARQUET_PATH` 指向 99 题分层 parquet，**不改 evaluation/ 任何文件**）

**配置**（官方 `evaluation/videomme/eval_cpp_config.py` 写死，无 env 覆盖）：
- 模型：MiniCPM-o-4_5 **F16** / ctx 40960 / -ngl 999 / --max-slice-nums 0
- 帧采样：**@1fps 均匀 + uniform_sample 到 MAX_NUM_FRAMES=64**（`MAX_FPS=1.0` 写死）
- 解码：temp 0.0（greedy）/ seed 42 / n-predict 100
- build-huawei（ccec 构建，含 attention -Inf F16 溢出修复 → 多帧退化已根治）

**结果**（output/20260811_211509，99 题 stratified）：

| 分层 | 官方pipeline | gap vs vLLM(96帧) |
|---|---|---|
| short | 60.6% (20/33) | −19.7pp |
| medium | 45.5% (15/33) | −24.8pp |
| long | 48.5% (16/33) | −10.7pp |
| **overall** | **51.5% (51/99)** | **−18.5pp** |

退化（`_`/NaN）= **0**（多帧退化已修复）。99 题 95%CI ≈ ±10pp。

## 二、gap 非参赛代码问题的证据

### 证据 A：Track B 对照（同 910B，换后端）
同一台 910B、同模型 F16、同 @1fps 均匀 64 帧、同 prompt、greedy，仅换推理后端：

| 后端 | 准确率（20 题）|
|---|---|
| llama.cpp-omni（子赛道 A）| 10/20 = 50% |
| HF transformers + torch_npu（独立参考实现）| **10/20 = 50%** |

两框架 **18/20 题答案完全一致**（都对 9、都错 9）→ **不是 llama.cpp 视觉 encoder 质量问题**，两个独立后端在该口径下都 ~50%。

### 证据 B：帧数对照（证伪"帧数是 gap"）
vLLM-Omni 用 minicpm-frames ≤96 帧，官方 evaluation/ 写死 64 帧。为隔离帧数变量，Track B 同框架仅变帧数：

| 帧配置 | 准确率（同 20 题）|
|---|---|
| @1fps 均匀 64 帧（官方口径）| 10/20 = 50% |
| @1fps 均匀 96 帧（对齐 vLLM）| 11/20 = 55% |

逐题仅 3 题变化（净 +1），short 完全不变（短视频 @1fps 帧<96 取全部）→ **帧数 64→96 几乎无影响**。同模型同 96 帧同 greedy：HF(910B)=55% vs vLLM=69.96% → gap 不是帧数。

### 证据 C：分层对比形态
vLLM(96帧) short80/medium70/long59 vs 我队(64帧) short61/medium46/long49：**所有层差 ~20pp，且 long 差距最小（−10.7）、short 差距最大（−19.7）**。若 gap 纯帧数，长视频应受益最大、差距最大，但相反 → 更像视觉/pipeline 系统差或环境差，非帧数。

### 证据 D：退化已根治 + 配置穷尽
- 多帧退化（曾输出 100 个 `_`）已由 attention -Inf F16 溢出修复根治，官方路径退化 0
- temp 0/0.2、帧数 8/64、max_slice_nums 0/2 全部穷尽，均无精度杠杆

## 三、我队环境

- 硬件：**Atlas 910B3**（厂家授权替代 910C），单 NPU 双 die（仅 die0/dev0 可用，die1 在 `aclnn_repeat_interleave` 崩溃 exit139）
- CANN：9.1.0-beta.1
- 框架：llama.cpp-omni 官方 `bench/huawei` 分支（ccec 构建），含 attention -Inf 修复
- 同机对照 Track B：torch 2.12 + torch_npu 2.12 + transformers 4.51

---

## 四、请赛方澄清的问题

**Q1（基线 69.0 的出处）.** Video-MME 官方基线 **69.0** 是在：
- (a) 什么**硬件**（910B 还是 910C）？
- (b) 几张卡？
- (c) 什么 **CANN 版本**？
- (d) 什么**框架**——子赛道 A 的 **llama.cpp-omni**，还是子赛道 B 的 **vLLM-Omni**（其部署指南给出 Video-MME 69.96%，使用 `minicpm-frames` ≤96 帧）？

**Q2（官方 evaluation/ 在 910B 的真实基线）.** 官方 `evaluation/`（不可改，64 帧 @1fps 写死）在 **910B 单 die** 上实测基线是多少？我队实测 51.5%、HF/transformers 同机 50%——**官方在 910B 上是否也是 ~50%**？若官方在 910B 实测显著高于 50%，请告知配置差异（我队可复现对齐）。

**Q3（子赛道 A 是否有独立可达基线）.** 若 69.0 实为 vLLM-Omni（子赛道 B，minicpm-frames 96 帧）口径，则**子赛道 A（llama.cpp-omni）在 910B 是否有独立的、用官方 evaluation/ 64 帧@1fps 实测的基线**？该基线是否就是 ~50%？

**Q4（精度准入判定）.** 精度准入规范为"相对官方基线绝对降幅 ≤2pp"。若子赛道 A 在 910B 的真实基线就是 ~50%（如 Q2/Q3 确认），则我队 51.5% **已达标**；若准入仍相对 69.0，则 910B + llama.cpp-omni + 官方 evaluation/ 物理上达不到（两个独立后端 + 帧数对照均佐证），此情形下**框架/环境受限项如何判定**（豁免 / 单独基线 / 降权）？

---

## 五、复现与附件

**复现命令**（官方 evaluation/ 不改，仅 EVAL_CONFIG 覆盖数据路径）：
```bash
cd code/llama.cpp-omni/evaluation
EVAL_CONFIG=../../benchmark/video-mme-cookbook/diag/eval-99q.env \
  ./run_all.sh --tasks videomme --smoke 99 --no-build
# 产物: output/<ts>/videomme_output.json + Accuracy 行
```
全量 2700 题同配置（仅 PARQUET_PATH 换全量、smoke=0）。

**可提供**：官方 pipeline 99 题逐题结果 json、Track B 对照脚本 + 20 题逐题 CSV、uni96 对照、build-huawei 构建日志、runtime 日志。如需我队在 910C 复测排除 910B 特有因素，请告知算力申请渠道。

---

**队名 / 参赛号**：__________________
**联系人 / 联系方式**：__________________
**日期**：2026-08-12
