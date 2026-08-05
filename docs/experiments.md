# 实验记录

## 910B3 云环境（2026-08-04 起）

- 硬件：昇腾 910B3 单卡 64GB HBM（厂家授权替代 910C）+ 鲲鹏 920 256 核 + 2TB 内存
- 构建：build-cann（GGML_CANN=ON, CANN 9.1.0-beta.3, aarch64）
- 权重：/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/（官方预置，只读直用）
- cann 补丁：见 [cann-patches.md](cann-patches.md)（5 处修复：T2W 线程 device 绑定 + event 接口 + SQR 断言）

### 实验 P0：910B3 全链路跑通（Q4_K_M, --omni --test 9, build-cann）
- 时间：2026-08-04
- 输入：omni_test_case_0000~0008（9 图片+语音，拼接 prefill 后单次 decode）
- 构建：build-cann + 5 处 cann 补丁
- 结果：退出 0，9 输入全 prefill（26 次），生成 23 wav（round_000）
  - T2W RTF：mean **0.861** | P50 0.850 | P95 1.040 | min 0.72 | max 1.11（23 chunk）
  - 实时占比：**87%（20/23 chunk RTF<1.0）**
  - wav 质量：24kHz/16bit/mono，RMS mean 2562 / min 1606，**0 静音**
  - LLM 输出：对 omni_test_case_0000.jpg（滑雪图）准确英文描述 → Q4_K_M 视觉+语义精度正常
- 观察：
  - 这是 **T2W 单段 RTF**（token2wav 推理），不含 LLM+TTS；e2e RTF 待 P1 perf-duplex
  - queue_wait 仍显著（T2W 等 TTS 产 token）→ 瓶颈在 TTS 段（与 4090 结论一致）
  - `--test N` 语义：N 个输入拼接 prefill + 单次 decode（非 N 轮独立对话）
- 意义：910B3 全链路首次跑通 + 首批可信 RTF；cann 补丁是关键（否则 T2W 必崩）
- 原始 log：tools/omni/output/p0_run9.log（gitignored，含完整 23 条 RTF）

### 实验 P1：910B3 perf-duplex 双工基线 + LLM offload 诊断（Q4_K_M / F16, build-cann）
- 时间：2026-08-04
- 目标：出 perf-duplex 双工基线（与 4090 实验002/016 同口径横向比）
- **关键发现：cann 后端量化算子缺失，LLM offload 失败**

诊断链（代码追踪 + 运行时探针 + npu-smi 确认）：
1. perf-duplex Q4_K_M 全 FAIL（TTS RTF 7.97、LLM 判定 P50 150s）→ LLM 在 CPU
2. npu-smi：推理时 **AICore=0%、HBM 3.4G**（LLM 4.7G 不在 NPU）
3. cann device 注册完整（dev_count=2、CANN0 type=GPU、进 gpus、devices 不空），ngl 链路正确（99/LAYER/main_gpu=0）
4. 真因：cann `device_get_props` 报 `host_buffer=true`（默认），llama 把 LLM 权重放 **cann host buffer（CPU pinned）**，compute 回退 CPU
5. **cann 量化算子缺失**：Q4_K_M 不支持（CPU，prefill 7.9s）；**F16 支持**（NPU，prefill 0.58s，13x）

结果对照（Q4_K_M vs F16 perf-duplex）：

| 指标 | Q4_K_M | **F16** | 4090(Q4_K_M) |
|---|---|---|---|
| TTS RTF | 7.97 FAIL | **0.99 PASS** ✅ | 0.75 |
| LLM 判定 P50 | 150000ms | 9133ms（仍 CPU） | 144ms |
| LLM prefill | 7.9s(CPU) | 0.58s(NPU,单工) | 0.065s |

- ✅ **F16 TTS RTF 0.99 = 首个可与 4090 横向比的有效基线**（910B F16 TTS 0.99 vs 4090 0.75，同量级实时）
- ⚠️ 残留：**F16 双工模式 LLM 仍 CPU**（单工 F16 prefill 0.58s 上 NPU、双工不上；`GGML_CANN_NO_PINNED=1` 双工不稳）→ LLM 双工 offload 待解
- 配置：`GGML_CANN_NO_PINNED=1` 让 LLM 用 device buffer（单工生效），详见 [cann-patches.md](cann-patches.md) 已知问题
- 原始 log：tools/omni/output/perf_f16.log（gitignored）

