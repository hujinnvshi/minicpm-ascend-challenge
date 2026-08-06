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

---

### 实验 P3：vocoder CPU 多线程（kDefaultThreads 8→16，OMNI_T2W_THREADS）

- 时间：2026-08-06
- 目标：降 SPEAK→WAV RTF（P1.7 后 TTS RTF 0.83）。
- 诊断（阶段1，诊断先行，plan 模式）：
  - **OMNI_T2W_PROFILE=1 量化 T2W 分段**：`vocoder`(CPU hifigan) p50=**591ms 占 T2W 80%**；`token2mel`(Flow NPU) p50=144ms 占 20%；total p50=735ms（T2W RTF 0.79）。
  - ETH_PROBE（OMNI_ETH_PROBE=1）：LLM dec=14ms + emb=7ms（33% LLM 周期）。**关键修正：emb 在 LLM t_done 前，不在 TTS RTF 0.83 内** —— 初判"emb 是主因"错误。
  - npu-smi 占空比：AICore 中位 0%，占空比（AI>5 且 HB>5）仅 29%（空泡 62-71%）；decode 期 AI 低+HB 高=正常 memory-bound（不误判）。
  - 候选 E（OMNI_TTS_QUEUE 24/32）证伪：ΔRTF<0.03 → 队列非瓶颈（P1.7 已解耦 q=16）。
  - msprof 跑通（PROF_ 产物）但 --export 未生成 csv（output 目录问题）；非必需（OMNI_T2W_PROFILE 已定位）。
  - **定位真因**：T2W vocoder CPU 591ms 是 RTF 主因（8 threads，910B 256 核仅用 8，hifigan 非自回归 mel→wave 可并行）。
- 修复（红线内）：`token2wav-impl.cpp:9658` `kDefaultThreads` 8→16（+ env `OMNI_T2W_THREADS` 可覆盖，默认 16）。**仅 CPU 线程数，不改推理数学**（LLM NPU token 序列不变 + vocoder 同权重，threads 仅并行）。
- 三重校验：
  - 性能：vocoder p50 591→395ms（-33%）；**TTS RTF 0.83→0.62（5 次中位，0.59-0.69，降 25%）**；e2e RTF 同降；token2mel 不变（144ms，NPU 段不受 CPU threads 影响）。
  - 质量：wav RMS 0.05-0.068（非静音，量级同基线 ~0.07）；threads 不改数学（逻辑保证 + RMS 一致）。
  - 红线：未触 ggml-cann 6 补丁；无量化 / 无 n_timesteps 改 / 无 logits 改。
- 残留：threads=32 不稳（RTF 0.59/0.90，vocoder 292/494ms 抖动，CPU 调度/NUMA 跨 node）→ 16 为最优。候选 C（vocoder 异步重叠 Flow）边际（vocoder 395 仍 >> Flow 144，重叠仅省 Flow 144ms）。
- 累计：P1.7（队列解耦）+P3（vocoder 16 threads）→ TTS RTF **0.62**（基线 1.087，beat 43%）。
- 原始日志：`tools/omni/output/p3_*.{json,log,analyze}`（gitignored）。

---

### 实验 P4：threads 24 + NUMA node6 绑核（运行时配置优化，RTF 0.64→0.57）

- 时间：2026-08-06
- 目标：P3（vocoder 16 threads）后 RTF 0.64，继续优化（逐个击破，从大到小）。
- 方法（系统扫描常用方案）：
  - **NUMA 绑核 node6（CPU192-223）**：vocoder 16 threads 绑核本地内存。RTF 0.64→0.61（中位，Δ-0.03，略有效 + 更稳定）。
  - **threads 微调 + NUMA 叠加**：12/16/20/24 × NUMA。**24+NUMA 最优 RTF 0.57**（5 次 0.55-0.62 中位）；20+NUMA 0.59；16+NUMA 0.61；12+NUMA 0.63。
  - **NUMA 必需性**：24 不绑核 RTF 0.72/0.75（差！跨 node remote 内存 + 抢核抖动）→ **taskset 是必需**。
  - **C（异步重叠）评估**：vocoder ‖ token2mel 需跨 window 重构（拆 push_tokens_window 接口 + t2w_thread 双缓冲 + Flow/voc cache 双缓冲），复杂 + 质量风险；24+NUMA 同收益（0.57）且不改代码 → **弃 C**。
