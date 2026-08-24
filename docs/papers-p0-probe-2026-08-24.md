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

## P1 图模式实测（2026-08-24 补充）——CLOSED，910B4 运行时不可用

- **编译层**：build-cann-graph 全量构建成功（perf-duplex + server，USE_ACL_GRAPH=ON）
- **off 基线**（GGML_CANN_ACL_GRAPH=off，graph binary）：TTS_STEP npu=6.60ms/步，
  与 build-cann 普通 binary 完全一致（控制变量成立）
- **on 实测**（GGML_CANN_ACL_GRAPH=on，decode 默认走图）：**证伪**——
  ① TTS "zero norm detected" 数值异常（graph capture 期间 host-device 数据流破坏）
  ② "build_whisper: Whisper encoder graph built" 反复出现 = 每帧 re-capture
  （输入/KV 变化触发，图缓存 LRU 失效——正是理论风险点）
  ③ frame 33 处理失败/超时 + 进程挂死（EXIT=143 强制终止）
- **结论**：与官方 README L320 警告完全一致（"必须保持 GGML_CANN_ACL_GRAPH=off，
  否则 vision encode 阶段可能因非法同步拷贝直接 abort"）——**910B 图模式运行时不可用**
  是官方实测结论，头文件齐全 + 编译通过 ≠ 运行时可用。**P1 图模式 CLOSED，不追。**
- **教训**：USE_ACL_GRAPH 旧"头文件缺失"结论错在编译层判断；但方向性结论
  （910B 不用图模式）恰好正确——编译层与运行时是两层，都要实测。

## P1 ③ VPM 构成量化（2026-08-24 补充）——graph build 非瓶颈，compute launch 主导

- **插桩**（vision.cpp build_minicpmv 三段计时 + op 统计，env OMNI_VPM_PROFILE=1 门控默认关）
- **graph build 仅 0.2-0.3ms**（推翻"每帧重建图是瓶颈"假设）——vpm_ms 227ms 几乎全是 compute 执行
- **op 构成**（883 nodes，~700 执行）：MUL_MAT 169 / ADD 281（~189 为 matmul 后 bias）/
  NORM 58 / CPY 56 / CONT 30 / FLASH_ATTN_EXT 28 / UNARY(GELU) 27 / MUL 58 /
  RESHAPE 88+PERMUTE 85（evaluate 跳过不执行）
- **结论**：~700 执行 op × 0.32ms/op = launch/搬运主导（MUL_MAT 理论计算 ~0.004ms/op）
- **融合候选评估**：
  | 候选 | 省 op 数 | 预期 | 工作量/风险 |
  |---|---|---|---|
  | matmul+bias 融合（aclnn 带 bias API 替代 Mm/BatchMatMul 三参调用） | ~189 ADD | encode -20%+ | 1-2 天，改 ggml-cann 核心，需验证 aclnn bias API 存在性 |
  | NORM 融合（扩展 ADD+RMS_NORM fusion 到 GGML_OP_NORM） | ~29 | encode -5% | 1 天，新 fused kernel |
  | CPY/CONT 削减（FA 分支 cast/cont 布局） | ~60 | encode -8% | 0.5-1 天，vision.cpp 布局 |
- **注意**：VPM norm 是 GGML_OP_NORM（LayerNorm mean-based，非 RMS）→ 现有
  GGML_CANN_OPERATOR_FUSION（ADD+RMS_NORM）对 VPM 无效（已实测 fusion=0/1 完全一致）；
  TTS ResiLM 的 RMSNorm 融合也实测无收益（npu 6.88 vs 6.60 噪声级）→ OPERATOR_FUSION 全场景关闭

## P1 ③ B 方案（CPY/CONT 削减）实测——证伪，vision.cpp 单文件无可省空间