### 实验 P1.5：host_buffer 默认 false 修复（单工 LLM 上 NPU，双工待解）
- 时间：2026-08-04
- 改动：补丁 6（ggml-cann.cpp:2825 host_buffer 默认 false，env 翻转 GGML_CANN_NO_PINNED→GGML_CANN_FORCE_PINNED）
- **单工 F16 验证（成功）**：omni-cli --test 1（不带 env）
  - npu-smi：**HBM 23674MB（23.6G）+ AICore 66% + Power 186W** = LLM 全上 NPU ✅
  - prefill 0.773s（NPU 快，vs host_buffer=true 时 7.9s CPU）
  - 意义：单工 LLM 稳定 offload NPU（不需 env），omni-cli 单工模式可用
- **双工 perf-duplex F16 验证（失败）**：HBM 3482 + AICore=0（LLM 仍 CPU），全 FAIL（TTS RTF 1.01）
  - 根因：双工 `duplex_llm_thread_func` 计算路径未走 cann device（host_buffer 修复不覆盖双工）
  - 下阶段：深查 duplex_llm_thread_func（见 cann-patches 已知问题 3）
- 结论：补丁 6 修复**单工** offload（有价值），**双工**是独立 duplex 路径问题

### 实验 P1.6：双工 LLM 上 device（use_mmap=false 突破）+ compute/流水线新瓶颈
- 时间：2026-08-04
- 改动：perf-duplex `use_mmap=false`（强制 eager copy 权重到 device）+ 双探针（LLAMA ngl + CANN alloc）
- **突破**：双工 LLM model **上 device**
  - LLAMA_PROBE：双工 n_gpu_layers=99（传对，非 params 问题）
  - CANN_PROBE：14.4G device alloc **成功**（err=0，dev_ptr=0x12c... 有效 HBM 地址）
  - npu-smi（加载后）：**HBM 23.6G + AICore 峰值 66% + Power 168W**
  - 之前"HBM 3481=model CPU"是**采样时机误判**（加载前/早期），实际 model 在 device
- **TTS RTF 0.80 PASS**（双工流水线，比 P1.5 的 0.99 好，接近 4090 0.75）
- **新瓶颈（复合问题）**：
  - decode 中 AICore 仅 4%（model 在 device 但 NPU 几乎没算 LLM）
  - LLM P50 8840ms / avg decode 1448ms（含大量等待，疑似 audio encoder/流水线瓶颈，非 LLM 本身慢）
  - model 后续释放（t=160 HBM 降到 3481，原因待查）
- 结论：**offload 成功**（model 上 NPU），但 **LLM compute 没真走 NPU**（AICore 4%）+ duplex 流水线有瓶颈。超出 offload 范围，下阶段查 compute 路径 / 流水线

### 实验 P1.7：双工 LLM compute 路径实测诊断 + LLM→TTS 队列解耦（P50 8295→977ms，8.5×）
- 时间：2026-08-05
- 目标：双工 LLM compute 真走 NPU + LLM P50 <1000ms（双工实时）

**第一手日志分析推翻 P1.6 的 "compute 没真走 NPU / AICore 4%" 误判**：复跑 P1.6（F16 perf-duplex 36 帧）+ 后台 npu-smi 0.5s 细粒度采样，decode 活跃窗口 AICore **峰值 60–84%、HBM 带宽 50%** —— decode **确在 NPU**（memory-bound，权重流式），"AICore 4%" 是**采样时机/时间均值伪影**（2min 窗口含 prefill 空闲 + 帧间等待 + drain 阶段，平均 14.5% 但实际 compute burst 到 72%）。**offload 一直正常**，原 cann-patches 已知问题3 的"compute 未走 NPU"前提**不成立**。

**真因定位（6 组对照实验 + micro-probe）**：

