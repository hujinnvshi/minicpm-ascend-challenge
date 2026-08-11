# 对组委会咨询邮件（Video-MME 基线澄清 · 2026-08-12 · 可直接复制发送）

> **发送方式**：沙箱 SMTP 被封，请在**腾讯企业邮箱客户端**手动发送。
> SMTP：`smtp.exmail.qq.com` SSL `465`（或 587 STARTTLS），用户名 `zhangning@secsmart.net` + 客户端密码。
> 流程：① 发到 `zhangning@secsmart.net`（己方）审阅 → ② 补 2 个占位符（队名/联系方式）→ ③ 转发 `contact@openbmb.cn`（组委会）→ ④ 发后禁用客户端密码。
>
> 关系：本邮件聚焦 **Video-MME 基线澄清**（修复多帧退化后的新情况）；性能 RTF 口径、910B/910C 排名等已于前邮（《organizer-inquiry-final.md》）提出，此处不重复，如已答复请忽略。

---

**收件人（审阅）：** zhangning@secsmart.net
**最终收件人（转发）：** contact@openbmb.cn
**主题：** 【赛道一·子赛道 A 咨询】Video-MME 基线口径澄清（多帧退化已修复，实测 51.5%）

---

组委会您好，

我队参加**赛道一 · 子赛道 A（llama.cpp-omni，核心指标 SPEAK→WAV RTF）**。先前多帧视觉退化问题已定位为 CANN 后端 attention 掩码 `-Inf` F16 溢出，按官方 `bench/huawei` 分支修复后**多帧退化已根治**。在此基础上，我队用官方不可改 `evaluation/` pipeline 完成三项精度评测，**Daily-Omni、TTS-Seed 已达标**，但 **Video-MME 实测 51.5% 与基线 69.0 存在 gap**。经充分调查（两个独立推理后端 + 帧数对照），gap 非参赛代码问题，疑为基线口径/环境差异，恳请贵方逐条澄清。

**我队当前进度：**
- 性能 SPEAK→WAV RTF 中位 **0.68**、调优最优 **0.57**（基线 1.087，已 beat）
- Daily-Omni：官方 pipeline **88%**（基线 79.5，准入 ≥77.5）✅ 超基线
- TTS-Seed：WER **1.501%**（基线 1.414，准入 ≤1.56）✅；ASV/SIM **0.694**（基线 0.709，准入 ≥0.689）✅
- Video-MME：官方 pipeline **51.5%**（基线 69.0，准入 ≥67.0）❓ **本次咨询重点**
- 官方 MiniCPM-o-Demo 三进程端到端跑通（含视频）；一键复现脚本齐

---

## 一、Video-MME 我队实测（官方不可改 pipeline）

**命令**：`cd evaluation && EVAL_CONFIG=<子集env> ./run_all.sh --tasks videomme --smoke 99 --no-build`（子集仅替换 `PARQUET_PATH` 指向 99 题分层 parquet，**未改 evaluation/ 任何文件**）

**配置**（官方 `evaluation/videomme/eval_cpp_config.py` 写死，无 env 覆盖）：
- 模型 MiniCPM-o-4_5 **F16** / ctx 40960 / -ngl 999 / --max-slice-nums 0
- 帧采样 **@1fps 均匀 + uniform_sample 到 MAX_NUM_FRAMES=64**（`MAX_FPS=1.0` 写死）
- 解码 temp 0.0（greedy）/ seed 42 / n-predict 100
- build-huawei（ccec 构建，含 attention -Inf 修复 → 退化 0）

**结果**（99 题 stratified short/medium/long 各 33）：

| 分层 | 我队(官方pipeline) | vLLM-Omni(参考,96帧) | gap |
|---|---|---|---|
| short | 60.6% | 80.33% | −19.7pp |
| medium | 45.5% | 70.33% | −24.8pp |
| long | 48.5% | 59.22% | −10.7pp |
| **overall** | **51.5%** | 69.96% | **−18.5pp** |

多帧退化（`_`/NaN）= **0**（已修复）。

## 二、gap 非参赛代码问题的证据

