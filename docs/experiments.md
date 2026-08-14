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

### 实验 P7 重验（2026-08-07）：多帧退化真因 = 非交错打包（框架 bug，非模型上限）

**触发**：官方 vLLM-Omni 指南证明多帧（Daily-Omni ≤64 帧、Video-MME ≤96 帧）可达 78%/70% → 推翻 P7"多帧=模型上限"结论。重验走 stack_frames 全链路代码（非静态推测根因，而是定位打包实现）。

**代码追踪（stack_frames → prefill）**：
1. `ws_handler.cpp:944-971`（视频拆解）：`extract_video_mp4_media` 用 ffmpeg 抽 **N 个 JPEG 帧 + 1 个整段 audio（capped 29.9s）**。第 1 帧 → `tmp_files.image_path`，第 2..N 帧 → `extra_image_paths`；audio → 单个 `tmp_files.audio_path`。**全程无 1s 分段、无 frame-audio 配对**。
2. `omni.cpp:5046-5092`（prefill 组装顺序）：
   ```
   <image>[overview]</image>
   <slice>[frame2]</slice> <slice>[frame3]</slice> …   ← N 帧塞进 high-res IMAGE SLICE 槽
   \n
   <|audio_start|>[整段 30s audio]<|audio_end|>         ← 单个解耦 audio blob
   [text/prompt]
   ```
3. `encode_image_with_vision_chunks`（omni.cpp:496-498）本就是 **MiniCPM 高清图像切片**机制（overview + 空间 tiles）——多帧视频被当成"一张高原图的多个 tile"喂入。

**根因（确认）**：llama.cpp-omni 对视频做 **STACKED 打包**（N 帧 = 图像切片 + 1 个整段 audio blob，audio 在所有帧之后一次性 prefill），而 MiniCPM-o 视频训练（及 vLLM `minicpm-interleave`）是 **INTERLEAVED 打包**（1fps 帧 + 1s 音频段按时间交错：frame0/audio0-1s/frame1/audio1-2s/…）。**堆叠布局 OOD → decode 陷入重复 token id=30（repetition collapse）**。
- 为什么 stack_frames=1 不退化：退化为"1 图 + 1 audio"单输入，是合法 omni 输入（图像+音频 QA），在分布内 → 正常（P7 T2）。
- 为什么 vLLM ≤64/96 帧正常：它用交错打包，在训练分布内。

**结论修正**：
- P7 的**观察**（stack_frames≥2 → token id=30 重复 40 次）✅ 正确、可复现。
- P7 的**根因结论**（"多帧超出 turn_based 训练分布 → 模型上限"）❌ 不准确：OOD 是真的，但不是"多帧本身对模型太难"，而是**llama.cpp-omni 把视频帧当图像切片 + 单段 audio 的非交错打包**与训练分布不符。**这是框架打包 bug/限制，非模型上限**——与 vLLM 78% 一致。
- `daily_omni_test.py` 的 `--stack-frames 1` 仍是当前**正确的 workaround**（单帧避免 OOD），但**不是终局**。

**修复方向（不动推理数学，红线内）**：在 `ws_handler.cpp`（抽帧改为 1fps + audio 切 1s 段）+ `omni.cpp`（prefill 改为按时间步交错 `<image>frame_i</image><|audio_start|>audio_i<|audio_end|>` 循环）实现 `minicpm-interleave` 式打包。仅改输入布局，不改模型/采样 → 数学等价、精度风险在打包层。

**状态**：静态代码分析强假设（打包实现已确证为非交错）；**definitive proof = 实现交错打包后 runtime 复测多帧不再退化**（下一步，属独立修复任务）。vision_backend 非阻塞（单帧 T2 已证视觉在昇腾可用，多帧问题在打包不在后端）。

#### Runtime 复测（2026-08-07，实现+构建+实测）— interleave 必要但不充分

交错打包已实现（`ws_handler.cpp` +114/-14）并**经日志验证布局正确**：`vision_set_max_slice_nums=0` → 每帧 1 chunk 无 `<slice>`；N 步 `<image>frame_i</image><|audio_start|>10 audio tok<|audio_end|>`；问题文本经独立文本项 emit（修了 consumer 在视觉项丢 `user_text` 的 bug）；单帧路径逐字节不变。

实测结果（**每个 case 必须用干净 server**，因退化会污染 shared_octx）：
- **干净 server stack-frames 1（红线回归）→ 连贯**（"woman...skincare product...smooth wrink"）。✅ 红线守住。
- **干净 server stack-frames 2（interleave）→ 连贯**（item: "C. Logo transition sound effect"，模型理解视频）。✅ 多图在低帧数**能工作**——相对旧 STACKED 是进步。
- **干净 server stack-frames 8（首次请求）→ 仍 `?`×40 崩溃**（token id=30 重复）。❌ 高帧数仍退化。
- ⚠️ 8 帧崩溃**污染 shared_octx**，其后所有请求（含 2/3 帧）都退化 → **必须重启 server 才能干净复测**（早期连续测 2/3/8 帧全 `?` 是污染假象，非本质）。

**新嫌疑（8 帧崩溃真因）**：log 显示 **whisper 音频 KV cache 在 N 个 1s 段间累积**（`current_total` 50→100→…→400，`KV cache iter incremented to 1..N`）——每段不是独立编码而是流式承接前段（streaming mode），N 大时嵌入污染严重 → LLM 崩溃。N=2 时累积轻 → 仍连贯。**下一步修复方向：每段编码前清 whisper KV cache（`audition_whisper_clear_kv_cache`），让各 1s 段独立编码（匹配 interleave 训练分布）。**