| 实验 | 配置 | LLM P50 | ms/token(30帧) | 结论 |
|---|---|---|---|---|
| C-1 | F16 + TTS（=P1.6 基线） | **8295ms** | 49 | decode 在 NPU（burst 72%）但 1.4s/帧 > 1s → 积压 |
| C-2 | F16 `--no-tts`（仅 LLM） | **304ms** | 22 | **LLM 单独 P95 872ms PASS** —— NPU compute 本就够实时 |
| C-5 | F16 + ETH_PROBE | — | dec 13 + emb 8 + 外层≈0 = 22 | per-token 拆解：13ms NPU compute、8ms embeddings 回拷 |
| C-4 | Q8_0 + TTS | 9266ms | 49 | **量化不降速**（Q8_0=F16）→ 非 memory-bandwidth 主导，per-token 开销主导 |
| C-6 | F16 T2W→CPU | — | — | T2W CPU RTF **8.6–10.3**（12× 太慢）→ T2W 不能下 CPU |
| C-7 | F16 TTS-model→CPU | — | 114（更差） | CPU TTS 反压（队列阻塞 LLM）→ TTS-model 不能下 CPU |
| C-8 | **F16 队列 1→16 解耦** | **977ms** | 24.5 | **P50<1000 达标**，复现 976.5 |

- **关键根因**：`omni.cpp:4292` LLM→TTS-model 队列 `TTSThreadInfo(1)`（容量=1）强制 **LLM 与 TTS-model 严格 1:1 锁步**——LLM 每产 10 token（step_size）即 `cv.wait` 等 TTS-model 消费（omni.cpp:10035）。于是每帧 decode 墙钟**叠加了 TTS-model 的 NPU decode 时间**（两者同 NPU 串行）→ 1.4s/帧 > 1s 进帧间隔 → decode_worker 串行积压 → ms_total 无界膨胀到 8.3s（2× per-token 放大成 27× P50 的积压效应）。
- **修复**：队列 1→16（env `OMNI_TTS_QUEUE` 可覆盖），LLM 可 burst、不每 chunk 阻塞，`ms_decode` 回归纯 LLM 时间 → per-token 49→24.5ms（接近 intrinsic 22ms），**P50 8295→977ms**。
- **验证三件套**：
  - npu-smi：解耦后 decode 期 AICore 峰值 68%、HBMbw 53%（compute 真在 NPU，无 CPU fallback）；HBM 维持 36%（model 不释放）✅
  - 质量：文本"没问题，我"正常；wav RMS 2005–2288（非静音，P0 同量级）；**queue=1 vs 16 token 序列逐字相同**（修复 quality-neutral，非回归）✅
  - 同口径：**LLM P50 977ms <1000 达标**（8.5×）；TTS RTF 0.80 PASS（维持/更优）✅
- **残留（exit 2，非 LLM compute 问题）**：① LLM P95 1014–1044ms（临界超 1000 ~14–44ms，per-token 已近 22ms floor）② 首响 e2e 1493–1557ms（T2W ~700ms floor + 首响应 LLM+TTS 路径，与 LLM compute 解耦）。两者达 exit 0 需 T2W 提速（n_timesteps，被 prompt_cache 绑定）或 NPU 多流并发（backend 级）。
- **副产物**：micro-probe（`eval_tokens_with_hidden` 计时 dec vs emb，env `OMNI_ETH_PROBE` 开）；`OMNI_TTS_GPU_LAYERS`/`OMNI_TTS_QUEUE` env 旋钮。
- 配置：F16 / n_ctx 4096 / ngl 99 / use_mmap=false（P1.6）/ stream-interval 1000 / 队列 16
- 原始 log：tools/omni/output/p17_{c1,c2,c4,c5,c6,c7,c8,c8b}.log + npu_c1.log（gitignored）

**结论**：P1.6 的"compute 没真走 NPU"是采样误判，offload 一直正常；P50 8.3s 的真因是 **LLM↔TTS-model 队列锁步**使单 NPU 上 LLM+TTS 串行。一行队列解耦（1→16）把 **LLM P50 砍到 977ms（<1000 达标，8.5×）** 且 TTS RTF 0.80 不回归。下阶段（P2）冲 exit 0 需攻 T2W 提速或 NPU 多流并发（decode 期 NPU 平均仅 ~23%，85% 空闲，硬件有余量但当前串行）。

