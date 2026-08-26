# 赛事系统知识全景（从基础到高级）

> 目标读者：参赛者本人（运维/DBA 背景，C++ 基础，转型 AI Infra）。
> 定位：把赛事进程 + 全部基础概念按"框架层次"组织，从地基到顶层，
> 每层解释清楚"是什么/为什么/怎么用"，并标注与仓库文档的映射。
> 最后更新：2026-08-06（与 GitHub main 18dde46 同步）。

---

## 第 0 层 · 赛事全景（先看地图）

### 0.1 赛事结构

```
MiniCPM × 昇腾推理优化与应用创新挑战赛（总奖金 496k）
│
├─ 赛道一：高性能推理优化（36.1 万 / 8 奖）★ 我们在这
│   ├─ 子赛道 A：llama.cpp-omni 推理优化（我们）—— 核心指标 SPEAK→WAV RTF
│   │     奖项：冠 1×90k / 亚 1×50k / 季 1×27k（独立评审独立排名）
│   └─ 子赛道 B：vLLM-Omni —— 核心指标 RTF + TTFT + TTFP（与我们无关）
│
└─ 赛道二：创新应用（13.5 万 / 6 奖）—— 已放弃
```

### 0.2 时间线（关键节点）

| 日期 | 事项 | 状态 |
|------|------|------|
| 7/13 | 开放报名 | ✅ |
| 7/31 | 报名（赛道一 A）| ✅ |
| 8/3 | 提交开启 | ✅ |
| 8/4 | 进入 910B3 云环境，P0-P1.6 攻坚 | ✅ |
| 8/5 | P1.7 RTF 0.83 / Demo 跑通 / 官方评测规范落地 | ✅ |
| 8/14 | 报名结束 | — |
| 8/31 | 提交截止（每天限 3 次提交）| ⏳ 主目标 |
| 9/15 | 复现评审 + 颁奖 | — |
| 10/1 | 奖金到账 | — |

### 0.3 当前进度（2026-08-26 更新：官方 910C 实测成绩回写）

| 准入/排名项 | 状态 | 证据 |
|---|---|---|
| 性能 RTF | ✅ **官方 910C 实测 0.8357** < 基线 1.087（beat 23.1%）| 官方成绩回写（2026-08-22 提交，8/26 回写）|
| 精度 4 项 | ✅ **全达标**：Daily-Omni 79.6% / Video-MME 69.3% / WER 1.336 / ASV 0.709 | 官方成绩单（准入线：77.5/67.0/1.56/0.689）|
| Demo 可用 | ✅ 3 进程端到端 + 演示视频 | demo_turnchat.webm |
| 材料（报告/复现）| ✅ 初稿全 | performance-report / reproduce-guide |
| 工程复现审查 | ⏳ 待官方环境复现 | — |

**一句话**：官方 910C 评测出分——性能 beat 基线 23.1%，精度 4/4 全过准入，
三张入场券全部拿下，进入有效排名。提交链：v3（探路）→ v4（FA）→ v5 →
v6（head 并行）→ v7（README 哈希修复，可选）。

### 0.4 决策链（为什么走到今天）

```
7/31 放弃赛道二（时间不够双线）→ 赛道一
7/31 发现无 910C 开发环境 → 一度想转赛道二
7/31 HiDevLab 提供 910C 算力 → 回到赛道一
8/4  910C 排队 → 厂家授权 910B3 替代（1 颗 910C = 2 颗 910B，同 CANN 栈）
8/4  CANN 不支持 Q4_K_M 量化 → LLM 用 F16（4090 经验在 910B 失效）
8/4  量化路线基本死刑（Q8_0 dequant-bound 不提速）→ 优化转流水线/调度层
8/5  P1.7 队列解耦 → RTF 0.83 确立领先
```

---

## 第 1 层 · 模型与推理基础（地基）

### 1.1 推理 vs 训练

- **训练**：用海量数据调整模型的 90 亿个参数（权重），使输出逼近正确答案。比赛不碰。
- **推理（Inference）**：加载训练好的权重，对新输入做预测。比赛全做这个。
- 类比 DBA：训练 = 造数据字典，推理 = 按字典执行 SQL。

### 1.2 Token（词元）

