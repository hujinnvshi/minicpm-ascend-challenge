#!/bin/bash
# package-submission.sh - 生成比赛提交包（对齐官方提交清单）
#
# 2026-08-14 重写（review-optimize 分支，修复评审发现的结构性缺陷）：
# 旧版问题：code/llama.cpp-omni 无独立 .git（外层 git 整树跟踪）→ git diff 恒为空 → 包里只有空 patch；
#           demo-guide.md 不存在 → demo/ 空包；benchmark 三项结果从未入包；dist/ 从未生成过。
# 新版策略：提交物 = 完整可构建源码目录（评审第 5 步要"能重跑"，patch 哲学不适用）
#         + 三项 benchmark 真实结果 + demo 证据 + perf 原始数据 + 权重准备脚本 + MANIFEST 校验。
#
# 用法: bash scripts/package-submission.sh [版本标签]
# 输出: dist/submission_<标签>_<日期>.tar.gz
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${1:-v1}"
DATE="$(date +%Y%m%d)"
PKG_DIR="$REPO_ROOT/dist/submission_${TAG}_${DATE}"
PKG="submission_${TAG}_${DATE}.tar.gz"

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR"/{code,scripts,benchmark,docs,perf_report,demo,weights}

LLAMA="$REPO_ROOT/code/llama.cpp-omni"

echo "[1/7] 完整可构建源码 → code/llama.cpp-omni/（排除 build 产物/权重/运行输出）"
if [ ! -d "$LLAMA" ]; then echo "FATAL: $LLAMA 不存在"; exit 1; fi
rsync -a \
  --exclude 'build' --exclude 'build-cann' --exclude 'build-huawei' \
  --exclude 'cmake-build-*' --exclude '*.safetensors' \
  --exclude 'bin/' --exclude 'obj/' \
  --exclude 'CMakeFiles/' --exclude 'CMakeCache.txt' --exclude 'CTestTestfile.cmake' \
  --exclude 'DartConfiguration.tcl' --exclude 'cmake_install.cmake' \
  --exclude 'tools/omni/output/' --exclude 'tools/omni/logs/' \
  --exclude 'evaluation/output/' --exclude 'evaluation/appendix/' \
  --exclude 'evaluation/*/__pycache__/' --exclude 'evaluation/*/log/' \
  --exclude 'evaluation/tts_seed/eval_results/' --exclude '*.bak' \
  --exclude 'evaluation/judge-final/sessions/20*' --exclude 'evaluation/config.local.env' \
  "$LLAMA/" "$PKG_DIR/code/llama.cpp-omni/"
# 记录评测用 binary 版本信息（评审重跑时对照）
BIN_VER=""
for b in build/bin/llama-omni-eval-cli build-cann/bin/llama-omni-eval-cli; do
  [ -f "$LLAMA/$b" ] && BIN_VER="$BIN_VER$b: $(stat -c '%y' "$LLAMA/$b")\n"
done
printf "$BIN_VER" > "$PKG_DIR/code/BINARIES_META.txt" || true
# 补丁说明（相对官方 bench/huawei 分支的改动点，评审人工核对用）
cp "$REPO_ROOT/docs/cann-patches.md" "$PKG_DIR/code/"

echo "[2/7] 脚本 → scripts/"
cp -r "$REPO_ROOT/scripts/." "$PKG_DIR/scripts/"

echo "[3/7] Benchmark 结果 → benchmark/（三项真实结果 + 转换/评测脚本）"
mkdir -p "$PKG_DIR/benchmark"
# Daily-Omni：结果 json + 转换脚本（数据 2.7GB 不入包，由顶层 README 指引从 shared_assets 转换）
rsync -a --exclude 'daily-omni-data/' --exclude '__pycache__' \
  "$REPO_ROOT/benchmark/daily-omni/" "$PKG_DIR/benchmark/daily-omni/"
rsync -a --exclude '__pycache__' \
  "$REPO_ROOT/benchmark/daily-omni-convert/" "$PKG_DIR/benchmark/daily-omni-convert/"
# TTS-Seed：结果 json + 转换/eval 脚本；wavlm 1.2GB 不入包（scripts/setup-tts-asv.sh 从 hf-mirror 拉）
rsync -a --exclude 'seedtts_testset/' --exclude 'sv/wavlm_large_s3prl.pt' --exclude 'sv/wavlm-large/' --exclude '__pycache__' \
  "$REPO_ROOT/benchmark/seed-tts-eval/" "$PKG_DIR/benchmark/seed-tts-eval/"