### 实验 P2-Stage0：exit-0 优化空间验证（三"易"杠杆全证伪，首响天花板澄清）
- 时间：2026-08-05（P1.7 后）
- 目标：验证 exit-0 路径上三个"易"杠杆的可行性（plan Stage 0），定方向。

**三组对照（全证伪）**：

| 杠杆 | 结果 | 机制/证据 |
|---|---|---|
| 2nd NPU device（T2W→dev1） | ❌ 死 | npu-smi `Total Count=1, Chip Count=1, 20 AICores, 64GB` —— **单 compute NPU**；CANN `dev_count=2` 是软件枚举假象 |
| T2W `OMNI_FLOW_STEPS=4`（5→4 减步） | ❌ 死（崩溃） | 放宽 `init_from_host_caches` 的 n_timesteps 硬拒(token2wav-impl.cpp:8308)后，cache 张量本身按 5 步 shape 存 → `ggml_cast` 触发 `GGML_ASSERT(nelements)` 崩溃(ggml.c:3485)。prompt_cache.gguf 需按 4 步重导，而 prompt_bundle 无生成工具（experiment 020 死路复现） |
| `OMNI_STEP_SIZE=5`（首块缩小） | ❌ 无效且更差 | 音频块尺寸由 T2W `T_chunk_token=28`(≈1s) 决定，**与 LLM step_size 无关**；减 step_size 只增 TTS-model 调用开销 → 首响 1493→**1545ms**(更差)、TTS RTF 0.80→**0.88**(更差)、LLM P95 1014→1040。wav dur 仍 1.00s 证实块未缩。 |

**首响 1493ms 真分解（C-8 实测）**：LLM 首解码 ~359ms + TTS-model 产 28 音频token ~430ms + T2W 首wav(1s块) ~700ms ≈ 1489ms，**首块串行**。

**澄清的天花板**：
- 真·首响杠杆 = **T2W `T_chunk_token` 首块专门缩小**（token2wav-impl.cpp:8326，session 常量 28；改首块更小如 8 token≈0.3s → T2W 首wav ~210ms + TTS 首块更短 → 首响可<1000）。但这是**侵入式 T2W session 改动**（变长 chunk + 音频输出适配），高工作量/中高风险，是 exit-0 的唯一路径。
- **稳态 LLM P95<1000 可达**（并发 Stage 3 + emb 清理），但**不帮首响**（首块串行）。
- exit 0 = 首响<1000，**需侵入式 T2W 首块 resize**；否则 exit 2 由首响 floor 锁定。

**副产物**：`OMNI_STEP_SIZE` env 旋钮（step_size 可调，默认 10 不变；实测减值无益但保留为可调）；token2wav cache 硬拒注释更新（说明为何减步不可行）。

**结论**：plan 的两个"易"杠杆（T2W 减步、首块缩小 via step_size）**Stage 0 全证伪**。剩余可行杠杆：① emb 清理（小，安全）+ 并发（Stage 3，稳态 LLM P95，backend 手术）——不碰首响；② T2W 首块 `T_chunk_token` resize（侵入式，唯一 exit-0 路径）。需决策是否为 exit 0 投入侵入式 T2W 改动，或接受首响 floor（exit 2）只拿稳态收益。

### 实验 P2-Stage3（诊断）：NPU 并发可行性 —— 证伪（runtime-capped 1.24×）
- 时间：2026-08-05
- 目标：诊断式验证"单 NPU 能否并发跑多个 CANN stream"（决定并发杠杆值不值得投 T2W async 手术）。
- 方法：`llama-bench`（纯 LLM decode，F16 8B，-ngl 99，tg128）单跑 vs 2 进程并发，npu-smi 采样 AICore + HBM 带宽。

| 配置 | tg128 单进程 | 总吞吐 | AICore max/avg | HBMbw max/avg |
|---|---|---|---|---|
| 单进程 | 27.65 t/s（36ms/tok） | 27.65 | 41 / 22.4% | 32 / 28% |
| 2 进程并发 | 17.2 t/s each | 34.4（**1.24×**） | 45 / 17% | 40 / 36% |