**修正 P7 重验结论**：交错打包**必要**（2 帧已证能工作 + 修了 user_text 丢弃 + 红线安全），但**不充分**——高帧数还卡在 whisper 流式 KV 累积。interleave 代码**保留**（gated、正确、低帧数有效、`OMNI_VIDEO_INTERLEAVE=0` 可回滚）。Daily-Omni 高精度（需多帧）还需再攻 whisper KV 清理这一关。

#### whisper KV 清理实测（2026-08-07，实现+构建+干净 server 复测）— 第二个假设证伪

每段编码前调 `audition_whisper_clear_kv_cache(octx->ctx_audio)`（ws_handler interleave 循环内，gated）。日志确认 **KV 不再累积**：每段都 `current_iter=0 → incremented to 1 (total_tokens=50)`（之前是 50→100→…→400 累加）。即各 1s 段现在**独立编码**，语义正确。

**但干净 server stack-frames 8 仍 `?`×40 崩溃** → **whisper KV 累积不是 8 帧崩溃的真因**，第二个假设也被 runtime 推翻。

#### 最终结论（runtime 推翻两个静态假设后）

- 修了两个**真实 bug**（interleave 打包 + whisper KV 流式累积），都**验证生效且保留**（gated、单帧红线安全、低帧改善、语义更正确）。
- 但**两个都没解决高帧崩溃**。clean server：1 帧/2 帧连贯，8 帧必崩（阈值在 2~8 之间，与音频 KV 无关）。
- 高帧崩溃的真正根因在**更深的层**：最可能是 **turn_based 多 `<image>` 视觉路径**——官方 910C 指南明示"**视觉模态未验证 / vision_backend 默认 metal**"。这不是 ws_handler 或音频层能修的，需要视觉编码/chat-template/多图位置编码层面的排查（或官方修复）。
- **Daily-Omni 高精度（需多帧）在 llama.cpp-omni 当前视觉路径下不可达**。方向转：① 问赛事方子赛道 A 多帧/视觉官方配置（Q1 已起草）；② 如实报告框架视觉限制；③ 可选深度诊断（纯多图无 audio、找 2~8 帧阈值、查 vision_backend 实际跑在哪）——但不改 server 层结论。

**方法论印证**：rigor-verify-loop 两次 runtime 实测推翻静态假设（先"打包是根因"、再"KV 累积是根因"）——静态推理只生成假设，runtime 才定根因。两个修复都是真实改进（值得保留），只是都不是高帧崩溃的那一关。

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

### 实验 P0：Daily-Omni 单帧红线复位验证（2026-08-07，分支 fix/video-extract-harden）

**起点**：最新 `benchmark/daily-omni/result.json`（n=3，全 `?????` 0%），而 `daily_omni_test.py` 默认 `--stack-frames 1`、P7 已证单帧=正常文本 → 疑似"单帧红线破了"。三个嫌疑：A1 当时 server 被多帧污染 / A2 interleave 改动引入单帧回归 / A3 未提交 omni.cpp 改动。

**代码复核（排除 A2/A3，不动 server）**：
- **A2**：`ws_handler.cpp:1067` interleave gating = `!interleave_timesteps.empty() && !(OMNI_VIDEO_INTERLEAVE=="0")`；`interleave_timesteps` 仅在 `extract_video_mp4_media` 的 `if (n_frames>1)` 块填充。**stack_frames=1 → n_frames=1 → timesteps 空 → 走 else legacy 老路径，与改前逐字节一致**（帧抽取命令 n_frames==1 也不加 `-vf fps=1`）。→ interleave 对单帧零影响，排除回归。
- **A3**：未提交 omni.cpp 改动仅 sampler 参数 LOG 打印（不影响推理数学），binary 08-07 08:04 已含。排除。

**runtime 实验（起全新干净 server，08:04 binary，未设 OMNI_VIDEO_INTERLEAVE）**：
- 起点状态：当前**无 server 在跑**（ps 空 / NPU Aicore 0% / HBM 5%）→ 最新 result.json 为上次残留；起 `scripts/serve.sh` 等价命令的全新 server。
- 关键特性印证：Omni server **omni_context 懒加载**——启动只起 HTTP + 265 线程，HBM 5%、RSS 910MB、wchan `inet_csk_wait_for_connect`；模型在首个 WS `session.init` 才加载。探针 `wait_ready` 触发后 HBM → 33%。（即"启动≠加载完成"，干等 HBM 涨是误判。）
- 探针（`benchmark/daily-omni/probe_p0.py`，干净 server）：
  - **T1 纯文本** "What is 2+2?" → `"2 + 2 = which means 4. The correct answer is B.4"` ✅ **NORMAL**
  - **T2 单帧视频**（daily-omni row 0，stack_frames=1）→ `"Okay, let me try to transcribe the audio in the video. <|SOA_0隅"` ✅ **NORMAL**（不乱码）

**结论：故障 A = A1（污染），红线没破，binary 健康。** 最新 result.json 的 `?????` = 当时那个 server 被多帧（stack≥8）测试污染了 `shared_octx`，退化扩散到后续单帧请求（P7 重验已知机制"8 帧崩溃污染，其后全退化，需重启 server 复位"）。

**副发现（修正 P7 "单帧=完全正常"）**：T2 单帧输出尾巴带 `<|SOA_0`（audio 起始标记）+ 乱码 `隅` → **即使单帧，模型也有概率滑向输出 audio token**。退化是**渐进/概率性**的，非"单帧 100% 稳 / 多帧 100% 崩"的开关。这指向 P2（logits 诊断）：高帧崩溃前，logits 在 audio-token 区间是否已抬升。

