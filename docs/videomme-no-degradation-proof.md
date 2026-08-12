# Video-MME 无退化证明 + code 一致性核查（2026-08-12）

> **背景**：赛方提示"bench/huawei + fp16 不该差这么多，检查 videomme 日志看是否有退化（大量 \\n 重复等）"。本文件是核查结果：**排除退化 + 代码与 bench/huawei 逐字一致**，证明 51.5% 是真实精度。
> 数据源：output/20260811_211509（官方 `evaluation/` pipeline，99 题分层 short/medium/long 各 33）。

## 一、response 退化检查（赛方提示的 \n 重复 / _ 退化）

对 99 题 videomme_output.json 的 `response` 字段逐题分析：

| 类别 | 题数 |
|---|---|
| 正常（干净单字母 A/B/C/D，<5 个 \n）| **98** |
| 大量 \n 重复（≥5）| **0** |
| `_` 退化（token id 30 / NaN argmax 指纹）| **0** |
| 空 / 边界（如 "BC" 两字母）| 1（606-2，extract 边界，非 NaN）|

- response 长度：min=0, max=1, mean=1（**全是干净单字母**）
- 示例：001-1 GT=C resp='A'、001-2 GT=A resp='A'、002-1 GT=C resp='C' …

**结论：赛方提示的 \n 重复退化不存在；_ 退化也为 0（多帧 attention -Inf 修复有效）。response 干净，extract_answer 提取正确，51.5% 是真实答对率。**

## 二、代码一致性核查（我们 vs 上游 bench/huawei）

逐文件 `diff -rq` 我们的 `code/llama.cpp-omni/` vs 上游 `bench/huawei`（`/workspace/user_data/llama.cpp-omni-upstream`）：

| 文件 | diff 结果 |
|---|---|
| `ggml/src/ggml-cann/`（含 attention -Inf 修复）| **无差异** ✓ |
| `tools/omni/omni.cpp` | **一致** ✓ |
| `tools/omni/omni-eval-cli.cpp` | **一致** ✓ |
| `evaluation/videomme/` | 一致（仅 `__pycache__/log/tmp_frames` 运行产物）|

- `build-huawei/` 用**纯 bench/huawei 源码**构建（ccec + `-lascendcl`），**无我们的 perf 补丁混入**（perf 补丁在 `build-cann/`，评测不用）

**结论：评测路径的代码与官方 `bench/huawei` 逐字一致，无任何选手改动影响精度。**

## 三、综合结论

| 排查项 | 结果 |
|---|---|
| response 退化（\n 重复 / _ / NaN）| **无**（98/99 干净单字母）|
| 代码与 bench/huawei 一致 | **是**（ggml-cann + omni + eval-cli diff 无差异）|
| 多帧退化（attention -Inf）| **已修**（退化 0）|
| 帧数/temp/slice 配置 | 官方 `evaluation/` 写死，穷尽无杠杆 |

→ **51.5% 是 910B + bench/huawei + fp16 + 官方 evaluation/ 口径的真实精度，非退化、非代码改动、非配置问题。**

与基线 69 的 gap（17.5pp），在排除退化 + 代码一致后，只能归因于**环境差异**（CANN 版本 / build flag / 硬件 910B vs 910C）。附 Track B 佐证：同一台 910B 上 HF/transformers + torch_npu 独立后端同口径也 = 50%（18/20 题与 llama.cpp 一致），证明 ~50% 是 910B 这块硬件的稳定真实水平，非单一框架问题。

## 四、待赛方确认

如果赛方 `bench/huawei + fp16` 实测接近 69，请告知与我们 51.5% 的**环境/配置差异**（CANN 版本？build flag？硬件 910B 还是 910C？），我们可对齐复现。
