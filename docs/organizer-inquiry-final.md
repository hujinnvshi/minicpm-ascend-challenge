# 对组委会咨询邮件（整合定稿 · 可直接复制发送）

> **本文件 = 3 份旧草稿整合后的主邮件。** 关系：
> - 旧 `organizer-inquiry-email.md` ⊂ `official-clarification-request.md`（后者更全）→ 已并入本文件；
> - **性能 RTF 口径 + 910B/910C 环境差异**（旧稿均缺，仅自报成绩）→ 本次新增为 Q1/Q2；
> - **TTS-Seed ASV(SIM)** 技术点独立，仍用 `organizer-inquiry-asv-sv.md` 单独发送（质量已高，不重写）。
>
> 发送方式：沙箱 SMTP 被封，请在**腾讯企业邮箱客户端**手动发送。
> SMTP：`smtp.exmail.qq.com` SSL `465`（或 587 STARTTLS），用户名 `zhangning@secsmart.net` + 客户端密码。
> 流程：① 发到 `zhangning@secsmart.net`（己方）审阅 → ② 补 3 个占位符 → ③ 转发 `contact@openbmb.cn`（组委会）→ ④ 发后禁用客户端密码。

---

**收件人（审阅）：** zhangning@secsmart.net
**最终收件人（转发）：** contact@openbmb.cn
**主题：** 【赛道一·子赛道 A 咨询】性能 RTF 口径与 910B/910C 环境差异、精度评测方法对齐

---

组委会您好，

我队参加**赛道一 · 子赛道 A（llama.cpp-omni，核心指标 SPEAK→WAV RTF）**。性能、Demo、复现、TTS-WER 已就绪，但在**性能排名可比性**与**精度评测口径对齐**上遇若干需确认的问题，恳请逐条指引。以下每问均附我队**实测数据与所采用口径**，便于贵方核验。

**环境说明（贯穿所有问题）：** 我队运行环境为 **910B3**（厂家授权替代 910C，未在 910C 复测）。贵方性能/精度基线均标注"昇腾 910C"。此差异是 Q1 的核心。

**我队当前进度（供参考）：** 性能 SPEAK→WAV RTF 多次复测中位 **0.68**、调优最优 **0.57**（基线 1.087，口径见 Q2）；官方 MiniCPM-o-Demo 三进程端到端跑通含视频；一键复现脚本齐；TTS-Seed WER **0.20**（≤1.56 ✅）。

---

## 一、性能排名可比性

**Q1（910B3 / 910C 环境差异，最优先）.** 性能基线"全部 chunk 平均 RTF 0.618 / SPEAK→WAV 完整链路 RTF 1.087"均标注"昇腾 910C，单并发"。我队受限于 910B3。请明确：
- 910B3 上的 RTF 成绩与 910C 基线**如何对比排名**？官方是否提供 910B→910C 的性能换算系数，或 910B3 选手**单独排名**？
- 是否需要我队在 **910C 上复测**以进入统一排名？若算力由贵方统筹，申请渠道与时序？

**Q2（SPEAK→WAV RTF 口径对齐）.** 按贵方定义 RTF = 音频 chunk 生成耗时 / 音频 chunk 时长，以 SPEAK 生成阶段为核心。为对齐口径，请确认我方测算方式是否与官方一致：
- **我方口径**：自研 perf-duplex 工具，通过 omni 音频输出回调钩子采集**每个 wav chunk 落盘时刻 + 时长**（duration = n_samples / sample_rate），SPEAK 轮与音频轮按**时间戳匹配**（非数组下标）。计算两个候选口径：① **TTS RTF** = LLM 判定完成(t_done) → 该轮末 wav 落盘耗时 / 该轮音频总时长；② **e2e RTF** = SPEAK 轮首帧 push → 末 wav 落盘 / 音频时长（含 LLM 等待，仅展示）。**我方"中位 0.68 / 最优 0.57"采用①TTS RTF。**
- 请明确：**(a)** 官方"chunk"对应我方哪个粒度（单个 wav 落盘片段 / 整轮 SPEAK 音频）？**(b)** "SPEAK 生成阶段"**是否包含"SPEAK 尾部"**（LLM 已结束、仅 TTS/T2W 收尾）？**(c)** 基线值 1.087 对应"平均 1087.3 ms"——据此推断**官方 chunk 时长基准为 1 秒**，是否正确？
- 综上，我方应以**①TTS RTF 还是②e2e RTF** 对齐官方基线 1.087？