**教训/流程**：跑过多帧（stack≥3）实验后，**同一 server 进程必须重启**才能跑正式评测或单帧对照，否则 shared_octx 污染制造假阳性"红线破了"。`daily_omni_test.py` 默认 stack_frames=1 防不住——这是同进程先后顺序问题，不是参数问题。

**代码改动**：新增 `benchmark/daily-omni/probe_p0.py`（干净 server 探针，T1 纯文本 + T2 单帧视频）；不动 server/推理数学/红线。

### 实验 P1：Demo 路径能否多帧 — 代码证伪（2026-08-07，分支 fix/video-extract-harden）

**假设（P6 遗留）**：Demo turnchat 经 gateway/worker 能正常答视频、直连 WS 乱码 → 差异在 gateway/worker payload 转换，定位它可能解锁多帧（被搁置的"钥匙"）。

**链路核实（纯代码层，未起 Demo）**：
- **前端**（`turnbased.html`）：视频 payload = `{type:'video', data, duration}`，**不传 `stack_frames`**（L2081/2388）；顶层 `omni_mode:true` + `image.max_slice_nums:1`（hasVideo，L2479-2480）。
- **gateway.py / worker.py**：**透传**（gateway L516-523 直接转发原始 JSON；worker `/v1/worker/chat` → backend `/backend`，mode 强制 `turn_based`）。
- **backend `protocol.cpp:464`**：`int stack_frames = json_int(part, "stack_frames", 1)` → **video stack_frames 默认 = 1**。
- **`omni_mode` 是 dead field**：`protocol.cpp:401` 读取赋值，但 grep 全仓（`tools/server/*.cpp` + `tools/omni/*.cpp`）**仅 protocol.cpp:401 赋值 + protocol.h:113 声明，ws_handler/omni.cpp/server-omni.cpp 零使用点**（protocol.h:113 自注 "pass-through hints §4.2"）。Demo `omni_mode=true` 与 daily-omni `false` **零行为差异**。

**结论：P1 前提证伪。** Demo "能正常答视频" = **Demo 默认 stack_frames=1（单帧）**，与 daily-omni `--stack-frames 1` 完全等价（P0 T2 已证单帧正常）。P6 "Demo 正常 / 直连乱码" 的真正差异 = **stack_frames 帧数**（Demo 默认 1，daily-omni 当时 8），**非** gateway/worker 转换。Demo 路径无多帧能力 → 起 Demo 全栈（3 进程+SSL+playwright 视频上传）无法验证"框架能否多帧"，只会复证"单帧正常"。

**修正 P6**：将"直连 WS 乱码 vs Demo 正常"归因为"gateway/worker payload 差异 / 前端 system_prompt / mode 字段"是误判，实为 `stack_frames` 帧数差异 + 当时 server 污染。

**方向**：故障 B（多帧 stack_frames≥3 崩）仍是真问题，Demo 救不了。下一步转 P2（logits 诊断，攻多帧崩溃本身）或 P3（基线口径，战略求证）。

**代码改动**：无（纯代码核实，未起 Demo，未动 server）。Explore agent 结论部分可信（stack_frames 默认 1 ✅），但其 "omni_mode 是 Demo 正常关键变量" / "mode 默认 full_duplex" 推断需修正（omni_mode=dead field；worker 显式设 turn_based）。

### 实验 P2：高帧崩溃 logits 诊断 — 全 NaN 数值崩溃（推翻 P7 repetition collapse）（2026-08-07，分支 fix/video-extract-harden）

**起点**：P7/P7重验 未定位高帧（stack≥3）崩溃根因（已排除交错打包、whisper KV 累积）；P7 结论 "token id=30 重复 = repetition collapse / 模型退化 OOD"。P0 副发现单帧也冒 `<|SOA_0` → 怀疑 audio-token 滑动。需下沉到 logits 数值层。

**实验**：`omni.cpp:1344 sample_with_hidden_and_token`（采样点，`logits = llama_get_logits_ith(ctx,-1)` @ L1345、`common_sampler_sample` @ L1398）加临时 LOG（env `OMNI_LOGIT_DIAG=1`，前 80 步）：每步打印 sampled id + logits `[n_vocab/max/min/nan_count/tok30/audio 区间[151687,158249)]` + top-10。rebuild，干净 server（binary 12:56），首请求 `--stack-frames 8`（默认 interleave 路径）。

**结果（决定性，40 步完全相同）**：
```
[P2 step 0..39] id=30 n_vocab=151748 nan=151748 | tok30=nan | audio_top10=0
  top10: (空)
```
- **`nan=151748` = 整个 vocab（151748 个 token）的 logits 全部 NaN**。top10 空（LOG 的 `v==v` 过滤排除了全部 NaN）。
- 每步 `id=30`：sampler 在**全 NaN logits** 下 argmax 无意义，返回固定 id=30（`\x1e`）→ 输出 `?`×40。**模型不是"选"了 30，而是输出全 NaN。**

**结论：故障 B = 数值崩溃，非 repetition collapse。** P7 的 "模型退化重复选 token 30" 被推翻 —— 真因是**多帧 prefill 后 LLM 前向传播产生全 NaN logits**（NaN 经矩阵乘扩散到整个 vocab），sampler 沦为返回无意义固定 token。**故障 B 从 "模型能力上限/OOD"（死路）重定性为 "数值溢出 bug"（可定位可修）。**