rsync -a --exclude '__pycache__' \
  "$REPO_ROOT/benchmark/tts-seed-convert/" "$PKG_DIR/benchmark/tts-seed-convert/"
# Video-MME：cookbook 全套（官方 pipeline 适配 + 99q 子集数据 + 诊断/日志；33 视频不入包由 setup 脚本解压）
rsync -a --exclude '__pycache__' --exclude 'videomme99_data/' --exclude 'videomme_domain180_data/' \
  "$REPO_ROOT/benchmark/video-mme-cookbook/" "$PKG_DIR/benchmark/video-mme-cookbook/"

echo "[4/7] 性能报告 → perf_report/（报告 + 原始 JSON + 量化探索证据）"
cp "$REPO_ROOT/docs/performance-report.md" "$PKG_DIR/perf_report/"
[ -d "$REPO_ROOT/docs/perf-reports" ] && rsync -a "$REPO_ROOT/docs/perf-reports/" "$PKG_DIR/perf_report/perf-reports/"
# perf 原始数据（gitignored 的运行产物，评审可复核 RTF 口径）
mkdir -p "$PKG_DIR/perf_report/raw"
if [ -d "$LLAMA/tools/omni/output" ]; then
  cp "$LLAMA"/tools/omni/output/perf_p8_*.json "$PKG_DIR/perf_report/raw/" 2>/dev/null || true
  cp "$LLAMA"/tools/omni/output/perf_t24_*.json "$PKG_DIR/perf_report/raw/" 2>/dev/null || true
  cp "$LLAMA"/tools/omni/output/perf_node6_r*.json "$PKG_DIR/perf_report/raw/" 2>/dev/null || true
  cp "$LLAMA"/tools/omni/output/*.analyze "$PKG_DIR/perf_report/raw/" 2>/dev/null || true
fi
[ -f "$REPO_ROOT/scripts/verify_rtf.py" ] && cp "$REPO_ROOT/scripts/verify_rtf.py" "$PKG_DIR/perf_report/raw/"
[ -f "$LLAMA/tools/omni/perf/analyze_perf.py" ] && cp "$LLAMA/tools/omni/perf/analyze_perf.py" "$PKG_DIR/perf_report/raw/"

echo "[5/7] Demo → demo/（运行证据 + 视频）"
rsync -a "$REPO_ROOT/benchmark/demo-evidence/" "$PKG_DIR/demo/demo-evidence/"
[ -f "$REPO_ROOT/benchmark/demo-video/demo_turnchat.webm" ] && cp "$REPO_ROOT/benchmark/demo-video/demo_turnchat.webm" "$PKG_DIR/demo/"
[ -f "$REPO_ROOT/benchmark/demo-video/final_chat.png" ] && cp "$REPO_ROOT/benchmark/demo-video/final_chat.png" "$PKG_DIR/demo/"

echo "[6/7] 文档 → docs/（复现/实验/决策/评测规范全量）"
rsync -a --exclude '.secrets.local' "$REPO_ROOT/docs/" "$PKG_DIR/docs/"
# 3 进程 Demo 启动说明（原 docs/demo-guide.md 不存在，用 reproduce-guide §6 + demo.sh 顶替，见 README）

echo "[7/7] 权重准备脚本 → weights/（评审环境拉取指引，模型/权重不随包）"
cat > "$PKG_DIR/weights/README.md" <<'EOF'
# 权重准备（评审环境）
模型与评测权重不随提交包分发（体积大），按官方评测环境预置 + 以下脚本补齐：

1. MiniCPM-o-4_5 GGUF（只读预置，官方环境已有）：
   /workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/
   (LLM MiniCPM-o-4_5-F16.gguf + vision/audio/tts/projector + token2wav-gguf/)
2. TTS-Seed ASV 依赖（WavLM-large 预训练权重，s3prl 格式）：
   运行 scripts/setup-tts-asv.sh —— 从 hf-mirror 拉取并写入 s3prl 缓存
   （wavlm_large_s3prl.pt 1.2GB；本机已下载副本: benchmark/seed-tts-eval/sv/）
3. Video-MME 视频（99q 子集 33 个 mp4 + 全量 2700 视频）：
   scripts/setup-videomme-videos.py —— 从官方 videos_chunked_*.zip 解压
   （官方数据集预置: /workspace/shared_assets/datasets/lmms-lab/Video-MME/）
4. Daily-Omni 数据转换：benchmark/daily-omni-convert/convert.py
   （parquet 预置: /workspace/shared_assets/datasets/MTEB/Daily-Omni/）
EOF
cp "$REPO_ROOT/scripts/setup-tts-asv.sh" "$PKG_DIR/weights/" 2>/dev/null || true

# ---- 顶层 README（使用说明 + 清单核对） ----
cat > "$PKG_DIR/README.txt" <<EOF
MiniCPM & 昇腾推理优化与应用创新挑战赛 - 赛道一 子赛道A (llama.cpp-omni)
提交版本: $TAG ($DATE)  |  生成: review-optimize 分支新打包流程

目录说明:
  code/llama.cpp-omni/   完整可构建源码（6 CANN 补丁 + P1.7 队列解耦 + P3/P4 vocoder/NUMA
                         + 协议对齐 OMNI_IMAGE_ID/TEXT_CHAT_SYS 门控）
                         ★ 与官方 llama.cpp-omni 的差异逐条见 code/cann-patches.md
  code/BINARIES_META.txt 评测用 binary 时间戳（对照重跑）
  scripts/               build-cann.sh / serve.sh / demo.sh / benchmark.sh / verify_rtf.py / 权重 setup
  benchmark/             三项精度 Benchmark（结果 json + 转换/评测脚本 + 99q 子集数据）
  perf_report/           性能报告 + 原始 perf JSON + 量化探索证据 + analyze_perf.py
  demo/                  Demo 运行证据（8 项检查 + 多轮截图 + 演示视频 demo_turnchat.webm）
  docs/                  复现/实验/决策/评测规范全量文档
  weights/               权重准备指引（评审环境从预置+脚本补齐）

构建与复现（详细见 docs/reproduce-guide.md）:
  1) bash scripts/build-cann.sh            # ccec 构建（GGML_CANN=ON, 6 补丁自动说明见 code/cann-patches.md）
  2) 性能: 见 docs/reproduce-guide.md §4   # SPEAK→WAV RTF <1.087（实测 0.58-0.59, 基线 1.087）
     ★ NUMA 绑核必须先查: cat /sys/bus/pci/devices/<NPU_bus>/numa_node 再绑该 node（勿照抄核号）
  3) 精度: 见 docs/{daily-omni-eval,tts-seed-eval,videomme-baseline-clarification}.md
  4) Demo: bash scripts/demo.sh (3 进程 gateway/worker/backend, https://127.0.0.1:8006/)

关键实测数字（2026-08-14/15 口径）:
  性能 RTF: 0.58-0.59（24 vocoder 线程 + NUMA 同 node; 默认 16 线程 0.68-0.69）
  Daily-Omni: 79.8% (全量 1196 题; 基线 79.5)
  TTS-Seed: WER 1.501% (基线 1.414) / ASV 0.694 (基线 0.709)
  Video-MME: 51.5-53.5% (99q KB 域) / 270 题合池 63.3%±5.7pp (NZ=off; 官方基线 69.0 全量口径待赛方澄清)

🔴 评测纪律（必读）:
  精度评测必须走官方 run_all.sh 路径（GGML_CANN_WEIGHT_NZ=off 自动注入）;
  任何直跑必须显式 export GGML_CANN_WEIGHT_NZ=off（ggml-cann 默认 on, NZ=on 会致
  空串/换行复读等异常输出, 直跑数据作废——详见 docs/nz-pollution-impact.md）。
  NUMA 绑核必须按机器探测: scripts/numa-bind.sh（勿照抄核号）。
EOF

# ---- MANIFEST（评审校验: 文件清单 + 大小 + sha256） ----
(cd "$PKG_DIR" && find . -type f | sort | while read -r f; do
  printf "%s\t%s\t%s\n" "$(du -h "$f" | cut -f1)" "$(sha256sum "$f" | cut -d' ' -f1)" "$f"
done > MANIFEST.txt)
echo "  MANIFEST: $(wc -l < "$PKG_DIR/MANIFEST.txt") files"

cd "$REPO_ROOT/dist" && tar czf "$PKG" "submission_${TAG}_${DATE}" && rm -rf "submission_${TAG}_${DATE}"
echo "DONE: $REPO_ROOT/dist/$PKG ($(du -h "$REPO_ROOT/dist/$PKG" | cut -f1))"
echo "校验: tar tzf $REPO_ROOT/dist/$PKG | head -5"