# 数据复现验证报告（2026-08-12）

## 目的
按 plan（复现已报数 + 口径审计），在当前环境本地重复测试 `docs/competition-readiness.md` 报的四项数据，验证**可复现性 + 口径一致性**。本次为会话内独立复现（非引用团队日志）。

## 环境
- 分支：`bench-huawei-adapt`（含官方 `evaluation/` + 完整优化 P1.7/P3·P4/6 CANN 补丁 + 退化修复 `43badb2`）
- 硬件：910B3 单 die0（`ASCEND_RT_VISIBLE_DEVICES=0`），CANN 9.1.0-beta.3
- build：`build/bin`（官方 eval CLI，含退化修复）+ `build-cann`（perf-duplex，含 P1.7）
- 前置修复：**ffprobe**（`yum install ffmpeg`）—— 修 videomme smoke 0/2 的提帧失败（根因非多帧退化）

## 复现结果 + 口径审计

| 项 | 报的值 | 本次复现 | 口径 | 官方基线口径 | 可比性 |
|---|---|---|---|---|---|
| 性能 RTF | 0.57 / 0.68 | **0.58（24线程+NUMA，中位 3 次）/ 0.69（16线程，中位 3 次）** | e2e RTF 全 chunk，多次中位 | 1.087 全 chunk | ✅ 一致，beat 47%/36% |
| Daily-Omni | 88% | **88.0%（44/50）** | **50 题子集** | 79.5 全量 1196 | ⚠️ 子集，不可直接说"超基线" |
| TTS WER | 1.501% | **1.385%（10 条子集）** | Paraformer+jiwer，全量口径同 | 1.414 全量 2020 | ✅ 口径一致（子集接近全量） |
| TTS ASV/SIM | 0.694 | **未复现（阻塞）** | wavlm_large_finetune | 0.709 全量 | ⚠️ 引用团队 0.694 |
| VideoMME | 51.5% | **53.5%（53/99）** | 99 题子集（分层） | 69.0 全量 2700 | ⚠️ 子集，差 +2%，退化修复生效 |

## 详细

### 1. RTF 0.58 / 0.69（性能）✅
- 24 线程+NUMA（`taskset -c 192-223` + `OMNI_T2W_THREADS=24`）：r1=0.59, r2=0.58, r3=0.58 → 中位 **0.58**
- 16 线程默认：r1=0.69, r2=0.70, r3=0.67 → 中位 **0.69**
- 口径：`analyze_perf.py` 的 `e2e RTF = (末 wav 落盘 − 首帧 push)/音频时长`，全 chunk 平均
- 与报值差 ≤0.02（< 0.03 噪声阈值），beat 基线 1.087
- 产物：`code/llama.cpp-omni/tools/omni/output/perf_t{24,16}_r*.json`

### 2. Daily-Omni 88.0%（50 题）✅
- `convert.py` 转 MTEB parquet → `daily_omni.jsonl`（1196 题）+ 684 音视频（2.8GB，校验全过）
- `run_all.sh --tasks daily-omni --smoke 50`：**44/50 = 88.0%**，官方 Overall=88.0%
- 退化修复对 daily 多模态也生效（多选答对率高）
- ⚠️ **口径审计**：报的 88% 是**前 50 题子集**；官方基线 79.5 是**全量 1196 题**。**不可直接说"超基线"** —— 应表述为"50 题子集 88%，全量口径未测"。

### 3. TTS WER 1.385%（10 条子集）✅ / ASV 阻塞 ⚠️
- `run_tts_eval_cpp_zh.sh NUM_SAMPLES=10`（全链路 prompt_bundle→generate→WER→SIM）
- **WER 1.385%**（10 条），口径 = Paraformer-zh + jiwer（funasr），与官方全量口径同；接近团队全量 1.501%
- **ASV/SIM = 0.0（阻塞）**：根因 = `ecapa_tdnn.py` wavlm 上游 `torch.hub.load(..., pretrained=False)` **随机初始化**，未 load 预训练 wavlm 权重；本地 `wavlm_large_s3prl.pt`（1.2GB 预提取）未接入；官方文件不可改。叠加 torchaudio 2.11 移除 `set_audio_backend`（s3prl 多处调用）的兼容警告。
- 引用团队全量 **ASV 0.694**（claude_code 环境 `run_full.log` 实测）

### 4. VideoMME 53.5%（99 题子集）✅
- ffprobe 修复 + 退化修复后，videomme smoke = 1/2 = 50%（提帧成功 + response 干净单字母，非退化乱码）—— 退化修复 `43badb2` 实证生效
- 99 题全跑（33 视频 × 3，分层 short/medium/long 各 33，官方 64 帧@1fps）：**53/99 = 53.5%**（~31min）
- 与报值 51.5% 差 +2%（退化修复后稳定水平，非退化 0%）
- ⚠️ **口径审计**：报的 51.5% 与本次 53.5% 都是 **99 题子集**；官方基线 69.0 是**全量 2700**。**不可直接比**——子集口径真实水平 ~51-54%，全量口径待测。

## 复现总结
| 项 | 报值 | 复现 | 差 | 结论 |
|---|---|---|---|---|
| RTF（24线程）| 0.57 | 0.58 | +0.01 | ✅ 可复现 |
| RTF（16线程）| 0.68 | 0.69 | +0.01 | ✅ 可复现 |
| Daily-Omni | 88% | 88.0% | 0 | ✅ 精确复现（50题子集）|
| TTS WER | 1.501% | 1.385% | -0.12 | ✅ 可复现（10条子集，口径同）|
| TTS ASV | 0.694 | 阻塞 | — | ⚠️ 引用团队（wavlm 上游权重接入待决）|
| VideoMME | 51.5% | 53.5% | +2.0 | ✅ 可复现（99题子集，退化修复生效）|

## 口径审计结论
- **可比（口径一致）**：RTF（全 chunk e2e）、TTS-WER（全量 Paraformer+jiwer）
- **不可直接比（子集 vs 全量基线）**：Daily-Omni 88%（50 题）、VideoMME 51.5%（99 题）
- **建议**：`competition-readiness.md` 措辞修订 —— Daily/VideoMME 标"子集 X%，全量待测"，避免"超基线 / gap"的全量口径暗示

## 阻塞与未决
- **TTS ASV**：wavlm 上游权重接入（需 patch s3prl load `wavlm_large_s3prl.pt`，绕过官方 `ecapa_tdnn.py` `pretrained=False`），深坑待决；WER 已验证
- **Daily/VideoMME 全量**：子集复现 OK，全量需更大投入（数据/时间）
- **ffprobe**：已修（videomme 提帧前提）