**补充排查（排除 RoPE，锁定 NPU vision）**：
- `n_ctx_train=40960` ≫ stack=8 的 n_past（8 步 ×78 ≈ 646）→ **RoPE 位置越界排除**（远未到训练上限）。
- 日志 `vision_ctx: vision using CANN0 backend` → **vision encoder 实际跑在 NPU（CANN）**，非 P7重验以为的 "metal / 未验证"。单帧正常 / 多帧全 NaN + 视觉在 NPU → 嫌疑 = **NPU（CANN）vision encoder 多帧计算产生 NaN embedding**（"视觉模态未验证" 的实操含义）。
- 日志无任何 nan/inf/overflow error → **NaN 静默产生**（CANN 算子输出 NaN 不报错）。
- 排除项：sampler bug、n_ctx、RoPE、interleave 打包逻辑（已修且 2 帧不崩）、whisper KV（已清）。

**下一步（P2.5，定位 NaN 源头）**：① vision encode 输出处（`omni_image_embed_make_chunks_with_filename` 返回的 embedding）加 NaN 检查，对照单帧（应非 NaN）vs 多帧（应 NaN）；② 若 omni 支持切 vision backend，做 **CPU vision 多帧隔离实验**（多帧 CPU vision 不崩 → 坐实 NPU vision 算子是源头）；③ 单帧/多帧 LLM 输入 embedding 数值对照。

**方法论印证**：rigor-verify-loop **第三次** runtime 实测推翻静态结论（P7重验推翻"打包根因"/"KV 根因"；P2 推翻"repetition collapse"）。**看 token id（行为）会误判"模型选 30"，看 logits（数值）才暴露 NaN —— 退化诊断必须下沉到数值层。**

**代码改动**：`omni.cpp:1399` 后临时 LOG（env `OMNI_LOGIT_DIAG=1` 门控，前 80 步，只读 logits 不改推理数学）。**待 P2.5 定位 NaN 源头后统一移除（净 0）**；当前暂留（P2.5 会扩展同点诊断）。

### 实验 P2.5：NaN 源头定位 — vision 干净，退化渐进，NaN 在 LLM 多步 prefill 累积（2026-08-07，分支 fix/video-extract-harden）

**起点**：P2 锁定"高帧全 NaN 数值崩溃"嫌疑 NPU vision encoder。需定位 NaN 源头。

**P2.5-B（vision embedding NaN 检查）**：`omni_image_embed_make_chunks_with_filename`（omni.cpp:884）的 `vision_chunks` 输出加 NaN/Inf 检查 LOG（env `OMNI_VISION_NAN_DIAG=1`）。干净 server，stack=8。
- 结果：8 帧 vision embedding **全部 nan=0 inf=0**（max 34~40，min -7，ViT 合理范围），size=262144（4096 embd × 64 tok）。
- **vision 非 NaN 源头**（否定 P2 嫌疑）。但 logits 仍全 NaN → NaN 在 vision 之后（（vision+audio embd）→ LLM eval）。

**P2.5 阈值对照（stack=2，P7重验称"连贯"）**：同 binary 双 LOG，干净 server，stack=2。输出 `\n\n\n...`（16 换行，**非 P7重验的"连贯文本"——不可复现**）。logits：
```
[P2 step 0] id=151667 max=22.8 nan=0 tok30=-7.66 audio_top10=1
  top10: [151667]=22.84 [785]=17.97 [6025]=17.16 ...
[P2 step 1] id=198(\n) max=30.25 nan=0
```
- **stack=2 logits 完全正常（nan=0，有明确 top10）**，但模型选 id=151667（omni 特殊 token，紧邻 audio 区间 [151687,158249)）+ id=198（`\n`）交替 → **语义退化（attention 没崩，选错 token），非数值 NaN**。

**退化渐进表（统一 P0 副发现 + P2 + P2.5）**：

| stack | vision embd | logits | 输出 | 性质 |
|---|---|---|---|---|
| 1（P0/P7） | 干净 | 正常 | 正常文本（偶冒 `<|SOA_0` 尾巴） | 健康（轻微 audio 滑动） |
| 2 | 干净 | **正常（nan=0）** | `\n` + id=151667 交替 | 语义退化（选 audio 边界/换行） |
| 8 | 干净 | **全 NaN（151748）** | `?`（id=30） | 数值崩溃 |

**结论**：
1. **vision 非 NaN 源头**（三种 stack 都干净）。否定 P2 "NPU vision 多帧 NaN" 嫌疑；P2.5-A（CPU vision 隔离）因此无必要（未做）。
2. **退化随帧数渐进**：1 正常 → 2 语义跑偏（logits 有形但选 audio 边界 token + 换行）→ 8 全 NaN 崩溃。**非"2 帧稳 / 8 帧崩"的开关**。
3. **NaN 在 LLM 多步 interleave prefill 累积**：vision embd 干净喂入，但每步 +vision+audio embd，LLM KV/attention 逐步累积，8 步时数值溢出 NaN（2 步尚可，语义退化但 logits 有形；1 步正常）。
4. **模型多帧倾向 audio token 输出**（id=151667 ≈ audio 边界 + P0 单帧 `<|SOA_0` 副发现）—— MiniCPM-o 全模态，视觉+audio 输入下倾向滑向 audio 输出，多帧加剧，8 帧数值崩。

**修正 P7重验**："2 帧连贯"不可复现（stack=2 实测语义退化，输出换行）——可能 P7重验的 case 不同或不可重现。

**P2.5-C（LLM 输入 embd NaN 检查，`prefill_with_emb` omni.cpp:380）**：env `OMNI_PREFILL_EMB_NAN=1`，检查喂给 `llama_decode` 的 `batch.embd`（vision+audio+text 拼接后的输入）。stack=8 结果：**所有输入 embd 段全部 nan=0 inf=0** —— vision 段（n_eval=64，max 34~40/min -7）+ **audio 段（n_eval=10，max 7~11/min -2~-3，whisper 合理）** 全干净；但 `[P2 step 0]` logits 仍全 NaN（nan=151748）。

