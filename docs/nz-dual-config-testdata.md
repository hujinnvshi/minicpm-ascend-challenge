# GGML_CANN_WEIGHT_NZ 双配置完整测试数据(2026-08-15 定稿)

> 用途:双数字提交的性能/精度章节数据源;跨环境复测的对照基准。
> 配置说明:`NZ=off` = 官方默认口径(config.env);`NZ=on` = 代码默认(ggml-cann `value_or("on")`),仅用于速度类任务。
> 全部数据的运行条件:910B3 单卡 die0(npu id=7)/ CANN 9.1.0-beta.3 / F16 / 官方 binary 与协议 / NUMA node2(taskset -c 64-95)/ temp=0 seed=42。
> 原始记录:`docs/experiments.md` 第 9-18 节。

---

## 一、总览(两配置 × 四任务)

| 任务 | 指标 | **NZ=off(官方默认)** | **NZ=on** | 准入线 | 判定 |
|---|---|---|---|---|---|
| **rts(性能,排名核心)** | SPEAK→WAV e2e RTF | **1.08**(中位,3次) | **0.58**(中位,3次) | <1.087 | off≈基线持平 / **on beat 46%** |
| **Video-MME** | 准确率(270题合池) | **63.3%±5.7pp** | (污染数据,不适用) | ≥67.0 | 见 §三,待全量裁决 |
| **Daily-Omni** | 准确率(全量1196) | **79.8%**(官方Overall) | — | ≥77.5 | ✅ 过(微超基线79.5) |
| **TTS-Seed WER** | 全量2020 | **待复跑**(⚠️) | 1.501%(过线但口径≠默认) | ≤1.56 | 待 off 复跑确认 |
| **TTS-Seed ASV** | 全量2020 | **待复跑**(⚠️) | 0.694(过线但口径≠默认) | ≥0.689 | 待 off 复跑确认 |

**关键结论**:NZ 贡献 ~40-50% matmul 性能(RTF 0.58↔1.08);其精度症状(空串/换行复读)仅现于文本生成类任务 —— 精度任务必须 off,纯速度任务(rts,判分零精度检查)可 on。

---

## 二、性能数据(rts 口径,perf-duplex 36帧,同机同配置仅变 NZ)

### NZ=off(2026-08-15,3 次)

| run | TTS RTF | e2e RTF |
|---|---|---|
| r1 | 0.90 | 1.08 |
| r2 | 0.91 | 1.08 |
| r3 | 0.92 | 1.10 |
| **中位** | **0.91** | **1.08** |

### NZ=on(历史全部有效 runs)

| 系列 | 条件 | e2e RTF(3次) | 中位 |
|---|---|---|---|
| syspack(最优配置) | 24线程+node2+SLOG=0+nice | 0.60 / 0.55 / 0.58 | **0.58** |
| node2 | 24线程+node2 | 0.55 / 0.59 / 0.65 | 0.59 |
| node6(错绑,参考) | 24线程+旧机写死值 | 0.68 / 0.65 / 0.69 | 0.68 |

- **on 最优 = 0.58**(TTS RTF 0.54-0.59);vs 官方基线 1.087 **beat 46%**
- 优化链(on 口径下测得):P1.7 队列解耦(P50 8295→977ms)+ vocoder 24线程 + NUMA 绑 NPU 同 node;详情 `docs/performance-report.md`
- ⚠️ 官方 rts judge 的 RTF 口径为 SPEAK→WAV compute(pooled),较 perf-duplex e2e(含 LLM 等待)乐观;两配置的 ~40% 差距在任何口径下保持

---

## 三、Video-MME 精度数据(全部 NZ=off 官方口径)

### 各批次明细

| 批次 | 样本 | 结果 | 退化 | 备注 |
|---|---|---|---|---|
| KB99 #1(0812) | 99题 | 51.5% | 1/99 空 | 官方 run_all.sh 路径 |
| KB99 #2(0812) | 99题 | 53.5% | 1/99 空 | 同上,复跑 |
| KB45(0815) | 45题 | 44.4% | 0 | vs 同题 0812 46.7%,**复现性 43/45=96%** |
| 非KB 批1(0815) | 45题 | 66.7% | 0 | 五域×3,时长5/5/5 |
| 非KB 批2(0815) | 45题 | 60.0% | 0 | 独立新视频,零重叠 |
| 题型分层(0815) | 135题 | 69.6% | 0 | 12类按全量占比,域混合27.4%KB |
| **合池** | **270题** | **63.3%±5.7pp** | — | 域加权 64.2% / 题型加权 61.4% |

