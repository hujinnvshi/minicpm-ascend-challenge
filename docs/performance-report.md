# 性能测试报告 — MiniCPM-o 4.5 双工推理优化(赛道一·子赛道 A: llama.cpp-omni)

> 状态:2026-08-05 版。SPEAK→WAV RTF 已实测;精度 benchmark 待官方评测脚本到位后补。
> 北极星指标:**SPEAK→WAV 完整链路 RTF**(单并发 F16),官方基线 **1.087**。
> 赛事:MiniCPM & 昇腾推理优化与应用创新挑战赛 · 赛道一 · 子赛道 A(llama.cpp-omni)。

## 1. RTF(核心指标 + 统计口径)

- **指标定义**:SPEAK→WAV 完整链路 RTF = (一轮 SPEAK 从首帧 push 到末 wav 落盘的墙钟时间) / (该轮生成音频时长)。单并发、F16。<1 表示快于实时。
- **口径对齐**:与官方"主要优化目标 = SPEAK 生成阶段 RTF(非全 chunk 平均)"一致 —— 本指标按 SPEAK 轮计,不对 LISTEN 帧平均。
- **实测结果(2026-08-05,perf-duplex 36 帧)**:

| 指标 | 我方(P1.7) | 官方基线(F16) | 结论 |
|---|---|---|---|
| **SPEAK→WAV RTF(e2e,完整链路)** | **0.83**(中位 0.81–0.83) | **1.087** | ✅ **beat 基线 ~24%** |
| TTS RTF(TTS 段,参考) | 0.82 | — | — |
| LLM 判定 P50(参考) | 977ms | — | <1000,实时 |

- 详:`speak#0/audio#0` 音频 53.84s,e2e wall 44.44s → RTF 0.83;TTS wall 44.08s → 0.82。

## 2. 测试环境

- **硬件**:昇腾 910B3 单卡(64GB HBM,20 AICore;厂家授权替代 910C,"1 颗 910C = 2 颗 910B")+ 鲲鹏 920 256 核 + 2TB 内存。
- **软件**:CANN 9.1.0-beta.3(官方指定 beta1,向上兼容);aarch64(openEuler)。
- **框架**:llama.cpp-omni(build-cann,GGML_CANN=ON),6 处 ggml-cann 补丁 + P1.7 队列解耦。
- **权重**:MiniCPM-o-4_5-**F16**.gguf(CANN 不支持 Q4_K_M 量化算子 → 用 F16)+ vision/audio/tts/projector F16 + token2wav-gguf(官方预置只读)。

## 3. 测试数据

- **工具**:`tools/omni/perf/perf-duplex`(perf-duplex,全双工模拟,1s 推帧节奏)+ `analyze_perf.py`。
- **输入**:`duplex_omni_test_case_`(36 帧:32 SPEAK / 4 LISTEN,音视频)。
- **配置**:F16 / n_ctx 4096 / ngl 99 / use_mmap=false(双工上 device)/ stream-interval 1000ms / LLM→TTS 队列 16(P1.7)。

## 4. 测试次数

- 多次复跑取一致值:P1.7 队列解耦后 C-8 / C-8b / 本次 → e2e RTF 0.81 / 0.80 / 0.83(中位 **0.81–0.83**,稳定 <1.087)。
- 方法论:每配置 ≥3 次,RTF 差异 <0.03 视噪声(experiments 016)。

## 5. 统计方式

- `analyze_perf.py`:按时间戳匹配 SPEAK 轮 ↔ 音频轮;e2e RTF = (末 wav − 首帧 push) / 音频时长。
- 辅助:npu-smi `info -t usages -i 1` 细粒度(0.5s)采样 AICore + HBM 带宽(证 compute 真在 NPU)。

## 6. 优化前后对比

| 优化项 | 前 | 后 | 机制 |
|---|---|---|---|
| **LLM↔TTS 队列解耦(P1.7)** | 队列 cap=1(锁步)→ LLM P50 8295ms | cap=16 → **P50 977ms(8.5×)** | 解除 LLM 与 TTS-model 1:1 锁步,LLM 可 burst 不每 chunk 阻塞 |
| 双工 model 上 device(P1.6) | host_buffer/use_mmap 致 model 在 CPU | use_mmap=false + 补丁6 → model 上 NPU(HBM 24G) | 强制 eager copy 权重到 device |
| cann 6 补丁(P0–P1.5) | T2W 线程 device 未绑定崩 | set/get_tensor + event +device 绑定 + host_buffer 默认 false | per-thread aclrtSetDevice + 权重上 device |

- **RTF 提升主杠杆**:队列解耦(消除单 NPU 上 LLM+TTS 串行等待)。

## 7. 资源使用

- **HBM**:推理期 ~24G(model 全上 device,稳定不释放)。
- **AICore**:decode 活跃窗 burst 60–84%、HBM 带宽 50%(证 LLM compute 真在 NPU,非 CPU fallback);窗口均值 ~23%(batch=1 自回归 decode 天然 memory-bound 的低 util,非故障)。

## 8. 异常情况说明

- **CANN 不支持 Q4_K_M 量化算子** → LLM 用 F16(4090 的"量化最优"在 910B 失效;Q8_0 实测不提速,dequant-bound)。非异常,平台约束。
- **P1.6 曾误判"AICore 4% = compute 没走 NPU"** → P1.7 npu-smi 细粒度采样澄清为时间均值伪影(实际 burst 60–84%),offload 一直正常。
- 910B3 替代 910C:算力约为半颗 910C,RTF 绝对值偏高但口径统一即公平。

## 9. 复现(摘要)

- 构建:`build-cann.sh`(GGML_CANN=ON)+ ggml-cann 6 补丁 + P1.7(`omni.cpp` 队列 cap 16,env `OMNI_TTS_QUEUE`)。
- 跑:`tools/omni/perf/run_perf.sh -m <F16> --test <duplex_omni_test_case_> 36` → `analyze_perf.py`。
- 详见 [reproduce-guide.md](reproduce-guide.md)、优化链 [experiments.md](experiments.md)(P0–P1.7)、补丁 [cann-patches.md](cann-patches.md)。

## 10. 待补(等官方 benchmark 脚本)

- 三项 benchmark 精度数(VideoMME ≥67.0 / Daily-Omni ≥77.5 / TTS-Seed ASV ≥0.689 / WER ≤1.56)—— F16 不改推理数学,预期 = 基线,待官方评测脚本跑出实测。
- Demo 演示视频(G3 栈已端到端跑通,录制中)。
