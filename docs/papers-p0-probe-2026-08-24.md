# P0 探针：论文 floor-first 方法论复核 + TTS per-step 插桩（2026-08-24）

> 触发：论文清单（DFlash/DARTree/SwiftSpec/MixedDimKV/Think-Before-Grid-Search 等）评审后，
> 唯一可迁移思路 = "先算理论下界再定位瓶颈"方法论 → 对 910B4+官方Σ口径四大段做复核，
> 发现 tts/encode 两大赛段离理论下限有 10x+ 差距（推翻 08-22"各段均为硬时间"结论）。
> 批准后执行 P0 四探针。全部红线内（不改推理数学），v5 提交包未动。

## 探针 1：TTS per-step 插桩（OMNI_TTS_STEP_PROFILE=1，omni.cpp sample_tts_token 5 点计时）

**发现：TTS 段 53% 是 CPU head_code matmul（标量循环），非 NPU 硬时间**

| 段 | 优化前 | 构成 | 优化后（行间并行 24 线程） | Δ |
|---|---|---|---|---|
| getemb（hidden 回拷） | 0.35ms | 2% | 0.33ms | — |
| **head（CPU matmul 6562×768）** | **8.6ms** | **53%** | **3.08ms** | **-64%** |
| sample（CPU 采样） | 0.46ms | 3% | 0.47ms | — |
| npu（prefill 1 token forward） | 6.9ms | 42% | 6.61ms | — |
| **total/步** | **16.3ms** | | **10.5ms** | **-36%** |

（238 稳态步均值，t=0 首步含 condition re-forward 除外；26 步/帧 × 帧数）

**根因**：head_code_weight（[6562,768] float）乘 hidden_state 的 logits 计算在 CPU 单核
标量执行。GCC -O3 不向量化：① 浮点归约（sum 累加）默认不向量化（FP 非结合律）；
② 指针无别名证明。8.6ms = 5.04M 次乘加 × ~1.7ns/次（纯标量）。

**修复**：行间并行（std::thread，env OMNI_HEADCODE_THREADS 默认 24，0=禁用）。
每行内部保持与原代码完全相同的标量累加顺序 → **logits 数值逐位一致**（零数学改动）。
采样在 head 之后串行执行，RNG 状态不受并行影响 → token 序列逐位一致。

## 探针 2：npu-smi 细粒度采样（0.3s 间隔，NPU id=3）

- AICore p50=61% 持续（4 线程轮转提交，NPU 不闲）
- HBMbw 90% 采样点 = 0（瞬时带宽脉冲 + 采样间隔漏峰；910B4 npu-smi 25.2.0 该列不可靠）
- **结论**：HBMbw 佐证力有限，TTS 段硬证据以插桩为准（CPU head 主导已直接证明）

## 探针 3：VPM op 清单（vision.cpp 静态）

- VPM 每帧 ~300 个 NPU op（27 层 ViT × ~10 op + resampler）
- FA（OMNI_VISION_FA）已换掉 attention 链 ~6 op/层 → encode -8.2%（FA 实验，8/22 已采纳）
- **结论**：encode 段 op 数主导，剩余空间 = norm/QKV 融合 + 消除 permute/cast + 图模式

## 探针 4：USE_ACL_GRAPH 复核 —— 旧结论推翻

- **旧结论**（8/2x env-scan/cann-tuning-guide）："910B 头文件缺失，编译 FATAL_ERROR"
- **实测**：`aclmdlRICaptureBegin/End/ExecuteAsync` 声明在
  `/usr/local/Ascend/cann-9.1.0-beta.3/include/acl/acl_rt.h`（:4440/4462）；
  CMakeLists `option(USE_ACL_GRAPH)` 默认 OFF，仅 310P 触发 FATAL（910B 不在列）；
  独立目录 `cmake -DUSE_ACL_GRAPH=ON` **编译链接成功**（build-cann-graph/）
- **意义**：图模式（graph capture + LRU 缓存 + ExecuteAsync，ggml-cann.cpp
  evaluate_and_capture_cann_graph 已完整实现）可实测。靶子 = TTS npu 6.6ms/步
  （580M 模型理论 ~1ms，~5.5ms 为 per-call launch/graph 开销）+
  VPM ~300 ops/帧。
