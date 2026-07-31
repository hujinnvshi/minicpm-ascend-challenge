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

### 实验 002：（待 perf 工具输出）
- 状态：进行中

## 优化队列（计划）

1. Q8_0 vs Q4_K_M 对比（量化对 RTF 影响）
2. 参数：ctx-size、chunk、滑动窗口 stride
3. 编译：-O3/LTO/march
4. CANN 侧（910C）：USE_ACL_GRAPH 图模式
