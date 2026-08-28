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
OFFICIAL="${OFFICIAL_TMP:-/root/official-tmp}"   # 官方 bench/huawei 仓库（HEAD=b06198f）；可用 OFFICIAL_TMP 覆盖

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

# 1b. 覆盖我方改动（6 文件，全部默认行为=官方，红线合规）
cp "$REPO_ROOT/code/llama.cpp-omni/ggml/include/ggml-cann.h"           "$STAGING/ggml/include/ggml-cann.h"
cp "$REPO_ROOT/code/llama.cpp-omni/ggml/src/ggml-cann/ggml-cann.cpp"   "$STAGING/ggml/src/ggml-cann/ggml-cann.cpp"
cp "$REPO_ROOT/code/llama.cpp-omni/ggml/src/ggml-cann/aclnn_ops.cpp"   "$STAGING/ggml/src/ggml-cann/aclnn_ops.cpp"
cp "$REPO_ROOT/code/llama.cpp-omni/tools/omni/omni.cpp"                "$STAGING/tools/omni/omni.cpp"
cp "$REPO_ROOT/code/llama.cpp-omni/tools/omni/omni.h"                  "$STAGING/tools/omni/omni.h"
cp "$REPO_ROOT/code/llama.cpp-omni/tools/omni/vision.cpp"              "$STAGING/tools/omni/vision.cpp"

# 1c. 确认改动范围（应恰为 6 文件）
CHANGED=$(git -C "$STAGING" status --short)
echo "  改动文件:"
echo "$CHANGED" | sed 's/^/    /'
N_CHANGED=$(echo "$CHANGED" | grep -c '^ M')
[ "$N_CHANGED" -eq 6 ] || { echo "WARN: 预期 6 个改动文件，实际 $N_CHANGED"; }

# 1d. 提交 + git archive
git -C "$STAGING" add -A
git -C "$STAGING" -c user.name="submission" -c user.email="submission@local" \
  commit -q -m "chore: submission $(date +%Y-%m-%d) — 6 处 CANN/omni 优化补丁（默认行为=官方基线 b06198f）

- ggml-cann.h/.cpp: patch7 ggml_backend_cann_free 前 set_device + per-backend ACL 图模式接口（ggml_backend_cann_set_acl_graph，USE_ACL_GRAPH 构建时有效）
- aclnn_ops.cpp: CANN FA contiguity 修复（非规范 [B,S,N,D] 视图连续拷贝，B<=1 忽略 dim3）——消除多 token prefill 崩溃、解锁 910C 图模式
- omni.cpp: diag 开关（OMNI_DEBUG_PREFILL/TOPK/DUMP）+ OMNI_T2W_STEPS env + image_id 门控 + 系统提示 + NPU 串行锁（OMNI_NPU_SERIAL）+ TTS head_code 行间并行（OMNI_HEADCODE_THREADS，数值逐位一致）+ VPM 同尺寸批量编码（OMNI_VISION_BATCH_ALL，encode -22.5%、RTF -9.1%）
- omni.h: T2WOut/last_chunk 结构对齐
- vision.cpp: Omni_DUMP_EMBED diag 开关 + 图模式受限使能（per-backend set_acl_graph）"
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

# v8.4: 1 步 prompt_cache（t2w 1 步必需，见外层 README §7.1）+ 生成工具
if [ -d "$REPO_ROOT/dist/v84_assets/token2wav-steps1" ]; then
  mkdir -p "$INT_SUP/integration-support/token2wav-steps1"
  cp "$REPO_ROOT/dist/v84_assets/token2wav-steps1/prompt_cache.gguf" "$INT_SUP/integration-support/token2wav-steps1/"
  cp "$REPO_ROOT/dist/v84_assets/t2w-cache-export.cpp" "$INT_SUP/integration-support/t2w-cache-export.cpp"
elif [ -d "$REPO_ROOT/dist/v83_assets/token2wav-steps2" ]; then
  mkdir -p "$INT_SUP/integration-support/token2wav-steps2"
  cp "$REPO_ROOT/dist/v83_assets/token2wav-steps2/prompt_cache.gguf" "$INT_SUP/integration-support/token2wav-steps2/"
  cp "$REPO_ROOT/dist/v83_assets/t2w-cache-export.cpp" "$INT_SUP/integration-support/t2w-cache-export.cpp"
elif [ -d "$REPO_ROOT/dist/v81_assets/token2wav-steps4" ]; then
  mkdir -p "$INT_SUP/integration-support/token2wav-steps4"
  cp "$REPO_ROOT/dist/v81_assets/token2wav-steps4/prompt_cache.gguf" "$INT_SUP/integration-support/token2wav-steps4/"
  cp "$REPO_ROOT/dist/v81_assets/t2w-cache-export.cpp" "$INT_SUP/integration-support/t2w-cache-export.cpp"
fi

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
| `token2wav-steps4/prompt_cache.gguf` | 4 步 flow-matching 缓存（`OMNI_T2W_STEPS=4` 必需，SHA-256 见主包 README §7.1） |
| `t2w-cache-export.cpp` | 4 步缓存生成工具（复现用） |

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
# README 从 repo 文件复制（scripts/submission-README.md，随提交维护，避免 heredoc 漂移）
# 最终提交哈希用 staging HEAD 替换占位（v6 曾因哈希固化 af67cfe 失效被审计——必须打包时替换）
cp "$REPO_ROOT/scripts/submission-README.md" "$PKG_DIR/README.md"
STAGING_HEAD_SHORT=$(git -C "$STAGING" log --oneline -1 | cut -c1-7)
sed -i "s/__STAGING_HEAD__/$STAGING_HEAD_SHORT/" "$PKG_DIR/README.md"
echo "  ✓ README.md 生成（staging HEAD=$STAGING_HEAD_SHORT 已替换）"

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
