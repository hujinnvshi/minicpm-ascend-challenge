# 基线口径证据汇总 — 79.5 / 69.0 是否为 llama.cpp-omni 框架基线

> 用途：支撑 [`official-clarification-request.md`](official-clarification-request.md) Q1。把赛事文档中关于 Daily-Omni 基线 **79.5**、VideoMME 基线 **69.0** 的全部相关表述提取汇总，呈现"官方规则口径 vs 我队实测疑点"的核心矛盾。
> 整理日期：2026-08-07。

---

## 一、赛事官方规则原文（最关键）

来源：`competition-research.md`（源自官方公众号 / MindSpore 活动页 / 官网，2026-07-31 获取）

> **精度约束**：在 Daily-Omni、TTS-Seed、Video-MME 等 Benchmark 上，优化后相对**对应框架基线**的精度降幅不超过 2 个百分点。

🔑 **关键词：「对应框架基线」**。官方规则明确把基线绑定到"对应框架"——子赛道 A 的基线理应是 **llama.cpp-omni 框架自身**的实测成绩，而非原生实现或别的模型。

## 二、官方评测规范中的基线数值

来源：`eval-spec.md`（来源：官方通知《评测规范说明》）

| Benchmark | 基线(F16) | 准入阈值 | 规范口径 |
|---|---|---|---|
| VideoMME | **69.0** | ≥ 67.0（降幅 ≤2pp） | "F16 不改模型 → 应 = 69.0，过" |
| Daily-Omni | **79.5** | ≥ 77.5（降幅 ≤2pp） | "F16 → 应 = 79.5，过（注：非公开 leaderboard 的 Qwen 61.82，那是另一框架）" |

规范"关键认知"自述：

> 基线是 **llama.cpp-omni 框架自身的 F16 基线**……精度 = 基线，准入必过。

## 三、我队实测产生的疑点

| 来源 | 表述 |
|---|---|
| `experiments.md` P8 | "79.5 / 69.0 **基线来源待官方确认**……**很可能非 llama.cpp-omni 实测，而是原生 MiniCPM/Qwen 成绩**。若是，**准入标准对 omni 框架不公**。" |
| `experiments.md` P6 | "官方基线 79.5% 是 **Qwen-Omni 类原生音视频模型**，框架代际差不可由 bug 修复跨越。" |
| `performance-report.md` §10 | "Daily-Omni 6.7%/12.5%……远低于基线 77.5。**79.5 基线来源待官方确认**……很可能非 llama.cpp-omni 实测。" |
| `submission-checklist.md` | "Daily-Omni 6.7%/12.5% — 框架硬上限……**79.5 基线来源待官方确认**。" |

## 四、核心矛盾

| 来源 | 立场 |
|---|---|
| 官方规则原文 | 基线 = "**对应框架**" 的（即 llama.cpp-omni） |
| eval-spec「关键认知」 | 断言基线 = "llama.cpp-omni 框架自身 F16 基线" |
| eval-spec 自注 + 我队实测 | Qwen 61.82 是"另一框架"；79.5/69.0 **疑似原生/Qwen 成绩**；omni 实测仅 ~10% |

**实测差距**：omni 框架 Daily-Omni ~10% vs 基线 79.5，相差约 **70 个百分点**；远超规则允许的"降幅 ≤2pp"。

## 五、三种可能 + 对应诉求

1. **79.5/69.0 不是 omni 框架基线**（实为原生 MiniCPM-o / Qwen-Omni）→ 请提供 **llama.cpp-omni 框架实测基线**，或调整这两项准入阈值以符合"对应框架基线"口径。
2. **79.5/69.0 是 omni 框架基线**，但我队运行配置不对 → 请提供**官方推荐的 omni 框架运行配置**（消除 60+ pp gap 是否源于配置差异）。
3. **omni 框架在这些 benchmark 上确有代际上限** → 请确认准入能否按框架能力如实论证 / 给部分分。

→ 已据此更新 `official-clarification-request.md` Q1（引入"对应框架基线"官方原文作为锚点）。
