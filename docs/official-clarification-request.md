# 向赛事方确认请求（草稿）— 子赛道 A 精度评测方法对齐

> 用途：子赛道 A（llama.cpp-omni）参赛队就 Daily-Omni / VideoMME 两项精度的**评测方法对齐、门槛刚性、框架限制**，向赛事方提交的正式确认请求。
> ⚠️ 发送前请补齐：**队名 / 参赛号 / 联系人 / 联系方式 / 日期**（文末标注处）。
> 语气定位：求证 + 请求指引，非申诉。两点核心：① 求证**准入基线 79.5/69.0 的口径归属**（子赛道 A llama.cpp-omni 实测 vs 子赛道 B vLLM/原生）；② 官方 vLLM-Omni 指南证实基线可达（Daily-Omni 78.28% / Video-MME 69.96%），求子赛道 A 对齐多帧评测配方的方法。

---

**致赛事组织委员会：**

感谢组织本次「MiniCPM 昇腾推理优化与应用创新挑战赛」。我队参加**赛道一 · 子赛道 A（llama.cpp-omni，核心指标 SPEAK→WAV RTF）**，当前进度如下：

- ✅ **性能 RTF**：SPEAK→WAV 完整链路 RTF 多次复测中位 **0.68**、调优最优 **0.57**，较官方基线 **1.087** 领先约 37%–48%；
- ✅ **Demo 准入**：官方 MiniCPM-o-Demo 三进程（gateway + worker + llama-omni-server）端到端跑通，中文提问 → 流式连贯回复 + 视频；
- ✅ **复现**：一键脚本（`scripts/{serve,benchmark,demo}.sh`）+ 提交 checklist；
- ✅ **TTS-Seed WER**：**0.20**（官方同口径 Whisper-large-v3 / Paraformer-zh + jiwer，准入 ≤ 1.56，达标）；
- ⚠️ **TTS-Seed SIM**：0.84（本机 WavLM base-plus 口径，与官方 UniSpeech `wavlm_large_finetune` 口径待对齐）；
- ❌ **Daily-Omni / VideoMME**：我队在子赛道 A 上跑出的精度与官方基线差距巨大，核心疑点在**评测喂法**，特此请教。

我队已研读官方《在昇腾 NPU 上使用 vLLM-Omni 部署 MiniCPM-o 4.5》指南（子赛道 B），其中给出的评测方法使基线**真实可达**（详见 Q1）。故本请求主要围绕：**子赛道 A（llama.cpp-omni）如何对齐该配方**。烦请组委逐条确认（按优先级排列）：

---

## 一、Daily-Omni / VideoMME 评测方法对齐（最优先）

**Q1（基线口径 + 评测方法对齐，最优先）.**

**(a) 基线口径归属：** 准入基线 **Daily-Omni 79.5 / Video-MME 69.0** 的来源，希望明确确认：
- 该基线是**子赛道 A（llama.cpp-omni）的实测成绩**，还是源自**子赛道 B（vLLM-Omni）/ 原生 MiniCPM-o**（如 HuggingFace transformers）？
- 官方 vLLM-Omni 指南显示 vLLM 配方可达 Daily-Omni **78.28%**（`minicpm-interleave`：1fps帧+1s音频交错≤64帧）/ Video-MME **69.96%**（`minicpm-frames`：≤96帧 JPEG；均 temperature 0、max_tokens 128、纯文本 MCQ、`Successful HTTP` 为分母），与基线 79.5/69.0 高度吻合——**强烈提示基线可能源自 vLLM/原生路径**。若如此，子赛道 A 以子赛道 B 成绩作准入门槛是否合适？子赛道 A 是否有**独立的、基于 llama.cpp-omni 实测的精度基线/门槛**？

**(b) 子赛道 A 多帧评测配方对齐：** 上述 vLLM 配方基于 `vllm bench serve`。在 **子赛道 A（llama.cpp-omni）** 上，官方推荐的等价评测方法是什么？具体：
- llama.cpp-omni 是否支持**多帧交错打包**（对应 `minicpm-interleave`）与**多帧抽帧**（对应 `minicpm-frames`）？通过哪个协议/参数（WS `/backend`、`stack_frames`、interleave 等）启用？
- 我队实测 `stack_frames ≥ 3`（多帧）会触发 **LLM 输出全 NaN 数值崩溃**（非模型退化；逐层诊断见第四部分 2），只能退回**单帧** → Daily-Omni 仅 ~10%。这是 llama.cpp-omni 的已知限制，还是我队配置有误？烦请提供**官方推荐的子赛道 A 多帧评测配置**。

## 二、准入门槛刚性

**Q2.** 精度准入是否为**硬性门槛**（任一项未达即不进入性能排名）？是否存在**框架受限项的豁免 / 降权 / 部分得分**机制？

**Q3.** 性能排名是否**以全部精度项达标为前提**？若某项因框架配置差异客观上难以达标，我队在**性能（RTF）、Demo、复现、TTS-WER** 上的成果能否作为排名依据？

