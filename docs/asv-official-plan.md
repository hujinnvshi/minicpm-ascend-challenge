# TTS-ASV 官方口径方案（待评审，不执行）

> 目标:用官方 UniSpeech SV 口径(ECAPA-TDNN + WavLM-large + wavlm_large_finetune.pth)重算 TTS-Seed SIM,替换当前 base-plus 0.84,对齐基线 0.709。**ASV 从 ⚠️ → ✅(精度 1/4 → 2/4)**。
> 创建:2026-08-10。流程:本方案 → 评审 → 执行 → 校验。

## SIM 算法(已调研,CookBook `tts_seed/eval_tools/speaker_verification/`)
- `verification_pair_list_v2.py`(入口,读 pair.lst `wav1|wav2` 对)
- `verification.py`(核心):
  - `init_model("wavlm_large", ckpt)` → `ECAPA_TDNN_SMALL(feat_dim=1024, feat_type="wavlm_large")`
  - `torch.load(wavlm_large_finetune.pth)["model"]` + `load_state_dict(strict=False)`
  - 算 wav1/wav2 speaker embedding + cosine
- `models/ecapa_tdnn.py`:`feat_type=wavlm_large` → **`torch.hub.load(s3prl_repo, "wavlm_large", source="local")`**(s3prl WavLM upstream 提特征)+ ECAPA-TDNN SV head

## 依赖矩阵
| 依赖 | 状态 |
|---|---|
| wavlm_large_finetune.pth (1.3GB) | ✅ shared_assets |
| 我们 20 zh wav + ref(prompt-wavs) | ✅ benchmark/seed-tts-eval |
| seedtts zh meta.lst | ✅ |
| torch / transformers | ✅ venv |
| librosa / soundfile / torchaudio / tqdm | ❓ 待查 venv,缺则 pip |
| **s3prl(s3prl/s3prl repo)** | ❌ **需 git clone**(github 通) |
| **s3prl 的 wavlm_large upstream 依赖 `microsoft/wavlm-large`(transformers)** | ⚠️ **HF 被封 → 需 modelscope/本地**(最大风险) |

## 执行步骤(评审通过后)
1. 拉 `speaker_verification/`(verification.py + verification_pair_list_v2.py + models/ecapa_tdnn.py + average.py)
2. `git clone https://github.com/s3prl/s3prl` → S3PRL_REPO
3. 解决 `microsoft/wavlm-large`(modelscope 下 / 本地缓存 / s3prl 是否自带)
4. 查/装 librosa/soundfile/torchaudio/tqdm
5. 构造 pair.lst(从 meta.lst:gen_wav | prompt-wav)
6. `python verification_pair_list_v2.py pair.lst --model_name wavlm_large --checkpoint wavlm_large_finetune.pth --device cpu --scores out.txt`
7. 汇总 20 对 SIM 平均

## 风险(评审重点)
1. **🔥 s3prl 的 wavlm_large → HF `microsoft/wavlm-large`**:s3prl 的 WavLM upstream 基于 transformers WavLMModel,要 WavLM config+weights。**HF 被封**。备选:① modelscope 下 WavLM-large;② 本地缓存(之前 base-plus 用 microsoft/wavlm-base-plus,可能有缓存机制);③ wavlm_large_finetune.pth 已含 WavLM 主干权重,strict=False 加载或许够(但要 config)。**这是方案能否成立的关键,执行前必须验证 wavlm-large 来源**。
2. **s3prl clone**:github 通,但 s3prl 较大(--depth 1)。
3. **device**:默认 cuda:0,910B4 是 NPU。用 `--device cpu`(WavLM 前向 20 wav,CPU 慢但可行 ~几分钟)。
4. **pair.lst 格式**:meta.lst 是 `id|prompt_text|prompt-wav|target_text`,要转 `gen_wav|prompt-wav` 对。
5. **ckpt 结构匹配**:ecapa_tdnn.py 的 wavlm_large 分支结构要与 wavlm_large_finetune.pth 的 state_dict["model"] 匹配(strict=False 容错,但要实质匹配)。

## 校验(执行后)
- SIM 输出 vs base-plus 0.84(应不同口径)+ 基线 0.709(同口径目标,≥0.689 达标)
- WER 用 `run_wer.py`(paraformer,对照我们 0.20)确认同口径
- 若 SIM ≈ 0.709 量级 → ASV 达标,精度 2/4

## 不执行(待评审)
**请评审**:
1. **风险 1(wavlm-large 来源)是否可解**——modelscope 有无 wavlm-large?本地缓存?s3prl 自带?这是方案闸口。
2. 步骤是否合理(s3prl clone / pair.lst / device cpu)。
3. 是否**先单独验证 wavlm-large 能加载**(步骤 1-3 小步验证),再跑全 20 对——避免装完发现 wavlm-large 拿不到白费。

建议:**先做风险 1 的可行性验证**(modelscope/本地 wavlm-large 能否到手 + s3prl 能 load),确认后再跑全流程。

## 【2026-08-10 执行实证 · ASV 本地不可实现,回退】

风险 1 验证 + A/B/C 三路全试,**卡在 UniSpeech GRP variant**(实证,非推测):

- **闸口验证**:本地 HF cache 无 wavlm;HF offline 失败(封);**modelscope 有 microsoft/wavlm-large(transformers 格式)可下** → 但 s3prl 要的是 `s3prl/converted_ckpts/wavlm_large.pt`(s3prl 自有格式),两者不通用。
- **A(modelscope s3prl converted)**:4 候选全 404,modelscope 无 s3prl converted。
- **B(wavlm_local(wavlm_large_finetune.pth))**:失败 `'cfg'` —— s3prl UpstreamExpert 期望 `{cfg, model}` 格式,我们的 SV ckpt 是 ECAPA `state_dict["model"]`,不匹配。
- **C(构造 s3prl ckpt)**:从 wavlm_large_finetune.pth 提取 `feature_extract.model.*`(WavLM 主干 488 keys)+ remap conv_layers norm(`.2.1`→`.2`)→ WavLM(large) load **missing=0**(主干可加载)。**但 wavlm_local 完整加载失败**:unexpected 暴露 `encoder.layers.N.self_attn.grep_a/grep_linear`(所有 24 层) + `relative_attention_bias` —— **wavlm_large_finetune.pth 的 WavLM 是 UniSpeech GRP(relative position)attention variant**,s3prl 标准 WavLM **无 GRP 结构**,不兼容(不是命名问题,是结构差异)。

**结论**:ASV 官方口径本地三路全堵(s3prl 无 GRP / UniSpeech 代码 github 封 / HF converted 封)。**印证 organizer-inquiry-asv-sv.md 早诊断**:该 ckpt 是 UniSpeech 格式,需 UniSpeech 加载代码。**需赛方提供 UniSpeech 代码 / 可运行 ASV 脚本 / s3prl converted ckpt**。

**回退**:保留 base-plus SIM 0.84(说明 TTS 正常,口径非官方);邮件(`organizer-inquiry-asv-sv.md`)明确求赛方提供 ASV 工具;转高 ROI 项(910C 对照 / WER 全量 / 提交材料)。