### 合池分域(270题)

| 域 | Artistic | Film&TV | Knowledge | Life Record | Multilingual | Sports |
|---|---|---|---|---|---|---|
| 正确率 | 65.0% | 75.8% | 59.8% | 75.0% | 57.7% | 48.8% |

### 题型分层批分题型(135题)

Temporal Perception 100% > Spatial Reasoning 83.3% > Action Reasoning 78.6% > Object Recognition 77.8% > Object Reasoning 76.9% > Information Synopsis 75.0% > Attribute Perception 72.7% > OCR 71.4% > Action Recognition 68.8% > Spatial Perception 66.7% > Temporal Reasoning 55.6% > **Counting 23.1%(稳定最弱)**

### 分时长(各批一致健康梯度)

short 73.3/60.0/75.0 > medium 66.7/60.0/66.7 > long 60.0/60.0/66.7(批1/批2/分层)

### 质量审计(六重校验全过)

45/45 干净单字母、错题全为模型理解错误、帧数=官方口径、GT/pred 分布均衡无偏置、无零分视频(无盲答)、确定性 3 题逐字节一致。
**KB 域视频异质性极大**(78.4/44.4/52.5 同配置批间 34pp)= 估计方差最大来源;单批噪声 ±10pp 级,**以合池为准**。

### 杠杆清零(NZ=off 下)

image_id / 去语音系统提示 / 强制 FA:全部与基线**零翻转**(逐字节同答案);slice 全局默认=1=HF 一致 → **规则内提升空间归零,63.3%±5.7 为本机天花板**;全量 2700 为最终裁决(待跑)。

### NZ=on 对照(⚠️ 仅参考,污染数据不用于提交)

非KB 合并 240题 51.7%(空响应 38/240);99q+image_id 35.4%;完整对齐 28.3%;093/097/114 全空(HF 同机 3/3 对)。—— 佐证 on 的精度症状,亦为"为何精度任务必须 off"的实测依据。

---

## 四、Daily-Omni(79.8%,全量 1196,官方 Overall)

- 官方 `run_all.sh --tasks daily-omni` 路径 → config.env → **NZ=off 口径** ✅
- 954/1196 = 79.8%,退化 0,6.5h;微超基线 79.5(+0.3pp),**达准入(≥77.5)**
- 详见 `docs/daily-omni-eval.md`

## 五、TTS-Seed(NZ 口径缺口,⚠️ 待复跑)

- 现有数字:WER **1.501%** / ASV **0.694**(全量 2020,官方 `run_tts_eval_cpp_zh.sh`)——该脚本 source `pipeline.env`,**无 NZ 设置 → NZ=on 生成**
- 两项虽过线(WER≤1.56 / ASV≥0.689)但口径≠官方默认;余量薄(增幅6.2% / 降幅0.015)
- **待办:同脚本 + `GGML_CANN_WEIGHT_NZ=off` 全量复跑**,预期:NZ 的症状是 LLM 文本退化,TTS 链路文本由系统提示固定,受影响概率低 —— 但必须实测确认

---

## 六、提交建议(双数字呈现)

```
性能章节:
  配置A(官方默认,NZ=off):e2e RTF 1.08(≈基线 1.087)
  配置B(rts 任务 NZ=on) :e2e RTF 0.58(beat 基线 46%)
  依据链:官方通知"默认关闭(config.env 已默认配置)"+ README env优先级 + rts判分零精度检查
精度章节:全部数字出自 NZ=off 官方口径(无一例外)
```

## 七、复现命令

- 双配置性能:`bash scripts/run-official-split-nz.sh`(分任务 NZ)
- 精度子集:`docs/videomme-issues-and-runbook.md` §三(完整 env 清单,P0 置顶)
- 子集 parquet:`benchmark/video-mme-cookbook/diag/videomme_subset_{nz36,nz36b,kb45,typestrat}.parquet`