## 三、子赛道 A 官方评测脚本 + VideoMME 稳定性

**Q4.** 官方 vLLM-Omni 指南已给出**子赛道 B** 的完整 `vllm bench serve` 评测脚本（含 Daily-Omni / Video-MME / TTS-Seed）。**子赛道 A（llama.cpp-omni）是否有对等的官方评测脚本/方法**？若有，何时、在何处发布？我队目前仅有自写的 `daily_omni_test.py` / `videomme_test.py`（参照 vllm-omni 口径移植），担心与官方口径有偏差。

**Q5.** VideoMME 的官方方法（`minicpm-frames` ≤96 帧、temperature 0、max_tokens 128）已从 vLLM 指南获悉。我队在 **llama.cpp-omni** 上复现时遇到一个稳定性问题：处理 VideoMME 较大视频文件（16MB+）时 omni server **进程静默崩溃**（无堆栈、非内存/显存资源不足，单/双 server 均可复现，崩溃点不一）——这是否为已知问题？是否有推荐的 build / 配置 / 处理方式？

**Q6.** 子赛道 A 评测的**接入方式**：直连 llama-omni-server 的 WebSocket（`/backend` 或 `/v1/worker/duplex`），还是经由 gateway？是否指定 system_prompt / 采样参数（vLLM 指南用 temperature 0、repetition_penalty 1.2）？评测为**全量**（Daily-Omni 1197 / VideoMME 2700）还是抽样？

## 四、框架限制与合规跑法（佐证材料）

我队在 llama.cpp-omni 上实测 Daily-Omni / VideoMME 时，观察到以下现象，致使精度远低于基线，特附上供组委参考（其中第 2 项多帧数值崩溃已逐层定位到 CANN LLM 内部、非模型上限；其余为待确认的配置/稳定性问题）：

1. **Whisper 30s 音频窗口**：omni 音频前端按标准 whisper 30s 窗口工作；Daily-Omni 样本约 96.7% 音频 > 30s（半数 60s）。我队已加 `-t 29.9` 修复崩溃，但长音频仍被截断。官方 `minicpm-interleave` 配方将音频切成 1s 段——子赛道 A 是否应/可做等价分段？
2. **多帧数值崩溃（runtime 逐层诊断已定位，非模型上限）**：llama.cpp-omni 在 turn_based 模式下，`stack_frames ≥ 3`（多帧）触发 LLM 输出 **logits 全 NaN**（vocab 151748 个 token 的 logits 全部为 NaN，采样退化为固定不可打印 token，输出 `?`×40）。我队做了**逐层数值诊断**（omni.cpp 临时 LOG，诊断后已还原净0）：
   - **vision embedding**（CANN0 后端 ViT 输出）：8 帧全部 `nan=0 inf=0`，数值正常（max 34~40 / min -7）——**非 vision 源头**；
   - **audio embedding**（whisper 输出）+ **prefill 输入 embd**（vision+audio+text 拼接后喂 LLM 的 `batch.embd`）：全部 `nan=0 inf=0`——**非 embd 拼接问题**；
   - → **NaN 产生在 `llama_decode`（CANN 后端 LLM 前向）内部**：多步 interleave prefill（每步 +64 vision +10 audio embd）累积后，LLM attention/FFN 数值溢出 → logits 全 NaN。
   - 退化**渐进**：stack=1 正常文本、stack=2 logits 正常但语义跑偏（输出换行 + audio 边界 token）、stack=8 全 NaN。即非"开关式"崩溃。
   - 结论：**CANN 后端 LLM 在多模态多步 prefill 下的数值稳定性问题**，非模型上限、非打包布局、非 vision/audio。vLLM-Omni ≤64/96 帧正常，进一步佐证**模型本身支持多帧**，问题在 llama.cpp-omni/CANN 路径。**子赛道 A 是否已知此问题？是否有推荐的 build flag / CANN 配置 / 规避方法？**
3. **输出风格**：模型在多模态 QA 下倾向 thinking 风格输出，常不直接给出明确的 ABCD 选项。官方配方用 `enable_thinking=false` + temperature 0 约束——子赛道 A 的对应设置是什么？
4. **VideoMME 稳定性**：处理 VideoMME 较大视频文件时 server 静默崩溃（见 Q5）。

**Q7.** 官方配方本身即采用**多帧交错 + 音频分段 + 纯文本 MCQ**。在子赛道 A 上，是否**允许/期望**做等价的框架级适配（多帧交错打包、音频分段、输出格式约束）来对齐？官方是否有子赛道 A 的指定处理方式或参考实现？

---

以上确认将直接决定我队后续在精度项上的投入策略（重点：能否在子赛道 A 上复刻官方多帧评测配方、把 Daily-Omni / VideoMME 从当前 ~10% / 未跑通 拉到接近基线）。如需我队提供更详细的运行日志、复现命令或崩溃现场，请随时告知，我队将全力配合。

盼复。

**队名 / 参赛号**：__________________
**联系人 / 联系方式**：__________________
**日期**：__________________