- 文本/音频处理的最小单元。不是"字"，是"子词"（如 "unbelievable" → un+believe+able）。
- 全模态里 audio token 是音频的离散化表示，TTS 输出它，Token2Wav 还原成波形。
- 推理成本按 token 计：输出 token 越多越慢。

### 1.3 权重与 GGUF

- **权重**：模型参数文件，推理时加载进显存/内存。
- **GGUF**：llama.cpp 生态的权重格式（GGML 统一格式，跨后端可加载），MiniCPM-o 4.5 官方提供。
- 我们用的：`MiniCPM-o-4_5-F16.gguf`（主 LLM）+ vision/audio/tts/projector 各模块 F16 + token2wav-gguf/。

### 1.4 MiniCPM-o 4.5 五模块链路（全模态核心）

```
输入（文本/图像/视频/音频）
  ↓
VPM 视觉编码器（SigLip2）→ 图像/视频 → 视觉 token
APM 音频编码器（Whisper）→ 音频 → 音频 token      [P1.7 瓶颈嫌疑段]
  ↓
LLM 大脑（Qwen3-8B）→ 理解 + 决定说什么 → 文本 token
  ↓
TTS 语音模型（CosyVoice2）→ 文本 → 音频 token     [RTF 测量段]
  ↓
Token2Wav（Flow Matching + vocoder）→ 音频 token → 波形 wav  [RTF 大头]
  ↓
输出：流式音频（chunk 一段段）
```

关键认知（实验 001-016 验证）：
- **理解力在 LLM 权重里，五模块 = 工程管道**——优化管道不影响模型能力
- RTF 瓶颈不在 LLM（快），在 TTS/Token2Wav 段（慢）——4090 量化矩阵证明
- vocoder（声码器）是 CPU 跑（CANN 不支持 CNN），是 RTF 大头

### 1.5 Prefill / Decode / KV Cache

| 阶段 | 干什么 | 影响 |
|---|---|---|
| Prefill | 一次性处理全部输入 token | 占首响延迟（TTFT）|
| Decode | 逐个生成输出 token | RTF 的大头 |
| KV Cache | 缓存历史 attention 计算，避免重复 | 调大提速但吃显存 |

910B 数据：F16 prefill 0.58s（NPU）vs Q4_K_M 7.9s（CPU fallback）——13x 差距说明后端是否真跑 NPU 是决定性因素。

### 1.6 量化（权重压缩）

- 原理：高精度（F16，2 字节/参数）→ 低精度（INT8 → INT4），减少显存占用、加速访存。
- 命名：`Q4_K_M` = Quantized 4-bit + K-quant 算法 + Medium 档位。
- 档位从高到低：F16 > Q8_0 > Q6_K > Q5_K_M > Q4_K_M > Q4_K_S > Q4_0。
- **本赛场的残酷现实**：
  - CANN 不支持 Q4_K_M 量化算子 → 910B 上 fallback CPU（慢 13x）→ 必须 F16
  - Q8_0 实测不提速（dequant-bound，反量化开销吃掉收益）
  - **结论：量化在 910B 基本死刑，别再追**（session-2026-08-05.md 红线）

### 1.7 RTF（核心指标，北极星）

```
RTF = 生成一个音频 chunk 的处理耗时 ÷ 该 chunk 的音频时长
RTF < 1 = 生成快于播放 = 实时
```

- 官方口径：**SPEAK→WAV 完整链路 RTF**（不是全部 chunk 平均），基线 **1.087**，我们 **0.83**。
- 类比 DBA：RTF ≈ SQL 响应时间/业务时间，<1 是实时性硬指标。
- 全程只为一件事：让"生成时间" < "音频时间"，其余全是手段。

---

## 第 2 层 · 硬件与软件栈（承重墙）

### 2.1 GPU/CUDA vs NPU/CANN

| 维度 | GPU（4090）| NPU（910B3）|
|---|---|---|
| 厂商 | NVIDIA | 华为海思 |
| 编程模型 | CUDA | CANN（ACL 接口）|
| 计算核心 | SM/CUDA core | AIV（AI Vector）/ AIC（AI Cube）|
| 优势 | 生态成熟、算子全 | 国产可控、图模式、推理性价比 |
| 我们的角色 | 本地试错（4×4090）| 官方评测（910B3）|