- **关键**：2 并发仅 1.24×（全串行应 1×、全并发应 2×），且 **AICore（22–45%）和 HBM 带宽（28–40%）均未饱和** —— 说明 "85% 空闲 AICore" **不是可榨取的免费算力**：某层 runtime/driver/per-token-overhead 把并发 LLM 吞吐封顶在 ~1.24×（两 decode 抢同一执行资源但无一项饱和）。
- **理论 floor**：F16 8B decode = 15.25GB / 1.3TB/s ≈ 12ms/tok；实测 36ms（llama-bench）/ 22ms（duplex）均高于 floor → per-token 开销主导（非纯带宽）。
- **结论**：**并发杠杆证伪** —— 不值得为 1.24× 投 T2W async backend 手术（且不帮首响）。idle AICore 是 bandwidth/overhead-bound 空闲，非并发可利用。

**P2 综合天花板**：exit 0 三"易"杠杆（T2W 减步 / step_size 首块 / 2nd device）Stage 0 全证伪；并发杠杆 Stage 3 诊断证伪（runtime-capped 1.24×）。**exit 0 在当前 910B/F16 配置下不可达**，唯一剩余路径是侵入式 T2W 首块 `T_chunk_token` resize（解首响 floor，高工作量/风险）。否则现实天花板 = P1.7 成果（LLM P50 977ms <1000、TTS RTF 0.80、exit 2，首响 ~1500ms floor）。

### 实验 P2-量化复核：Q8_0 在 CANN 上更慢（量化杠杆终结核伪）+ 910B 贴 F16 floor
- 时间：2026-08-05
- 背景：框架纠正后重估"量化能否闭合 vs 4090(Q4_K_M) 的精度差"。Agent 查 CANN 后端：Q8_0 "support" = `aclnnWeightQuantBatchMatmulV2`（dequant INT8×F16→F16 再 F16 matmul），非硬件 INT8；无 `aclnnInt8Matmul`/W8A8 路径。
- **实测（llama-bench 纯 decode，隔离 duplex 开销）**：

  | model | tg128 | pp512 |
  |---|---|---|
  | F16 | 27.65 t/s（36ms/tok） | 1196 t/s |
  | Q8_0 | **25.57 t/s（39ms/tok，慢 ~7%）** | 1184 t/s |
  | Q4_K_M | CPU fallback（超时） | — |

- **结论**：Q8_0 即使在纯 decode（无 duplex 开销掩盖）也比 F16 **慢** —— `aclnnWeightQuantBatchMatmul` 是 dequant-bound，未用 910B INT8 单元，dequant 开销 > 带宽节省。**量化杠杆终结核伪**（CANN 此 build 无原生 INT8/W8A8；要真 INT8 需自研 W8A8 type + aclnn 通路 + loader，大工程）。
- **910B LLM decode 已贴 F16 floor**：`llama_decode` 13ms/token vs 理论 12ms（15.25GB/1.3TB/s）→ 硬件高效，per-token 可减开销有限（emb ~8ms + scheduler/logits 几 ms），非大杠杆。
- **exit-0 真阻塞定性为架构性**：首响 T2W ~700ms 首块 floor（需侵入式 T2W 首块 resize）+ P95 临界（贴 floor）。非"CANN 低效可低成本修"。

---

> 2026-07-31 补充：llama-omni-server 启动日志确认两条 ctx 告警
> - LLM: n_ctx_seq 8192 < n_ctx_train 40960（只用 1/5，910C 显存够可加大）
> - TTS: n_ctx_seq 8192 > n_ctx_train 4096（官方 demo 默认 -c 8192 超出 TTS 训练长度！
>   解释实验 019 的悖论：2048（训练长度内）慢、8192（超限）快，机制待查——可能 TTS 的
>   行为一致不影响对比）

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

### 实验 004-007：量化矩阵（Q6_K/Q5_K_M/Q4_K_S/Q4_0, 4090, 双工 perf）

