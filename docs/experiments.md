# 实验记录（Baseline & 优化迭代）

## 环境

- 本地测试机：secs（172.16.49.6），GPU1 = RTX 4090 D 24G（共享，剩 ~14G）
- 构建：build-cuda（GGML_CUDA=ON, nvcc 12.0, CUDA 12.8 driver）
- 权重：/data/minicpm-omni/weights/MiniCPM-o-4_5-gguf/（全套）
- 输入：文本轮次对话（llama-omni-cli，stdin 管道）

## 实验方法

- 手测：echo 文本 | llama-omni-cli -m <llm> -ngl 99 → 观察 T2W 线程 RTF 日志
- 正式：tools/omni/perf/run_perf.sh（全双工模拟，1s 推帧节奏）
  - BUILD_DIR=build-cuda 指定 CUDA 构建
  - 输出 perf_report.json / perf_report.md
  - 退出码：0=可支撑双工，2=不满足实时性，3=数据不完整

## 基线记录

### 实验 001：手测文本对话（Q4_K_M, -ngl 99, GPU1）
- 时间：2026-07-31 19:03
- 输入："你好，请用一句话介绍你自己"
- 结果：38 个音频 chunk 生成成功（1s/chunk）
- T2W RTF：2.41-2.72（平均 ~2.43）
- 观察：queue_wait 46661ms —— TTS 生成跟不上（每 chunk 2.4s 但音频 1s）
- 说明：T2W 段 RTF 2.4；全链路（含 LLM+TTS 排队）更慢，待 perf 报告量化

### 实验 002：双工 perf 基线（Q4_K_M, -ngl 99, GPU1 全空 24.5G）
- 时间：2026-07-31 19:2x
- 工具：run_perf.sh（perf-duplex，36 帧：SPEAK 12 / LISTEN 24，1s 推帧）
- 结果：全部 PASS
  · LLM 判定延迟：P50 144.7ms | P95 214.2ms（<1000ms ✓）
  · 首响 e2e：P50 417ms | P95 508ms（✓）；tts：P50 242ms | P95 296ms
  · TTS RTF（硬判据）：平均 0.73（0.66-0.80）✓ <1.0
  · e2e RTF：平均 0.79
  · chunk 时长：~1.0s（满窗），轮末 remainder (0,1.0]s
- 关键认知：双工模式（流水线并行）RTF 0.73 << 轮次模式手测 2.4
  → 比赛评测形态即此（流式 chunk），基线已实时，优化目标 <0.5
- 报告存档：docs/perf-reports/perf_report_Q4KM_baseline.md

### 实验 003：双工 perf Q8_0（-ngl 99, GPU1）
- 时间：2026-07-31
- 结果：TTS RTF 平均 0.32（全 PASS）
  · 注意：本轮音频 101.84s（模型话痨），长音频摊薄固定开销，
    RTF 与 Q4_K_M（2-3s 音频）不完全可比，需统一测试集验证
- 初步观察：Q8_0 在 4090 量化核效率高，RTF 显著低于 Q4_K_M
- 报告存档：docs/perf-reports/perf_report_Q8_baseline.md
- 待办：量化矩阵全部跑完后，用固定输入复测交叉验证

## 优化队列（更新）

1. 量化对比：Q8_0（精度参考）→ Q3/Q2（RTF 下限试探）——需补下 Q6_K/Q5_K_M/Q3 档
2. 参数：ctx-size、stream-interval、chunk 边界
3. 编译：-O3/LTO/march
4. CANN 侧（910C）：USE_ACL_GRAPH 图模式
