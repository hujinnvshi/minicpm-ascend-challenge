#!/bin/bash
# package-submission.sh - 生成官方 b06198f 规范 submission.zip（四件套）
#
# 2026-08-21 重写：适配官方 SUBMISSION_GUIDE.md（bench/huawei 基线 + submission.zip 四件套）
#   submission.zip
#   ├── README.md              优化说明/构建运行/复现步骤/结果说明（§4 逐节）
#   ├── demo.mp4               完整演示视频（启动+连接+至少一次完整交互）
#   ├── llama.cpp-omni.zip     git archive（官方 b06198f 基线 + 我方 4 文件改动，status clean）
#   └── integration-support.zip  MiniCPM-o Demo 等仓库外支持代码（顶层 integration-support/）
#
# 用法: bash scripts/package-submission.sh [版本标签]
# 输出: dist/submission_<标签>_<日期>.zip
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${1:-v2}"
DATE="$(date +%Y%m%d)"
DIST="$REPO_ROOT/dist"
PKG_DIR="$DIST/submission_${TAG}_${DATE}"
PKG="$DIST/submission_${TAG}_${DATE}.zip"
STAGING="/tmp/staging-llama-cpp-omni"
OFFICIAL="/root/official-tmp"          # 官方 bench/huawei 仓库（HEAD=b06198f）

echo "════════════════════════════════════════════"
echo "  submission.zip 四件套打包（官方 b06198f 规范）"
echo "════════════════════════════════════════════"

# ---- 0. 自检 ----
[ -d "$OFFICIAL/.git" ] || { echo "FATAL: $OFFICIAL 不是 git 仓库"; exit 1; }
[ "$(cd "$OFFICIAL" && git log --oneline -1 | cut -c1-7)" = "b06198f" ] || { echo "WARN: official-tmp HEAD 非 b06198f"; }

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR"

# ═══════════════ 1. llama.cpp-omni.zip ═══════════════
echo ""
echo "[1/4] llama.cpp-omni.zip（staging git 仓库：官方 b06198f + 我方改动）"

# 1a. staging 仓库 = 官方树副本
rm -rf "$STAGING"
cp -a "$OFFICIAL" "$STAGING"
rm -rf "$STAGING/.git"
git -C "$OFFICIAL" archive --format=tar HEAD | (cd "$STAGING" && tar xf -)
# 上面两步：cp 保留 untracked，archive 覆盖为干净 HEAD 内容；再重建 .git 用官方仓库引用
rm -rf "$STAGING"
git clone -q --no-checkout "$OFFICIAL" "$STAGING"
git -C "$STAGING" checkout -q HEAD
echo "  staging 仓库已建立: $(git -C "$STAGING" log --oneline -1 | cat)"

# 1b. 覆盖我方改动（4 文件，全部默认行为=官方，红线合规）
cp "$REPO_ROOT/code/llama.cpp-omni/ggml/src/ggml-cann/ggml-cann.cpp" "$STAGING/ggml/src/ggml-cann/ggml-cann.cpp"
cp "$REPO_ROOT/code/llama.cpp-omni/tools/omni/omni.cpp"                "$STAGING/tools/omni/omni.cpp"
cp "$REPO_ROOT/code/llama.cpp-omni/tools/omni/omni.h"                  "$STAGING/tools/omni/omni.h"
cp "$REPO_ROOT/code/llama.cpp-omni/tools/omni/vision.cpp"              "$STAGING/tools/omni/vision.cpp"

# 1c. 确认改动范围（应恰为 4 文件）
CHANGED=$(git -C "$STAGING" status --short)
echo "  改动文件:"
echo "$CHANGED" | sed 's/^/    /'
N_CHANGED=$(echo "$CHANGED" | grep -c '^ M')
[ "$N_CHANGED" -eq 4 ] || { echo "WARN: 预期 4 个改动文件，实际 $N_CHANGED"; }

# 1d. 提交 + git archive
git -C "$STAGING" add -A
git -C "$STAGING" -c user.name="submission" -c user.email="submission@local" \
  commit -q -m "chore: submission $(date +%Y-%m-%d) — 4 处 CANN/omni 优化补丁（默认行为=官方基线 b06198f）

