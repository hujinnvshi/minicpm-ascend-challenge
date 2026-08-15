# 对组委会咨询邮件 v2（Video-MME 基线 + RTF NZ 口径 · 2026-08-15 · 可直接复制发送）

> **发送方式**：沙箱 SMTP 被封，请在**腾讯企业邮箱客户端**手动发送。
> SMTP：`smtp.exmail.qq.com` SSL `465`（或 587 STARTTLS），用户名 `zhangning@secsmart.net` + 客户端密码。
> 流程：① 发到 `zhangning@secsmart.net`（己方）审阅 → ② 补 2 个占位符（队名/联系方式）→ ③ 转发 `contact@openbmb.cn`（组委会）→ ④ 发后禁用客户端密码。
>
> 版本：v2（2026-08-15）——数字全面更新（Daily 全量 79.8、Video-MME 270 合池 63.3±5.7、RTF 新口径 1.01/1.08），新增 NZ 选择权问题 Q5；v1（2026-08-12）留档同目录。

---

**收件人（审阅）：** zhangning@secsmart.net
**最终收件人（转发）：** contact@openbmb.cn
**主题：** 【赛道一·子赛道 A 咨询】Video-MME 基线口径 + RTF 评测的 NZ 配置口径（含更新数据）

---

组委会您好，

我队参加**赛道一 · 子赛道 A（llama.cpp-omni，核心指标 SPEAK→WAV RTF）**。先前的多帧视觉退化已定位为 CANN attention 掩码 -Inf F16 溢出，按官方 `bench/huawei` 分支修复后**多帧退化已根治**（官方路径退化 0）。在此基础上我队用官方不可改 `evaluation/` pipeline 完成评测，**Daily-Omni、TTS-Seed 已达标**；**Video-MME 与基线 69.0 存在 gap**，且 **RTF 评测的 NZ 配置存在官方文档措辞矛盾**，恳请贵方逐条澄清。

**我队当前进度（2026-08-15，官方不可改 evaluation/ pipeline 实测）：**
- 性能 SPEAK→WAV RTF：**NZ=on（默认配置）e2e 1.01** / **NZ=off（官方 config.env 口径）e2e 1.08**（基线 1.087）——详见 Q5
- Daily-Omni：官方 pipeline **79.8%**（全量 1196 题；基线 79.5，准入 ≥77.5）✅
- TTS-Seed：WER **1.501%**（基线 1.414，准入 ≤1.56）✅；ASV/SIM **0.694**（基线 0.709，准入 ≥0.689）✅（NZ=off smoke 复核：WER 逐位相同、ASV 0.752 vs 0.762 噪声内，NZ 不影响生成）
- Video-MME：**63.3%±5.7pp**（270 题合池：KB 135 题 + 非 KB 135 题；99q KB 域 51.5-53.5%）❓ **本次咨询重点**
- 官方 MiniCPM-o-Demo 三进程端到端跑通（含视频）；一键复现脚本齐

---

## 一、Video-MME 我队实测（官方不可改 pipeline，NZ=off 官方路径）

**命令**：`cd evaluation && EVAL_CONFIG=<子集env> ./run_all.sh --tasks videomme --smoke 99 --no-build`（子集仅替换 `PARQUET_PATH`，未改 evaluation/ 任何文件）

**配置**（官方 `eval_cpp_config.py` 写死）：模型 F16 / ctx 40960 / -ngl 999 / 帧采样 @1fps 均匀 + uniform 到 MAX_NUM_FRAMES=64 / temp 0.0 / seed 42 / n-predict 100。

**结果（2026-08-14/15，多轮子集）**：

| 样本 | 我队 | 基线 | gap |
|---|---|---|---|
| 99q KB 域（short/med/long 各 33） | 51.5-53.5% | 69.0 | −15.5~−17.5pp |
| **270 题合池（KB 135 + 非KB 135）** | **63.3%±5.7pp** | 69.0 | **−5.7pp（误差上沿擦线）** |
| 非 KB 各批（独立重复） | 60-66% | — | — |

**KB 视频异质性极大**：同配置不同 KB 批 78.4 / 44.4 / 52.5；非 KB 批稳定 63-66%。**全量 2700 题期望 ≈63%**（分层估计），仍低于准入 67.0。

## 二、gap 非参赛代码问题的证据