- **代码大部分通用**：llama.cpp 的后端抽象层（Backend）屏蔽差异，`GGML_CUDA=ON` / `GGML_CANN=ON` 切换。
- **行为不通用**：量化算子支持、图模式、线程模型都不同——4090 经验必须重验。

### 2.2 llama.cpp / ggml / llama.cpp-omni

```
llama.cpp（C++ 推理框架）
├─ ggml：张量计算库，跨硬件
│   └─ ggml-cann.cpp：CANN 后端实现（我们的 6 处补丁在这）
├─ llama-omni-cli：命令行单工/轮次测试
├─ llama-omni-perf-duplex：双工性能测量（官方 RTF 数据来源）
└─ llama-omni-server：OpenAI 兼容服务（Demo 后端）
```

### 2.3 CANN 特有机制（910B 攻坚核心）

1. **per-thread device 绑定**：`aclrtSetDevice` 是线程级状态，独立线程（T2W）必须显式绑定，否则 `context is a null pointer` 崩溃 → 补丁 1-4。
2. **host_buffer**：llama offload 默认把权重放 CPU pinned RAM（host buffer），compute 回退 CPU（AICore=0 假象）→ 补丁 6 翻转默认 false，权重上 device HBM。
3. **图模式 USE_ACL_GRAPH**：算子序列编译成图省调度——910B **不支持**（头文件缺），910C 未知，已砍。
4. **量化算子缺失**：CANN 对 Q4_K_M 的 kernel 缺失 → 静默 fallback CPU（不报错！只能靠 npu-smi 看 AICore 发现）。

### 2.4 硬件体检（实测：910B3 → 910B4 → 官方 910C）

**910B3（2026-08-04，旧机）**：
- Atlas 800T A2 容器透传 1 卡：910B3，64GB HBM，NPU ID = **1**（/dev/davinci1）
- **单 compute NPU**：`npu-smi` Total Count=1（dev_count=2 是双 die 聚合假象，dev1 不可单独用）
- 并发 runtime-capped ~1.24×（LLM+LLM）——并发优化空间极小
- NUMA node6 = CPU 192-223（vocoder 24 线程绑核推荐区）
- 鲲鹏 256 核 / 2TB 内存

**910B4（2026-08-21 起，当前本地测试机）**：
- 910B4 单卡，HBM **32GB**，NPU id=3（/dev/davinci3），NUMA node4 → CPU 128-159
- F16 全模态权重 ~19GB（LLM 15.3G + vision 2.0G + audio 0.63G + tts 1.1G + token2wav 0.88G）→ 32GB 可全量上卡
- 绑核纪律：`scripts/numa-bind.sh` 自动探测（旧机 node6=192-223 / 新机 node2=64-95 / 910B4 node4=128-159），照抄会跨 NUMA 退化

**官方 910C（2026-08-26 出分确认）**：
- 双 die 封装（= 2×910B die），FP16 算力约 2 倍，HBM 64GB+
- **同代码实测对照（v5 配置）：官方 910C 0.8357 vs 本地 910B4 1.3291 → 910C 快 59%（1.59x）**
  ⚠️ 注意：knowledge-map/status-assessment 早先写的"910C 快 28%"（0.8357 vs 1.166）是 v5官方 vs v6本地的**异代码对照**（混入 head 并行 -12% 软件差异），非硬件加速比；正确同代码加速 = 1.3291/0.8357 = 1.59x，与 8/25 仿真模型校准值 1.57x 吻合
- 未达 2 倍原因：瓶颈段含 CPU vocoder/T2W（不随 NPU 算力翻倍），且双 die 有互联损耗（~33%）
- 8/25 理论外推（预测 0.51-0.78）方向正确但略乐观——CPU 段占比比模型预估高

---

## 第 3 层 · 双工流水线（业务逻辑）

### 3.1 轮次模式 vs 双工模式

- **轮次（单工）**：你说完 → 我说完 → 你说……串行。RTF ~2.4（慢）。
- **双工（Full-Duplex）**：边听边说、流水线并行。RTF 0.73-0.83（快 3 倍）。
- 结论：**流水线重叠是最大的 RTF 杠杆**（4090 实验 002 证明），比赛跑的就是双工。

