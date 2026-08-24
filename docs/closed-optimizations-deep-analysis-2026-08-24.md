# CLOSED 优化点原理级深度分析（2026-08-24）

> 目的：对全部已关闭优化点做"原理级"重审（表层实测结论 → 底层机制 → 关闭是否成立 →
> 是否有被掩盖的深度机会 / 910C 重查项），而非停留在"实测无收益"表面。
> 触发：用户要求"从原理上进行深度分析，而不是浮于表面"。

## 一、总框架：910B4 耗时模型（原理级）

```
段耗时 = Σ(算子数 × 算子内部固定成本) + 带宽下限项
        ───────────────┬───────────────    ──────┬─────
        所有 NPU 段共同支配项（CANN 算子       decode 独有
        的 GetWorkspaceSize/启动/同步固定成本，  （F16 权重读取
        ~0.05-0.3ms/op，图模式触及不到）        13.7ms/tok）
```

各段实测归因（2026-08-24 插桩/Profile 数据）：

| 段 | 实测耗时 | 图规模 | per-op 成本 | 带宽下限 | 归因 |
|---|---|---|---|---|---|
| encode-VPM | 227ms | 883 nodes (~700 执行) | 0.32ms | ~5ms | 算子内部成本主导 |
| encode-APM | 17ms/帧 | whisper | — | — | 小头，无空间 |
| llm_decode | 13.7ms/tok | — | — | 13.7ms/tok | **贴带宽下限** |
| tts npu | 6.6ms/步 | ~50-100/步 | ~0.1ms | ~1ms | 算子内部成本主导 |
| t2m | 115ms (5步) | 11740 nodes/帧 | 0.05ms | ~8ms | 算子成本，per-op 已低 |
| vocoder | 117ms | 2321 nodes | 0.08ms | ~5ms | 算子成本 + 计算长尾 |

**核心结论**：除 decode（带宽下限）外，所有段都是算子内部固定成本主导。
两个通用杠杆（图模式省 ggml 调度、算子融合省算子数）均已原理级证伪
（详见下）——910B4 收口是**原理性**的，不是"碰巧没试出"。

## 二、CLOSED 点原理级重审

### 1. 量化（Q8_0/Q4_0）——关闭成立，机制 = dequant-bound
- 表层：Q8_0+FA 1.6484（decode 0.446，比 F16 慢 90%）；Q4_0 质量崩
- 原理：ggml-cann 的量化 matmul 实现 = 先 dequant 权重到 F16 再走 FP16 Cube
  → Q8 读取省一半带宽（0.58GB vs 1.16GB）但 dequant 开销 + F16 中间量
  抵消，且 FP16 Cube 算力未变 → 净负。Q4 的 4-bit 精度损失致推理异常。
- **Ascend Cube 原生 INT8 算力是 FP16 的 2 倍**——但 ggml 的 Q8_0 语义是
  权重量化+激活 F16（非 QAT int8 双量化），CANN 无"int8 权重×fp16 激活"
  原生 matmul（aclnn 的 int8 路径要求两侧同型）→ 原理性关闭。
- 910C 重查项：无（同样受 ggml 语义限制，除非改数学=红线）。

### 2. KV 量化——关闭成立（910B4），910C 必须重查
- 表层：CANN 无 QUANTIZE 算子，CPU 反量化带宽反增
- 原理：decode 是带宽下限（13.7ms/tok = 16.4GB/1.2TB/s，KV 读取占大头）。
  KV 量化（INT8）能省 KV 读取带宽 → decode 0.24 理论上可降 30-40%——
  **原理上有效，是算子缺失型关闭**（不是原理不可行）。
- **910C 重查项：若 910C CANN 有 QUANTIZE/DEQUANTIZE 算子（或 FA 支持
  int8 KV），KV 量化是 decode 段最大剩余杠杆**——本地无法验证，等官方环境。

### 3. 投机解码——关闭成立（工程 + 数据双否定）
- 表层：CANN 无 draft 支持
- 原理：投机解码省的是 target 串行步数（draft 并行 + batch 验证）。
  官方 Σ 口径下**原理有效**（decode 段自身耗时可降）——关闭原因是：
  ① EAGLE/Medusa 类需第二模型权重（无）；② **n-gram 投机（免权重）对
  音频 token 序列可预测性极低**（TTS 的 token 是声学单元，无文本 n-gram
  规律）→ 接受率 <5%，验证开销反超；③ CANN batch 验证路径未实现。
- 910C 重查项：低优先（即使 CANN 支持，音频 token 可预测性限制不变）。

### 4. 图模式——910B4 原理级关闭（三层否定）
- 表层：全量崩 → 受限版（VPM only）规避成功但无提速
- 原理：图模式省的是"ggml 层逐节点调度"（微秒级函数调用，~1ms/图）。
  段耗时的真正大头是 **CANN 算子内部固定成本**（aclnn 的
  GetWorkspaceSize→workspace 分配→kernel 启动→同步，~0.05-0.3ms/op，
  录制图重放时一个不少）→ aclmdlRIExecuteAsync 与 eager 逐帧同耗时。
- **910C 重查项：CANN 910C 的图执行若是真正图编译（算子融合+单次调度），
  收益可能大——set_acl_graph 接口已就绪，一行 env 启用。**

