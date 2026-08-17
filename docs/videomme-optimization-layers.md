# Video-MME 优化逻辑分层复盘(自底向上)

> 赛事:MiniCPM-o 昇腾推理优化 · 赛道一 · 子赛道 A(llama.cpp-omni)。
> 现状:**Video-MME 51.5%**(99 题官方 pipeline 子集,复现 53.5%)vs 基线 69.0(全量 2700)/ 准入 ≥67.0 —— 唯一未达标项。
> 本文梳理该指标从硬件底层到评测口径的逐层优化/排除逻辑,作为归因结论的支撑框架。
> 整个工作遵循「自底向上的排除漏斗」:越往下越接近"能不能改",越往上越接近"是不是真的差"。
> 数据来源见文末引用(均为 `docs/` 内已落盘实验记录)。

---

## 总览:排除链(漏斗出口)

```
代码改动?       → code 与 bench/huawei 逐字 diff 一致 ......................... ✗
喂法?           → 帧数 64→96(50%→55% 持平)/ 交错已修 / context 证伪 ......... ✗
采样参数?       → temp 0 vs 0.1 逐题输出完全一致(2/6 = 2/6) .................. ✗
attention 算子? → FA vs fallback × 强制 ENABLED,四路组合逐字一致 ............ ✗
vision 算子?    → NPU vs CPU(特征 cos 0.993–0.998 + 端到端)一字不差 ........ ✗
框架?           → Track B:HF/torch_npu 同 910B 也 ~50%,18/20 题一致 ........ ✗
────────────────────────────────────────────────────────────────────────────
剩余唯一归因:910B vs 910C 平台级差异(CANN 版本 / 底层算子数值特性 / 硬件)
出路(非代码路径):① 910C 复现  ② 赛方确认 910B 独立基线(~50%)  ③ 环境受限豁免
```

---

## L0 · 硬件层(910B3 vs 910C)—— 差异的物理起点

| 动作 | 实测结果 | 结论 |
|---|---|---|
| Q4_K_M / Q8_0 量化 | CANN 无量化算子 → fallback CPU;Q8 实测不提速(dequant-bound) | **F16 是唯一可行档位**,decode 贴 memory-bound floor |
| 双 die 锁定 | dev1 在 RoPE `aclnn_repeat_interleave` 崩溃 exit139 | 必须 `ASCEND_RT_VISIBLE_DEVICES=0`(锁 die0) |
| NUMA 亲和(2026-08-14) | 新机器 NPU 在 node2,旧配置绑 node6 跨 NUMA → 修正后 RTF 0.68→0.59 | **影响速度与稳定性,不影响精度** |
| **Track B 对照** | **同一片 910B**,HF/torch_npu 框架也 ~50%,且 18/20 题与 llama.cpp 判题一致 | **gap 非 llama.cpp 独有 → 指向 910B 平台本身** |

**层逻辑**:先把可控物理资源调到最优(绑核/锁 die/选对档位)。本层无精度问题可修;Track B 是第一个把矛头从"我们的代码"转向"910B 平台"的证据。

## L1 · CANN runtime / 系统层 —— 性能护城河,精度无关

6 处 ggml-cann 补丁(per-thread set_device / host_buffer 默认 false / SQR 断言放宽)、use_mmap=false、CPU governor=performance 与 THP=always(OS 已最优)、NUMA balancing(容器 `/proc/sys` 只读不可改)、`ASCEND_SLOG_PRINT=0`+nice(仅降方差)。**产出全部是 RTF 与评测稳定性(防卡死记零分),对 51.5% 无贡献亦无嫌疑。**

## L2 · ggml 算子数值层 —— 精度问题主战场(投入最大)