| 档位 | TTS RTF | e2e RTF | LLM P50 | LLM P95 | 首响e2e P50 | 备注 |
|------|---------|---------|---------|---------|-------------|------|
| Q8_0 | 0.32* | 0.32* | - | - | - | *101s 长音频，待验证 |
| Q6_K | 0.75 | 0.83 | 127.9 | 160.2 | 426ms | |
| Q5_K_M | 0.86 | 0.90 | 133.5 | 166.1 | 453ms | 含 13.9s 长轮 |
| Q4_K_M | 0.73 | 0.79 | 144.7 | 214.2 | 417ms | 基线 |
| Q4_K_S | 0.86 | 0.90 | 126.0 | 153.5 | 463ms | |
| Q4_0 | 0.87 | 0.91 | 120.3 | 144.5 | 447ms | |

关键洞察：
1. 除 Q8_0 异常外，TTS RTF 0.73-0.87，档位间差异仅 ~15%——
   量化不是 RTF 的主要杠杆（与预期不同）
2. Q4_K_M 最优（0.73），Q6_K 接近（0.75）；Q4_K_S/Q4_0 反而不如
   Q4_K_M（K-quant 在此 workload 上更优）
3. LLM 判定延迟 P50 仅 120-145ms（间隔 1000ms）→ LLM 不是瓶颈
4. RTF 瓶颈在 TTS 生成 + Token2Wav 段（LLM 快≠RTF 好）
5. 对比噪声：各档模型输出内容/音频时长不同，需固定输入交叉验证

下一步：
1. ~~交叉验证 Q8_0~~ ✅ 完成——见实验 008
2. 转向 TTS/Token2Wav 参数优化（真正瓶颈区）

### 实验 008：交叉验证 + 输出质量检查（关键发现）

Q8_0 / Q4_K_M 各重跑 2 次，RTF 完全可复现（0.32 / 0.73）。
但检查 llm_debug/llm_text.txt 发现：

| 档位 | RTF | 输出内容 | 判定 |
|------|-----|---------|------|
| Q8_0 | 0.32 | "??????" 重复乱码（957B 循环） | ✗ 生成 bug，出局 |
| Q4_K_M | 0.73 | 正常中文对话 | ✓ 4090 最优 |
| Q6_K | 0.75 | 正常 | ✓ |
| Q5_K_M | 0.86 | 正常 | ✓ |
| Q4_K_S | 0.86 | 正常 | ✓ |
| Q4_0 | 0.87 | 正常 | ✓ |

结论：
- Q8_0 的 0.32 是虚假性能（重复 token 循环，内容不可用）
- 判定标准必须加"输出内容质量检查"——RTF 低但内容乱码无意义
- 4090 上最优档位 = Q4_K_M（0.73）
- 待办：910C（CANN 后端）上重新验证 Q8_0——乱码可能是 CUDA 后端
  特定 bug，CANN 算子路径不同可能正常（届时仍需内容检查）

### 实验 009-011：ctx 参数矩阵（Q4_K_M, 4090）

| ctx | TTS RTF | e2e RTF | 输出 | 结论 |
|-----|---------|---------|------|------|
| 2048 | 0.81 | 0.87 | 正常 | 差（滑动窗口频繁触发） |
| 4096 | 0.73 | 0.79 | 正常 | 基线 |
| 8192 | 0.68 | 0.73 | 正常 | 甜点 |
| 16384 | 0.68 | 0.73 | 正常 | 饱和 |

结论：ctx=8192 最优（-7%），大 ctx 减少 KV cache 滑动窗口触发；
LLM 判定延迟基本不变（120-122ms）→ 影响在 TTS/滑窗段

当前最优组合：Q4_K_M + ctx 8192 → TTS RTF 0.68

待验证：Q6_K × ctx 8192（档位×ctx 组合是否叠加）

### 实验 012：组合验证（Q6_K × ctx 8192）

结果：TTS RTF 0.77（vs Q6_K×4096 的 0.75）——大 ctx 对 Q6_K 无提升
结论：ctx 提升仅对 Q4_K_M 有效，无组合叠加收益
✅ 最终最优组合：Q4_K_M + ctx 8192 → TTS RTF 0.68（-7% vs 基线）

### 实验 013-015：优化候选验证（TTS 缩容 / march=native）