**证据 A · Track B 后端对照**：同一台 910B、同 F16、同 @1fps 均匀 64 帧、同 prompt、greedy，仅换推理后端——llama.cpp-omni = **50%**（10/20），HF/transformers+torch_npu = **50%**（10/20），**18/20 题答案完全一致**。→ 两个独立后端在该口径下都 ~50%，**非 llama.cpp 视觉 encoder 质量问题**。

**证据 B · 帧数对照（证伪帧数）**：vLLM 用 minicpm-frames ≤96 帧，官方 evaluation/ 写死 64 帧。Track B 同框架仅变帧数——64 帧 = 50%，96 帧 = 55%（逐题仅 3 变化、short 完全不变，噪声内持平）。→ **帧数 64→96 几乎无影响**。同模型同 96 帧同 greedy：HF(910B)=55% vs vLLM=69.96%，gap 仍在。

**证据 C · 分层形态**：所有层差 ~20pp，且 **long 差距最小（−10.7）、short 差距最大（−19.7）**——若 gap 纯帧数，长视频应受益最大、差距最大，实际相反 → 更像视觉/pipeline 系统差或环境差。

**证据 D · 配置穷尽 + 退化已修**：temp 0/0.2、帧数 8/64、max_slice_nums 0/2 全部穷尽均无杠杆；多帧退化已由 attention 修复根治（官方路径退化 0）。

→ **51.5% 是 910B + 官方 64帧@1fps 口径的稳定真实水平**（两个独立框架一致佐证）。

## 三、我队环境

- 硬件 **Atlas 910B3**（厂家授权替代 910C），单 NPU 双 die（仅 die0/dev0 可用）
- CANN **9.1.0-beta.1**
- 框架 llama.cpp-omni 官方 `bench/huawei` 分支（ccec 构建）
- Track B 对照：torch 2.12 + torch_npu 2.12 + transformers 4.51（同机）

## 四、请贵方澄清

**Q1（基线 69.0 的出处）.** Video-MME 官方基线 **69.0** 是在：什么**硬件**（910B/910C）、几张卡、什么 **CANN 版本**、什么**框架**（子赛道 A 的 llama.cpp-omni，还是子赛道 B 的 vLLM-Omni——其部署指南给出 69.96%，用 `minicpm-frames` ≤96 帧）？

**Q2（官方 evaluation/ 在 910B 的真实基线）.** 官方 `evaluation/`（不可改，64 帧 @1fps 写死）在 **910B 单 die** 上实测基线是多少？我队实测 51.5%、HF 同机 50%——**官方在 910B 是否也是 ~50%**？若官方在 910B 实测显著更高，请告知配置差异，我队可复现对齐。

**Q3（子赛道 A 独立基线）.** 若 69.0 实为 vLLM-Omni（子赛道 B）口径，则**子赛道 A（llama.cpp-omni）在 910B 是否有独立的、用官方 evaluation/ 64 帧@1fps 实测的基线**？是否即 ~50%？

**Q4（精度准入判定）.** 准入规范为"相对官方基线绝对降幅 ≤2pp"。若子赛道 A 在 910B 真实基线即 ~50%（如 Q2/Q3 确认），我队 51.5% **已达标**；若仍相对 69.0，则 910B + llama.cpp-omni + 官方 evaluation/ 物理上达不到（两个独立后端 + 帧数对照均佐证），此**框架/环境受限项如何判定**（豁免 / 单独基线 / 降权）？

---

我队可提供：官方 pipeline 99 题逐题结果 json、Track B 对照脚本 + 20 题逐题 CSV、uni96 帧数对照、build-huawei 构建日志、runtime 日志、完整复现命令。如需我队在 910C 复测排除 910B 特有因素，请告知算力申请渠道。

Daily-Omni、TTS-Seed 评测细节与复现脚本已随代码提交（分支 `bench-huawei-adapt`，含 `docs/daily-omni-eval.md`、`docs/tts-seed-eval.md`）。盼逐条回复，谢谢！

此致

**队名 / 参赛号**：__________________
**联系人 / 联系方式**：__________________
**日期**：2026-08-12
