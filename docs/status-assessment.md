# 参赛状态评估（2026-07-31，08-04 更新，08-05 P1.7 纠正）

## 🔧 2026-08-05 P1.7 纠正（覆盖下文"AICore 4% / compute 未走 NPU / model 释放"等判断）

下文（08-04 版）把"双工 decode AICore 仅 4%"当作"compute 未真走 NPU"的结构性瓶颈。
**P1.7 实测推翻该误判**：npu-smi 细粒度采样证 decode **一直在 NPU**（burst AICore 60–84% +
HBM 带宽 50%），"AICore 4%"是采样时机/时间均值伪影；"model 释放（t=160 HBM 3481）"同
为采样误判（model 维持 HBM 36%）。**offload 从未失败**。

**P50 8840ms 真因**：`tools/omni/omni.cpp` omni_init 的 `TTSThreadInfo(1)`（LLM→TTS-model
队列容量=1）强制两者 1:1 锁步 → 每帧 decode 墙钟叠加 TTS-model 的 NPU decode → 1.4s/帧 > 1s
→ 积压 → P50 8.3s。**修复（队列 1→16）→ 双工 LLM P50 8295→977ms（8.5×，<1000 达标）**，
TTS RTF 0.80 不回归。残留 exit 2：P95 1014ms（临界）+ 首响 1493ms（T2W ~700ms floor）。
详见 [experiments.md](experiments.md) P1.7、[cann-patches.md](cann-patches.md) 已知问题3。

> 下文 08-04 版的"AICore 4% / compute 未走 NPU / model 释放"三处判断以此为准作废。

## ⚠️ 框架纠正（2026-08-05）：对比基线不当，真瓶颈是 CANN 后端而非 910B 硬件

下文（含 P1.7/P2 段及 08-04 版）多处用"910B vs 4090 → 910B 是瓶颈、要追 4090 实时"框架，**此框架有两个混淆，需纠正**：

1. **硬件档位不对等**：910B 是**数据中心级 NPU**（对标 A100/H100 档），4090 是**消费/工作站 GPU**（Nvidia 高端算力是 H100/H200/B200，非 4090）。纸面 910B 的 HBM 带宽（1.3TB/s）**高于** 4090（1TB/s），INT8 算力是其强项——**同精度下 910B 本应胜出**，不应是"追赶方"。
2. **精度不对等（更致命）**：4090 跑 **Q4_K_M**（~5GB 权重，贴 floor ~8ms/token）；910B 跑 **F16**（~16GB）——**被迫**，因 CANN 不支持 Q4_K_M 量化算子（P1 发现）。这 **3.2× 权重大小差**不是硬件差，是 **CANN 后端缺量化支持**，占了大半性能 gap。

**证据：910B NPU 算子本身高效**——`llama_decode` 实测 13ms/token，而 F16 8B 理论 floor = 15.25GB/1.3TB/s = **12ms**（贴 floor）。但 llama-bench 实测 36ms/token，多出的 ~23ms 是 **ggml/CANN per-token 管线开销**（scheduler dispatch + KV + logits 处理），非 NPU 算力也非纯带宽。即：**4090 跑在 ~1.5× floor、910B 跑在 ~3× floor**——910B 离自己 floor 更远的这部分，是 CANN 后端开销，不是硬件。

**纠正后的真瓶颈** = **CANN 后端两个 gap**：① 不支持量化算子（被迫 F16，多 3.2× 带宽）；② per-token 管线开销大（~3× floor）。**不是 910B 硬件不行。**

**公平 baseline 与优化目标（纠正）**：不是"追 4090"，而是"**逼近 910B 自身 floor（12ms/token）**"——这样 910B 作为数据中心卡本应稳过双工实时门槛，exit-0 自然达成，而非靠 T2W 首块手术硬抠。重新打开两条更对档位的杠杆：
- **A. 砍 per-token CANN/ggml 管线开销**（36ms→贴近 13ms floor）：scheduler/KV/logits 路径。同精度下即可反超 4090，且首响/P95 一起下来（它们卡住的根因也是 per-token 开销）。
- **B. 让量化在 CANN 上真正工作**（非 gguf Q8_0 那种 on-the-fly dequant——P1.7 实测无效；而是 CANN 原生 INT8/W8A8 通路，发挥 910B INT8 强项）。P1.7 未探，待重估。

> 下文 P2"接受天花板"结论按此重述：天花板是 **CANN 后端**（有 backend 工作可做），非硬件绝路；exit-0 可达性比原结论更乐观。