**最终定位（P2.5-C）**：**输入 embd（vision+audio 拼接）全干净，NaN 在 `llama_decode`（CANN 后端 LLM 前向）内部产生**。即 LLM attention/FFN 在 8 步 interleave prefill（每步 +64 vision +10 audio embd）累积后数值溢出 → logits 全 NaN。

**修复可达性（关键结论）**：输入 embd 干净 → **非 omni.cpp embd 拼接问题（omni.cpp 层不可修）**；NaN 在 `llama_decode` 内部 → **入 CANN 后端（ggml-cann）/ llama 内核**。**红线内（仅流水线/调度）不可修**，需框架/CANN 层或官方修复。

**诊断链闭环**：vision 干净（P2.5-B）→ audio embd 干净（P2.5-C）→ 输入 embd 全干净（P2.5-C）→ NaN 在 LLM（CANN）多步 prefill 内部累积溢出。故障 B = CANN 后端 LLM 在多模态多步 prefill 下的数值稳定性 bug，非模型上限、非 vision、非打包、非 embd 拼接。

**务实结论**：继续深挖需 hook llama 内核层（ROI 极低，且改 CANN/llama 内核超红线）。建议：① 转 P3 求证官方基线口径（79.5/69.0 是否 omni 实测，若非则多帧精度非我方责任）；② 如实报告"CANN 后端 LLM 多步 prefill 数值稳定性"为框架限制；③ 单帧（stack=1）精度仍可达，作为可交付口径。

**方法论印证**：rigor-verify-loop 第 4/5 次 runtime 推翻静态（P2 "NPU vision 嫌疑"被 P2.5-B 推翻；P7重验 "2 帧连贯" 被 stack=2 复测推翻）。**逐层 NaN 检查 + 阈值对照逐步缩小范围**——vision 干净 → logits 对照（2 正常 / 8 NaN）→ 锁定 LLM 累积。

**代码改动**：P2 sample LOG（omni.cpp:1399）+ P2.5-B vision NaN LOG（omni.cpp:884），均 env 门控只读。**待统一移除净 0**（见 task12/17）。

---

### 实验 P3：CookBook 官方 pipeline 实证 — context 40960 不是解，退化是 910B3/CANN 框架 bug（2026-08-10）

**起点**：P2.5 定位 NaN 在 CANN 后端 LLM 多步 prefill。P2.5 务实结论建议 P3 求证官方基线口径。期间曾假设"context 过小（4096/8192 vs 官方 40960）是退化根因"。本实验接入官方 pipeline 实证。

**接入**（commit `ab5653e` feat(eval) + `e1d79f4` build-cann.sh ccec）：
- 官方评测路径：`OpenSQZ/MiniCPM-V-CookBook` `evaluation/videomme` 的 `llama-omni-eval-cli`（pipe 驱动，`media_type=2` 固定、`use_tts=false`），**非 WS server**（前几轮自建 WS turn_based 路径本就不对）。
- build：**ccec（CANN bisheng clang 15）**——系统 gcc 12.3.1（openEuler）.o COMDAT/binding/symtab 异常，bfd/lld/gold 三 linker 全失败；ccec 干净编过（见 memory `910b-cann-gotchas` 第10条）。
- 官方参数：`CTX_SIZE=40960`、`MAX_NUM_FRAMES=64 @1fps`、`temp 0.2`、`max_tokens 100`。

**实证（smoke_test 2 题，video fFjv93ACGo8）**：
- ✅ 跑通：CLI 6.4s ready + ffmpeg 抽 64 帧 + 多帧 prefill（n_past 4071→4538，**ctx 40960 无滑窗**）+ decode 100 token。
- ❌ 精度 **0/2**：两题输出 100 个 `_`（退化 token）。CLI log **无 NaN/inf 报错**（logits 退化，非 P2.5 的数值崩溃 NaN；但同属多帧退化谱系）。

**结论（推翻 context 假设）**：
1. **context 40960 不是解**——官方 pipeline + 64 帧 + 40960 context 仍退化，"context 过小"假设**证伪**。
2. **退化是 910B3/CANN 框架 bug**（P2.5 已定位 CANN 多步 prefill 数值稳定性），与 context/喂法（官方 pipeline）/编译器（ccec）都无关。
3. **官方基线 69.0 极可能 910C 实测**（910C 不退化）——910B3 厂家替代 910C 的精度代价。
4. 单帧（stack=1）仍可达（~10%），但官方口径 64 帧退化 → 多帧精度项（VideoMME/Daily-Omni）在 910B3 客观难达标。

**务实结论**：解铃在赛方/910C。向赛方确认（`organizer-inquiry-final.md`）：① 官方基线环境（910C?）；② 910B3 选手多帧精度如何判定；③ 框架受限项是否豁免。我方强项 = 性能（RTF 0.68）+ Demo + TTS-WER（0.20）。

**方法论印证**：rigor-verify-loop 第 6 次——"context 过小"静态假设被官方 pipeline 实测推翻（40960 仍退化）。**精度退化根因诊断必须 runtime 实测，静态推理（含"context 越大越好"的直觉）会误导**。

---

## 实验 P6：vocoder overlap + CPU 亲和（2026-08-12）— bit-精确失败，接受 RTF 0.57

> 分支 `perf-vocoder-overlap`（**未 merge**，信息性留档，含 step1/step2 完整代码 + 本 P6 详节）。

