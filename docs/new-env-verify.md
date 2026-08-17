# 新环境验证清单（确定多帧退化是否 910B 硬件问题）

> 用途：在新环境（可能 910C，镜像完全匹配官方基线）跑对照实验，确定 VideoMME/Daily-Omni 多帧退化是否 910B 硬件特有。
> 创建：2026-08-10。前置：`docs/experiments.md` P3（910B3 CookBook 实证退化）、memory `910b-cann-gotchas` 第10条（ccec build）。

## 战略
镜像是完全匹配的 = **软件栈（CANN/依赖/代码）变量被隔离**。新环境硬件不同（910C）且多帧不退化 → 退化是 910B 硬件特有，一锤定音。这是确定"硬件 vs 软件"根因的唯一干净办法。

## 第一步：确认环境身份（对照前提，最关键）
```bash
npu-smi info                    # chip 型号 910B / 910C（最关键）
npu-smi info -t usages -i 0     # NPU 可用 + AICore/HBMbw
cat $ASCEND_TOOLKIT_HOME/version.cfg 2>/dev/null || ls /usr/local/Ascend/  # CANN 版本
```
→ 新环境**也是 910B** = 对照无意义（同硬件）；**910C** = 对照决定性。

## 第二步：同步代码 + 模型
```bash
git pull origin fix/video-extract-harden   # 含今天 4 commit（ccec + CookBook + P3 + 交接）
# 模型/数据：shared_assets 是否预置？
ls /workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/  # F16 16G + audio/vision/tts/token2wav 子目录
ls /workspace/shared_assets/datasets/lmms-lab/Video-MME/         # parquet + videos_chunked zip
```

## 第三步：ccec build（若镜像未含产物）
```bash
bash scripts/build-cann.sh   # 已固化 ccec（系统 gcc 12.3.1 编不了，见 memory 第10条）
# 产物：code/llama.cpp-omni/build-cann/bin/{llama-omni-cli,llama-omni-eval-cli,llama-omni-eval-daily-cli,...}
```

## 第四步：对照实验（CookBook videomme smoke_test，复刻 910B3）
```bash
cd benchmark/video-mme-cookbook
cp .env.example .env 2>/dev/null; vim .env   # 配 LLM_MODEL_PATH/VIDEO_DATA_DIR/PARQUET_PATH（本地路径）
# 解压 Video-MME 前 2 题 mp4（parquet videoID → zip → VIDEO_DATA_DIR/<videoID>.mp4）
source /workspace/venv-g23/bin/activate      # pandas/PIL/dotenv（decord aarch64 无，ffmpeg fallback）
python3 smoke_test.py 2
```

## 判断矩阵
| 新环境 smoke_test 结果 | 结论 | 动作 |
|---|---|---|
| ✅ 不退化（出 A/B/C/D，精度合理） | 退化是 **910B 硬件特有** → **实锤** | 邮件（organizer-inquiry-final.md）补实锤，求 910C 复测/豁免 |
| ❌ 也退化（输出 `_`） | 退化在**软件/代码层**（镜像同+退化同） | 改查 CANN/ggml-cann，非硬件 |

## 910B3 基线结果（对照基准）
videomme smoke_test 2 题：**0/2，输出 100 个 `_`**。CLI log 无 NaN/inf（logits 退化，非数值崩溃）。n_past 4538 / ctx 40960 无滑窗。详见 `docs/experiments.md` P3。

## 注意
- 新环境 venv 可能无 pandas/PIL/dotenv → `pip install pandas python-dotenv Pillow`（decord 无 wheel，走 ffmpeg/torchvision fallback）。
- ccec 在 `$ASCEND_TOOLKIT_HOME/tools/bisheng_compiler/bin/ccec`。
- 镜像若已含 build 产物，跳过第三步。