**证据 A · Track B 后端对照**：同一台 910B、同 F16、同 @1fps 64 帧、同 prompt、greedy，仅换推理后端——llama.cpp-omni = 50%（10/20），HF/transformers+torch_npu = 50%（10/20），**18/20 题答案完全一致**。→ 两个独立后端同口径下一致，**非 llama.cpp 视觉 encoder 质量问题**。

**证据 B · 帧数对照**：64 帧 = 50%，96 帧 = 55%（逐题仅 3 变化，噪声内持平）→ 帧数 64→96 几乎无影响。同模型同 96 帧同 greedy：HF(910B)=55% vs vLLM=69.96%，gap 仍在。

**证据 C · 分层形态**：KB-only 子集 short/med/long 均 ~20pp 差且 long 差距最小——非纯帧数效应，更像视觉/pipeline 系统差或环境差。

**证据 D · 协议层零翻转（2026-08-15，NZ=off 下复核）**：image_id 帧编号、去语音克隆系统提示、attention FA 探针四杠杆 45 题 **逐字节零翻转**——**规则内（不改推理数学、不改 evaluation/）已无提升空间**，63%±6pp 即官方 evaluation/ + 910B 单 die 的本机上限。

## 三、我队环境

- 硬件 **Atlas 910B3**（厂家授权替代 910C），单 NPU 双 die（仅 die0/dev0 可用）
- CANN **9.1.0-beta.3**；框架 llama.cpp-omni 官方 `bench/huawei` 分支（官方不可改文件逐字节一致，已自查）
- Track B 对照：torch 2.12 + torch_npu 2.12 + transformers 4.51（同机）

## 四、请贵方澄清

**Q1（基线 69.0 的出处）.** Video-MME 官方基线 69.0 是在什么**硬件**（910B/910C）、几张卡、什么 CANN 版本、什么**框架**（子赛道 A 的 llama.cpp-omni，还是子赛道 B 的 vLLM-Omni——其部署指南给出 69.96%，用 ≤96 帧）？

**Q2（官方 evaluation/ 在 910B 的真实基线）.** 官方 evaluation/（64 帧 @1fps 写死）在 910B 单 die 实测基线是多少？我队 270 题合池 63.3%±5.7、99q KB 51.5%、HF 同机 50%——**官方在 910B 是否也是 ~63%±6 或更低**？若官方实测显著更高，请告知配置差异。

**Q3（子赛道 A 独立基线）.** 若 69.0 实为 vLLM-Omni（子赛道 B）口径，子赛道 A（llama.cpp-omni）在 910B 是否有独立的、用官方 evaluation/ 实测的基线？是否即 ~63%±6？

**Q4（精度准入判定）.** 准入为"相对官方基线绝对降幅 ≤2pp"。若子赛道 A 在 910B 真实基线即 ~63%（如 Q2/Q3 确认），我队 63.3% **已达标**；若仍相对 69.0，910B + llama.cpp-omni + 官方 evaluation/ 物理上限 ≈69（协议层零翻转证明），此**框架/环境受限项如何判定**（豁免 / 单独基线 / 降权）？

**Q5（🔴 RTF 评测的 NZ 配置选择权，新增）.** 官方 FAQ 要求"**必须保持 GGML_CANN_WEIGHT_NZ=off**，否则空串/换行复读"，但 evaluation/README §2 的 off 论证限定为"否则**精度任务**可能异常或崩溃"；config.env 注释为"off（F16 精度/vision 稳定性）"。**RTS（RTF 性能评测）任务无精度指标**（judge 仅按时长拼接音频，无转写/相似度检查）。我队实测：**NZ=on e2e RTF 1.01 vs NZ=off 1.08**（同机同配置独占各 ≥2 次），NZ 影响 ~7%——在基线 1.087 下，这决定"达标"还是"擦线"。**恳请确认：RTS 任务是否允许 NZ=on（精度任务保持 off）？** 若允许，我队将按"精度 off + RTS on"配置并在提交说明中透明披露。

---

我队可提供：270 题逐题结果 json、Track B 对照脚本 + 逐题 CSV、帧数对照、协议层零翻转 A/B 产物、NZ=on/off RTF 各次运行 json、构建日志、完整复现命令。如需在 910C 复测排除 910B 特有因素，请告知算力申请渠道。

Daily-Omni、TTS-Seed 评测细节与复现脚本已随代码提交（分支 `bench-huawei-adapt`，含 `docs/daily-omni-eval.md`、`docs/tts-seed-eval.md`）。盼逐条回复，谢谢！

此致

**队名 / 参赛号**：__________________
**联系人 / 联系方式**：__________________
**日期**：2026-08-15