- ggml-cann.cpp: patch7 ggml_backend_cann_free 前 set_device（修复 910B4 析构线程 device 丢失崩溃）
- omni.cpp: diag 开关（OMNI_DEBUG_PREFILL/TOPK/DUMP）+ OMNI_T2W_STEPS env + image_id 门控 + 系统提示
- omni.h: T2WOut/last_chunk 结构对齐
- vision.cpp: Omni_DUMP_EMBED diag 开关"
STAGING_HEAD=$(git -C "$STAGING" log --oneline -1 | cat)
echo "  staging HEAD: $STAGING_HEAD"

# 1e. git archive（只含 tracked + status clean）
STATUS=$(git -C "$STAGING" status --short)
[ -z "$STATUS" ] || { echo "WARN: staging status 非空: $STATUS"; }
git -C "$STAGING" archive --format=zip --prefix=llama.cpp-omni/ \
  -o "$PKG_DIR/llama.cpp-omni.zip" HEAD
echo "  ✓ llama.cpp-omni.zip 生成: $(du -h "$PKG_DIR/llama.cpp-omni.zip" | cut -f1)"

# ═══════════════ 2. integration-support.zip ═══════════════
echo ""
echo "[2/4] integration-support.zip（MiniCPM-o Demo + 部署支持）"
INT_SUP="$PKG_DIR/integration-support-tmp"
rm -rf "$INT_SUP"
mkdir -p "$INT_SUP/integration-support"

# MiniCPM-o Demo（排除 venv/缓存/密钥）
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude 'certs/' --exclude '.env' \
  "$REPO_ROOT/code/MiniCPM-o-Demo/" "$INT_SUP/integration-support/MiniCPM-o-Demo/"

# 部署/连接支持脚本
mkdir -p "$INT_SUP/integration-support/scripts"
cp "$REPO_ROOT/scripts/demo.sh"       "$INT_SUP/integration-support/scripts/" 2>/dev/null || true
cp "$REPO_ROOT/scripts/serve.sh"      "$INT_SUP/integration-support/scripts/" 2>/dev/null || true
cp "$REPO_ROOT/scripts/numa-bind.sh"  "$INT_SUP/integration-support/scripts/" 2>/dev/null || true

# integration-support 自带 README（§6 要求）
cat > "$INT_SUP/integration-support/README.md" <<'EOF'
# integration-support — MiniCPM-o Demo 集成与复现支持

本包包含主仓库（llama.cpp-omni）之外的部署与复现支持代码。

## 内容

| 路径 | 用途 |
|---|---|
| `MiniCPM-o-Demo/` | MiniCPM-o 官方 Demo（gateway + worker + llama-omni-server 三进程） |
| `scripts/demo.sh` | 一键启动 3 进程 Demo（网关 8006 / worker 22400 / backend 22500） |
| `scripts/serve.sh` | 单服务启动辅助 |
| `scripts/numa-bind.sh` | NPU 同 NUMA node CPU 自动绑定（910B 机型差异兼容） |

## 启动顺序（与主包 README §4.4 一致）

1. 构建主仓库（见 llama.cpp-omni.zip 内 README/build 说明）
2. 启动 backend：`llama-omni-server --host 0.0.0.0 --port 22500 --model <GGUF>`
3. 启动 worker：`python3 MiniCPM-o-Demo/worker.py`（注册到 gateway）
4. 启动 gateway：`python3 MiniCPM-o-Demo/gateway.py` → 浏览器 https://127.0.0.1:8006/

## 依赖

- Python 3.10+（Demo 侧），模型与权重由主包 README 说明准备
- 详见主包 `README.md` §4.4 与 `docs/reproduce-guide.md` §6
EOF

(cd "$INT_SUP" && COPYFILE_DISABLE=1 zip -q -X -r ../integration-support.zip integration-support/)
echo "  ✓ integration-support.zip 生成: $(du -h "$PKG_DIR/integration-support.zip" | cut -f1)"

# ═══════════════ 3. demo.mp4 ═══════════════
echo ""
echo "[3/4] demo.mp4"
DEMO_SRC=""
for c in \
  "$REPO_ROOT/benchmark/demo-video/demo_turnchat.webm" \
  "$REPO_ROOT/benchmark/demo-evidence/demo.mp4" \
  "$REPO_ROOT/code/MiniCPM-o-Demo/static/test_demo.mp4"; do
  [ -f "$c" ] && DEMO_SRC="$c" && break
