# 竞品情报：doma（深大&广工）子赛道 A 优化全公开（2026-08-26 收集）

> 来源：GitHub `gegemeimingzi/MiniCPM-o-Ascend-Optimization-Docs`（doma 队实验归档，109 文件，8/21 后仍在更新）
> 价值：① **证实大学有 910C**（doma 明确"910B3 → 910C 换服务器"）；② 他们的优化补丁全公开，4 项是
> 我们 CLOSED/未做方向 → v7 移植候选；③ 910C 实测数据可校准我们的仿真模型。

## 一、doma 概况与硬件（证实"大学有 910C"）

- 队伍：doma（深圳大学 & 广东工业大学），榜单第 2（RTF 0.5417，8/23）
- 硬件：Ascend 910 ×2（CANN 9.1.0-beta.1），Ubuntu 22.04 aarch64
- **项目总结.md 原文："1. 910B3 → 910C：换服务器，基线 1.369 → 1.0086"** → 大学渠道拿到真 910C
- 代码：bench/huawei @ 48076a8（base b06198f）——与我们同基线

## 二、RTF 演进（910C 上实测）

| 阶段 | 日期 | 配置 | RTF |
|---|---|---|---|
| 910B3 基线 | 08-13 | F16 | 1.369 |
| 910C 基线 | 08-14 | F16 | 1.0086（decode 0.318/tts 0.259/t2w 0.243/encode 0.176）|
| 主 LLM FA | 08-14 | OMNI_FLASH_ATTN | ~0.835（decode -56%）|
| Sprint16 | 08-20 | 官方复测修正 | core 0.762（-29.9%）|
| 本轮 | 08-20~21 | TTS FA+VPM batch+4步flow | FULL 0.694（core ~0.70）|
| 官方榜 | 08-23 | 后续迭代（sprint17/18）| **0.5417**（比 8/21 自测好 22-28%）|

## 三、最终提交配置（48076a8）

| env | 值 | 作用 | 我们对应 |
|---|---|---|---|
| OMNI_TTS_FLASH_ATTN | 1 | TTS FA，decode -7~10% | ❌ 8/22 测 voxcpm2 use_flash_attn 负收益关闭（可能路径不同）|
| OMNI_VISION_BATCH_ALL | 默认开 | VPM overview+slice 同尺寸批量编码，encode -24%（0.147→0.111）| ❌ 8/21 H3 "slice=1 无空间" |
| OMNI_TTS_HEADCODE_NPU | 1 | head_code matmul 放 NPU，bit-identical | ✅ CPU 行间并行（v6，不同方案）|
| OMNI_T2W_N_TIMESTEPS | 4 | flow 4 步（需与 prompt_cache 一致），byte-identical | ❌ 5 步拐点 CLOSED（实现差异）|
| OMNI_T2W_F16_CONV | 0 | vocoder F16 禁用 | ✅ 同（我们也否决 F16）|
| OMNI_T2M_SKIP_REDUNDANT_CONT | ADD_MUL | t2m 冗余 CONT 消除，t2m -3.9~-7.7%，bit-identical | ❌ 未做 |

⚠️ config.env（Sprint16）里 OMNI_TTS_FLASH_ATTN=0（"双工 server 路径破坏流式 8 SPEAK/4轮 vs 27/5轮 → RTS 固定 FA off"）——但最终提交配置表 =1，需查 本轮优化-20260820-21.md 确认最终态。

## 四、否决项（与我们高度重合）

Q4/Q8/W8A8 量化（launch 墙）、executor 复用（CANN 段错误）、ACL 图捕获（SPEAK capture H2D 崩溃 EE9999）、
cache in-place/KV slot-write（aclnnInplaceCopy strided 写错）、vocoder F16（负优化）、flow B=1（TTS 精度评测 reset 崩溃）、
flow 3 步（GPU init 失败）、ARN 融合。

## 五、v7 移植候选（910B4 可验证性评估）

1. **VPM batch（OMNI_VISION_BATCH_ALL）**：我们 encode 0.359 是大头（他们 910C 才 0.176）→ 910B4 上收益可能更大。patch_vpm_batch.patch 公开。
2. **t2m CONT 消除（OMNI_T2M_SKIP_REDUNDANT_CONT）**：纯算子级消除，bit-identical，风险最低。340 个冗余 CONT。
3. **head_code NPU（OMNI_TTS_HEADCODE_NPU）**：与我们的 CPU 并行互补（可叠加或替代）。sprint3-headcode-npu-result.md。
4. **TTS FA（OMNI_TTS_FLASH_ATTN）**：我们试的路径可能错了（voxcpm2 命名陷阱已记录）。tts_fa_graph_diff.md 可对照。
5. **4 步 flow**：我们 CLOSED（5 步拐点），他们改代码让 4 步可行——移植需谨慎（精度/图缓存）。

## 六、对我们的启示

1. 910C vs 910B3 基线：1.369/1.0086 = **1.36x**（doma 实测，纯基线口径）；910C vs 910B4 默认 ≈1.57-1.70x
2. 他们的优化组合（FA+TTS FA+head NPU+VPM batch+4步+CONT 消除）在 910C 上比我们多榨 ~35% →
   我们的 v6 在 910C 上 ~0.71 vs 他们 0.5417，差距主要在这 4 项未做优化 + 后续迭代
3. 移植 2 项（VPM batch + t2m CONT）预估 910B4 RTF 1.166 → ~1.05-1.10，官方 910C 出分再降 5-10%
4. 风险：910C 上有效的优化在 910B4 上未必有效（硬件/算子差异），必须本地分布分离验证 + bit-identical 精度门禁

## 七、文件清单（/tmp/doma-intel/ 已下载）

- patch_vpm_batch.patch / sprint17_18_tracked_changes.patch / sprint17_18_untracked_configs.patch
- 本轮优化-20260820-21.md / 优化成果.md / 项目总结.md / config.env
- sprint3-headcode-npu-result.md / sprint5-tts-flash-attn-result.md / sprint13-cont-view-result.md
- tts_fa_graph_diff.md / headcode_correctness.md / flow-B1尝试.md / sprint16-rtf-remeasure-finding.md
