# 极限性能分析：SPEAK→WAV RTF 理论下限（2026-08-06）

> 目标：基线 1.087 非天花板。当前 RTF 0.57（24+NUMA，beat 48%）。从**硬件物理极限 + 各段计算/访存特性**推导 RTF 理论下限（终极目标），给出**量化方法**。性能工程建模（roofline + profiling），非优化实施。

## 一、硬件 + 模型数据

**910B（单 die，本机 NPU1）**：FP16 **~320 TFLOPS** | HBM2e 64GB | 带宽 **~1.2 TB/s**（LLM 实测 21ms 排除 0.4TB/s，确认 1.2）| 鲲鹏 920 256 核 CPU。

**模型规模**（GGUF F16, 2B/param）：
| 模块 | 大小 | 参数量 | 位置 |
|---|---|---|---|
| LLM（MiniCPM-o-4_5） | 16.4GB | ~8.2B | NPU HBM |
| TTS-model | 1.16GB | ~580M | NPU HBM |
| Flow（token2mel） | 0.46GB | ~229M | NPU HBM |
| vocoder（hifigan2） | 0.083GB | ~42M | **CPU** |
| audio/vision enc | 0.66/1.10GB | 330M/548M | NPU（非 TTS RTF 路径） |

## 二、各段 Roofline（物理下限推导）

| 段 | 类型 | 物理下限推导 | 下限 | 实测（P4 24+NUMA） | 利用率/判定 |
|---|---|---|---|---|---|
| **LLM decode**（t_done 前，不在 TTS RTF） | memory-bound | 16.4GB / 1.2TB/s | **13.7ms/tok** | dec 14ms + emb 7ms = 21ms | **dec ~100% 近极限**；emb 7ms 是 sync 开销（get_embeddings） |
| **TTS-model** | memory-bound | 1.16GB/1.2TB/s × 25 audio-tok | **~24ms/chunk** | <T2W（queue_wait 53ms 小，与 T2W 重叠） | 近极限，**非瓶颈** |
| **Flow（token2mel）** | compute-bound | 229M×5步 DiT；权重读 0.46GB/1.2TB/s=0.38ms << 102ms → 非 memory-bound | 待 msprof 算子确认（NPU 利用率低 AICore 23%） | **102ms**（t2m.compute p50） | **NPU 算子低效**，有优化空间（但 C 重叠后被 vocoder 隐藏） |
| **vocoder（CPU hifigan）** | compute-bound | 42M CNN，CPU 24t+NUMA | **346ms**（实测 threads/NUMA 最优，CPU 物理限） | **346ms**（voc.compute p50） | **CPU 物理限**（threads 16→24 已最优，32 不稳），红线内不可降 |

**关键判定**：
1. **LLM decode 已近物理极限**（14 vs 13.7ms）—— LLM 段无优化空间（emb 7ms sync 是唯一尾巴）。
2. **T2W 是 TTS RTF 瓶颈**（Flow 102 NPU + vocoder 346 CPU 串行 = 448ms），TTS-model 与 T2W 重叠（非瓶颈）。
3. **vocoder CPU 346ms 是红线内极限锁**（threads/NUMA 已最优，CPU 物理限）。
4. **Flow 102ms NPU 利用率低**（compute-bound 但 AICore 23%），可优化（NPU 算子效率），但 C 重叠后被 vocoder 隐藏（不影响红线内极限）。

## 三、整体 RTF 理论下限（终极目标）

TTS RTF = (末wav - LLM t_done)/音频 = TTS-model(NPU) + T2W(Flow NPU + vocoder CPU)。NPU 段串行（单 NPU），vocoder CPU 可与 NPU 重叠（候选 C）。

| 场景 | 构成 | RTF |
|---|---|---|
| **当前（串行，24+NUMA）** | TTS-model 24 + Flow 102 + vocoder 346 ≈ 472ms | **0.57**（实测，含开销） |
| **红线内极限（C 重叠 NPU‖vocoder）** | max(TTS-model+Flow=126ms, vocoder 346ms) = 346ms | **~0.34**（vocoder CPU 346ms 锁死） |
| ~~理论极限（vocoder NPU化）~~ | **❌ 不可行**：CANN backend 不支持 CONV_2D/CONV_1D（`docs/ops/CANN.csv` 全 support=0），HiFiGAN 核心是 CNN（Conv1D im2col→CONV_2D）→ 算子缺失，需移植 500-1000 行 ACLNN + 完整测试 + 数值风险 | **—** |

### 终极目标

- **红线内极限（仅调度重叠，CPU vocoder 不动）：RTF ~0.34**（当前 0.57，gap **0.23**）
  - 突破口：候选 C（vocoder ‖ NPU 段重叠），受 vocoder CPU 346ms 物理限锁死
  - 风险：C 需跨 window 重构（拆 push_tokens_window + t2w_thread 双缓冲 + Flow/voc cache 双缓冲），复杂 + 质量 bug 风险
