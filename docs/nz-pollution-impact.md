# NZ 污染对提交物证据链的影响清单（2026-08-15 review-optimize）

> 背景：官方 evaluation/README FAQ 要求 **`GGML_CANN_WEIGHT_NZ=off`**（否则"可能出现空串、换行复读等异常输出"）；ggml-cann.cpp:1286/1554 默认 `value_or("on")`；off 只经 run_all.sh→run_eval.sh→run_eval.py 官方路径注入（run_eval.py 4 处 `cfg(..., "off")` 默认）。**一切绕过官方路径的直跑（eval_cpp_pipeline.py 直接起 / 诊断 binary）如未 export NZ → NZ=ON（官方禁止配置）**。直跑产出数据一律作废或需复核。

## 一、实测事实（2026-08-15）

| 事实 | 数据 | 来源 |
|---|---|---|
| NZ=off 下空响应几乎为零 | 99q（08-12 复现 run 20260812_102746）：**empty=1/99（606-2）**；smoke33 基线（20260814_235530）：empty=0/33；smoke8 门控（20260815_001110）：empty=0/8 | 本清单逐 json 统计 |
| NZ=ON 直跑空响应高发 | 08-14 晚 180 题 31 空（17%）；60 题 7 空；KB99 1 空 | experiments.md 08-14 晚节 |
| 官方 FAQ 症状"空串"与 NZ=ON 高发空响应吻合 | — | evaluation/README FAQ |

**结论：08-14 晚"空响应=缺 image_id→EOS 临界翻转"整套归因建立在 NZ=ON 直跑数据上，对象是 NZ 布局 bug 制造的假象 → 作废。**

## 二、提交物逐项判定

| 提交物数字/声明 | 评测路径 | NZ 状态 | 判定 |
|---|---|---|---|
| 性能 SPEAK→WAV RTF 0.58-0.59（排名核心）| perf-duplex 直跑 | NZ=on（默认，无 env）| ⚠️ **NZ=on vs off 对比实验进行中**（见下）；若 RTF 无差异则有效，有差异需重测口径 |
| Daily-Omni 79.8%（全量 1196）| run_all.sh 官方路径 | NZ=off（注入）| ✅ 干净 |
| TTS-Seed WER 1.501% / ASV 0.694（全量 2020）| run_tts_eval_cpp_zh.sh（**无 NZ export**）| ⚠️ NZ=on 嫌疑 | ⚠️ **需 NZ=off 重跑生成复核**（准入线 WER≤1.56 / ASV≥0.689，余量 0.059/0.005，擦线风险）|
| Video-MME 51.5-53.5%（99q 子集）| run_all.sh 官方路径 | NZ=off | ✅ 干净（空响应 1/99，真实答案分歧水平）|
| Video-MME gap 归因：空响应 12% / EOS 临界带 / 910B gap 机制解释 | 直跑诊断（OMNI_DEBUG_TOPK 探针等）| NZ=on | ❌ **作废**。NZ=off 下无空响应杠杆，gap 主体=真实答案分歧 |
| 协议对齐 OMNI_IMAGE_ID 修复（12d22a9/ee3fbad/b6b8bb8）| 直跑诊断 | NZ=on | ❌ 修复对象作废（NZ=off 无空响应）；门控保留为探针，**不得默认启用** |
| 协议对齐 A/B：九节"28.3% 路线关闭" | 并行会话直跑 | NZ=on | ❌ 作废（数据无效，但"关闭"结论因 NZ=off 无退化而意外成立——见 smoke33）|
| 协议对齐 A/B：smoke33 门控 60.6% = 基线 60.6%（review-optimize 实测）| 手动直跑（source env 含 NZ=off）| NZ=off | ✅ 有效：NZ=off 下对齐无净影响（因问题不存在）|
| Track B HF 对照：同机 3 题 HF 全对 vs llama.cpp 全空（08-14）| HF 侧无 NZ 概念；llama.cpp 侧直跑 | llama.cpp 侧 NZ=on | ⚠️ 对照结论（"协议差异"）作废方向；HF 50%（08-11 KB99 旧机）与 NZ 无关仍有效 |
| 域偏差 60/180 题（339 合并 ≈52%）| 直跑 | NZ=on | ⚠️ 数值作废；但合并 52% ≈ NZ=off 的 51.5-53.5%，**方向性结论仍成立** |
| 帧数 64 vs 96（uni96）| 直跑 | 待查（大概率 NZ=on）| ⚠️ 结论"帧数无杠杆"大概率仍成立（NZ 与帧数无关）|
| 温度 0/0.1 对照 | 直跑 | NZ=on | ⚠️ 结论"无杠杆"大概率仍成立（同分布噪声）|
| multi-frame 退化（attention -Inf 修复, 43badb2）| 官方路径+直跑混合 | 官方路径 NZ=off | ✅ 退化 0 在 NZ=off 下也成立（51.5-53.5% 无退化）|

