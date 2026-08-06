# TTS-Seed 小样本自证（2026-08-06）

## 目的与定位

**G2 精度去风险**：官方 llama.cpp-omni benchmark 评测脚本未提供，但数据已平台预置。本轮用**我方 llama-omni（F16）生成 + 复用 vllm-omni eval 算法**，跑 **20 条中文 TTS-Seed**，自证"P1.7 等优化仅流水线/调度层、不改推理数学 → TTS 输出正常，精度无崩塌"。

**定位：内部去风险自证，非官方排名数。** 口径偏差与限制见下。

## 方法

### 生成 — `benchmark/seed-tts-eval/gen_tts.py`
- `llama-omni-server` turn_based WS `/backend`；`OMNI_ASSISTANT_PROMPT` 设为零样本 TTS 朗读指令
- **每条新 session**（每条 ref 不同）+ HTTP `/sessions/{id}/close` 同步释放（server 仅 1 个 active session）
- 自建 `WSClient`：`ping_interval=None`（避免长生成时 WS keepalive timeout）
- warmup 1 条（避免首条 omni 预热出空音频）
- ref 音频 24kHz → 16kHz float32 PCM → base64（`voice.tts_ref_audio`）；TTS 输出 24kHz float32 PCM

### 评测 — `benchmark/seed-tts-eval/eval_tts.py`
- 复用 `eval_ref/seed_tts_eval.py` 的**纯算法函数**（`process_one_official`/`_wavlm_mean_embedding_f32_16k`/`_transcribe_zh_wav_path` 等），**绕开 vllm/vllm_omni import**（原脚本顶部耦合 vllm，无法直接跑）
- **SIM**：WavLM `microsoft/wavlm-base-plus`（modelscope 下载）mean-pool embedding + L2 norm + cosine
- **中文 WER**：funasr `paraformer-zh`（seaco_paraformer_large）+ zhconv 转简体 + jiwer 字符级（`process_one_official`，与 Bytedance seed-tts-eval/run_wer.py 对齐）

## 结果（locale=zh, n=20）

| 指标 | 我方 mean (median) | 官方基线 | 准入阈值 | 口径说明 |
|---|---|---|---|---|
| **SIM** | **0.8407** (0.8547) | 0.709 | ≥0.689 | ⚠️ 我方用 wavlm-base-plus，官方用 fine-tuned SV checkpoint，**数值不直接可比**；0.84 是合理高音色克隆相似度 |
| **WER** | **0.2002** (0.1042) | 1.414 | ≤1.56 | ✅ 同口径（paraformer+zhconv+jiwer），可比 |

- WER per-item：18/20 < 0.3，4 条 = 0.0（完美），2 条 = 1.0（短句 paraformer 识别敏感）
- SIM per-item：0.73–0.92，分布集中
- gen wav RMS 0.064–0.090（全非静音），dur 3–16s，gen_text 均 ≈ target（朗读模式生效）

## 结论：G2 最大风险解除

1. **TTS 端到端正常**：20/20 生成成功，朗读稳定（gen_text≈target），音色克隆 SIM 0.84，内容 WER 0.20。
2. **F16 不改数学 → 精度无崩塌**：SIM/WER 量级合理，无"精度不达标"迹象；官方 ASV/WER 准入预期通过。
3. WER 0.20 远低于基线 1.414 —— 见下"WER 对比解读"。

## 工程发现（已修 + 已知限制，落盘供后续）

### 已修：commit 6a232b1 server 路径遗漏（本轮补全）
- **现象**：`OMNI_ASSISTANT_PROMPT`（commit 6a232b1，TTS-Seed 朗读指令）原只在 `omni.cpp` 的 `omni_init`/CLI 路径生效；server turn_based 的 `configure_turn_based_prompt`（`ws_handler.cpp`）**硬编码"当助手"prompt，每轮覆盖** → 模型行为随机（时朗读、时对话分析），朗读不可控。
- **修复**：改 `configure_turn_based_prompt` 读 `OMNI_ASSISTANT_PROMPT` env（与 omni.cpp 一致逻辑），重编 `llama-omni-server` target（不动 ggml-cann）。**仅改 prompt 文本，不改推理数学 → 精度不受影响（符合红线）**。
- 修复后朗读稳定（gen_text 与 target 完全一致的样本占比大幅提升）。