### 3.2 双工流水线架构（omni.cpp）

```
音频帧 → encoder(CPU) → LLM decode(NPU, duplex_do_decode/stream_decode)
        → TTS-model(NPU, ctx_tts_llama) → token2wav/T2W(NPU Flow + CPU vocoder) → wav
多线程 + 队列，逐 chunk 流水
```

### 3.3 P1.7 核心突破：LLM↔TTS 队列解耦

- 问题：LLM 和 TTS 共用队列 cap=1 → 互相等待 → LLM P50 8295ms
- 修复：`OMNI_TTS_QUEUE`（默认 16）解耦 → **LLM P50 8295 → 977ms**，RTF 0.83
- 类比 DBA：把共享锁改队列缓冲，生产者（LLM）不再阻塞消费者（TTS）

### 3.4 环境旋钮（运行时参数全家桶）

| 变量 | 作用 | 实测 |
|---|---|---|
| OMNI_TTS_QUEUE | LLM↔TTS 队列深度 | 16 = P1.7 主杠杆 |
| OMNI_T2W_THREADS | token2wav CPU 线程 | 24 + 绑核 → RTF 0.57 |
| OMNI_T2W_PROFILE | 打印 token2mel/vocoder 分段 | 诊断用 |
| OMNI_TTS_GPU_LAYERS | TTS 模型 offload 层数 | — |
| OMNI_STEP_SIZE / OMNI_ASSISTANT_PROMPT | 步长/助手提示 | — |
| taskset -c 192-223 | NUMA node6 绑核 | vocoder 提速关键 |

---

## 第 4 层 · 优化方法论（战术层）

### 4.1 一句话思维链

```
目标(RTF<1) → 拆三段 → 找最慢 → 抓最大杠杆 → 选对手段(从大到小)
→ npu-smi+质量验证 → 不越红线
```

### 4.2 瓶颈定位：两件武器

1. **perf-duplex + analyze_perf.py**：分模块计时（LLM/TTS/T2W 各占多少）+ RTF/P95/首响
2. **npu-smi 细粒度采样**：`npu-smi info -t usages -i 1`（≤0.5s），看 Aicore Usage + **HBM Bandwidth Usage**（后者高 = 真在 NPU 算）

⚠️ 血泪教训：
- 不能看单次/粗均值——曾误判 "AICore 4% = 没走 NPU"，细粒度采样证实 burst 60-84%
- "HBM 3481 = model 在 CPU" 是采样时机误判（加载前/早期采样）

### 4.3 杠杆排序（先抓最大头）

```
优化收益 = 该段占比 × 可降幅度
```

| 阶段 | 杠杆 | 幅度 |
|---|---|---|
| P1 | LLM 上 NPU（host_buffer）| prefill 7.9s → 0.58s（13x）|
| P1.7 | LLM↔TTS 队列解耦 | P50 8295 → 977ms |
| P3/P4 | vocoder 线程 + 绑核 | RTF 0.83 → 0.57 |
| 死刑 | 量化（CANN 不支持/不提速）| 0 |
| 死刑 | 图模式（910B 头文件缺）| 0 |
| 死刑 | 并发（单 NPU capped 1.24x）| ~0 |

### 4.4 手段工具箱（从大到小按层试）

| 层 | 手段 | 910B 实例 |
|---|---|---|
| 1 后端/部署 | 权重放对设备（offload/host_buffer）| 补丁 6 → LLM 上 NPU |
| 2 量化档 | 选后端支持的 | cann 只支持 F16 → 用 F16 |
| 3 编译开关 | 图模式/优化 | USE_ACL_GRAPH 910B 砍 |
| 4 运行时参数 | 队列/线程/绑核/ctx | OMNI_TTS_QUEUE=16 + T2W 24 线程 |
| 5 算子级 | 改 cann 算子 | 最难，最后（SQR 补丁）|

### 4.5 验证三件套（防自欺）

