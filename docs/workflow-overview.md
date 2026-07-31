# 工作链全景（Workflow Overview）

更新：2026-07-31
赛道一：llama.cpp-omni 推理优化（MiniCPM-o 4.5 RTF 优化）

## 全局图

赛题理解 → 资源准备 → 工具链掌握 → 本地基线 → 优化迭代 → 910C 验证 → 材料交付
   ✅ 已完     ✅ 已完     ✅ 已完       ✅ 已完      🔄 进行中    ⏳ 排队中    8/15 起

## 一、赛题理解

- 目标：降低每个音频 chunk 的 RTF（RTF = 生成耗时 ÷ 音频时长，<1 即实时）
- 环境约束：910C + CANN 9.1.0-beta1 + llama.cpp-omni，官方统一复现
- 三张入场券（缺一直接出局）：
  1. 精度降幅 ≤2pp（Daily-Omni/TTS-Seed/Video-MME）
  2. 可复现（照说明能重跑出一样结果）
  3. 材料完整（代码/脚本/报告/对比/复现说明/视频）
- 排名核心：RTF 越低越好

## 二、资源准备（✅）

- 算力：官方 HiDevLab 910C（100 卡时，已获批排队中）
  本地 secs 4×4090（GPU1 已释放 24.5G 全空，GPU0/2/3 为他人服务勿动）
- 权重：ModelScope 全套 GGUF（/data/minicpm-omni/weights/）
  Q8_0/Q6_K/Q5_K_M/Q4_K_M/Q4_K_S/Q4_0 六档 + audio/tts/vision/token2wav 五模块
- 代码：llama.cpp-omni（本机 CPU 版 + secs CUDA 版已编译）
  MiniCPM-o-Demo（官方 Demo，Gateway+Worker+Backend，C++ 后端）
- 工具：官方 perf-duplex + run_perf.sh（RTF 测量，判据内嵌）
  benchmark.py（MiniCPM-o-Demo 附带）

## 三、工具链掌握（✅）

- 全链路跑通：文本 → 视觉 → TTS（4090 上 Q4_K_M 手测 38 chunk 成功）
- 官方 perf 工具出报告：基线 Q4_K_M RTF 0.73、Q8_0 RTF 0.32（全 PASS）
- 架构认知：模型 5 模块（VPM/APM/LLM/TTS/Token2Wav），
  RTF = LLM decode + TTS + Token2Wav 链上各段耗时之和 ÷ 音频时长

## 四、本地实验（🔄 进行中）

- 阶段 A：量化矩阵——六档权重逐个跑 perf，找 RTF-精度平衡点
  Q8_0 ✅(0.32) | Q4_K_M ✅(0.73) | Q6_K/Q5_K_M/Q4_K_S/Q4_0 下载中
  ⚠️ 注意：Q8_0 与 Q4_K_M 音频时长差异大（101s vs 2-3s），
     需固定输入交叉验证后定论
- 阶段 B：参数优化——ctx-size/chunk/stream-interval 等
- 阶段 C：编译优化——-O3/LTO/march
- 原则：4090 上把参数空间搜完，910C 只验证候选

## 五、910C 验证（⏳ 排队中）

1. 环境确认：npu-smi、CANN 版本、镜像预装内容
2. 权重入库：secs → /user_data（官方大容量共享目录）
3. 编译：/workspace 编 CANN 版
   cmake -DGGML_CANN=ON -DCANN_INSTALL_DIR=<路径> -DUSE_ACL_GRAPH=ON
   （USE_ACL_GRAPH 图模式是 910C 最大杠杆）
4. 复现候选：4090 筛出的 3-4 个最优配置各跑一次
5. 官方精度 benchmark（Daily-Omni 等）+ 正式 RTF 数据
- 预计 20-30 卡时

## 六、材料交付（8/15-8/17）

- 性能报告：基线 → 分模块耗时分解 → 每步优化前后对比 → msprof 热点分析
- 复现说明：30 分钟可重跑的标准
- Demo 视频：优化前后 RTF 对比
- 代码/脚本：实验全流程脚本化

## 数据流动方向

- 权重：ModelScope → secs（测试）→ 910C /user_data（验证）
- 代码：GitHub → secs（编译测试）→ 910C /workspace（CANN 编译）→ 提交物
- 数据：perf 报告 → 本地仓库 docs/perf-reports/ → 最终性能报告

## 时间线

| 日期 | 事项 |
|------|------|
| 7/31 | 资源 + 基线（已完成 60%） |
| 8/1-8/3 | 量化矩阵 + 参数优化（4090） |
| 8/4-8/10 | 910C 验证 + 复现 |
| 8/11-8/14 | 深度优化 + 报告初稿 |
| 8/15-8/17 | 材料收尾 + 提交（8/17 截止） |

## 核心逻辑

本地 4090 把"怎么优化"全部摸清（量化/参数/编译），910C 只做
"验证和出正式数据"（编译 CANN 版 + 复现候选 + 官方评测），
最后把过程写成专业报告。用算力换时间，用工程方法换确定性。
