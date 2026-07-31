# 赛道一筹备计划（llama.cpp-omni 推理优化）

## 赛题要点（官方）

- 指定模型：MiniCPM-o 4.5（9B 全模态）
- 指定框架：llama.cpp-omni
- 镜像版本：CANN 9.1.0-beta1
- 核心指标：音频 chunk RTF（RTF = chunk 生成耗时 ÷ chunk 时长，越低越好）
- 约束：保证模型精度（降幅 ≤2pp）与 Demo 可用性
- 算力：HiDevLab 单卡 910C

## 技术架构（来自 llama.cpp-omni README）

模型拆分为 5 个 GGUF 模块：
- VPM：SigLip2 视觉编码器（+Resampler）
- APM：Whisper 音频编码器（16kHz，1 秒 chunk 切片）
- LLM：Qwen3-8B 主语言模型（量化支持 F16/Q8_0/Q4_K_M）
- TTS：LLaMA 架构，将 LLM hidden states 自回归生成音频 token
- Token2Wav：Flow Matching vocoder，音频 token → 24kHz 波形
  （滑动窗口 28 tokens 输入 / 25 stride）

RTF 构成（音频 chunk 生成路径）：
  LLM 解码（生成 <|speak|> 后的文本/语义 token）→ TTS 生成音频 token → Token2Wav 合成波形
  即：chunk 耗时 ≈ TTS 生成 + Token2Wav 合成

## 官方基线（RTX 4090, F16, 供参考）

| 阶段 | 延迟 |
|------|------|
| TTFT | <550ms |
| Prefill（视觉+音频） | ~65ms |
| Decode-LLM | ~38ms/token |
| TTS Generation | ~8.5ms/token（25 tokens ~215ms） |
| Token2Wav | RTF ~0.15（25 tokens→1s 音频 ~150ms） |

内存（NVIDIA）：F16 ~18GB / Q8_0 ~11GB / Q4_K_M ~8GB
→ 910C 单卡内存充足，量化是 RTF 优化的主战场

## 模型文件结构（GGUF）

```
MiniCPM-o-4_5-gguf/
├── MiniCPM-o-4_5-Q4_K_M.gguf     # LLM（可换 F16/Q8_0）
├── audio/MiniCPM-o-4_5-audio-F16.gguf
├── tts/MiniCPM-o-4_5-tts-F16.gguf
├── tts/MiniCPM-o-4_5-projector-F16.gguf
├── token2wav-gguf/{encoder,flow_matching,flow_extra,hifigan2,prompt_cache}.gguf
└── vision/MiniCPM-o-4_5-vision-F16.gguf
```
下载：HuggingFace openbmb/MiniCPM-o-4_5-gguf；国内走 ModelScope 镜像

## 构建（本地 CPU 学习版）

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target llama-omni-server --target llama-omni-cli -j
```

## CLI 关键参数

| 参数 | 说明 |
|------|------|
| -m <path> | LLM GGUF 路径（自动发现其他模块） |
| --vision/--audio/--tts/--projector | 覆盖模块路径 |
| -c, --ctx-size | 上下文（默认 4096） |
| -ngl <n> | GPU 层数（默认 99） |
| --test <prefix> <n> | 用音频文件跑测试（benchmark 入口） |
| --bench-vision <img> | 视觉编码 benchmark |
| --vision-batch-encode | 同尺寸切片批处理编码（1.5-2.3x 视觉加速） |

## 优化靶点（从易到难）

1. LLM 量化档位：Q8_0 → Q4_K_M → Q3/Q2（每档测 RTF + 精度，红线 ≤2pp）
2. 编译参数：Release/-O3、march 指令集、CANN 后端编译开关
3. 运行时参数：ctx-size、chunk 大小、线程/并行度、KV cache
4. TTS/Token2Wav 参数：滑动窗口 stride、批大小
5. --vision-batch-encode（视觉场景）
6. 进阶（看缘分）：算子级优化、流水线重叠

## 阶段计划

- 7/31-8/03 本地编译 CPU 版跑通 + secs 下载权重 + 精读 docs/ops.md CANN 部分
- 8/04-8/10 910C 基线 + 量化档位扫描
- 8/11-8/14 参数深度优化 + benchmark 完整数据
- 8/15-8/17 性能报告 + 提交材料（8/17 截止）