- **风险**：KV 增长 → FLASH_ATTN shape 变化 → 每次 re-capture（= 无收益）；
  decode 段 `use_cann_graph = (Q ne[1]==1)` 门控已处理 prefill 排除；需实测确认
  TTS/LLM decode 的 KV 是否触发 re-capture。运行时 env `GGML_CANN_ACL_GRAPH=off`
  （官方评测默认关，可门控）。

## 官方 rts 实测（eval-singlecard-910b.env，全量，turn=7 core 7 帧）

| 段 | 8/22 三锁（v5 基线） | 今日（+head 并行） | Δ |
|---|---|---|---|
| encode | 0.402-0.409 | 0.359 | -0.05 |
| llm_prefill | ~0.02 | 0.016 | ~0 |
| llm_decode | 0.241 | 0.240 | ~0 |
| **tts** | **0.417** | **0.275** | **-0.142（-34%）** |
| token2wav | 0.257 | 0.249 | ~0 |
| **core RTF** | **1.3291** | **1.139** | **-0.19（-14.3%）** |

- batch_validity 全 true（data_valid + realtime_eligible + core_sufficient + score_eligible）
- 收益与插桩预测一致（-5.5ms/步 × 26 步 ≈ -143ms ≈ -0.14 RTF）
- 3 次独立 rts（smoke2 ×2 + 全量）tts 段 0.267-0.292 稳定

## 代码改动（review-optimize 分支，env 门控默认关=官方行为）

1. `tools/omni/omni.cpp` sample_tts_token：5 点 per-step 计时插桩（OMNI_TTS_STEP_PROFILE=1）
2. `tools/omni/omni.cpp` head_code matmul 行间并行（OMNI_HEADCODE_THREADS=24，0=禁用；
   默认 24 开启，因数值逐位一致无风险）
3. 未动：ggml-cann、官方文件、v5 提交包

## 下一步（P1 候选，待批准）

1. **图模式实测**（build-cann-graph 已编译）：TTS/LLM decode 段 graph capture 是否避免
   re-capture（KV 增长风险验证）→ 若有效，npu 6.6ms/步 可压向 ~2ms → tts 再 -0.1，
   RTF → ~1.03
2. **VPM op 融合**（沿用 FA 成功模式）：norm/QKV 融合 + permute/cast 消除 → encode -10~20%
3. head 线程数调优（24 vs 48/64）微测
4. 精度验证（逐位一致论证已充分；如需实证可跑 seed-tts-eval smoke）

## 方法论沉淀

- "08-22 各段均为硬时间"结论错在：TTS 段从未被直接计时（910B3 时代靠 queue_wait 推断），
  且 head_code CPU matmul 长期被当作"NPU 段"的一部分。floor-first 复核 + per-step 插桩
  直接暴露 53% CPU 占比 —— 与论文 Think Before You Grid-Search 的"先算下界再定位"
  完全对应。
- 教训：结论要标注测量方式与时间（哪些段是被直接计时的、哪些是推断的）；
  旧机结论（910B3）换新机（910B4）后必须复核。

## 精度确认（2026-08-24 补充）：同 seed A/B wav 逐字节一致 —— 零影响实锤

- **方法**（比 benchmark 更严格）：llama-omni-server 两次（OMNI_HEADCODE_THREADS=0 vs 24，
  其余同：--seed 42 / NZ=off / FA+VPM_FA+NPU_SERIAL），gen_tts.py 各生成 zh 前 20 条
  （同 ref+target），wav md5 逐字节对比
- **结果**：**20/20 wav 逐字节一致**（md5 全同，0 不一致）——整条生成链路
  （LLM→TTS head_code→token2mel→vocoder→wav）在并行 on/off 下输出同一份音频
- **推论**：WER/ASV 必然相同（音频即同一文件），无需再跑 benchmark 评分；
  head 并行对 TTS 质量影响 = 0（数学零改动 + RNG seed 固定下确定性一致）
- **方法论沉淀**：零影响验证的最强形式 = 同 seed A/B 端到端 wav 逐字节对比
  （比 logits 字节对比更全链路，比精度 benchmark 更严格更快——20 条 ~8 分钟生成）
  server 需 --seed 固定（TTS 采样 RNG 来自 common_sampler，--seed 可控）
- 产物：/tmp/tts_a_th0/（THREADS=0）vs /tmp/tts_b_th24/（THREADS=24）