**目标**：RTF 0.57 → 理论 0.34（vocoder CPU 346ms ‖ t2m NPU 126ms 完全 overlap）。P5（experiments.md:345-358）试 overlap 失败归因"CPU 竞争"，decision L18 留"CPU 亲和"未试。

- **step1（拆分 + env gate，✅ bit-精确）**：拆 `push_tokens_only`(t2m)+`vocoder_only`(vocoder+cache)，保留原函数；env `OMNI_VOC_OVERLAP` gate。on 串行调子函数 = off，wav **20/20 byte-identical**（解决 P5 遗留 58/57）。
- **step2（async overlap，❌ bit-精确失败）**：`feed_window_overlap`(t2m N 主 ‖ vocoder N-1 `std::async`)+`flush_overlap`。on 总长一致（434880 样本）但 **PCM 改内容**（max_diff 27756, mean 1994, 非零 99.67%）。
- **根因**：step1 串行 bit-精确 vs step2 async 改内容 → **ggml 跨 backend（NPU+CANN vs CPU）并发非 thread-safe**（async vocoder 与主线程 t2m 共享 ggml state 污染内容）。**这是 P5 失败真因**（不只 CPU 竞争，还有并发改内容）。
- **决策**：off env 关 = bit-精确零破坏 RTF 0.57；overlap on 改内容违反"不改数学"红线 → 不可用 → **接受 0.57（beat 基线 1.087 共 48%）**。
- **教训**：ggml 跨 backend 并发需先验证 context 隔离；未来多 backend overlap 需重构 t2m/vocoder 为独立 ggml context（大改 + 高风险）。性能优化终点 = 0.57。

---

## 实验 2026-08-14：系统层参数优化 — NUMA 亲和修正（RTF 0.68→0.59）

> 分支 `bench-huawei-adapt`。**纯运行时，不重编**。新机器（npu-smi id=**7**，Atlas 910B3 die0，64GB）环境校准发现。plan 见 `/root/.claude/plans/resilient-inventing-planet.md`。

**起因**：用户要求系统参数优化。A0 baseline 探测发现新机器 NPU 的 NUMA 归属与旧配置不符 —— 这是测出 0.68（而非记忆里 0.57）的根因。

**关键发现 — NUMA 亲和失效（唯一真实系统杠杆）**：
- 新机器 NPU（PCI `0000:42:00.0`）`numa_node=2`（查法：`cat /sys/bus/pci/devices/0000:42:00.0/numa_node`）。
- 旧配置（CLAUDE.md / 记忆）绑 `taskset -c 192-223`（node6）→ **vocoder 线程跨 NUMA 与 NPU（node2）搬数据**。
- 旧机器测 0.57 时 NPU 大概率在 node6 故绑 192-223 正确；新机器 NPU 在 node2，配置失效 → 实测 0.68。

**A/B（各 3 次，e2e RTF，SPEAK→WAV 口径，F16，`OMNI_T2W_THREADS=24`）**：

| vocoder 绑核 | 3 次 e2e RTF | 中位 | 说明 |
|---|---|---|---|
| node6 `192-223`（旧，跨 NUMA） | 0.68 / 0.65 / 0.69 | **0.68** | NPU 在 node2，跨 NUMA DMA |
| node2 `64-95`（NPU 同 node） | 0.55 / 0.59 / 0.65 | **0.59** | 本地 DMA，RTF −13% |
| node2 + SLOG=0 + nice-10（系统包） | 0.60 / 0.55 / 0.58 | **0.58** | 中位 ≈ node2，方差 0.10→0.05 |

**其余系统项（均为边际 / 不可行）**：
- A1 CPU governor = `performance`、A4 THP = `[always]`：**OS 镜像已最优，跳过**。
- A3 关 NUMA balancing：**容器内 `/proc/sys` 只读，不可改**（Read-only fs）。
- A5 `ASCEND_SLOG_PRINT=0` + A6 `nice -n -10`：中位无显著收益（0.59→0.58，噪声内），**主要降方差**。
- A7 perf-duplex 参数：无 `-b/-ub` batch；`--stream-interval` 是"模拟真实流式"口径参数（动则偏离 SPEAK→WAV 口径，不动）。

**结论**：
- 系统层真实杠杆 = **NUMA 亲和**（查 NPU `numa_node` → 绑对应 CPU）。推荐配置：`OMNI_T2W_THREADS=24 taskset -c 64-95`（本机）+ `ASCEND_SLOG_PRINT=0`（降方差）。
- RTF = **0.58–0.59**（中位，新机器物理限），vs 旧错误配置 0.68；仍 beat 基线 1.087 共 ~46%。
- **方法可推广**：换机器先 `cat /sys/bus/pci/devices/<NPU_bus>/numa_node`（NPU bus 从 `npu-smi info` 取），再绑该 node 的 CPU（numactl 缺失，用 taskset）。**不同机器 NPU node 不同**（旧机 node6 / 新机 node2）—— 旧 `taskset -c 192-223` 写死值不能跨机器照抄。
- **Video-MME 精度**：本轮纯运行时空间 ≈ 0（评测参数锁死 + `OMNI_DEBUG` 探针需重编）；评测日志 grep 无 NaN/inf（B2），无 attention fp32 红线触发证据。精度提升杠杆（attention fp32 累加）在红线+重编，本轮按约束不做。