- **假设**：VPM op 统计 CPY 56 + CONT 30 = 86 个数据移动 op 可削减
- **实测**：把 build_attn 的 `v=ggml_cont(v)`（每层 1 个）移到 mul_mat 分支 →
  **op 计数零变化**（CONT:30 不变）——ggml_cont 对连续布局是 no-op（构建时
  直接返回原 tensor，从未生成图节点）。vpm 中位 227.5→223.2ms 纯噪声。
- **真相反推**：CONT 30 = cont_2d(attn)×27（布局重排必须）+ inp cont + resampler；
  CPY 56 = k/v F32→F16 cast×54（FLASH_ATTN_EXT 只对 q 有内部 cast（aclnn_ops.cpp:3854），
  k/v 直接 create_tensor 无 cast 处理 → 预 cast 必须）+ resampler。
- **结论**：vision.cpp 单文件无可削减（v cont no-op、cast/cont_2d 必须）。
  **B 关闭**。真正的肉在 ggml-cann 层：① flash_attn 内部 cast k/v（省 54 CPY ~20ms，
  encode -9%）；② matmul+bias 融合（省 ~189 ADD ~40ms，encode -17%）。
  两者均为 ggml-cann 核心改动（1-2 天），且官方 README L268 允许 env 上传。
- 已回滚（vision.cpp 恢复原状，仅保留 VPM_PROFILE 插桩）；git diff 验证只剩插桩

## P1 ③ B'（flash_attn 内部 cast k/v）实测——净负收益，回滚

- **实现**：aclnn_ops.cpp ggml_cann_flash_attn_ext 加 k/v 内部 cast（复制 q 的 Step 1 模式，
  pool allocator + aclnn_cast）+ vision.cpp 删预 cast → **CPY 56→0 实锤**（nodes 883→827）
- **性能**（perf-duplex vpm 分布对比）：
  | 指标 | B'前 | B'后 | Δ |
  |---|---|---|---|
  | p50 | 227.5 | 225.4 | -0.9% |
  | p90 | 288.8 | 297.8 | +3.1% |
  | p99 | 1836 | 5116 | **+179%** |
  | max | 3577 | 5658 | +58% |
  | 均值 | 280.7 | 363.5 | +30% |
- **结论**：中位微降但尾部大幅恶化（p99 3.5x）——flash_attn 内部 cast 的 pool 分配在长尾帧
  引入大抖动；官方 Σ 口径（pooled 均值）下 RTF 变差。**B' 回滚**（aclnn_ops.cpp 备份恢复 +
  vision.cpp 预 cast 恢复，git diff 验证工作区=HEAD）
- **教训**：① "省 op 数"≠"省时间"——cast 本身没消失（图节点→内部调用），省的是节点调度；
  ② 改动必须看分布（p50/p90/p99/max），只看中位会漏掉尾部恶化——Σ 口径对尾部敏感；
  ③ **vision.cpp 预 cast（图节点，数据流明确）是更稳的设计**，ggml 层内部 cast 的 pool
  分配抖动不可接受。VPM 剩余融合空间（matmul+bias）同样有 pool/调度风险，收益未证，
  **VPM 优化线正式收口**（除 matmul+bias 大工程外无红线内空间）

## P1 ③ B（matmul+bias 融合）——CLOSED，CANN 无匹配 API

- **验证**：aclnn 头文件扫描——`aclnnMatmul` 4 参（self/mat2/out/cubeMathType，**无 bias**）；
  `aclnnAddmm` 有 bias（self 支持 F32）但 **mat1/mat2 只支持 F16/BF16**——VPM 激活是 F32
  （ggml mul_mat src1 F32）→ 需额外 F32→F16 cast → 收益被 cast 抵消（B' 已证 cast 尾部抖动）。
- **结论**：matmul+bias 融合在 CANN 无匹配 API，**CLOSED**。VPM 优化线彻底收口
  （构成量化/OPERATOR_FUSION/B/B' 全部实测完毕，无红线内空间）。
- 注：若未来 CANN 提供 F32 输入的 bias matmul（如 aclnnFusedMatMul 变体），可重估。