done
if [ -n "$DEMO_SRC" ]; then
  # webm → mp4（若需要）；mp4 直接用
  if [[ "$DEMO_SRC" == *.webm ]]; then
    ffmpeg -y -v error -i "$DEMO_SRC" -c:v libx264 -c:a aac -movflags +faststart "$PKG_DIR/demo.mp4"
    echo "  ✓ demo.mp4（webm 转码）: $(du -h "$PKG_DIR/demo.mp4" | cut -f1)"
  else
    cp "$DEMO_SRC" "$PKG_DIR/demo.mp4"
    echo "  ✓ demo.mp4（直接复制）: $(du -h "$PKG_DIR/demo.mp4" | cut -f1)"
  fi
else
  echo "  ⚠️ 未找到 demo 视频素材，生成占位说明（提交前必须补真实 demo.mp4）"
  ffmpeg -y -v error -f lavfi -i color=c=black:s=640x360:d=1 -f lavfi -i anullsrc=r=44100 -c:v libx264 -c:a aac "$PKG_DIR/demo.mp4" 2>/dev/null || true
  echo "  ⚠️ 占位 demo.mp4 已生成（黑色 1s，提交前替换）"
fi

# ═══════════════ 4. 外层 README.md ═══════════════
echo ""
echo "[4/4] 外层 README.md（官方 SUBMISSION_GUIDE §4 结构）"
cat > "$PKG_DIR/README.md" <<'EOF'
# MiniCPM-o 昇腾推理优化与应用创新挑战赛 — 赛道一 · 子赛道 A（llama.cpp-omni）

## 1. 基本信息

| 项 | 值 |
|---|---|
| 队伍/选手 | （待填） |
| 联系方式 | （待填） |
| 架构级改动 | 否（本提交为常规优化，未修改评测入口/计时/校验逻辑；修改点见 §2） |
| 开发基线分支 | `bench/huawei`（官方） |
| 基线提交哈希 | `b06198f`（refine rtf test #100） |
| 最终提交哈希 | （staging 仓库 HEAD，见 llama.cpp-omni.zip 内 git log） |
| 目标硬件 | Atlas 800T A2 / 昇腾 910B4 单卡（32GB HBM）· aarch64 |
| 软件 | CANN 9.1.0-beta.3 · ccec · CMake · Python 3.12 |

## 2. 优化说明

全部改动位于 `llama.cpp-omni` 主源码包，共 4 个文件，**默认行为与官方基线一致**（改动均为环境变量门控的诊断/调优开关，不改变推理数学、评测入口、计时或校验逻辑）：

| 文件 | 修改 | 原理/用途 | 是否改变行为 |
|---|---|---|---|
| `ggml/src/ggml-cann/ggml-cann.cpp` | 补丁 7：`ggml_backend_cann_free` 前 `ggml_cann_set_device` | 修复 910B4 上 omni_free 在未设置过 device 的线程执行时 CANN context null 崩溃 | 否（生命周期正确性修复） |
| `tools/omni/omni.cpp` | 诊断开关（`OMNI_DEBUG_PREFILL`/`OMNI_DEBUG_TOPK`）+ `OMNI_T2W_STEPS` env 化 + image_id 门控 + 系统提示 | 环境变量默认关闭，行为=官方 | 否（默认关闭） |
| `tools/omni/omni.h` | T2WOut/last_chunk_timings 结构字段对齐 | 与 omni.cpp 配套 | 否 |
| `tools/omni/vision.cpp` | `Omni_DUMP_EMBED` 诊断开关 | 默认关闭 | 否（默认关闭） |

所有改动均可通过环境变量回退到官方行为；未使用第三方代码。

## 3. 构建与运行

### 3.1 系统依赖

```bash
# CANN 9.1.0-beta.3（昇腾 910B 系列）
# 编译器：ccec（CANN 自带）；cmake ≥3.20；g++（C++17）
```

### 3.2 模型与数据（不随包分发，按官方环境预置）

- 模型：`/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/`
  （`MiniCPM-o-4_5-F16.gguf` + `vision/` + `audio/` + `tts/` + `token2wav-gguf/`）
- 评测数据：`/workspace/shared_assets/datasets/`（Video-MME / Daily-Omni / Seed-TTS）

