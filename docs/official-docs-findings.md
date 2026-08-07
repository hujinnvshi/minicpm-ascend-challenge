# 官方文档情报整理（2026-08-07）— 基线可达 + 评测方法论 + 策略修正

> 来源：4 篇赛事官方文档，已放在 `Astro_Starlight_GitHubPages/src/content/docs/tech/`：
> - `MiniCPM 昇腾挑战赛 · 高性能推理优化赛道 — 评测规范说明.md`（权威评测规范）
> - `在昇腾 NPU 上使用 vllm-omni部署 MiniCPM-o 4.5.md`（子赛道 B 部署 + **三项 benchmark 完整评测方法**）
> - `MiniCPM-o 4.5 昇腾 910C 部署上手指南.md`（子赛道 A / llama.cpp-omni 基线部署）
> - `面壁大赛群 QA 整理.md`（纯运维，价值低）
>
> 本文摘录对**子赛道 A 决策有影响**的关键信息，并**修正我们此前的错误结论**。

---

## 0. 一句话结论

**基线 79.5 / 69.0 是真能跑到的（vLLM-Omni 实测 78.28% / 69.96%），我们 ~10% 是喂法错了（单帧 vs 官方多帧交错），不是框架天花板、也不是基线虚高。** 多帧退化很可能是 llama.cpp-omni 的 bug 或配置问题，要重查。

---

## 1. 四篇价值评级

| 文章 | 价值 | 要点 |
|---|---|---|
| **评测规范说明** | ⭐⭐⭐⭐⭐ | 权威：指标定义（SPEAK→WAV RTF 1.087）、基线值、准入门槛、"对应框架基线"原文 |
| **vLLM-Omni 部署指南**（子赛道 B） | ⭐⭐⭐⭐⭐ 颠覆性 | 证明基线可达 + 给完整评测方法 + ModelScope 转换脚本 + vocoder-CPU 印证 |
| **910C 部署指南**（子赛道 A） | ⭐⭐⭐⭐ | llama.cpp-omni 基线部署；确认 F16/CANN；**坦白"视觉模态未验证"** |
| **群 QA 整理** | ⭐⭐ | 纯运维（DevEnv/418/502/CANN 升级），无基线/精度内容 |

---

## 2. 颠覆性发现：基线可达 + 关键配方（vLLM 指南 §7.7/§7.8）

同一模型（MiniCPM-o 4.5），vLLM-Omni 实测：

| Benchmark | 官方基线 | vLLM-Omni 实测 | 关键配方 |
|---|---|---|---|
| Daily-Omni | 79.5 | **78.28%**（937/1197） | `minicpm-interleave`：**1fps 帧 + 1s 音频 交错**，≤64 帧 |
| Video-MME | 69.0 | **69.96%**（1889/2700） | `minicpm-frames`：≤**96 帧** JPEG（w/o subs） |

**Daily-Omni 分维度**（vLLM 实测）：Comparative 86.26% / Inference 83.77% / Reasoning 81.71% / AV Event Alignment 76.05% / Context 75.65% / Event Sequence 73.53%；按时长 30s 78.36%、60s 78.18%（长短视频基本持平）。

**Video-MME 分时长**（vLLM 实测）：short 80.33% / medium 70.33% / long 59.22%。

**配方关键参数**（子赛道 A 要类比对齐的目标）：
- **Daily-Omni**：交错打包（1fps 帧 + 1s 音频），`--interleave-mm-strings`，`temperature 0`、`max_tokens 128`、`repetition_penalty 1.2`、modalities `["text"]`；deploy YAML `limit_mm_per_prompt` image≥64、audio≥64。
- **Video-MME**：仅抽帧（≤96 帧 JPEG），`temperature 0`、`max_tokens 128`、modalities `["text"]`；`limit_mm_per_prompt.image` ≥96。
- 共同：greedy（temperature 0），不开 thinking，纯文本 MCQ（不 TTS），`Successful HTTP` 为分母。

---

## 3. 权威坐实（评测规范说明）

