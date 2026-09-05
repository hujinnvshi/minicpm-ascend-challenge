# DFlash 资产保全 + 自训方法论文档（2026-09-05）

> 目的：①「等我启动」队 DFlash 方案与模型作为**可复用资产**保全（用户确认以后会用到）；
> ② 对方 training.md 方法论浓缩——未来**自己设计并训练 draft 模型**的参考蓝本。
> 关联：docs/competitor-intel-dflash-2026-08-26.md（方案分析）+ docs/dflash-probe-2026-09-05.md（探针环境/冒烟）

## 一、资产清单（本机路径 + 校验和 + 恢复命令）

| 资产 | 路径 | 校验和/说明 | 恢复命令 |
|---|---|---|---|
| draft 模型（84MB） | /workspace/hf-models/cs-qyzhang/MiniCPM-o-4_5-tts-dflash/ | model.safetensors sha256 `d5f0b42e...c28b`；config.json `3f3f78ba...5052` | curl hf-mirror.com/cs-qyzhang/MiniCPM-o-4_5-tts-dflash/resolve/main/{config.json,config.py,model.safetensors} |
| base 模型（18.7GB） | /workspace/hf-models/OpenBMB/MiniCPM-o-4_5/ | 54 文件（4×safetensors + 远程代码 + assets） | modelscope snapshot_download('OpenBMB/MiniCPM-o-4_5') |
| 对方代码（15MB） | /workspace/hf-models/third-party/tts-dflash-intel/ | git clone 备份（含 benchmark/simplex/duplex + training.md） | git clone https://github.com/cs-qyzhang/minicpm-o-4.5-tts-dflash |
| 运行 venv | /workspace/venv-dflash | python3.12 + torch 2.8 CPU + transformers 4.51（依赖清单见 dflash-probe 文档） | 按 dflash-probe-2026-09-05.md §二 重建 |
| CPU patch 脚本 | /tmp/patch-stepaudio2-cpu.sh（已备份至 repo 文档） | 27 处 CUDA→CPU 硬编码替换 | 见 dflash-probe §三 |
| 评测输出 | /workspace/hf-models/dflash-bench/ | bench1.json（冒烟）+ 进行中 | — |

⚠️ /workspace 为本地 overlay（非 NFS），**云机重置会丢**；重要资产另备：模型可随时重下（上面恢复命令），
代码/方法论文档已在 git（docs/），venv 可重建。模型本体 18.7GB 不建议入库，恢复命令即保障。

## 二、对方官方 benchmark 自测（20 样本套件，训练后最终模型，seed 42）

> 条件：draft temp 0.8 / verifier temp 0.8（全 vocab）/ distribution-preserving（accept_top_k=0，
> lossless）/ block=8 提议 7 token。**这是我们复测的基准表，our 复测目标 = 复现 overall 行。**

| Group | Samples | Rounds | Acceptance | EAL | **tokens/round** |
|---|---:|---:|---:|---:|---:|
| **overall** | **20** | **1724** | **22.24%** | **1.5568** | **2.5516** |
| en | 7 | 602 | 25.72% | 1.8007 | 2.7973 |
| zh | 13 | 1122 | 20.37% | 1.4260 | 2.4198 |
| qa | 6 | 812 | 23.82% | 1.6675 | 2.6626 |
| read | 11 | 815 | 21.17% | 1.4822 | 2.4785 |
| style | 1 | 42 | 20.07% | 1.4048 | 2.4048 |
| translate | 2 | 55 | 16.36% | 1.1455 | 2.1091 |

（12068 proposed / 2684 accepted / 4399 codec tokens / 46.5s decode；EAL 满分 7/轮）

**我方复测**：冒烟 zh-read-short tokens/round=2.6731（略高于其 read 类均值 2.4785，短句样本偏高，合理）。
→ 复测环境可信。全量 20 样本跑完若 overall ≈ 2.55 即完成独立复现闭环。

## 三、自训方法论浓缩（对方 training.md，未来自己训 draft 的蓝本）

### 3.1 为什么能训（机制前提）
- Talker 条件输入 = emb_text + projector_semantic(thinker_hidden)（L2-norm）+ emb_code[0] 反馈
- draft 输入必须用 **per-position input embedding**（不是 token id）——embedding-fed 是核心设计
- verifier（Talker）权重冻结；可训练 = fc + 2 norms + N 层 draft decoder（~30M 参数）

### 3.2 数据构造（纯文本语料即可——Talker 条件无图像/音频特征）
- 语料：DailyDialog/Topical-Chat（英）、NaturalConv/LCCC（中，去空格 detokenize）、open-perfectblend
  （英，只留单行 assistant 输出——TTS 对含换行的 LLM 输出朗读有精度问题）
- 请求构造两种模式混合：
  1. repeat：utterance 既是输入又是输出（"Please repeat: <句>" → <句>）
  2. multi-turn：k 条请求带前 2k 轮累积对话，末轮 assistant 为 teacher-forcing 目标
- 奇数轮 user → repeat 请求；偶数轮 assistant → multi-turn 请求（同一 utterance 两种覆盖）

### 3.3 数据生成（vllm-omni fork，teacher-forcing 记录）
- 三段裁两段：Thinker + Talker，**不加载 Code2Wav**（与 drafter 训练无关，提速明显）
- teacher forcing：assistant 段包 <|tts_bos|>answer<|tts_eos|>，禁 add_generation_prompt，
  Thinker max_tokens=1（只 prefill 拿 hidden，跳过 decode）→ hidden 交给 Talker 全自回归
