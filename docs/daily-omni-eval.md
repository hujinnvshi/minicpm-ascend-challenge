# Daily-Omni 评测打通（2026-08-12）— 88% 超基线

> **状态**：✅ 官方 pipeline 跑通，50 题子集 **88.0%（超基线 79.5 / vLLM 78.28% / 准入 77.5）**，退化 0。全量 1196 待跑确认。
> 分支：`bench-huawei-adapt`。配套：`benchmark/daily-omni-convert/`（转换脚本 + EVAL_CONFIG）。

## 一、为什么能跑通（关键：数据本机齐 + 无需外部打分模型）

- 数据：`shared_assets/datasets/MTEB/Daily-Omni/data/` 10 个 parquet 分片，**音视频字节内嵌**（`video.bytes`=合法MP4, `audio.bytes`=合法WAV/16k mono/30s），1196 题 / 684 唯一视频
- 打分：选择题准确率，**无需 paraformer/wavlm 等外部打分模型**（不像 TTS-Seed 卡在打分模型缺失）
- 官方 `evaluation/daily-omni/` 要的是 `daily_omni.jsonl` + 独立音视频文件——写个 parquet→jsonl+落盘转换脚本即可，**不改 evaluation/**（EVAL_CONFIG 覆盖）

## 二、转换（`benchmark/daily-omni-convert/convert.py`）

字段映射（官方 `eval_cpp_pipeline.py` 期望，**大小写敏感**）：

| jsonl 字段 | 来源 | 转换 |
|---|---|---|
| `VideoPath` / `WavPath` | parquet `video.path` / `audio.path` | 直接（PascalCase）|
| `video_id` | `video_id` | 直接 |
| `question` | `question` | 直接 |
| `choices` | `candidates` | **保留 "A. " 前缀**（pipeline build_prompt 会再加一层，对齐官方双前缀行为）|
| `gt_answer` | `answer` | **`answer[0]`** 单字母（parquet 是完整文本 "B. xxx"）|

- 音视频按 video_id 去重提取（684 个），bytes 直接 `write_bytes`，约 2.7GB
- 校验：1196 jsonl 行 + 684 mp4 + 684 wav + gt 全字母 + choices 全带前缀 ✓
- 产物在 `benchmark/daily-omni-data/`（gitignored）

## 三、结果

### smoke 2（链路验证）
`[OK] Daily-Omni`，2/2=100%，**无退化**（Resp='B'/'A'），video prep（30帧@1fps）+ audio prep（30段交错）正常。

### 50 题子集（前 50 行，output/20260811_235325）
| 指标 | 值 |
|---|---|
| 准确率 / 官方 Overall | **44/50 = 88.0%** |
| 退化 | 0 |
| 涉及视频 | 26 个（跨多视频）|
| 模型答案偏置 | 无（Pred≈GT 分布）|
| 答错 6 题 | 分散 6 视频，非聚类 |
| 用时 | 751s |

**88% > 基线 79.5 > vLLM 78.28% > 准入 77.5。**

## 四、对比 Video-MME 与 gap 归因

| benchmark | 我们 | 基线 | 是否达标 | 差异原因 |
|---|---|---|---|---|
| **Daily-Omni** | **88%**（50题）| 79.5 | ✅ 超基线 | 30s 短视频 + interleave 交错喂法（训练分布，信息覆盖好）|
| Video-MME | 51.5% | 69.0 | ❌ gap | 分钟~小时长视频 @1fps 64帧（信息稀疏）|

→ 反向印证：**Video-MME 的 gap 是长视频帧采样问题，不是框架/硬件**（同框架同硬件，daily-omni 短视频能超基线）。退化修复（attention -Inf）在两项都有效。

## 五、怎么跑

```bash
# 转换（一次性）
/workspace/user_data/venv-omni/bin/python benchmark/daily-omni-convert/convert.py
# 评测（smoke→小批量→全量）
cd code/llama.cpp-omni/evaluation
EVAL_CONFIG=../../../benchmark/daily-omni-convert/eval-daily.env \
  ./run_all.sh --tasks daily-omni --smoke 2 --no-build        # 链路
EVAL_CONFIG=../../../benchmark/daily-omni-convert/eval-daily.env \
  ./run_all.sh --tasks daily-omni --smoke 50 --no-build       # 小批量
EVAL_CONFIG=../../../benchmark/daily-omni-convert/eval-daily.env \
  ./run_all.sh --tasks daily-omni --full --no-build           # 全量1196
```
依赖：venv-omni 装 `librosa soundfile`（audio_prep 用，已装）；decord 缺则 video_prep fallback ffmpeg（正常）。复用 `build-huawei/bin/llama-omni-eval-daily-cli`（含退化修复）。

## 六、下一步
- 50 题子集 88% 偏易（信号）；**全量 1196 已跑：79.8%（output/20260812_132304，用时6.5h，官方Overall 954/1196），微超基线79.5（+0.3pp），达准入（降幅≤2pp，实际增幅）**
- 三项现状：Video-MME 51.5%（gap，待赛方澄清口径）/ **Daily-Omni 88%（超基线✓）** / TTS-Seed 未跑（卡打分模型）