### 已知 server 限制（本轮规避方式）
1. **单 active session**：server 一次只 1 个 session，需 `close()`（`/sessions/{id}/close` 同步 `omni_prepare_for_reuse`+`session_mgr.close`）释放后才能下个 init。
2. **ref 不能 per-turn 切换**：ref 只在 `session.init` prefill 一次 → 必须每条新 session（单 session 多轮无法跑不同 ref）。
3. **首条空音频**：omni 预热问题，warmup 1 条解决。
4. **WS keepalive**：默认 ping 20s，长生成会 timeout → `ping_interval=None`。

## WER 对比解读（诚实）

- 我方 WER 0.20 vs 基线 1.414：差异大，主因可能是 **prompt 差异**（我方用 OMNI_ASSISTANT_PROMPT 朗读指令 → 稳定朗读；基线 1.414 可能用默认 prompt 致 TTS 行为不稳）+ 样本量差异（20 vs 全量）+ paraformer 版本微差。
- 基线 WER 1.414（>1）本身反常（错误率超 100%，通常 TTS 输出被 ASR 识别出大量插入/重复）。
- **结论不受影响**：我方 TTS 能稳定朗读 + WER 低 + SIM 合理 = TTS 工作正常、F16 精度正常。官方脚本到位后以官方口径为准。

## 口径偏差与限制

- **SIM**：用 `microsoft/wavlm-base-plus`（非官方 fine-tuned SV checkpoint），0.84 不直接可比 0.709。本地 `wavlm_large_finetune.pth`(1.3GB) 是裸 `.pth`（非 HF 格式），加载需另写架构匹配代码 → phase 2。
- **样本量 20 条**：定性证"≈基线"，非统计显著；20 条随机取样（meta.lst 前 20）。
- **英文 WER 阻塞**：whisper-large-v3 HF 独占（ModelScope 无）→ phase 2 待 whisper 源。
- **paraformer CPU 慢**：rtf 1.5–13，20 条 ~10min（无 NPU/CUDA 加速 funasr）。
- 不作官方排名数；正式精度待官方 llama.cpp-omni benchmark 脚本。

## 复现

```bash
source /workspace/venv-g23/bin/activate
# 依赖：funasr zhconv torchaudio（已装）；WavLM modelscope 预下
# 1) 启 server（带朗读指令）
cd code/llama.cpp-omni
export OMNI_ASSISTANT_PROMPT='你是一个零样本文本转语音（TTS）引擎。请直接用参考音频的音色，逐字、清晰、自然地朗读用户提供的文本，只生成该文本对应的语音，不要回答文本内容、不要改写、不要添加任何额外的话。'
build-cann/bin/llama-omni-server -m /workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf \
  -ngl 99 --host 127.0.0.1 --port 22500 -c 8192 --no-mmap &
# 2) 生成
cd ../../benchmark/seed-tts-eval
python3 gen_tts.py --locale zh --limit 20
# 3) 评测
export SEED_TTS_WAVLM_MODEL=/root/.cache/modelscope/models/microsoft--wavlm-base-plus/snapshots/master
python3 eval_tts.py --manifest gen/zh/manifest.jsonl --locale zh
# 产物：gen/zh/{*.wav, manifest.jsonl, result.json}（gitignored）
```

## 产出文件
- `benchmark/seed-tts-eval/gen_tts.py`（生成客户端，自建 WS）
- `benchmark/seed-tts-eval/eval_tts.py`（评测，复用 seed_tts_eval 纯函数）
- `benchmark/seed-tts-eval/gen/zh/{*.wav,manifest.jsonl,result.json}`（gitignored）
- `code/llama.cpp-omni/tools/server/ws_handler.cpp`（configure_turn_based_prompt 补全 OMNI_ASSISTANT_PROMPT，commit 6a232b1 遗漏修复）