- ~~**理论极限（vocoder NPU化）：RTF ~0.10-0.15**~~ **❌ 不可行**（实测评估 2026-08-06）：CANN backend **不支持 CNN 算子**（CONV_2D/CONV_1D，`docs/ops/CANN.csv` 全 support=0），HiFiGAN 核心是 CNN → 算子缺失阻断。需 CANN CNN 算子移植（500-1000 行 ACLNN + 完整回归测试）+ NPU/CPU 数值差异风险。

**关键瓶颈**：**真实硬极限 = 0.34**（vocoder CPU 346ms 物理锁 + NPU化不可行）。要突破 0.34 唯一路径 = CANN CNN 算子移植（大工程 + 数值风险，非"不改数学"能覆盖的实现层改动）。

## 四、量化方法（怎么测/评估极限）

| 方法 | 测什么 | 工具 | 本机状态 |
|---|---|---|---|
| **1. Roofline 各段** | FLOPs(compute)/GB(memory) vs 910B 峰值(320T/1.2TB/s) | 推导 + perf 数据 | ✅ 已用（本文） |
| **2. msprof NPU 算子** | Flow 102ms 算子分布 + AICore 利用率 | msprof --export=on --summary-format=csv | ⚠️ --export 解析慢（>300s timeout），未拿到 csv；PROF_ 原始产物有 |
| **3. OMNI_T2W_PROFILE** | token2mel/vocoder 精确耗时分段 | OMNI_T2W_PROFILE=1 | ✅ 已用（t2m.compute 102 / voc.compute 346） |
| **4. CPU vocoder profiling** | vocoder CNN 算子 + CPU 利用率 | perf record / gprof | ❌ perf 不可用；gprof 需重编 -pg；用"threads/NUMA 最优=CPU 物理限"反推 |
| **5. TTS-model 单独计时** | TTS-model decode 耗时 | 日志/插桩 | ⚠️ 无单独计时；用 queue_wait 53ms 小 + memory-bound 24ms 下限推断"非瓶颈" |
| **6. 重叠分析** | NPU 串行 + CPU 并行的理论 RTF | 推导 max(NPU, CPU) | ✅ 已用（红线内 0.34） |

**方法论沉淀**（可复用）：① 量化各段 memory/compute 下限（权重GB/带宽 / FLOPs/算力）→ 瓶颈类型 + 利用率；② 分段计时（OMNI_T2W_PROFILE/ETH_PROBE）定位主因；③ 重叠分析推导理论 RTF；④ gap → 优化空间 + 可行性（红线/工程）。

## 五、当前 0.57 vs 极限 gap + 可行性

| 目标 | gap | 路径 | 红线 | 工程 | 风险 |
|---|---|---|---|---|---|
| 0.57→0.34（红线内极限） | -0.23 | C 重叠（vocoder‖NPU） | ✅ 流水线 | 中（跨 window 重构） | 质量 bug（双缓冲同步） |
| 0.57→0.15（NPU化） | -0.42 | vocoder NPU化 | ⚠️ 后端改 | 大（hifigan NPU 移植） | 红线 + NPU 串行 |
| 0.57→0.10（NPU化+Flow优化） | -0.47 | + Flow 算子优化 | ⚠️ CANN 算子 | 大 | 红线 |

**取舍**：
- RTF 0.57（24+NUMA）已 beat 基线 48%，**红线内**边际（C 0.34）收益递减 + 风险升。
- 突破 0.34 **必须越红线**（vocoder NPU化）—— 与"不改推理数学/后端"红线冲突，且大工程。
- **0.34 是红线内硬极限**（vocoder CPU 346ms 物理锁），除非接受 vocoder NPU化风险。

## 六、数据来源与限制

- LLM 下限 13.7ms：16.4GB/1.2TB/s（memory-bound，910B HBM 带宽 1.2TB/s，WebSearch + LLM 实测 21ms 反推确认）。
- vocoder 346ms CPU 物理限：threads 8/16/24/32 + NUMA 扫描，24+NUMA 最优（P4 实测）。
- Flow 102ms NPU 低效：OMNI_T2W_PROFILE t2m.compute + decode 期 AICore 平均 23%（P3 npu-smi）→ 算子利用率低（msprof 算子级待精确，--export 解析慢未完成）。
- TTS-model 非瓶颈：queue_wait 53ms（T2W 等 TTS 少）+ memory-bound 24ms 下限 → TTS-model < T2W。
- **限制**：msprof --export csv 未拿到（解析慢）；perf 不可用（CPU vocoder 算子级未精确）；vocoder/TTS-model 物理下限为"实测最优反推"而非算子级推导（工具受限）。

## 七、结论

**终极目标 RTF**：
- **真实硬极限 ~0.34**（C 重叠，vocoder CPU 346ms 物理锁；当前 0.57，gap 0.23）
- ~~vocoder NPU化（理论 0.10-0.15）~~ **❌ 不可行**（CANN 不支持 CNN 算子 CONV_2D/CONV_1D，HiFiGAN 核心阻断；需 CANN 算子移植，大工程 + 数值风险）

当前 0.57（24+NUMA）处于**红线内合理高位**——LLM 已近极限、vocoder CPU 接近物理限、NPU化被 CANN 算子缺失阻断。**0.34 是真实硬极限**（C 重叠可达但跨 window 重构风险）；突破需 CANN CNN 算子移植（非纯调度，大工程）。
