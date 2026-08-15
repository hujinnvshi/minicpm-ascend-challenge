# TTS-Seed 评测打通（2026-08-12）— WER/SIM 链路 + 环境踩坑

> **状态**：✅ **全量 2020 题达标**（WER 1.501% 增幅6.2%<10%、ASV 0.694 降幅0.015<0.02，两项均过准入）。
> 分支：`bench-huawei-adapt`。配套：`benchmark/tts-seed-convert/run-tts.env`。

## 一、链路（官方 `run_tts_eval_cpp_zh.sh`，4 阶段）

1. **extract_prompt_bundle**：Step-Audio ONNX（`speech_tokenizer_v2_25hz.onnx` + `campplus.onnx`，本机 `MiniCPM-o-4_5/assets/token2wav/` 已有）把参考音频编码成 (spk_f32 + prompt_tokens_i32 + prompt_mel_btc) 三件套 → C++ 消费
2. **generate**：`llama-omni-eval-cli` 的 `llama-omni-tts-eval`（C++/NPU）用 token2wav-gguf 做声音克隆 → 生成 wav
3. **WER**：funasr `paraformer-zh`（modelscope 自动拉）+ jiwer 算字错率
4. **SIM/ASV**：ECAPA-TDNN + WavLM-large（s3prl）+ `wavlm_large_finetune.pth` 算说话人余弦相似度

## 二、环境（venv-tts 新建，CPU torch）+ 踩坑全解

| 坑 | 现象 | 解 |
|---|---|---|
| transformers 5.15 import 卡 | >180s 无输出 | 降到 **4.44.2**（funasr 兼容）|
| extract 缺 torchcodec | `TorchCodec is required` | `pip install torchcodec` |
| torchaudio 2.11 移除 set_audio_backend/sox_effects | s3prl import 崩 | `venv-tts/.../sitecustomize.py` 加 **sys.modules 级** stub（`from torchaudio.sox_effects import X` 需要真模块,属性注入不够）|
| s3prl wavlm 联网下 wavlm_large.pt（HF 封）| ConnectionError | **hf-mirror.com** 下官方 converted_ckpts `wavlm_large.pt`（sha256 **6fb4b3c3...**,1.26GB）→ s3prl 缓存；⚠️ **必须官方版**：其它来源副本（如 9130cbd4）与 s3prl 0.4.18 WavLM 结构不匹配（grep_linear 等 Unexpected keys）→ expert.py strict 加载崩 → SIM 全 0 |
| funasr 1.4.1 import 慢 | ~300s（aarch64 加载大量模型注册）| 只是慢，给足时间能成功 |
| **torchaudio.load aarch64 极慢（2026-08-15 新增）** | 61s/条（7.5s 音频）| sitecustomize 用 soundfile 实现替换 `torchaudio.load`（0.06s；s3tokenizer.load_audio 依赖）|
| **s3tokenizer quantize 极慢（2026-08-15 新增）** | onnx2torch torch CPU 4min+/条 | venv 包内 patch `load_model` → **onnxruntime 直跑** speech_tokenizer_v2_25hz.onnx（0.13s/条,快 2000 倍；smoke 验证 WER/ASV 与 onnx2torch 逐位一致）|

**关键发现**：Step-Audio ONNX 本机已有（`MiniCPM-o-4_5/assets/token2wav/`）；wavlm_large.pt 用 hf-mirror 下；paraformer 用 funasr+modelscope 自动下。**国内镜像（modelscope + hf-mirror）能补齐所有缺口**，HF 封不是死结。

合规：`evaluation/` 不改。SIM 的 `verification.py` `.cuda()` 用 `SIM_DEVICE=cpu` 绕过（不改码）；s3prl/torchaudio 兼容性用 venv 的 `sitecustomize.py` patch（不动 evaluation/）。

## 三、smoke 3 条结果（链路验证）

| 指标 | smoke(3条) | 基线 | 准入 |
|---|---|---|---|
| **WER** | 4.618% | 1.414 | ≤1.56（增幅≤10%）|
| **SIM/ASV** | **0.762** | 0.709 | ≥0.689 |
| generate wav 时长 | 7/10/7s（合理）| — | — |

ASV 0.762 > 基线 0.709 → **SIM 达标**。smoke 3 条 WER/SIM 无统计意义，全量定论。

## 四、怎么跑

```bash
# 0. 一次性准备（venv-tts + 解压 + clone + wavlm 缓存，见上）
source /usr/local/Ascend/ascend-toolkit/set_env.sh
source /workspace/user_data/venv-tts/bin/activate
source benchmark/tts-seed-convert/run-tts.env
export PATH=/workspace/user_data/venv-tts/bin:$PATH
cd code/llama.cpp-omni/evaluation/tts_seed

# 1. smoke
python smoke_test.py 3
bash run_eval_only.sh eval_results/smoke-3   # WER+SIM

# 2. 全量 2020
export NUM_SAMPLES=10000000 GPUS_PER_NODE=1 DEVICE_ENV_VAR=ASCEND_RT_VISIBLE_DEVICES ASCEND_RT_VISIBLE_DEVICES=0
bash run_tts_eval_cpp_zh.sh
# 产物: eval_results/cpp-zh-*/wav_res_ref_text.{wer,sim}
```

设备：generate 走 NPU（`--t2w-device gpu:0`，CANN 映射）；WER/SIM 走 CPU 16 线程并行（合规不改 evaluation/）。

## 五、全量结果（2020 题，output/cpp-zh-20260812_024010-42）

| 指标 | 全量(2020题) | 基线 | 准入阈值 | 判定 |
|---|---|---|---|---|
| **WER** | **1.501%** | 1.414% | ≤1.56（增幅≤10%）| ✅ 增幅 6.2% < 10% |
| **ASV/SIM** | **0.694** (var 0.004) | 0.709 | ≥0.689（降幅≤0.02）| ✅ 降幅 0.015 < 0.02 |

2020 wav 全量生成、2020/2020 WER 条、SIM 32 片并行。**两项均达标**（ASV 接近准入线但过）。

## 六、三项 benchmark 全景

| 场景 | 结果 | 基线 | 准入 | 状态 |
|---|---|---|---|---|
| Video-MME | 51.5%（99题）| 69.0 | ≥67.0 | ❌ gap，待赛方澄清口径 |
| Daily-Omni | 88%（50题）| 79.5 | ≥77.5 | ✅ 超基线 |
| **TTS-Seed WER** | **1.501%（全量2020）** | 1.414 | ≤1.56 | ✅ 达标 |
| **TTS-Seed ASV** | **0.694（全量2020）** | 0.709 | ≥0.689 | ✅ 达标 |

**三项里 Daily-Omni + TTS-Seed（两项）达标，Video-MME 待赛方澄清**。