## P1.7 完成状态（2026-08-05）+ P2 优化空间

**P1.7 成果**：双工 LLM P50 **8295→977ms（8.5×，<1000 达标）**，TTS RTF **0.80**（不回归），quality-neutral（queue=1 vs 16 token 序列逐字相同）。offload 证实在 NPU（burst AICore 60–84% + HBMbw 50%）。修复 = `tools/omni/omni.cpp` LLM→TTS 队列 1→16 解耦（env `OMNI_TTS_QUEUE`）。**未达 exit 0（exit 2）**：LLM P95 1014ms（临界超 14ms）+ 首响 e2e 1493ms（T2W ~700ms floor）。

**P2 优化空间**（按 P1.7 实测证据排序，分三角度；冲 exit 0 = 解 P95 + 首响）：

### 角度一：硬件算力流程（最大杠杆，直击 exit-0 阻塞）
1. **NPU 多流并发** 🔥（首选）：P1.7 npu-smi 证 decode 期 **NPU 平均仅 ~23%（85% 空闲）** —— LLM decode + TTS-model + T2W 三者在单 NPU 上**时间片串行**（队列解耦消除了锁步阻塞，但三者仍共享 NPU 调度，未真并行）。若 CANN 多流让三者真并发 → 吞吐叠加 → P95 与首响同降。待查：`ggml-cann` 是否单 stream / 设备级锁导致串行；910B 多 stream 并发能力。
2. **T2W 提速**（解首响 floor）：首响 1493ms 的 T2W ~700ms floor 来自 Flow ODE 5 步（`n_timesteps`，experiment 020 被 `prompt_cache.gguf` 绑定）。破绑定减步数 → T2W 线性降 → 首响降。待查：prompt_cache 重新导出路径 / CANN 侧 cache 校验可否绕过。
3. **decode per-token dispatch**：dec=13ms/token 中可能含 per-token graph dispatch。ACL graph 缓存可减，但 910B `USE_ACL_GRAPH` 头文件缺失（不支持）→ 受限，次选。

### 角度二：数据结构（per-token 下探）
1. **embeddings 回拷**：`eval_tokens_with_hidden` 每 token `malloc` + `memcpy` hidden_states（n_embd=4096 floats）= **emb 8ms/token（36% intrinsic）**。改预分配 buffer + 异步/批量 device→host 回拷 → 省 per-token sync。待查：CANN 异步回拷可行性。
2. **KV cache 量化**：KV 当前 F16。若 CANN 支持量化 KV（Q8_0）→ KV 内存/带宽减半 → attention 提速。待查：CANN KV 量化算子。
3. **LLMOut/队列对象零拷贝**：`hidden_states` 用 `std::vector::insert` 拷贝（omni.cpp:9902），可改 move / 预分配。

### 角度三：存储空间（多为非瓶颈，剔除伪杠杆）
1. **权重量化 = 伪杠杆（已证）**：P1.7 C-4 证 **Q8_0 decode 速度 = F16**（per-token 开销主导，非带宽）→ 量化对 910B 双工 decode **无收益**，不再追求（纠正 track1-optimization-space.md 的 Q8_0 假设）。
2. **HBM 余量足**：64G 用 ~36%，非吞吐瓶颈（瓶颈是串行调度，见角度一）。
3. **prompt_cache.gguf**：T2W `n_timesteps` 绑定属角度一 T2W 提速项。
4. **磁盘 GGUF**：全套只读预置，非瓶颈。

**推进顺序**：角度一.1（NPU 多流并发）→ 角度一.2（T2W 提速）→ 角度二.1（emb 回拷）。下阶段进 plan 模式对角度一.1 深挖（ggml-cann 调度/并发模型）定方案。详见 [experiments.md](experiments.md) P1.7、[cann-patches.md](cann-patches.md) 已知问题3。

## 结论（2026-08-04 更新）

**910B3 环境就位 + 全链路跑通 + 双工 TTS RTF 0.80 基线成立**（首个 <1，
接近 4090 的 0.75）。硬门槛从"全部未产生"推进到"性能基线已有，精度/Demo 待补"。
最大变量已从"环境到位时间"转为"双工 compute 是否真走 NPU"的结构性问题。

## 一、硬门槛（准入，决定能否进排名）