### 5. 多流并发/重叠——结构性关闭（口径 + 无排队双确认）
- 表层：Σ 口径段耗时双计 → 无收益；q_before 恒 1 无排队
- 原理：官方 RTF = Σ段耗时/音频（judge_support.py stage_total 相加）。
  重叠只降墙钟不降 Σ；排队等待若存在则计入段耗时（重叠可消），
  但 q_before 恒 1 证明无排队 → 重叠无对象。原理闭环。

### 6. 绑核——关闭成立（负载依赖，原理 = NUMA 距离 × 负载）
- 表层：绑核 vs 不绑核 1.3342 vs 1.3291-1.342 噪声内
- 原理：绑核收益 = f(线程跨 NUMA 的远端内存代价, 调度器能否就近放置)。
  系统负载 ~10%（256 核）→ 调度器总能就近放置 → 绑核无增益。
  8/21 绑核 -21%（910B3）是 CPU 侧瓶颈时代（vocoder 340ms CPU 主导）的
  结论；910B4+FA 后 NPU 主导 → 失效。**同参数结论跨硬件变更必须重扫**。
- 910C 重查项：官方环境若 CPU 竞争大，OMNI_NPU_BIND 代码已备（默认关）。

### 7. vocoder ——"CPU 物理限"结论**推翻**（910B4 上在 NPU）
- 表层（旧）：vocoder CPU 170ms 近物理限（perf-ceiling 文档，910B3 时代）
- 实测（2026-08-24，OMNI_T2W_PROFILE=2）：**vocoder 在 NPU**（im2col+matmul
  表达卷积，token2wav-impl.cpp 5 处 ggml_im2col + conv_transpose_1d），
  voc.compute p50=117ms（图 2321 nodes，per-op 0.08ms）+ 长尾 p99=224ms
  （长音频帧的序列长度 → 计算主导）。
- 深度结论：vocoder 已是 NPU 最优表达（im2col→matmul 原生算子），
  117ms 中算子成本与计算各占部分，无 IM2COL 替换类新杠杆；长尾为
  计算主导（硬时间）。**"物理限"表述错误但"无优化空间"结论仍成立**
  （已是最优表达 + 融合/图模式原理级证伪）。
- 910C 重查项：无（表达已最优，910C 快在硬件）。

### 8. t2m（Flow）——11740 节点但 per-op 已低，空间 ~10-20ms 级
- 实测：t2m.compute 115ms（5 步），图 11740 nodes（5 步展开），
  per-op 0.05ms（近算子成本下限，比 VPM 低 6 倍）
- 原理：t2m 的执行效率其实不差（per-op 成本低），115ms 中真实计算
  占比高；融合空间 = 减算子数 → 理论 ~10-20ms（t2w -5%）——但受
  aclnn API 限制（融合全证伪）→ 不成立。**per-op 0.05ms 说明该段
  已接近 CANN 算子成本下限，无调度层空间。**

### 9. VPM 融合全家族（OPERATOR_FUSION/B/B'/matmul+bias）——原理级关闭
- 表层：五连实测全关（详见 vpm-optimization-closed-2026-08-24.md）
- 原理：① VPM norm 是 GGML_OP_NORM（非 RMS）→ 现有融合不匹配；
  ② cast 是必须（FLASH_ATTN 只对 q 内部 cast，k/v 预 cast 是更稳设计）；
  ③ matmul+bias：aclnnMatmul 4 参无 bias、aclnnAddmm 限 F16 输入（VPM
  激活 F32 需额外 cast，B' 已证 cast 尾部抖动 p99 3.5x）→ API 层无解。
- 910C 重查项：无（aclnn API 限制与硬件无关）。

### 10. 其余（队列/内存 env/ctx/token2mel 细锁/n_timesteps）——原理清晰
- 队列：Σ 口径 + q_before 恒 1（输入节奏限制，非反压）→ 结构性关闭
- 内存 env：HBM 分配策略不影响算子内部执行路径 → 原理性无空间
- ctx-size：KV 预分配不影响单帧执行 → 无空间
- token2mel 细锁：三锁=串行化上限（core 帧 NPU 串行 1132ms > 帧周期
  1000ms，锁可消竞争不可消超载）→ 墙钟预算原理性关闭
- n_timesteps≠5：图构建编译期常量（token2wav-impl.cpp:48，steps≠5
  初始化即崩）→ 结构限制

## 三、结论

1. **910B4 原理级收口成立**：所有段（除 decode 贴带宽下限外）受"算子内部
   固定成本"支配，而 CANN 910B 的图执行不省该成本（实测）、aclnn API
   不支持算子融合（API 扫描）、算子集不支持量化/投机（符号扫描）——
   三条原理路径全部封死，非"没试出"。
2. **910C 适配清单**（唯一可能有新空间的场景，均需官方环境实测）：
   - KV 量化（若 CANN 有 QUANTIZE/DEQUANTIZE 或 FA 支持 int8 KV）→ decode
   - 图模式（若 910C 图执行真提速）→ t2m/vocoder/VPM（set_acl_graph 就绪）
3. 修正两条旧文档结论：vocoder"CPU 物理限"（实为 NPU，表达已最优）、
   "APM 是盲区"（实测 17ms/帧，无空间）。