| 配置 | TTS RTF | 结论 |
|------|---------|------|
| TTS n_ctx=2048 + march | 0.75 | TTS 缩容无效（vs 0.68 基线） |
| TTS 回退 + march | 0.75 | march=native 无效 |
| TTS 回退 无 march | 0.75 | 与 ctx8192 早期 0.68 矛盾 |

关键发现：perf-duplex 虽固定 seed=42（OMNI_SAMPLER_SEED），
但生成内容仍非确定（md5 不同）→ 单次 RTF 波动 ~10%

方法论沉淀：
- 每个配置必须多次运行（≥3 次）取中位数/均值
- RTF 差异 <0.03 视为噪声，>0.05 视为真实差异
- 报告中的对比数据全部来自标准化测试

### 实验 016：标准化验证（Q4_K_M，每配置 3 次）

| 配置 | run1 | run2 | run3 | 结论 |
|------|------|------|------|------|
| ctx 8192 | 0.75 | 0.75 | 0.75 | 真实（3 次一致） |
| ctx 4096 | 0.77 | 0.77 | 0.77 | 基线 |

结论修正：
- ctx 8192 真实收益 2.6%（0.77→0.75），早期 0.68 为环境状态异常值
  （GPU 刚释放/温度/其他卡负载影响）
- 同环境多次运行高度可复现（3 次完全一致）
- 跨时段有环境波动（~10%）→ 正式评测数据须稳定环境 + 多次取均值

✅ 4090 最终配置：Q4_K_M + ctx 8192 + 默认编译（Release, GGML_CUDA）
   TTS RTF = 0.75（标准化）

注意：量化矩阵（实验 004-007）为单次测量，档位间真实差异需
以标准化重测为准（Q4_K_M vs Q6_K 的 0.02 差异在噪声内）

## 优化队列（更新）

1. ~~量化对比~~ ✅ 完成——Q4_K_M 最优 0.73（Q8_0 乱码出局）
2. ctx 参数矩阵：2048→0.81、4096→0.73、8192→0.68（进行中，16384 待测）
3. 编译：-O3/LTO/march
4. CANN 侧（910C）：USE_ACL_GRAPH 图模式

## 实验 020：Flow 采样步数（n_timesteps）优化探索（2026-08-01）

背景：官方 QA 确认允许对 Token2Wav/Flow 蒸馏/微调替换权重。
代码发现：C++ Token2Wav 的 Flow ODE 采样步数 n_timesteps 硬编码 5（omni.cpp 三处），
减少步数可线性降低 TTS/Token2Wav 段（瓶颈段）计算量。

改动：omni.cpp 三处传参改为 OMNI_FLOW_STEPS env 控制（默认 5 保持基线）。
已同步 secs 重编译。

实验结果：
| 步数 | 结果 | 说明 |
|---|---|---|
| 5（默认） | 基线 0.75 | 正常 |
| 4 | 失败 EXIT=3 | GPU init failed，无 wav |
| 3 | 失败 EXIT=3 | GPU init failed，无 wav（LLM 段正常 P50 124.7ms） |

根因（代码定位）：prompt_cache.gguf 内嵌 n_timesteps=5（导出时写入），
init_from_host_caches 校验 cache_host.n_timesteps != n_timesteps → 拒绝
（token2wav-impl.cpp:8309）。图构建本身支持任意步数（need_rebuild 按步数重建），
但被 cache 校验封死。解法需按新步数重新导出 prompt_cache.gguf。

重新导出三路评估：
1. prompt_bundle 现算 + T2W_EXPORT_CACHE_DIR：bundle 文件无生成工具（只读不写）→ 死路
2. Python T2W（pyt2w/）：支持 n_timesteps 现算，但无 CLI 开关 + 需 1.2GB PyTorch 模型
   + Python 基线慢 → 性价比低，放弃
3. 蒸馏 flow 少步数 + 自定义导出（官方允许）：训练路径，时间紧 → 列为 910C 期可选加分项

结论：n_timesteps 是真实杠杆但被 cache 绑定封死；本次 env 改动保留（默认 5 无副作用）；
910C 上如 CANN 后端无此校验可复用。后续优先级：图模式 → 量化重扫 → 大 ctx。