**B1 温度对照（排除性验证，2026-08-14）**：videomme99 子集前 6 题，`TEMPERATURE=0.0`（greedy）vs `0.1`，其余官方锁定（top-p=0.8 / top-k=100 / repeat=1.02 / seed=42 / 64帧@1fps）。env：`LLM_MODEL_PATH=F16`、`PARQUET_PATH=videomme_subset_99q.parquet`、`VIDEO_DATA_DIR=appendix/videomme99/data`、`LLAMA_CLI_BIN=build/bin/llama-omni-eval-cli`，绑核 `taskset -c 64-95`。
- 结果：**两温度逐题 Raw 完全一致**（题1 `\nC. Berries` / 题2 `A` / 题3 `C. 2.` / 题4 全`\n`退化 / 题5 `\n\nA` / 题6 `C`），准确率均 2/6。
- 结论：低温度区间（0~0.1）**采样参数无杠杆**，temp=0 已最优 —— 排除性验证完成，符合 eval_cli 注释预期（temp>0 让 MCQ 跑偏）。
- **副产品**：题4 temp=0/0.1 **均**输出全 `\n` 硬退化（Pred=''，非 NaN、确定性、非随机）→ 多帧退化在个别题仍有残留（非本轮纯运行时可解），留作 attention fp32 红线实验的潜在触发点（证据方向：长 context 非随机字符退化）。

---

## 实验 2026-08-14（下午）： 题4 退化根因四路排除（attention 路径 / vision backend 全排除）

> 分支 `bench-huawei-adapt`。题4 = 99q 子集第 4 题（video `N1cdUjctpG8`，GT=C），B1 发现其在 temp=0/0.1 下均输出全 `\n`（确定性退化）。本轮用该样本做根因定位，四种组合全部实验。

**四路结果（题4 输出一字不差的全 `\n`，Pred=''）**：

| # | vision backend | attention 路径 | 题4 输出 | 耗时 |
|---|---|---|---|---|
| 1 | NPU | fallback（默认） | 全`\n` | ~25s |
| 2 | NPU | fallback（DISABLED，**=1 无效对比**） | 全`\n` | ~25s |
| 3 | **CPU**（参考精度） | fallback | 全`\n` | **15.2min** |
| 4 | NPU | **FA**（FusedInferAttentionScoreV2，ENABLED） | 全`\n` | 0.3min |

**关键中间发现（修正上午阶段1 的草率结论）**：
- `llama-context.cpp:3397-3408`：**AUTO + CANN → flash_attn 强制 off**（注释原文："the fused attention operator is numerically unstable on some SOCs under long / multi-image shapes. Force-disable FA on CANN in AUTO mode; pass --flash-attn on to opt back in"）→ **生产路径从未走 FA，一直是 fallback（QK^T F32 累加 + softmax）**。
- 上午阶段1 的 DISABLED 实验 = 默认同路径，**无效对比**；其"推翻 oghub 假设"的结论作废 —— oghub 说"FA 被关"是对的（只是关在 llama.cpp 层、是上游故意的，且 forcing off 理由正是多帧不稳）。
- vision backend 切换 = `Omni_BACKEND_DEVICE=CPU`（vision.cpp:231，纯 env）；CPU vision 实测 **13.8s/帧**（64 帧 ≈883s）必然超 eval client 的 `INFER_TIMEOUT=300s`（evaluation/ 不可改），故绕过 client 直接驱动 eval-cli 的 stdin/stdout JSONL 协议（脚本 `benchmark/video-mme-cookbook/diag/q4_cpu_vision.py`，自控超时、vision backend 可选）。
- eval-cli 重编：CMakeCache 链接缺 `-lascendcl` 会报 `aclrtGetDevice/aclrtSetDevice undefined`（--no-allow-shlib-undefined），需在 `link.txt` 补 `-L$ASCEND_TOOLKIT_HOME/aarch64-linux/lib64 -lascendcl` 后手动链接。

**结论**：
1. **vision NPU/CPU 漂移（cos 0.993–0.998）不是根因** —— CPU vision（参考精度）题4 输出一字不差。补上 08-12 诊断路径 B 的端到端缺口，与路径 A（特征级）闭环一致。
2. **attention 路径（FA vs fallback）不是根因** —— 强制 FA（ACLNN FusedInferAttentionScoreV2，prefill `innerPrecise=2`）题4 输出一字不差。
3. 退化是**确定性的、与 vision backend 和 attention 路径均无关** → 指向 LLM 更底层（RoPE / KV 累积 / 其他算子）或模型本身对该视频多帧 context 的行为，或 910B 环境数值特性 —— 均非"换 backend / 切路径"可解。
4. **强化"51.5% 是真实水平"归因**：oghub attention 假设 + flash/fallback + NPU/CPU vision 全部实验排除。剩余出路仍为非代码路径：910C 复现 / 赛方确认 910B 独立基线 / 环境受限豁免。

**可回滚状态**：源码已 `git checkout`（ENABLED/DISABLED 行均已去）；`build-cann/bin/llama-omni-eval-cli` 为 FA 实验版（**勿用于评测**，评测用 `build/bin` 0812 版）；`flashon.bak` 为 Aug10 旧版（无 `--seed`，同样勿用）。

---

## 实验 2026-08-14（晚）：域偏差假设证伪 + 空响应根因 = EOS 临界翻转（机制级定位）

> 分支 `bench-huawei-adapt`。三个连续实验：60 题非 KB 对照 → 180 题分层验证 → 空响应逐 token 定位。

### 一、域偏差假设：先起后落，最终证伪