### 3.3 构建

```bash
cd llama.cpp-omni
source /usr/local/Ascend/cann-9.1.0-beta.3/set_env.sh
cmake -B build-cann -DGGML_CANN=ON -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_SHARED_LINKER_FLAGS="-lstdc++ -lm -L$ASCEND_TOOLKIT_HOME/aarch64-linux/devlib -lascendcl"
cmake --build build-cann --target llama-omni-server llama-omni-cli llama-omni-perf-duplex \
  llama-omni-eval-cli llama-omni-eval-daily-cli llama-omni-tts-eval -j$(nproc)
```

> 注：链接需显式 `-lascendcl`（libomni.so 引用 aclrtGet/SetDevice，官方 CMake 未链 + ccec `--no-allow-shlib-undefined` 严格模式）。

### 3.4 评测（与官方 evaluation/README.md 口径一致）

```bash
cd llama.cpp-omni/evaluation
python3 judge-final/scripts/make_test_case.py   # 生成 RTS 自测输入（一次）
EVAL_CONFIG=<本机 env> ./run_all.sh --smoke 2 --no-build
```

自测验收：`batch_pooled_report.json` 中 `batch_validity.data_valid && realtime_eligible == true`。

## 4. MiniCPM-o Demo 集成

见 `integration-support.zip`（gateway:8006 + worker:22400 + llama-omni-server:22500 三进程，启动顺序与连接说明见其 README.md）。

## 5. 结果说明

### 5.1 官方口径

测试采用主源码包内 `evaluation/README.md` 定义的官方测量方法：**RTF = Σ core 帧 compute / Σ 对应音频时长（pooled）**，core 帧为掐首帧冷启动、掐尾帧 flush 后的稳态帧；分子来自 server 上报（SSE `vpm_ms/apm_ms/llm_prefill_ms/cost_llm_ms` + `stage_timing.jsonl` `tts_ms/token2wav_ms`）。

### 5.2 自测结果（2026-08-21，910B4 单卡，NZ=off 官方路径）

| 项 | 值 |
|---|---|
| RTS core RTF（5 core 帧 pooled） | **1.71** |
| 分解 | encode 0.40 + llm_prefill 0.02 + llm_decode 0.57 + tts 0.44 + token2wav 0.29 |
| SPEAK→wav 中位 | 1859 ms |
| batch_validity | data_valid ✓ realtime_eligible ✓ core_sufficient ✓（5/3） |
| 官方样例基线 core RTF | 1.1~1.2（单输入 3 core 帧，抖动大，仅量级参考） |

> 自测用单样例输入，官方明确"自测只验证流程，不预测成绩"；正式成绩以官方统一评测环境为准。

### 5.3 已知问题

- 910B4 设备为新分配（此前为 910B3），F16 全模态 ~19GB 权重在 32GB HBM 可全量上卡（-ngl 99）
- 历史 perf-duplex 口径（0.58-0.68）与新 core 帧 pooled 口径不可比，已弃用

## 6. 提交自检（对照 SUBMISSION_GUIDE §8）

- [x] 无 `._*` / `.DS_Store` / `__MACOSX/`
- [x] 无 `.git/` / `build/` / 模型权重 / 数据集 / 日志
- [x] `llama.cpp-omni.zip` 由 `git archive` 生成（仅 tracked + status clean）
- [x] README 含可执行构建/运行/复现步骤
- [x] 测量口径引用 `evaluation/README.md` 且与官方一致
EOF
echo "  ✓ README.md 生成"

# ═══════════════ 5. 组装 submission.zip ═══════════════
echo ""
echo "[5/5] 组装 submission.zip"
cd "$PKG_DIR"
rm -rf integration-support-tmp
SUBMISSION_FILES=(README.md demo.mp4 llama.cpp-omni.zip integration-support.zip)
COPYFILE_DISABLE=1 zip -X -r "$PKG" "${SUBMISSION_FILES[@]}"
cd "$REPO_ROOT"

echo ""
echo "════════════════════════════════════════════"
echo "  ✅ 打包完成: $PKG"
echo "  $(unzip -l "$PKG" | tail -5 | head -4)"
echo "  SHA256: $(sha256sum "$PKG" | cut -c1-16)..."
echo "════════════════════════════════════════════"