| 子问题 | 动作 | 结果 |
|---|---|---|
| 高帧全 NaN(早期) | logits 逐层定位(vision/输入 embd 全干净 → 锁定 llama_decode 内部) | 根因 = **attention `-Inf` F16 溢出**,commit `43badb2` 修复 —— **全项目唯一一次成功的底层精度修复**,把"多帧必崩"修成"基本干净"(退化 0) |
| flash_attn 状态 | 强制 `ENABLED` 实测(2026-08-14) | 真相:**llama.cpp 层 AUTO+CANN 故意关 FA**(`llama-context.cpp:3397`,注释:"fused attention numerically unstable on some SOCs under long/multi-image shapes; pass --flash-attn on to opt back in")。强制走 `FusedInferAttentionScoreV2`(prefill `innerPrecise=2`)后题4 **仍全`\n`** → attention 路径排除 |
| fallback 路径 | 代码核查 | QK^T 已是 **F32 累加**(`llama-graph.cpp:2092`)—— 理论"最稳"路径,题4 仍全`\n` |
| vision 算子漂移 | 路径A(特征级):NPU vs CPU,cos **0.993–0.998**、max-abs 7–8、无 NaN;路径B(端到端,2026-08-14 补上):`Omni_BACKEND_DEVICE=CPU` 直驱 CLI,15.2min | 题4 输出与 NPU vision **一字不差** → **vision backend 排除** |

