# ASV SV 评测口径询问(单独发送)

> 发送方式:沙箱 SMTP 被封,请在**腾讯企业邮箱客户端**手动发送。
> **流程**:先发 `zhangning@secsmart.net` 审阅 → 补 3 个占位符 → 转发 `contact@openbmb.cn`。发送后禁用客户端密码。
> 与主询问(`organizer-inquiry-email.md`)的关系:主询问覆盖多帧视觉/准入/基线/VideoMME;**本文聚焦 TTS-Seed ASV(SIM)评测口径**,可单独、优先发送(技术点明确、回复成本低)。

---

**收件人(审阅):** zhangning@secsmart.net
**最终收件人(转发):** contact@openbmb.cn
**主题:** 【赛道一·子赛道 A 咨询】TTS-Seed ASV(说话人相似度)官方评测脚本与 SV 模型加载方式

---

组委会您好,

我队参加**赛道一 · 子赛道 A(llama.cpp-omni)**。就 **TTS-Seed ASV(说话人相似度 SIM)** 这项精度准入(基线 0.709 / 准入 ≥0.689)的**官方评测口径**,有一个明确的技术问题恳请指引。

**背景与现状:**
- 我队 TTS-Seed **WER 0.20**(官方同口径 paraformer/Whisper + jiwer,≤1.56 ✅)已达标;但 **ASV SIM 目前只有 0.84,是用 HF `microsoft/wavlm-base-plus` 算的(非官方口径)**,无法与基线 0.709 直接比较。
- 我们注意到**官方 SIM 用 UniSpeech `verification_pair_list_v2.py` + 微调过的 WavLM SV checkpoint**,且该 checkpoint 已预置在评测环境:`/workspace/shared_assets/datasets/CowboyZ/seed-tts-eval/wavlm_large_finetune.pth`(1.24 GB)。

**我们检查了该 checkpoint 的结构**,确认它是 **UniSpeech 格式的 WavLM-Large 说话人验证模型**:
```
model (711 keys):
  feature_weight (25)
  feature_extract.model.*            ← WavLM-Large 主干(卷积特征提取 + 24 层 transformer)
     .self_attn.grep_a / grep_linear ← UniSpeech GRP 注意力(非标准 HF WavLM)
  layer1/2/3/4 + pooling + bn + linear ← 说话人验证头(x-vector 式)
best_valid_eer (float)
```

**问题:** 我们**在评测环境内全面检索过**,`verification_pair_list_v2.py` 及 UniSpeech 的 SV 模型类(GRP 注意力 + SV head 的加载代码)**均不在平台任何路径**;而该代码所在的 `microsoft/UniSpeech` GitHub 仓库,**从评测环境无法访问**(出站受限,GitHub/HF 不通)。即:**平台有"SV 模型权重",但没有"加载并运行它的程序"**。

**恳请明确:**

1. **子赛道 A 选手应如何运行官方 ASV SV 评测?** 是否有官方提供的、可在评测环境直接执行的脚本 / Docker / 命令?
2. `verification_pair_list_v2.py`(或等价 SV 推理脚本)**从何处获取?** 是否会随官方 benchmark 脚本一并发布?若是,计划何时?
3. 若需自行从 `microsoft/UniSpeech` 拉取模型加载代码,**评测环境无法访问 GitHub**,是否可由官方提供该部分代码的镜像 / 离线包?
4. 官方 SIM 计算的关键参数(如 pooling 模式、采样率、音频归一化、 enrol/test 切分)应如何对齐,以保证与基线 0.709 同口径?

我队可提供:平台 checkpoint 路径、我们现有的 base-plus SIM 流程、以及上述 checkpoint 结构的完整 key 列表。盼回复。

此致

**队名 / 参赛号**:__________________
**联系人 / 联系方式**:__________________
**日期**:__________________