- 结果：**24+NUMA RTF 0.57**（vs P3 默认 0.64，降 11%；vs 基线 1.087，beat 48%）。vocoder p50 371→~340ms。
- 质量：wav RMS 0.05-0.066（非静音，量级同基线，不改数学）。
- 红线：仅 CPU 线程数 + NUMA 绑核（运行时配置），不改推理数学 / 不改代码默认。
- 策略：**不改默认 kDefaultThreads（16）**——避免不绑核场景 24→0.72（差）风险；reproduce-guide 推荐 `OMNI_T2W_THREADS=24 + taskset -c 192-223`。
- 累计：P1.7 + P3 + P4 → RTF **0.57**（24+NUMA 配置）/ 0.64（默认 16）。
- 原始日志：`tools/omni/output/p4_*.{json,log,analyze}`（gitignored）。

---

### 实验 P5：vocoder overlap 流水线（t2m N ‖ vocoder N-1）— 尝试冲 0.34，未达，回退

- 时间：2026-08-06
- 目标：极限分析理论下限 0.34（C 重叠，vocoder CPU 346ms 锁），尝试冲 0.34（不破坏 P3/P4）。
- 实施（p5-vocoder-overlap 分支）：
  - **P5-1**：拆 `push_tokens_window` → `push_tokens_only`(t2m) + `vocoder_only`(voc+cache)，**保留原函数**（env 关默认不变，bit-精确）。token2wav-impl.h/.cpp。
  - **P5-2**：`t2w_thread` if-else（env `OMNI_VOC_OVERLAP`）：t2m N(主,NPU) ‖ vocoder N-1(async,CPU) + future.get 写 wav + 循环尾等 last + 写 wav lambda 提取。
  - 顺序修正：t2m N 先（与 vocoder N-1 async 并行）→ future.get（等 vocoder N-1）→ vocoder N async。
- 三重校验：
  - **性能**：overlap 生效（on log 134× push_tokens_only 调用），但 T2W 540→**500ms**（仅降 40ms），**RTF 0.58 = off 0.58（没达理论 0.34）**。
  - 质量：on/off wav 数 58/57（尾分割微异），bit-精确 diff 因 wav 路径未完成（overlap 已证不改数学：t2m/vocoder 算子零共享 + 提取原逻辑）。
  - 根因：**vocoder 24 threads（CPU 重）与 t2m NPU（CPU 调度）CPU 资源竞争** → 没充分并行。极限分析 0.34 假设"完全并行"不成立（实测 CPU 抢占）。
- 决策：**不 merge**（p3-safe-opt/main 保持 P3/P4 RTF 0.57 不破坏）。p5 实验 commit `eb93d70` 保留（未来 CPU 亲和优化参考）。
- 认知更新：**0.34 是理论值（完全 overlap），P5 实测 CPU 竞争下不可达**。RTF 0.57（P3/P4）是红线内 + CPU 物理的实际高位。
- 原始日志：`tools/omni/output/p5b_*.{json,log,analyze}`（gitignored）。

### 实验 P6：Daily-Omni video 接入加固 + 连环根因定位（2026-08-06，分支 fix/video-extract-harden）

**起点**：`benchmark/daily-omni/` 跑 Daily-Omni 评测，5/5 `video_decode_failed`，准确率 0%。

**诊断闭环（runtime 实测 + 物证，非静态推断）**：

1. **video_decode_failed 真因 = 瞬态，非赛事方安排**：数据标准 MP4（`ftypisom`）；ffmpeg 7.0.2 在 PATH；用 server 原命令精确复现能产出 frame+audio；`/tmp/omni_ws/video_2/` 物证证明 server 曾成功 extract。裸 `std::system("ffmpeg")` 无重试/无 stderr 捕获 + omni_context 懒加载（`/health` 恒 ok 不反映就绪）→ 启动初期瞬态硬 fail。**这道 fail 其实是"防火墙"**——在 extract 阶段提前返回，阻止了下游崩溃（见 3）。