- **起因**：99q 子集 = 纯 Knowledge 域（parquet 前 99 行，全量占比仅 30%）→ 疑"51.5% 被子集偏难拖低"。
- **60 题非 KB 对照**（五域分层，`videomme_subset_nonkb.parquet`）：63.3%（38/60）vs KB 51.5/53.5% → 表观 +10.8pp，域加权全量期望 ≈60%（但 z=1.33 未过显著）。
- **180 题独立验证**（每域 12 视频严格 4/4/4 时长均衡、排除已测视频，`videomme_subset_domain180.parquet`）：**47.8%**（86/180）——直接打回。合并非 KB = 51.7% ≈ KB 52-53%。
- **终局**：Kruskal p=0.26，KB vs 非KB p=0.37。**域差异假设未通过验证；"60% 期望"不成立；339 题合并 ≈52%，与最初 51.5% 一致**。观察到的域间点估计差（33-61%）在样本量内不可与噪声区分。

### 二、空响应：从现象到机制（本轮最大成果）

**现象规模**：KB 1/99 → 非KB60 7/60 → 180题 **31/180**，全为真空串 `''`（与 q4 的全`\n` 是两个签名）。

**归属分解**（31 题）：
- 3 题 = **视频文件损坏**（nO2B4haj2BQ.mp4 本地 0 字节；zip 源 397MB 正常 → 首次解压被 2min 超时杀断，续跑因"文件存在"跳过 —— **我方解压脚本 bug，已定位**）；
- 28 题 = **帧正常、prefill 完第一步即 end-token**（涉及 23 视频，Film&TV 最多；与运行位置无关 → 非状态累积）。

**机制定位**（env 门控探针 `OMNI_DEBUG_TOPK`，插入 `sample_with_hidden_and_token` 采样前；build-cann 诊断版 binary，`build/bin` 官方版未动）：

093（drbi6HK1gSc，Film&TV short，3/3 空）首 token 真实分布：
```
#0 <|im_end|>  12.27  ← 真 argmax，greedy 正确采样（采样器无罪）
#1 "A"         11.64  ← 答案字母，仅差 0.63 logit（~5%）
#2 <think>      9.95
```
- **空响应 = 模型在 910B/F16 数值下 EOS 以 ~0.6 logit 微弱优势压过答案字母的临界翻转**。不是采样 bug、不是框架 bug。
- **这是 910B vs 910C gap 的机制级解释**：~12% 题落在 EOS-answer 临界带（修复上限 +6~7pp），加答案选择上的同级临界翻转 → 17.5pp gap 的主体 = "临界决策落在哪边"。外部 910C 全量 69.7% 反推其空响应率必然 <3%，与该机制自洽。
- **规则内不可修**（压 EOS = 改 logits = 改数学红线）。归因从"推测平台差异"升级为"定位到首 token 临界带"。

**首版探针的教训**：第一版插在 `is_end_token` 命中处（采样后），读到的是 `eval_id_with_hidden` 把采样 token decode 之后的"下一步"分布 → 曾误判"greedy 选了 rank-4"。**采样探针必须放采样前**。

### 三、Track B 同机对照（HF/torch_npu 复跑 3 个空响应题）— ⭐结论反转

本机重建 venv-trackb（torch 2.8.0 + torch_npu 2.8.0.post5 + transformers 4.51.3，注意本版 chat API 用 `msgs=[{"role":"user","content":[img...,text]}]` 结构化消息）。脚本 `trackb_empty_margin.py`（官方 prompt 模板，64帧，greedy）。

**结果：HF 三题全对，llama.cpp 同机三题全空**：

| 题 | GT | llama.cpp-omni | HF/torch_npu（同 910B, F16） |
|---|---|---|---|
| 093-1 | D | `''` 空 | **'D' ✅**（7s） |
| 097-3 | A | `''` 空 | **'A' ✅**（2s） |
| 114-1 | D | `''` 空 | **'D' ✅**（6s） |

**推翻"910B 环境级归因"**：EOS 临界空响应是 **llama.cpp-omni 特有现象**（同硬件同精度下 HF 不触发）。两种可能剩余解释：
1. **协议层差异**（可修方向！）：C++ 的 prefill 构造 vs HF 参考 —— 手工拼的 `"<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"` 模板（omni.cpp:11025）token 边界 vs HF chat template、帧分隔符（C++ 每帧后 prefill `"\n"` vs HF `<image>./</image>`）、图像预处理细节。
2. **数值层差异**（不可修）：ggml-cann vs torch_npu 的 kernel/累加顺序 → logits 微差 → 临界翻转。

**与既有证据的合成**：旧 Track B（08-11 旧机）HF 在 KB99 子集 ~50% ≈ llama.cpp 51.5-53.5% —— 两框架在"有作答"的题上水平相当；HF 的优势集中在**不产生空响应**。若 llama.cpp 的 ~12% 空响应按 HF 行为恢复 → +6~7pp。910C 全量 69.7% 的 gap 仍部分未解（HF 在本机全量分未知），但"硬件末日论"已死：**瓶颈 = llama.cpp-omni ×（协议细节 ∨ 数值路径）**。

**下一步（若继续）**：① 取 HF 首 token logits（EOS vs 'D' 的 margin）与 C++ 的 0.63 对比 —— margin 大 → 协议差异为主；② 逐项对齐协议变量（模板字符串 tokenize 对比、帧分隔符、预处理）做消融。注意任何引擎改动都需重新过精度红线与 bench/huawei 一致性。

### 附：本次踩坑记录

- `head -N` 关管道 → SIGPIPE 杀 cmake（机器手册 §8 原班坑）；构建输出必须落文件再 grep。
- omni.cpp 属 **libomni.so**（target `omni`），exe link.txt 之外还需重链 lib；两个 link.txt 都要补 `-lascendcl`。
- 新 API：`llama_n_vocab(model)` 已弃用 → `llama_vocab_n_tokens(llama_model_get_vocab(model))`；`llama_get_model` 返回 const。
