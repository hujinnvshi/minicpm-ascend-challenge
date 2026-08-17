# 多帧退化复现 + 对比分析指南

> 用途：在新/旧环境复现 Video-MME 多帧退化，并用 logits 数值打印对比根因（NaN vs 塌缩）。
> 配套：诊断打印在 `omni.cpp`（commit `5859e35`，env 开关默认关）；诊断脚本在 `benchmark/video-mme-cookbook/diag/`。

## 背景

Video-MME 多帧退化：≥6 帧时模型输出 100 个 `_`（0/2 正确）。本指南把"退化"从现象推进到**机制**，并在不同 CANN 版本间对比。

## 已知结果

| 环境 | 退化阈值 | 6帧 logits | vision embed | 单帧红线 |
|---|---|---|---|---|
| **新设备 beta.1**（910B / CANN 9.1.0-beta.1）| **6 帧**（≤5 正常）| **NaN**（maxlogit=nan）| 正常（emb_nan=0）| ✅ 1帧 2/2 全对 |
| 旧设备 beta.3（910B3 / CANN 9.1.0-beta.3）| 同（0/2）| **未测** | 未测 | — |

⚠️ **关键**：旧环境那句"logits 退化，非数值崩溃"是**看 CLI log 文本**得出的——但 CLI log 默认**不打印 logits 数值**，所以"没看到 NaN"≠"真没有 NaN"。beta.3 是否也 NaN，**需要用本指南复测才能定论**。

## 复现步骤

### 1. 拿到诊断打印 + 脚本
```bash
git pull origin fix/video-extract-harden   # 含 commit 5859e35（omni.cpp 诊断打印）+ diag/ 脚本
```

### 2. build（含诊断打印）
```bash
bash scripts/build-cann.sh "$PWD/code/llama.cpp-omni"     # 注意传 REPO 参
cmake --build code/llama.cpp-omni/build-cann --target llama-omni-eval-cli -j$(nproc)
```

### 3. 准备视频 + .env（见 `session-2026-08-10-newenv.md` 阶段4）
- 解压 `fFjv93ACGo8.mp4`（在 `videos_chunked_07.zip`）到 VIDEO_DATA_DIR
- 写 `benchmark/video-mme-cookbook/.env`（覆盖默认：`LLAMA_CLI_BIN` / `LLM_MODEL_PATH` / `PARQUET_PATH` / `VIDEO_DATA_DIR` / `CTX_SIZE=40960`）

### 4. 跑帧数梯度（找阈值）
```bash
cd benchmark/video-mme-cookbook
source <venv>/bin/activate          # pandas/pyarrow/Pillow
CUDA_VISIBLE_DEVICES=0 python diag/diag_frames.py "1,2,4,5,6,7,8,16,32" 2
```
预期（beta.1 实测）：1/2/4/5 帧 ✅全对，6/7/8/16/32 帧 ❌输出 `_`。**阈值=6 帧**。

### 5. 看 logits 判根因（NaN vs 塌缩 vs vision）
```bash
CUDA_VISIBLE_DEVICES=0 OMNI_DEBUG_LOGITS=1 OMNI_DEBUG_NAN=1 \
  python diag/diag_rootcause.py 5 6 1
# 产物：./rc-log-5.log（正常）+ ./rc-log-6.log（退化）
grep DBGLOGITS rc-log-5.log rc-log-6.log
grep DBGNAN    rc-log-6.log
```

## 对比判读矩阵（关键）

| `rc-log-6.log` 的 `[DBGLOGITS]` | `[DBGNAN]` | 含义 | 结论 |
|---|---|---|---|
| `maxlogit=nan`（argmax=0，p_argmax=nan）| `emb_nan=0` | LLM 后端数值溢出 NaN，vision 正常 | **与 beta.1 同根因**（旧环境漏判）|
| `maxlogit` 正常，argmax=`_`，p_argmax≈1 | `emb_nan=0` | softmax 塌缩（非 NaN）| **beta.3 机制不同于 beta.1** |
| 任意 | `emb_nan=1` | vision encoder 输出 NaN | 根因在 vision（两环境都查）|

> `argmax=0 '!'` 是 NaN 的指纹：`x > NaN` 恒为 false，比较全部跳过，argmax 停在初始值 0。

## 诊断打印说明（commit 5859e35，env 开关默认关，不改推理数学）

| env | 位置 | 输出（到 stderr → cli_gpu0.log）|
|---|---|---|
| `OMNI_DEBUG_LOGITS=1` | `omni.cpp:sample_with_hidden_and_token` | 前 10 个生成 token 的 `n_past / argmax / maxlogit / p_argmax` |
| `OMNI_DEBUG_NAN=1` | `omni.cpp:prefill_with_emb` + `prefill_emb_with_hidden` | 每个 prefill batch 输入 embed 的 `n_past / n_elements / emb_nan`（vision→LLM 边界）|

## 复现红线（踩过的坑）

- **双 die device**：perf 必须 `ASCEND_RT_VISIBLE_DEVICES=0`（否则跑到 die1 崩 `aclnn_repeat_interleave`）；smoke 带 `CUDA_VISIBLE_DEVICES=0`。详见 `CLAUDE.md` 红线。
- **帧数控制**：必须**显式传** `max_num_frames`（`prepare_video_frames` 的该参数是默认参数，def 时绑定 64，monkey-patch 模块级 `MAX_NUM_FRAMES` 无效）。
- **每帧数独立 CLI 进程**：避免多帧退化污染 `shared_octx` 影响后续帧数（P7 已知）。
- **build-cann.sh 传 REPO 参**：`bash scripts/build-cann.sh "$PWD/code/llama.cpp-omni"`（默认 `$PWD/llama.cpp-omni` 不存在）。
- **aarch64 Python**：pandas3/pyarrow25/numpy2.5 段错误 → 降级 numpy1.26.4/pandas2.2.3/pyarrow16.1.0。

## 产物（新设备 beta.1 实测归档）

`/workspace/user_data/verify-ascend-2026-08-10/diag/`：`diag_frames.py` / `diag_rootcause.py` / `CONCLUSION.txt` / `diag.log`（1,2,4,8,16,32）/ `diag-fine.log`（5,6,7）/ `rc-log-5.log` / `rc-log-6.log`。

## 下一步（依 beta.3 复测结果）

- beta.3 也 NaN → 坐实"同一根因（LLM 后端 NaN），旧环境漏判"，邮件升级
- beta.3 塌缩非 NaN → beta.1/beta.3 机制不同，新设备 beta.1 反而多了 NaN bug，结论改写