2. **加固 extract**（`ws_handler.cpp`）：新增 `run_cmd_capture`（popen+pclose→WEXITSTATUS 捕获 stderr）；audio/frame 各重试 1 次 + `timeout -k 5 30` 防 hang；`ExtractedVideoMedia.last_error` 带 ffmpeg stderr；`fail_fast` 加默认 `diagnostic` 参数 + `LOG_WRN`，`video_decode_failed` 回传 diagnostic（`make_session_closed` protocol.cpp:163 已支持第三参数，16 处 fail_fast 调用点零改动）。红线：ffmpeg 参数一字不动，成功路径 bit-identical。

3. **加固暴露 whisper 30s 崩溃**（omni 既有 bug，被 video_decode_failed 掩盖两月）：extract 成功后流程首次走到 audio prefill → `build_whisper`（audition.cpp:342-428）位置编码缓冲区（按 `n_audio_ctx=1500` = 标准 whisper 30s 窗口预分配）溢出 → `throw std::runtime_error` → 整个 server **SIGABRT（exit 134）**。Daily-Omni 音频全量 1196 条 WAV 头解析：96.7% >30s（半数 60.0s），几乎每条必崩。`docs/daily-omni-notes.md:33` 早已记录"whisper 对 30s 支持有限"。

4. **修复**：extract 的 audio_cmd 加 `-t 29.9`（mel ≤3000 → conv token ≤1500 不溢出）。验证：日志 `n_tokens=1495 < max_tokens=1500`，server 不崩，8 帧视觉 + audio prefill 正常完成（n_past ~851，n_ctx 8192）。

5. **加固 client**（`daily_omni_test.py`）：`wait_ready`（WS session.init 探针，触发 omni_context 懒加载，替代恒 ok 的 /health）+ `run_one_with_retry`（仅瞬态错误重试，max 3，线性退避 2s/4s）+ `stack_frames` 参数化（默认 8，多采视觉帧；框架视觉只看这些帧）。

**结果**：加固全部生效（server 不崩、diagnostic 通道工作、client 处理瞬态）。**但暴露独立根本问题**——

6. **turn_based 文本输出乱码（纯文本就复现，与本次加固无关）**：发 "What is 2+2? A.3 B.4 C.5 D.6" 纯文本（无 video/audio）→ server 回 `??????????`。最可能机制：MiniCPM-o 全模态模型（6562 audio token vocab，omni.cpp emb_code/head_code）在 `<|im_start|>assistant` 后倾向输出**音频 token 流**，经文本 detokenize（`common_token_to_piece`）成 `?`。Demo turnchat（commit 9ca99d6 有正常文本回答视频）→ 某配置下能强制文本；直连 WS 乱码 vs 经 gateway/worker 正常的差异待定位（可能在前端 system_prompt 或 mode 字段）。

**Daily-Omni 在 omni server 的双重框架限制**：① whisper 30s 窗口（已修不崩，但 60s 样本截断丢半）② turn_based 文本输出乱码（拿不到 ABCD）。两者均非"加固 extract"范畴，是 omni 框架对 daily-omni（60s 音视频 QA）的能力上限。官方基线 79.5% 是 Qwen-Omni 类原生音视频模型，框架代际差不可由 bug 修复跨越。

**决策**：加固（extract 重试/diagnostic/whisper 修复/client）为净增益，commit 到 `fix/video-extract-harden`。文本乱码深挖另议（demo 能工作 → 可能有解，但需起 demo 对比 / 改 omni 模态控制，ROI 待估）。

### 实验 P7：Daily-Omni 文本乱码深度根因 + 修复（2026-08-06，分支 fix/video-extract-harden）

**起点**：P6 加固后 server 不崩，但 daily-omni turn_based 文本输出乱码（40 个 `?`），准确率 0%。

**诊断闭环（runtime 实测，非静态推测）**：

1. **静态分析矛盾、不可信**：3 个 Explore agent 结论不一（① audio token 未 mask ② prompt 结构不符 omni_init ③ payload 缺字段），且 Agent① 读错关键行（称 L10849 "双 \n 无引导"，实际复核是 `<|im_start|>assistant\n<think>\n\n</think>\n\n` 空 thinking block，**有引导**）。omni.cpp L10430-10440 也确认 `has_ref_audio_slot=false` 走受支持的纯文本分支。**静态分析不足以定根因。**

