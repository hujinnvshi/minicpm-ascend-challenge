# 工作链全景（Workflow Overview）

更新：2026-08-04（910B3 实测环境基线见 docs/env-scan.md）
赛道一：llama.cpp-omni 推理优化（MiniCPM-o 4.5 RTF 优化）

## 全局图

赛题理解 → 资源准备 → 工具链掌握 → 本地优化 → 910B3 验证 → 材料交付
   ✅ 已完     ✅ 已完     ✅ 已完       ✅ 收敛      ✅ 环境就位   8/31 截止

## 一、赛题理解（✅）

- 目标：降低每个音频 chunk 的 RTF（RTF = 生成耗时 ÷ 音频时长，<1 即实时）
- 环境约束：910B3（厂家授权替代 910C）+ CANN 9.1.0-beta.3 + llama.cpp-omni，官方统一复现
- 三张入场券（缺一直接出局）：
  1. 精度降幅 ≤2pp（Daily-Omni/TTS-Seed/Video-MME，准入后才排名）
  2. Demo 可用（必须接入官方 MiniCPM-o-Demo，仅跑 Benchmark 不算）
  3. 材料完整 + 可复现（代码/脚本/报告/对比/复现说明/视频，官方环境重跑）
- 排名核心：RTF 越低越好（统一硬件/环境/模型/输入/脚本）

## 二、资源准备（✅）

- 算力：官方 HiDevLab 910B3（厂家授权替代 910C，1 颗 910C = 2 颗 910B；100 卡时 = 1NPU，已就位）
  备选：910B 云购买（星宇智算/华为云，~10-30 元/小时，仅链路预演）
  本地：secs 4×4090（GPU1 已释放 24.5G 专用，GPU0/2/3 他人服务勿动）
- 权重：ModelScope 全套 GGUF（secs /data/minicpm-omni/weights/）
  六档量化（Q8_0/Q6_K/Q5_K_M/Q4_K_M/Q4_K_S/Q4_0）+ 五模块（audio/tts/vision/token2wav）
- 代码：llama.cpp-omni（本机 CPU 版 + secs CUDA 版，含 llama-omni-server 已构建）
  MiniCPM-o-Demo（官方 Demo：Gateway :8006 + Worker :22400 + Backend :22500）
- 工具：官方 perf-duplex + run_perf.sh（RTF 测量）；capture-env.sh（资源采集）；
  build-cann.sh（910C 编译）；sync-weights.sh（权重传输）；package-submission.sh（提交打包）

## 三、工具链掌握（✅）

- 全链路跑通：文本 → 视觉 → TTS（4090 Q4_K_M 手测全通）
- 官方 perf 出报告：Q4_K_M RTF 0.73 基线（全 PASS），Q8_0 乱码出局
- 后端验证：llama-omni-server 构建 + 启动 + omni_init 全模块加载成功（GPU1 11.3G）
- 架构认知：RTF = LLM decode + TTS + Token2Wav 链上各段耗时之和 ÷ 音频时长

## 四、本地优化（✅ 收敛，4090 全量完成）

- 量化矩阵（六档全测）：Q8_0 0.32(乱码出局) | Q4_K_M 0.73 | Q6_K 0.75 |
  Q5_K_M 0.86 | Q4_K_S 0.86 | Q4_0 0.87 —— 量化非 RTF 主杠杆，瓶颈在 TTS/Token2Wav 段
- ctx 矩阵：8192 为唯一有效参数优化（+2.6%，标准化 3 次验证），
  LLM 训练 ctx 40960、TTS 训练 ctx 4096（8192 已超 TTS 训练长度，机制待查）
- 排除项：TTS n_ctx 缩容（有害，已回退）、march=native（无效）、
  Q8_0（CUDA 重复 token 乱码）
- 候选配置：Q4_K_M + ctx 8192 + 默认编译 → RTF 0.75（4090 可复现）
- 方法论：每配置 3 次取一致值；RTF 必须配 llm_debug 输出质量检查

## 五、910B3 验证（✅ 环境就位，待执行）

1. 环境确认：npu-smi、CANN 版本、外网连通性
2. 权重入库：ModelScope 直拉 → /user_data（无 SSH 通道，文件夹上传/直拉）
3. 编译：/workspace 编 CANN 版 cmake -DGGML_CANN=ON [-DUSE_ACL_GRAPH=ON]
   （USE_ACL_GRAPH 图模式 = 910C 最大未验证杠杆）
4. 复现候选：Q4_K_M + ctx 8192（+ 910C 上重扫量化档，CANN 算子行为可能不同）
5. 官方精度 benchmark（Daily-Omni 已调研口径）+ 正式 RTF 数据 + msprof 热点
- 预计 20-30 卡时；若 910C 持续排队 → 910B 小时卡预演（同流程，正式数据仍等 910C）

## 六、材料交付（截至 8/31）

- 性能报告：基线 → 分模块耗时分解 → 每步优化前后对比 → msprof 热点分析
  （8 字段：RTF/环境/数据/次数/统计方式/前后对比/资源/异常）
- 复现说明：30 分钟可重跑标准（build-cann + sync-weights + run_perf 脚本链）
- Benchmark 结果：Daily-Omni/TTS-Seed/Video-MME 三份（命令+参数+原始输出+汇总）
- Demo：使用说明 + 演示视频（llama-omni-server + MiniCPM-o-Demo 全链路）
- 提交包：scripts/package-submission.sh 一键生成（6 目录结构，权重不入包）

## 数据流动方向

- 权重：ModelScope → secs（测试）→ 910C /user_data（验证，直拉为主）
- 代码：GitHub → secs（编译测试）→ 910C /workspace（CANN 编译）→ 提交物
- 数据：perf 报告 → docs/perf-reports/ → 最终性能报告 → 提交包

## 时间线（更新）

| 日期 | 事项 |
|------|------|
| 7/31 | 资源 + 基线 + 本地优化收敛（已完成） |
| 8/4 | 进入 910B3 云环境 + 环境扫描 + 文档基线修订（已完成） |
| 8/5-8/15 | 910B3 验证 + 量化扫描 + 精度 benchmark + 正式 RTF 数据 |
| 8/16-8/25 | 深度优化（参数/编译）+ Demo 全链路 + 报告定稿 |
| 8/26-8/31 | 材料收尾 + 提交（8/31 截止，每天限 3 次） |

## 核心逻辑

本地 4090 把"怎么优化"全部摸清（量化/参数/编译/后端验证），910C 只做
"验证和出正式数据"，最后把过程写成专业报告。用算力换时间，用工程方法换确定性。