| 准入项 | 状态 | 说明 |
|---|---|---|
| 精度 ≤2pp | 红 | 3 个 benchmark 零数据，仅调研口径（daily-omni-notes.md）；F16 无损精度理论安全但未实测 |
| Demo 可用 | 黄 | llama-omni-server 后端验证通过（GPU1 全模块加载 11.3G）；worker/gateway/前端/流式/稳定未验证 |
| 可复现 | 黄→绿 | 910B3 全链路跑通（cann 补丁 1-6 落盘 cann-patches.md），复现材料可执行；官方环境复现验证待 910B 重跑 |

## 二、材料完整度（提交物 5 大块）

| 提交物 | 状态 | 说明 |
|---|---|---|
| 代码/配置 | 绿 | llama.cpp-omni 6 补丁 + build-cann.sh + 配置齐（ggml-cann.cpp） |
| Benchmark 结果 | 红→黄 | 3 benchmark 仍零数据，但 Daily-Omni 脚本已在 code/daily-omni/（910B 权重已预置） |
| 性能报告 | 黄 | 8 字段骨架初稿，910B3 实测数据已积累（RTF 0.861/0.99/0.80），缺正式版 |
| Demo | 黄 | 后端验证 + Demo 仓库就位，缺演示视频 + 全链路 |
| 复现说明 | 黄 | 初稿有，910B3 实测可回填 |

## 三、竞争力（排名）

- 910B3 双工 TTS RTF **0.80**（首个 <1，vs 4090 0.75）——接近但未超越
- 910B3 与 910C 同 CANN 栈（9.1.0-beta.3），数据迁移参考价值高
- 关键差异已确认：**cann 不支持 Q4_K_M 量化**（4090 最优档在 910B fallback CPU）
  → LLM 用 F16（精度无损，prefill 13x）；910B 优化路径与 4090 不同，不能照搬
- 待解结构性瓶颈：双工 decode AICore 仅 4%（compute 未真走 NPU）+ LLM P50 8840ms（流水线等待）+
  model 中途释放——解掉任一即可显著下探 RTF

## 四、910B3 六步走（替代 910C；环境已就位）

编译 CANN 版 ✅ → 权重预置 ✅ → 跑官方基线 ✅（P0 全链路 9 用例）→
优化候选（F16/补丁6/P1.6 双工）✅ → 精度 benchmark ⏳ → 正式 RTF 数据 ⏳

## 五、风险

- ~~910C 一直拿不到（最大）~~ → ✅ 已解除：厂家授权 910B3 替代，环境就位（见 env-scan.md）
- benchmark 代码：✅ code/daily-omni/ 已提供 Daily-Omni 完整脚本，不再等 starter kit
- 8/31 截止（赛事方调整后）：时间窗口宽裕，按计划推进
- **新增风险**：双工 compute 未真走 NPU（AICore 4%）——若为 cann 后端算子缺失类问题，
  修复周期不可控；预案：先用"流水线重叠 + 参数调优"守住 0.80，compute 路径作为增量

## 六、08-04 进展评估（详见 session-2026-08-04.md）

**里程碑**：
- 环境基线对齐（910B3 / CANN 9.1.0-beta.3 / 鲲鹏 256 核 / 64G HBM / 权重预置）
- P0 全链路跑通：cann 补丁 1-5（T2W 线程 device 绑定 + SQR 断言）→ T2W RTF 0.861
- P1 战略发现：cann 量化支持有限（Q4_K_M fallback CPU 7.9s）→ F16 战略（NPU 0.58s）
- P1.5 补丁 6（host_buffer 默认 false）→ 单工 LLM 上 NPU（HBM 23.6G + AICore 66%）
- P1.6 双工 model 上 device（use_mmap=false）→ TTS RTF 0.80 PASS

**当前瓶颈（按杠杆排序）**：
1. 双工 decode AICore 仅 4%——compute 没真走 cann 算子（最大杠杆，解了 RTF 可下探 0.6x）
2. LLM P50 8840ms vs avg decode 1448ms——6x 差距 = 流水线等待（audio encoder 串行？），
   4090 已证明流水线是最大 RTF 杠杆，910B 未吃满
3. model 中途释放（t=160 HBM 3481）——chunk 生命周期待查，避免重复加载吃卡时

**下一步（P1.7）**：
1. 查 duplex compute 路径（对照单工成功的 backend 调用链找差异）
2. 流水线重叠分析（msprof/时间戳对齐，找等待段）
3. P2 量化重扫（Q8_0/Q6_K 在 cann 的支持，Q8_0 无 CUDA 乱码 bug 可能可用）
4. model 释放问题排查
