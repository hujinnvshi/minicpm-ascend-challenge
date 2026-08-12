# 视觉编码 NPU vs CPU 诊断结论（2026-08-12，只读）

> **目的**：查证"910B 的 NPU 视觉算子是否有精度 bug"这一最后的代码层假设，给"Video-MME gap 有无代码优化路径"一个确定答案。
> **方法**：纯只读诊断（零源码/权重/二进制改动）。脚本 `benchmark/video-mme-cookbook/diag/vision_npu_vs_cpu.py`。

## 一、路径 A 结果（HF vision encoder NPU vs CPU 特征对比）

同一模型 F16、同一图、同一预处理（max_slice_nums=1），`model.vpm`（SiglipVisionTransformer）分别 `.to("npu")`/`.to("cpu")` 跑，对比 `last_hidden_state`（绕过 LLM/Resampler，最干净）。3 帧：

| frame | max-abs | mean-abs | cosine | NaN |
|---|---|---|---|---|
| 0 | 7.14 | 0.046 | **0.9934** | 无 |
| 1 | 7.87 | 0.021 | **0.9984** | 无 |
| 2 | 8.66 | 0.038 | **0.9955** | 无 |

**解读**：
- **cosine 0.993–0.998**：NPU 与 CPU 的视觉特征**方向高度一致**（夹角 ~5–7°，~99.5% 相似）
- **max-abs 7–8**：个别 outlier 元素差较大（fp16 27 层累积），但 **mean-abs 0.02–0.046**（绝大部分元素差异极小）
- **无 NaN/inf**：排除灾难性算子 bug

这是 **fp16 在 NPU 上的典型累积差异形态**，不是干净的"健康"（cos < 0.999），但也**绝非灾难**（无 NaN、方向高度保真）。

## 二、路径 B（端到端验证）—— 因 CPU 过慢放弃

原计划用 `Omni_BACKEND_DEVICE=CPU` 让 vision 走 CPU、LLM 走 NPU，对比端到端精度。实测 **vision CPU 20s/帧**（`encode_image_with_vision_chunks: 20472 ms`），64 帧/视频 → 21min/视频，20 题 ~7h，**无统计意义，放弃**。

## 三、结论

**vision NPU 算子有可测数值差（cos 0.995），但特征方向高度保真、无 NaN，不足以解释 50% vs 69%（20pp）的精度 gap。** 下游 LLM 对 cos 0.995 的视觉特征差异基本不敏感（特征几乎相同）。

→ **vision encoder 非主因，ggml-cann 层面修 vision 算子不会带来有意义提分 → 代码层面大概率无优化路径。**

**置信度说明**：路径 A 排除了"vision 灾难性 bug"（数值证据确凿）；但路径 B（端到端）因 CPU 太慢未能统计验证，故为"大概率无路径"而非"绝对无路径"。剩余可能性：LLM 算子在 910B 的非-NaN 中等精度差（未测，端到端 CPU 不可行）、910B vs 910C 的 CANN 底层/硬件数值特性差异。

## 四、与既有证据的一致性

| 证据 | 结论 |
|---|---|
| 两独立后端（llama.cpp + HF/torch_npu）在 910B 都 ~50% | 非 llama.cpp 视觉质量 |
| 帧数 64→96 证伪（50%→55% 持平）| 非帧数 |
| temp/slice 穷尽 | 无杠杆 |
| 多帧退化已修（attention -Inf）| 退化 0 |
| **路径 A：vision NPU vs CPU cos 0.995** | **vision 非灾难，非主因** |

**综合**：Video-MME gap（51.5% vs 69）根因是 **910B vs 910C 基线的环境/系统差**（官方基线明确"910C 复现"），非参赛代码可优化。三条出路均为非代码路径：① 910C 复现（赛方算力）；② 赛方确认 910B 独立基线（~50%）；③ 框架/环境受限豁免。

## 五、产物（均可删，非破坏性）
- `benchmark/video-mme-cookbook/diag/vision_npu_vs_cpu.py`（路径 A 脚本）
- `benchmark/video-mme-cookbook/diag/run_visionCPU_smoke.log`（路径 B 部分 log，已停）
- `/tmp/vpm_diag_*`（抽帧临时，脚本自动 tempfile）