1. **npu-smi 细粒度**：确认真在 NPU 算（HBM 带宽高 = 真算）
2. **质量检查**：RTF 低但乱码 = 负优化（4090 Q8_0 0.32 教训）
3. **同口径对比**：perf-duplex vs perf-duplex（跨硬件可比）；单工 vs 双工不可比

### 4.6 三条红线（碰了出局）

1. 精度降幅 ≤2pp（VideoMME ≥67.0 / Daily-Omni ≥77.5 / TTS-Seed ASV ≥0.689、WER ≤1.56）
2. Demo 接入官方 MiniCPM-o-Demo 可用（仅跑 Benchmark 直接出局）
3. 材料完整可复现（30 分钟重跑标准）

**我们的安全垫**：所有优化都是流水线/调度层，不改推理数学 → F16 精度 = 基线，准入必过。

---

## 第 5 层 · 性能天花板（认知边界）

### 5.1 已探明的硬极限

- **vocoder NPU 化不可行**：CANN 不支持 CNN（conv2d 类）→ vocoder 只能 CPU
- **真实硬极限 RTF ≈ 0.34**：vocoder CPU 单线程理论时间 / 音频时长（perf-ceiling-analysis.md）
- **量化无路**：Q4_K_M 缺算子、Q8_0 dequant-bound
- **图模式无路**：910B 不支持
- **并发无路**：单 compute NPU，capped 1.24x

### 5.2 未探明的（低成本剩余杠杆）

- 量化"修调用"复核：Q8_0 为何不快（per-token 23ms 归因）
- T2W + LLM 定向并发（与 LLM+LLM 不同，未单独测）
- msprof 算子级热点（观测工具已备，命令模板在 cann-patches.md）

### 5.3 战略判断（2026-08-26 更新：官方出分后）

```
官方 910C 实测 RTF 0.8357（v6 配置）已 beat 基线 1.087 达 23.1% → 有效排名
精度 4/4 全过准入 → 获奖资格确定（排名看 RTF 相对位置）
910C vs 910B 硬件对照：同代码官方 0.8357 / 本地 1.166 → 910C 快 28%
（双 die 算力翻倍但 CPU 段不加速，故非 2 倍）
理论外推已验证：8/25 预测 910C 0.51-0.78，实测 0.8357 略高但方向一致
剩余杠杆：FA（v4 已含）+ head 并行（v6 已含）已入提交；910C 上若再加
v7 哈希修复重提交，RTF 预期持平或小幅改善（优化空间已系统性穷尽）
```

---

## 附录 A · 仓库文档地图

| 文档 | 内容 | 何时读 |
|---|---|---|
| session-2026-08-05.md | 会话交接（当前状态/命令/下一步）| 每次开始前 |
| eval-spec.md | 官方评测规范（基线/准入/口径）| 理解规则 |
| cann-patches.md | 6 补丁 + 已知问题 + 观测命令 | 优化前 |
| experiments.md | P0-P1.7 全实验记录 | 查历史数据 |
| optimization-methodology.md | RTF 优化方法论（本文第 4 层来源）| 每次优化前 |
| performance-report.md | 提交物：8 字段性能报告 | 定稿时 |
| reproduce-guide.md | 提交物：复现说明 | 定稿时 |
| decisions.md | 决策链（时间倒序）| 理解"为什么" |
| env-scan.md | 910B3 环境基线 | 环境排查 |

## 附录 B · 术语速查

| 术语 | 一句话 |
|---|---|
| RTF | 生成耗时 ÷ 音频时长，<1 实时 |
| TTFT | 首 token 时间 |
| Prefill/Decode | 输入处理 / 逐 token 生成 |
| KV Cache | attention 历史缓存 |
| GGUF | llama.cpp 权重格式 |
| Backend | CPU/CUDA/CANN 硬件实现抽象 |
| host_buffer | CPU pinned RAM（权重误放 = 假 offload）|
| AICore | NPU 计算核心占用率 |
| HBM 带宽 | 显存带宽（高 = 真在 NPU 算）|
| dequant-bound | 反量化开销吃满收益 |
| OMNI_TTS_QUEUE | LLM↔TTS 队列深度（P1.7 主杠杆）|
| USE_ACL_GRAPH | 图模式（910B 不支持）|
| SPEAK→WAV RTF | 官方性能指标口径 |