- 强制 use_tts_template=true + enable_thinking=false（对齐真实音频路径的 <|tts_bos|> 边界）
- **禁用 prefix caching**（会跳 re-embed 造成 inputs_embeds 空洞）
- 记录层：Talker 层 {2,6,10,14,17}（20 层均匀 5 层）+ 末层（框架自动追加，verifier teacher logits 源）
  ——层配置一旦固定训练侧必须逐字一致（KV-injection 对齐）

### 3.4 记录格式（格式契约，可自实现）
| Field | Shape | 含义 |
|---|---|---|
| input_embeds | [C+2+T, 768] | C 条件 tokens（emb_text+projector 逐位求和）+2 边界(<text_eos>,<audio_bos>)+T codec 反馈 emb_code[0] |
| hidden_states | [C+2+T, 6, 768] | 捕获层 {2,6,10,14,17}+末层（pre-final-norm，训练框架自己 apply verifier_norm） |
| loss_mask | [C+2+T] | 条件前缀 0，codec 位置 1 |
| codec trajectory | [T] | Talker 实际采样轨迹（EOS 不入序列，作最后监督目标） |

- 记录服务器**真实采样轨迹**（非确定性重放），采样参数随样本保存
- merge/finalize：codec 非空 + EOS 正常结束才留；Talker 截断丢弃；d2t/t2d 恒等映射；mask=6562 不在预测 vocab
- **规模：5 语料合并 460k 样本，bf16 ~10.5KB/token，总量 ~1TB**（复现需预留磁盘）

### 3.5 Talker 提取（独立 verifier）
tts.emb_code.0 → model.embed_tokens；tts.head_code.0（weight_norm 重组）→ lm_head；
tts.model.norm → model.norm；embed/lm_head 各追加 1 行作 mask token（id 6562）——20 层 backbone 原样保留。

### 3.6 Draft 架构（ablation 后选择）
4 层 Qwen3（hidden 768 = Talker 同宽 / FFN 2304 / 12 head 全 attention 无 sliding window / vocab 6563）≈ **30M 参数**
——单次 draft 前向成本远低于 20 层 verifier。ablation 空间：depth{2-5}×FFN{1536,2304,3072}×attn{full,sliding}
×block{4,6,8,12,16}（每组合 1 run 无多 seed，不 exhaustive）。

### 3.7 训练配置
| Item | Value |
|---|---|
| speculator | dflash（sample_from_anchor=false） |
| block size | 8（每轮 7 个推测 token，写入 checkpoint） |
| target layer ids | 2 6 10 14 17（KV-injection，与记录层一致） |
| loss | KL(draft vs teacher logits)，positional decay fixed-exp-decay（gamma 4.0） |
| optimizer/lr | Muon / 3e-4 |
| epochs | 8（checkpoint_best = 最低 val loss） |
| 采样对齐 variant | temp 0.8 / top-k 25 / top-p 0.85（对齐部署时 verifier 截断采样；draft 侧只 temperature 生效） |

### 3.8 speculators 框架改动（仅 2 处）
1. 数据管线：样本可只带 input_embeds 无 input_ids
2. DFlash 核心：anchor slot（每 block slot 0）不再收 token id，直接覆写 verifier 的 per-position embedding

## 四、未来自训路径建议（铺路视角）

1. **复用现成 draft**（近期）：直接加载 cs-qyzhang 权重 → 评估/移植（零训练成本）
2. **针对自己 verifier 微调/重训**（中期）：若换 verifier（不同 codec/架构）→ 按 §3 管线重走；
   改进空间 = 对方自认：语料更贴近官方评测分布、ablation 补多 seed、采样对齐 variant 调优
3. **工程前提**：需要 NVIDIA GPU 训练环境（speculators 框架 CUDA 系；910C 昇腾需 torch_npu 适配，
   未验证）+ ~1TB 记录数据磁盘 + vllm-omni fork 记录管线
4. **本方案对 llama.cpp-omni 移植的落点**：draft 权重 GGUF 化（4 层 Qwen3 + KV-injection 自定义层）
   + omni.cpp TTS decode 循环改造（多 token 并行验证已被 FA contiguity 修复解锁）

## 五、推测解码通用范式（为什么到处能用——方法论层）

**机制本质**：用"并行验证"换"串行猜测"。NPU/GPU 并行前向成本远低于串行轮次（batch 大 N 倍
只贵一点），而自回归的逐 token 串行是硬成本。draft 质量决定收益（EAL），但"猜错"惩罚只是
退回原位不亏本——哪怕接受率 23%（DFlash 实测）也有 2.67× 净推进。

**三条成立条件**（评估任何新场景是否可挂推测解码）：
1. 目标模型自回归串行生成（逐 token 依赖，无法并行）
2. 存在廉价猜测器（小模型 / N-gram / 规则近似；embedding-fed 可解决非 token-id 输入）
3. 验证成本 < 省下的串行成本（需实测，用 tokens/round 判）

**适用场景清单**（猜测器 / 先例）：
| 场景 | 猜测器 | 状态 |
|---|---|---|
| 通用 LLM 文本生成 | EAGLE / Medusa / 自推测 / 小 draft | 工业界标配 |
| TTS 音频 codec 生成 | DFlash（本文）| 对方验证 tokens/round 2.55 |
| 自回归语音合成（CosyVoice/GPT-SoVITS 系）| 同思路 | 架构同源，方法论直接搬 |
| 自回归图像/视频 token | VAR / LlamaGen 类 | 学术圈已验证 |
| 多模态流式解码 | 各路共享/独立 draft | 前沿 |

**lossless 保证**：distribution-preserving 接受（min(1,p/q) + 残差重采样）→ 输出分布与
verifier 原样数学等价——这是推测解码区别于 layer-cap 等"改推理数学"方案的根本优势，
可过最严精度门禁（greedy 下逐字节一致）。