- **性能指标 = SPEAK→WAV 完整链路 RTF，基线 `1.087`**（"主要优化目标"），**全部 chunk 平均 RTF `0.618` 仅供参考**。
  - 公式：`RTF = 音频 chunk 生成耗时 / 音频 chunk 时长`。
  - 三态：LISTEN / **SPEAK 生成**（优化目标，负载最高）/ SPEAK 尾部。
  - ⚠️ 官方明确："误用全部 chunk 的平均 RTF 会造成误导，应以 SPEAK 生成阶段 RTF 为准。"
  - → **我们 perf-duplex 的 SPEAK→WAV RTF（0.68/0.57）口径正确**，与官方一致。
- **精度准入**：优化版相对官方基线，VideoMME/Daily-Omni 绝对降幅 ≤2pp；ASV ≤0.02；WER 相对增幅 ≤10%。不达标情形包括"修改模型行为导致评测失去可比性"。
- **测试流程**（§七 步骤4）："正式测试前进行**多轮预热**，统一配置下执行**多轮测试**"（具体次数未给；vLLM bench 用 `--num-warmup 3`）。
- **子赛道 A 框架仓库**：`github.com/tc-mb/llama.cpp-omni`。
- **子赛道 B 基线**（参考）：TTFT 333.27ms / TTFP 986.47ms / RTF 0.4423。

---

## 4. ⚠️ 我们此前结论的修正

| 之前（P7/P8 + baseline-sourcing-evidence） | 修正后 |
|---|---|
| Daily-Omni ~10% = omni 框架**硬上限** | ❌ 错。是**单帧喂法**导致；官方多帧交错能到 78%。 |
| 79.5/69.0 基线"可能不是 omni 实测 / 不公" | ❌ 错。基线**真实可达**（vLLM 实测 78.28%/69.96%），不是虚高。 |
| 多帧视觉触发模型退化（stack_frames≥2）→ 只能单帧 | ⚠️ 很可能是 **llama.cpp-omni 的 bug 或配错**，不是模型本身限制（vLLM 用 ≤64/96 帧正常）。**P7 需重新验证。** |

> 这也意味着 `baseline-sourcing-evidence.md` 和 `official-clarification-request.md` 的 Q1 立场需要更新——见 §6。

---

## 5. 其他高价值收获

1. **ModelScope Daily-Omni 转换脚本**（vLLM 指南 §7.7.1，`convert_daily_omni_modelscope.py`）：把平台预置的 `MTEB/Daily-Omni` parquet 转成官方 `qa.json + Videos/{id}/{id}_video.mp4 + {id}_audio.wav` 布局。**这是我们之前缺的环节**（1196 QA → 684 videos，answer 取首字母 A-D）。
2. **vocoder CPU 是两个框架共同瓶颈**：vLLM-Omni 也把 HiFiGAN/HiFT 声码器放 CPU 跑（§11 Q4："已将 NPU 上的 HiFT 声码器放到 CPU"；Q12：单卡抢占致首包延迟高）。→ **坐实我们 perf-ceiling 的判断**（vocoder CPU 346ms 物理锁，CANN 无 CNN 算子；我们的多线程+NUMA 思路正确）。
3. **910C 部署指南（子赛道 A 基线）**：确认 F16 最快（Q4_K_M 退 CPU）；build `GGML_CANN=ON -DLLAMA_OPENSSL=OFF`；⚠️ **`vision_backend` 默认 `metal`，"视觉模态未验证/需适配"**——这正面解释了我们 VideoMME/Daily-Omni（依赖视觉）在 llama.cpp-omni 上的挣扎。
4. **TTS-Seed WER 方法对齐**：官方用 `vllm bench serve --seed-tts-wer-eval`，ASR = Whisper-large-v3 / Paraformer-zh + jiwer。我们 WER 0.20 用 paraformer+jiwer，**基本同口径，数靠谱**。SIM 官方口径仍未完全明确（eval-spec 基线 0.709，我们 0.84 是 base-plus 口径）。

---

## 6. 对策略/动作的影响