## 二、精度基线口径与门槛

**Q3（基线口径归属 + 子赛道 A 多帧对齐）.**
**(a)** 准入基线 Daily-Omni 79.5 / Video-MME 69.0 的来源：是**子赛道 A（llama.cpp-omni）实测**，还是源自**子赛道 B（vLLM-Omni）/ 原生 MiniCPM-o**？贵方《vLLM-Omni 部署指南》给出的 vLLM 配方可达 Daily-Omni 78.28% / Video-MME 69.96%（与基线高度吻合），提示基线可能源自 vLLM/原生路径。若是，子赛道 A 是否有独立的、基于 llama.cpp-omni 实测的精度门槛？
**(b)** 我队在 llama.cpp-omni turn_based 模式实测：**多帧视频（stack_frames ≥ 3）稳定触发 LLM logits 全 NaN**。逐层诊断：vision / audio / prefill 输入 embd 均无 NaN，NaN 产生在 **CANN 后端 `llama_decode` 内部多步 prefill 累积溢出**；stack=1 正常、stack=2 语义跑偏、stack=8 全 NaN，**渐进式非开关式**。单帧 Daily-Omni 仅 ~10%。而 vLLM-Omni ≤64/96 帧正常，证明**模型本身支持多帧**，问题在 llama.cpp-omni/CANN 路径。**子赛道 A 是否有官方推荐的多帧评测配置？该 NaN 是否在官方 910C 环境复现？是否需我队在 910C 重测排除 910B 特有因素？**

**Q4（框架受限精度项的准入认定）.** 我队理解精度准入为硬性门槛（规范 4.1：须同时满足）。对于子赛道 A 因**框架客观限制**可能难以达标的精度项（如 Q3 多帧视觉），贵方认定机制是：仍按统一门槛刚性判定，还是对框架受限项有**豁免 / 降权 / 部分得分**？此点直接决定我队后续投入策略。

## 三、评测执行

**Q5（官方脚本 + 接入方式）.**
**(a)** 群内已确认**基线评测脚本正在准备中**。进一步请确认：该脚本是否覆盖**子赛道 A（llama.cpp-omni）**并与子赛道 B（`vllm bench serve`）对等？预计发布时序？我队目前仅自写 `daily_omni_test.py` / `videomme_test.py`（参照 vLLM 口径移植），盼以官方脚本为准对齐。
**(b)** 子赛道 A 评测接入方式：直连 llama-omni-server WebSocket（`/backend` 或 `/v1/worker/duplex`）还是经 gateway？是否指定 system_prompt / 采样参数（vLLM 用 temperature 0、repetition_penalty 1.2、enable_thinking=false）？评测为**全量**（Daily-Omni 1196 / VideoMME 2700）还是抽样？

**Q6（VideoMME 稳定性）.** 我队 omni server 处理 VideoMME 较大视频（16MB+）时**进程静默崩溃**（无堆栈、非内存/显存资源不足，单/双 server 均可复现，崩溃点不一）。是否已知问题？有无推荐 build / 配置？

---

**关于 TTS-Seed ASV（SIM）评测口径**：官方 SIM 用 UniSpeech SV checkpoint，评测环境**有权重但无加载代码**，技术点独立，**另发专邮详询**（见 `organizer-inquiry-asv-sv.md`），此处不展开。我队 TTS-Seed WER 0.20（paraformer + jiwer，≤1.56）已达标。

我队可提供完整 runtime 日志、perf-duplex 原始 JSON、多帧 NaN 崩溃的逐层诊断现场与复现命令。盼逐条回复。

此致

**队名 / 参赛号**：__________________
**联系人 / 联系方式**：__________________
**日期**：__________________