## 三、待完成验证（结果将回填本节）

1. **🔴 RTF × NZ（战略级，最高优先）**：官方 `run_eval.py` 的 **RTS（RTF 性能评测）任务也注入 `GGML_CANN_WEIGHT_NZ=off`**（L321，与精度任务同）。并行会话实测（5771843，**但对照不对称——NZ=on 用历史独占 0.58，NZ=off 为同期新测**，且时段 CPU 竞争 load 15-53）：NZ=off 三跑 e2e RTF **1.08 / TTS 0.91** vs NZ=on 0.58 → **NZ 贡献 ~50% 性能，若官方 RTF 口径为 NZ=off，RTF 优势归零（1.08 ≈ 基线 1.087 边缘）**。我方首测（同竞争时段）NZ=on 1.01/1.05 vs off 1.12/1.18 亦被污染不可判。**待办（NPU+CPU 独占）：同条件 NZ=on vs off 各 ≥2 次，确定真实影响**；同时确认官方 RTF 评测脚本是否强制 NZ=off（run_eval.py rts 是官方代码事实，但比赛实际流程待查）。若 NZ=off 确认使 RTF≈1.0：出路 a) 申诉"FAQ 的 off 论证仅针对精度任务，RTS 无精度指标"（并行会话方案 A：精度 off + RTS on，env 覆盖+披露）；b) 研究 ggml-cann NZ 路径性能差异（NZ=on 快 50% 的机理，合规内恢复性能）；c) 接受 NZ=off 下排名（全队同口径，比优化）。
   运行记录：tools/omni/output/rtf_nz{on,off}_r{1,2}.json（被污染，勿用）；并行会话 NZ=off 三跑产物待查。
2. **TTS-Seed NZ=off 生成复核**（未做）：**venv-tts 已随机器迁移丢失**（/workspace/user_data/venv-tts 不存在，run-tts.env 亦未随包入库——benchmark/tts-seed-convert/ 只有转换脚本），重建需重装 torch/torchaudio/s3prl/funasr 并复踩 tts-seed-eval.md 记录的 5 个坑（transformers 降级 4.44.2、torchcodec、sitecustomize stub、hf-mirror wavlm、funasr 慢 import），约 1-2h。**建议子集 200 条先验**（生成 ~30min + WER/SIM CPU）——此项决定 TTS 准入数字（WER 1.501 vs 线 1.56 余量 0.059；ASV 0.694 vs 线 0.689 余量 0.005）是否有效，**优先级最高**。

## 四、对策略的影响

- Video-MME："球在赛方"（基线口径申诉）主线不变，但**必须从证据链中剔除空响应论证**（organizer-inquiry-2026-08-12.md 若未发，重写证据段：去掉 12% 空响应/EOS 临界，保留 51.5%（NZ=off 官方路径）+ Track B 同机 50% + 帧数/温度无杠杆 + 基线 69.0 出处质疑）。
- 性能：待 NZ 实验定口径。
- TTS：待 NZ=off 复核定准入数字。
- 纪律（写入 docs）：**评测/诊断必须走官方路径或显式 export GGML_CANN_WEIGHT_NZ=off**；任何直跑数据不得直接进入提交物。
