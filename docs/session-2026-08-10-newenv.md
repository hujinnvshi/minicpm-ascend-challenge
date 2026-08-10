# 会话交接 2026-08-10 新设备验证（910B / CANN beta.1）

> 新分配设备的赛事核心验证结论。与 `session-2026-08-10.md`（旧环境 beta.3）配套读。
> 验证产物全在 `/workspace/user_data/verify-ascend-2026-08-10/`（stage0-5，46 文件）。
> 对应 git tag：`verify-ascend-910B-cann-beta1-20260810`（在 `2a8c2d2`）。

## 环境（新设备，与旧环境三处关键差异）

| 项 | 新设备 | 旧环境(beta.3) |
|---|---|---|
| NPU | Ascend910, npu-smi id=**5**, 双die各64G (PCI 0xD803) | 910B3, id=1, PCI 0xD802 |
| CANN | **9.1.0-beta.1** | 9.1.0-beta.3 |
| Python venv | **`/workspace/user_data/venv-omni`**（自建；旧 venv-g23 不存在） | `/workspace/venv-g23`（预置） |
| 项目根 | `/workspace/user_data/claude_code/minicpm-ascend-challenge` | `/workspace/user_data/temp_project/...` |
| git | HEAD `2a8c2d2` (fix/video-extract-harden), 工作树干净 | 同分支 |

资产就绪：F16 权重 + 子模块 + 三项数据集 + ccec/atc/cmake/python3.12.13 全在；640核/2TB/300G。

## 两个关键发现（容器重建后必读）

### 1. 双die device 锁定（最重要 gotcha）
- 双 die 被 CANN 枚举为 **device0 + device1**（`aclrtGetDeviceCount=2`）。
- **dev1（die1）不可单独用**：perf-duplex 双工流水线会跑到 dev1，在 `aclnn_repeat_interleave`（RoPE sin/cos 用，`aclnn_ops.cpp:2837/2838`）崩溃 `exit 139`（`Can not find kernel`，kernel_name 空）。
- **解法**：跑 perf/duplex 前 **必须** `export ASCEND_RT_VISIBLE_DEVICES=0 CUDA_VISIBLE_DEVICES=0`（→ `aclrtGetDeviceCount=1`，只看 die0）。
- smoke（eval-cli, `use_tts=false`）默认走 dev0 不受影响，但建议都加。
- 设备号二元区分：`npu-smi` 查询用 `-i 5`（物理 id）；binary / `CUDA_VISIBLE_DEVICES` 用 `0`（逻辑 dev0 = die0 = NPU5）。

### 2. aarch64 Python 依赖降级
- pandas 3.0 / pyarrow 25 / numpy 2.5（pip 默认最新）在 aarch64 **段错误**（读 parquet 时 SIGSEGV 139）。
- **降级到 numpy 1.26.4 / pandas 2.2.3 / pyarrow 16.1.0**（venv-omni 已 freeze 到 `stage1/requirements-frozen.txt`）。
- decord 无 aarch64 wheel，不装（video_prep 自动 fallback `/usr/bin/ffmpeg`）。

## 验证结果

### build ✅
ccec 编译成功（4m14s），3 binary 齐：`llama-omni-cli` / `llama-omni-eval-cli` / `llama-omni-perf-duplex`。
sha256 + 备份：`/workspace/user_data/verify-ascend-2026-08-10/stage2/build-cann-bin/`。
build 命令注意：`bash scripts/build-cann.sh "$PWD/code/llama.cpp-omni"`（**必须传 REPO 参**，默认 `$PWD/llama.cpp-omni` 不存在）+ `cmake --build ... --target llama-omni-eval-cli`（脚本只构 cli+perf-duplex）。

### 性能 RTF ✅ 达标
锁 dev0 连跑 3 次：

| run | TTS RTF（官方口径） | e2e RTF |
|---|---|---|
| 1 | 0.49 | 0.50 |
| 2 | 0.52 | 0.52 |
| 3 | 0.53 | 0.54 |
| **中位** | **0.52** | **0.52** |

**中位 TTS RTF = 0.52**，远低于官方基线 1.087（优于旧环境 0.57-0.83）。
首响 e2e 1072ms > 1000ms（perf 双工门槛 FAIL，**非官方排名指标**）。

### Video-MME smoke → 判定矩阵【情形B】
beta.1 下 `0/2`，输出 100 个 `_`，与旧环境 beta.3 P3 基线**完全一致**（条件对齐：ctx 40960 / 64帧@1fps / temp 0.2 / n_predict 100 / backend=ffmpeg / dev0）。
→ **多帧退化跨 beta.1 & beta.3 持续，非 CANN 版本差异**，是 910B/CANN 后端多步 prefill 数值稳定性问题。
（原对照目标"910B vs 910C"未达成——本机也是 910B；但 beta.1 对照给出等价结论：非 CANN 小版本。）

## 判定矩阵 → 情形B
- 退化跨 beta.1&beta.3 持续；非硬件（本机亦 910B）；非 CANN 小版本。
- 下一步：① 邮件升级（**beta.1 也退化 = 新证据**）求豁免 / 求 910C 复测；② 单帧口径作可交付（stack=1 预期正常）；③ 不再追多帧（ROI 低，超红线）。

## 关键命令（新设备专用）
```bash
REPO=/workspace/user_data/claude_code/minicpm-ascend-challenge
VENV=/workspace/user_data/venv-omni
MODEL=/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf
LLAMA=$REPO/code/llama.cpp-omni
source $VENV/bin/activate

# build（传 REPO 参 + 补 eval-cli）
bash $REPO/scripts/build-cann.sh "$REPO/code/llama.cpp-omni"
cmake --build $LLAMA/build-cann --target llama-omni-eval-cli -j$(nproc)

# perf RTF（⚠️ 必须锁 dev0！）
ASCEND_RT_VISIBLE_DEVICES=0 CUDA_VISIBLE_DEVICES=0 \
  $LLAMA/build-cann/bin/llama-omni-perf-duplex -m "$MODEL" -c 4096 -ngl 99 \
  --ref-audio $LLAMA/tools/omni/assets/default_ref_audio/default_ref_audio.wav \
  --test $LLAMA/tools/omni/assets/test_case/duplex_omni_test_case/duplex_omni_test_case_ 36 \
  -o $LLAMA/tools/omni/output --out-json /tmp/perf.json
python3 $LLAMA/tools/omni/perf/analyze_perf.py /tmp/perf.json --interval-ms 1000

# smoke（device0，use_tts=false 不触 dev1）
cd $REPO/benchmark/video-mme-cookbook && CUDA_VISIBLE_DEVICES=0 python3 smoke_test.py 2

# NPU 监测（物理 id=5）
npu-smi info -t usages -i 5
```

## 回滚 / 可追溯
- git 工作树未改源码（HEAD `2a8c2d2`），任一步可回滚；binary 备份在 `stage2/build-cann-bin/`（容器重建后 `cp -a` 恢复免重 build）；venv 可 `rm -rf` 重建（`requirements-frozen.txt`）。
- 全部产物（stage0-5，46 文件）+ SUMMARY 在 `/workspace/user_data/verify-ascend-2026-08-10/`。