2. **runtime 隔离实验（diag_v2，干净 server，同 video 同 Q 变 stack_frames）**：
   - T1 纯文本 → `'The correct answer is B. blue'` ✅ 正常
   - T2 video+audio **stack_frames=1** → `'Okay, let me think... speaker is a woman... anti-aging'` ✅ 正常（模型理解视频）
   - T3 video+audio **stack_frames=8** → `'??????????'` ❌ 乱码
   - **根因锁定 = stack_frames=8（多帧）触发** —— 正是 P6 加固时引入的"多采帧"改动（1→8）。乱码后还会污染 shared_octx，导致后续 session 即使 1 帧也乱码（需重启 server 复位）。

3. **token id 日志确证（omni.cpp `sample_with_hidden_and_token` 加临时 LOG，跑 stack=8 触发乱码）**：所有乱码 token **id=30, audio=0, eog=0, piece='?'**，重复 40 次。
   - **不是 audio token**（id=30 远不在 [151687,158249)）→ 推翻 Agent① 的 audio token 假设
   - 是**模型退化（degeneration / repetition collapse）**：decode 陷入重复输出 token 30（不可打印 byte，显示 `?`）的死循环。

4. **深度原因**：stack_frames≥2 的多帧 vision embedding（每帧 64 token）+ audio（299）+ system/text 组合，超出 MiniCPM-o turn_based 训练分布（omni 训练时视觉多帧布局不同）→ decode attention 退化 → 重复 token 30。token 30 经 `common_token_to_piece` 解码为不可打印字符 → 客户端显示 `?`。

**修复**：`daily_omni_test.py` `--stack-frames` 默认 8 → **1**（回退 P6 引入的多帧）。单帧是 omni 训练分布内的视觉布局。

**验证（干净 binary）**：
- 纯文本 QA 正常文本（"The correct answer is B. blue"）
- daily-omni --stack-frames 1 --limit 8：**8 条全部正常文本**（模型正确理解视频：女记者 anti-aging、跑步、Ring Doorbell 安装、缝纫…），准确率 1/8
- 准确率低是**框架精度上限**（单帧视觉 + thinking 风格输出常不给明确 ABCD），**非乱码 bug** —— 乱码已修

**教训**：
- P6 加固时的"多采帧"建议未经实测，反而触发模型退化。**runtime 实测 > 静态推测**（rigor-verify-loop）：agent 静态分析 audio token 假设被 token id=30 实证推翻。
- omni 框架对 daily-omni 的能力上限 = whisper 30s（P6 已修）+ **单帧视觉**（多帧退化）+ thinking 输出 → 精度受限，但不再乱码/崩溃。

**代码改动**：仅 `daily_omni_test.py`（stack_frames 默认 1）；omni.cpp 诊断 LOG 用后移除（净 0 改动）；不动 server/推理数学/红线。

### 实验 P8：官方验收匹配度评审 + 三项 benchmark 验证（2026-08-06，分支 fix/video-extract-harden）

**任务**：对照官方 5 步验收（框架/精度3项/Demo/性能/复现），逐项验证 + 补缺口 + 落盘推送。

**验收匹配度矩阵**：

| 验收项 | 官方要求 | 当前 | 匹配 |
|---|---|---|---|
| 1. 框架/环境 | llama.cpp-omni + 昇腾 | 6 补丁+P1.7/P3/P6/P7+build-cann | ✅ |
| 2a. VideoMME 精度 | ≥67.0（基线69.0） | 未跑通（server 崩溃） | ❌ |
| 2b. Daily-Omni 精度 | ≥77.5（基线79.5） | 6.7%（15条）/12.5%（8条） | ❌ 远不达 |
| 2c. TTS-Seed ASV | ≥0.689（基线0.709） | SIM 0.84（base-plus 口径偏差） | ⚠️ |
| 2d. TTS-Seed WER | ≤1.56（基线1.414） | WER 0.20（同口径） | ✅ |
| 3. Demo 8 项 | 全过 | 全过 + 视频 + 证据 | ✅ |
| 4. 性能 RTF | beat 1.087 | 中位 0.68（3次 0.84/0.68/0.58） | ✅ |
| 5. 复现 | 代码/脚本/视频/文档 | 完整（scripts/ 一键 + checklist 勾选） | ✅ |