1. **`official-clarification-request.md` Q1 改写**（最紧要）：从"基线公不公平"改成——
   > "vLLM-Omni 用 `minicpm-interleave`/`minicpm-frames` 打包能到 78%/70%。**llama.cpp-omni（子赛道 A）是否支持等价的交错多帧打包？** 我们实测多帧（stack_frames≥2）会触发模型退化、只能退回单帧 → Daily-Omni 仅 ~10%。请提供子赛道 A 跑 Daily-Omni/VideoMME 的**官方推荐配置**。"
2. **`baseline-sourcing-evidence.md` 加修正说明**：基线真实可达，矛盾从"是不是 omni 的"转为"llama.cpp-omni 怎么实现多帧交错"。
3. **重验 P7**：在 llama.cpp-omni 里找多帧/交错喂法（非 turn_based 的 stack_frames），验证"多帧退化"是否真是 bug。
4. **Daily-Omni/VideoMME 从"放弃项"改为"再冲项"**：有官方配方 + 转换脚本，值得照着在子赛道 A 再跑。
5. **性能侧无变化**：RTF 0.68/0.57 口径正确，继续 beat 1.087。

---

## 7. 待办

- [ ] 改写 `official-clarification-request.md` Q1（多帧交错配方方向）
- [ ] `baseline-sourcing-evidence.md` 加"基线可达"修正说明
- [ ] 重验 P7：llama.cpp-omni 多帧/交错喂法
- [ ] 跑 `convert_daily_omni_modelscope.py` 把 MTEB/Daily-Omni 转成官方布局
- [ ] 子赛道 A 对齐 Daily-Omni/VideoMME 配方跑精度（温度 0 / max_tokens 128 / 纯文本 / 多帧）

---

## 附录：官方 benchmark 评测命令（vLLM-Omni，子赛道 A 的"对齐目标"）

> 以下来自 vLLM 指南，是**子赛道 B 的跑法**。子赛道 A（llama.cpp-omni）需在自身协议（WS `/backend` 或 HTTP legacy）里**复刻同等打包/采样逻辑**：多帧交错、temperature 0、max_tokens 128、纯文本 MCQ。

**Seed-TTS（WER）**：
```bash
vllm bench serve --omni --port 8091 --max-concurrency 1 \
  --num-warmup 3 --dataset-name seed-tts \
  --dataset-path /workspace/seed-tts-eval --num-prompts 32 --no-oversample \
  --seed-tts-wer-eval --seed-tts-wer-save-items \
  --model openbmb/MiniCPM-o-4_5 --endpoint /v1/chat/completions --backend openai-chat-omni \
  --extra_body '{"modalities":["text","audio"],"chat_template_kwargs":{"enable_thinking":false,"use_tts_template":true}}'
```

**Daily-Omni（精度，minicpm-interleave）**：
```bash
vllm bench serve --omni --port 8091 --max-concurrency 10 \
  --dataset-name daily-omni --num-prompts 1197 --no-oversample \
  --temperature 0 --output-len 128 \
  --daily-omni-input-mode all --daily-omni-pack-mode minicpm-interleave \
  --daily-omni-video-dir /workspace/Daily-Omni/Videos --daily-omni-qa-json /workspace/Daily-Omni/qa.json \
  --model openbmb/MiniCPM-o-4_5 --endpoint /v1/chat/completions --backend openai-chat-omni \
  --extra_body '{"modalities":["text"],"chat_template_kwargs":{"enable_thinking":false}}'
# serve 侧需：--interleave-mm-strings --allowed-local-media-path /workspace/Daily-Omni/Videos
```

**Video-MME（精度，minicpm-frames）**：
```bash
vllm bench serve --omni --port 8091 --max-concurrency 4 \
  --dataset-name videomme --dataset-path /workspace/Video-MME --num-prompts 2700 \
  --no-oversample --disable-shuffle --temperature 0 --output-len 128 \
  --videomme-pack-mode minicpm-frames --videomme-max-frames 96 --videomme-duration all \
  --model openbmb/MiniCPM-o-4_5 --endpoint /v1/chat/completions --backend openai-chat-omni \
  --extra_body '{"modalities":["text"],"chat_template_kwargs":{"enable_thinking":false}}'
# serve 侧需：--allowed-local-media-path /workspace/Video-MME；deploy YAML image≥96
```