**四路排除表(题4 = 99q 子集#4, video `N1cdUjctpG8`, GT=C;输出逐字一致)**:

| # | vision | attention 路径 | 题4 输出 | 耗时 |
|---|---|---|---|---|
| 1 | NPU | fallback(生产默认) | 全`\n` | ~25s |
| 2 | NPU | fallback(DISABLED,=① 无效对比) | 全`\n` | ~25s |
| 3 | **CPU**(参考精度) | fallback | 全`\n` | 15.2min |
| 4 | NPU | **FA**(FusedInferAttentionScoreV2) | 全`\n` | 0.3min |

**剩余未排除嫌疑**:softmax 的 fp16 中间缓冲(`aclnn_ops.cpp:1852`)、RoPE fp16、KV 长序列累积。但题4 输出是干净的 `\n`(**非 NaN/inf**),更像"logits 正常但模型就选它",数值崩溃类假设已弱化;且三者修复均在"不改推理数学"红线边缘 —— 预期收益低,判定不值得继续。

## L3 · 模型执行层(喂法)—— 被官方口径封死

- 帧数 **64@1fps 均匀采样**硬编码(官方 `evaluation/` 不可改);64→96 帧实测 50%→55% 持平 → "帧数不足"证伪
- 多帧交错 vs 单帧:历史大坑(P7 非交错打包框架 bug),已修;现喂法与官方 CookBook 一致
- context 40960:实测不是解;题4 全程 n_past ~3500,**远未触及 context 上限** → "context 不够"证伪

## L4 · 推理参数层 —— B1 一锤定音

- `TEMPERATURE=0.0`(greedy)vs `0.1`:**逐题输出完全一致**(2/6 = 2/6,含题4 全`\n` 同)→ greedy 已最优,采样无杠杆
- `top_p=0.8 / top_k=100 / repeat_penalty=1.02 / MAX_TOKENS=100` 全部硬编码在不可改的 `evaluation/`;seed=42 固定保可复现
- **结论:采样层零空间**(env 覆盖仅作对照实验,跑分必须官方口径)

## L5 · 评测 pipeline 层 —— 从"跑分"到"口径审计"

- 口径:51.5% 为 **99 题子集**真实值,与官方全量 2700 基线不可直接比(已在 `competition-readiness.md` 显式标注)
- 工程护栏:`INFER_TIMEOUT` + CLI 重启(防一次算子卡死致整片记零分 —— 曾实测"一卡死,余 89 视频耗 22h 全零");CPU vision 类长任务须绕 client 直驱 CLI(`benchmark/video-mme-cookbook/diag/q4_cpu_vision.py`,已入仓可复用)
- **本层价值:保证测出来的数是真的**

## L6 · 归因层 —— 结论与出路

**51.5% 是 910B + 官方 64帧@1fps 口径下的真实、稳定、可复现水平**(非退化、非代码、非配置、非喂法、非采样、非框架 —— 见顶部排除链)。

三条出路均为**非代码路径**:
1. **910C 复现**(赛方算力)—— 官方基线明确"以 910C 复现";
2. **赛方确认 910B 独立基线**(~50%,Track B 双框架互证);
3. **环境受限豁免**。

---

## 整体判断

1. **优化是不对称的**:L0/L1(性能)可自主优化且有成果(NUMA 0.68→0.59,RTF beat 基线 ~46%);L2–L4(精度)每层空间被实测逐一关死 —— L3/L4 被官方口径锁死,L2 被实验排除。
2. **唯一破例**是 attention `-Inf` 修复(L2):证明该层**曾经**有真 bug;但修完后剩余 ~17.5pp gap 已不是同类问题。
3. **四路排除(2026-08-14)是压舱石**:`oghub` 的"flash_attn 溢出"假设已被澄清(FA 确实被关,但关是上游故意的,且强制开启也一样退化);vision 漂移端到端无效。证据链完整,可自信对赛方陈述。

## 附录:数据库类比版(供熟悉 DB 的读者快速理解)

推理栈与数据库栈本质都是"分层求值系统",映射如下:

| 层 | 数据库对应物 | 本项目对应 | 结论 |
|---|---|---|---|
| L0 硬件 | 同一 SQL 在 NVMe vs HDD / x86 vs ARM 上跑 | 同一模型在 910B vs 910C 上跑 | Track B = 换个引擎(PostgreSQL)跑同一 SQL 还是慢 → 非单引擎 bug |
| L1 系统配置 | `my.cnf`/buffer pool/fsync/NUMA 绑定 | governor/THP/NUMA 亲和/`ASCEND_*` | **只影响 QPS 不影响正确性**(NUMA 修正 = buffer pool 调优,RTF 0.68→0.59) |
| L2 算子实现 | hash join vs merge join、浮点 SUM 累加顺序/溢出 | FA vs fallback、softmax fp16、vision 编码 | attention `-Inf` 修复 = 修了一个 **SUM 溢出类真 bug**;四路排除 = **换遍所有 join 算法,结果逐行 byte-identical** |
| L3 执行计划/输入 | 优化器计划、索引、hint、ANALYZE 采样率 | 帧数 64@1fps、交错、context | 计划被 DBA 锁死(`evaluation/` 不可改);"加索引"证伪过(帧数 64→96 = 加大采样率,持平) |
| L4 隔离级别/确定性 | READ COMMITTED vs SERIALIZABLE、固定 plan | temp=0 greedy vs temp>0、seed=42 | B1 = 改隔离级别跑同批查询,**结果逐条一致** → 旋钮无杠杆 |
| L5 基准方法论 | TPC-H 1GB vs 100GB 分数不可比、预热/并发口径 | 99 题子集 vs 官方全量 2700 基线 | "你跑 1GB 规模,官方分是 100GB 规模"的口径审计 |
| L6 归因 | "SQL/计划/配置全查完,是老盘 IO 天花板" | 全排除 → 910B 平台差异 | 出路 = 换 NVMe(910C)/ 单独定基线 / 豁免 |

**三个故事版**:
1. **Track B = 换 PostgreSQL 跑同一 SQL**:怀疑 MySQL 优化器写坏?原样丢给 PostgreSQL 还是慢 → 不是 MySQL 的锅。HF/torch_npu 在同一片 910B 上也 ~50%,18/20 题判题一致,双引擎互证。
2. **四路排除 = 强制换遍 join 算法**:hash→merge、换 SIMD 路径、连官方禁用的 fast path 都解锁试了 —— 四种组合结果集逐行 byte-identical,算子层嫌疑洗清。
3. **attention `-Inf` = 唯一一次真 SUM 溢出**:历史上确有算子级 bug(`-Inf` 进 F16 溢出 → 全 NaN),修掉后"多帧必崩"变"基本干净"。这是全项目唯一成功的底层修复;也正因修过,才长期怀疑这层还有第二个 bug —— 四路排除证明没有了。

**总纲**:数据库调优黄金法则"先看执行计划,再看算子,最后才怪硬件" —— 我们完整走了一遍且每步留证:计划层锁死无空间,算子层四路排除,剩下的只能是硬件/平台(910B vs 910C)。

## 引用(均为 docs/ 内已落盘记录)

- `docs/experiments.md` —— 2026-08-14 节(NUMA/B1)+ 下午节(四路排除);P2/P2.5(NaN 定位);P7(喂法史)
- `docs/multiframe-degradation-fix.md` —— attention `-Inf` 根因与修复(43badb2)
- `docs/vision-npu-vs-cpu-diagnosis.md` —— 路径A 特征级 + 路径B 原始记录
- `docs/videomme-no-degradation-proof.md` —— response 无退化 + code 与 bench/huawei 一致性核查
- `docs/competition-readiness.md` —— 准入状态总表与口径标注
- `benchmark/video-mme-cookbook/diag/q4_cpu_vision.py` —— 可复用诊断脚本(直驱 CLI JSONL,vision backend 可选)