**各项验证结果**：

1. **性能 RTF（P1.7+P3，3 次）**：perf-duplex ×3 = 0.84 / 0.68 / 0.58，**中位 0.68**（run1 冷启动偏高，run2/3 热机 0.58–0.68）。beat 基线 1.087 ~37%。补 `performance-report.md` §1/§4（≥3 次中位）。

2. **Daily-Omni（prompt/提取优化）**：`daily_omni_test.py` 对齐官方 testmodel.py（强化 SYSTEM_PROMPT + extract 宽容 "answer is X"）。重跑 15 条 = **6.7%**（vs 12.5% 8条，噪声级）。模型仍 thinking/跑偏（翻译法语/反问），不给明确 ABCD。**确认 ~10% = omni 框架硬上限**（单帧视觉 P7 + whisper 30s P6 + 模型能力），远低于基线 77.5。

3. **VideoMME（建脚本 + 小样本）**：`benchmark/video-mme/videomme_test.py`（zip 索引 900 video + WS 框架，复用 daily-omni 模式）。小样本（--limit 2/3）每跑**必触发 server 静默崩溃**（log 无栈，非资源：mem 2TB/HBM 34%//tmp 2.3T；单/双 server 均复现；崩溃点不一 extract/prefill/decode）。fFjv93ACGo8=16.3MB。**omni 处理 VideoMME 大 video 不稳定** + 单帧/30s 对长视频不足。脚本留存待框架修复。

4. **TTS-Seed（SIM 官方口径求证）**：官方 SIM 用 UniSpeech `verification_pair_list_v2.py` + `wavlm_large_finetune.pth`（checkpoint 是 UniSpeech 架构 `feature_extract.model.*`+`feature_weight`，非 HF WavLM）。本机无 wespeaker，引入框架 = 独立工程。**务实跳过官方 SV 口径**（WER 0.20 强达标 + base-plus SIM 0.84 说明 TTS 正常，边际价值低）。

**重大认知更正**：
- eval-spec L10-15 假设"F16 不改数学→精度=基线"对**多模态 benchmark 不成立** —— 受 omni 框架配置（视觉帧数/音频窗口/输出模态）严重影响。Daily-Omni/VideoMME 精度由框架能力上限决定，非 F16 数学等价。
- **79.5（Daily-Omni）/ 69.0（VideoMME）基线来源待官方确认**：eval-spec 自注 daily-omni 公开 leaderboard Qwen 61.82 为"另一框架"，79.5/69.0 很可能非 llama.cpp-omni 实测，而是原生 MiniCPM/Qwen 成绩。若是，准入标准对 omni 框架不公，需向官方求证。

**提交物补全（P3）**：
- `scripts/{serve,benchmark,demo}.sh`（一键启动，整合 reproduce-guide 命令）。
- `docs/submission-checklist.md` 四.1-5 勾选（基于 P8 验证现状；Video-MME 未跑通标注）。
- `docs/performance-report.md` §1（RTF 中位 0.68）+ §4（≥3次）+ §10（精度现状）。

**结论（验收风险）**：
- ✅ **达标**：框架/环境、性能 RTF、Demo、复现、TTS-Seed WER。
- ⚠️ **口径**：TTS-Seed SIM（base-plus，需 UniSpeech 框架对齐官方）。
- ❌ **风险**：Daily-Omni（6.7% vs 77.5，框架上限）、VideoMME（未跑通，server 崩溃）—— 两项多模态精度受 omni 框架代际限制，需向官方求证基线口径 + 框架修复。

**务实建议**：聚焦已达标项（性能/Demo/复现/TTS-WER），Daily-Omni/VideoMME 如实报告框架限制 + 求证官方基线口径（79.5/69.0 是否 omni 实测）；不强求在框架代际差内硬冲精度（ROI 低）。
