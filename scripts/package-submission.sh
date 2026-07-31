#!/bin/bash
# package-submission.sh - 生成比赛提交包（对齐官方提交清单）
# 用法: bash package-submission.sh [版本标签]
# 输出: dist/submission_<标签>_<日期>.tar.gz（不含权重，权重按官方规范单独提供）
# 命名规范：字母/数字/下划线/中划线（官方要求）
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${1:-v1}"
DATE="$(date +%Y%m%d)"
PKG_DIR="$REPO_ROOT/dist/submission_${TAG}_${DATE}"
PKG="submission_${TAG}_${DATE}.tar.gz"

rm -rf "$PKG_DIR"
mkdir -p "$PKG_DIR"/{code,scripts,benchmark_results,perf_report,demo,reproduce}

echo "[1/6] 代码与配置 → code/"
# 优化代码 = 官方框架 + 本地改动（patch 形式，避免携带 1G 源码）
if [ -d "$REPO_ROOT/code/llama.cpp-omni/.git" ]; then
    (cd "$REPO_ROOT/code/llama.cpp-omni" && \
     git diff > "$PKG_DIR/code/llama.cpp-omni.patch" 2>/dev/null || true)
fi
cp -r "$REPO_ROOT/code/llama.cpp-omni/tools/omni" "$PKG_DIR/code/omni-tools-ref" 2>/dev/null || true
# 关键配置（若有）
find "$REPO_ROOT/code/llama.cpp-omni" -maxdepth 2 -name "*.cmake" -o -maxdepth 2 -name "CMakeLists.txt" | head -0

echo "[2/6] 启动/测试脚本 → scripts/"
cp -r "$REPO_ROOT/scripts/"* "$PKG_DIR/scripts/" 2>/dev/null || true
# 服务启动脚本（llama-omni-server / gateway），有则拷
[ -f "$REPO_ROOT/code/MiniCPM-o-Demo/docker-compose.cpp.yml" ] && \
    cp "$REPO_ROOT/code/MiniCPM-o-Demo/docker-compose.cpp.yml" "$PKG_DIR/scripts/" 2>/dev/null || true

echo "[3/6] Benchmark 结果 → benchmark_results/"
[ -d "$REPO_ROOT/docs/perf-reports" ] && cp -r "$REPO_ROOT/docs/perf-reports" "$PKG_DIR/benchmark_results/" || true
# 三个官方 benchmark 的目录占位（910C 数据到位后填入）
for b in daily-omni tts-seed video-mme; do
    mkdir -p "$PKG_DIR/benchmark_results/$b"
done

echo "[4/6] 性能报告 → perf_report/"
[ -f "$REPO_ROOT/docs/performance-report.md" ] && \
    cp "$REPO_ROOT/docs/performance-report.md" "$PKG_DIR/perf_report/"
[ -f "$REPO_ROOT/docs/perf-reports/"*.md ] && cp "$REPO_ROOT/docs/perf-reports/"*.md "$PKG_DIR/perf_report/" 2>/dev/null || true

echo "[5/6] Demo → demo/（视频/说明）"
[ -f "$REPO_ROOT/docs/demo-guide.md" ] && cp "$REPO_ROOT/docs/demo-guide.md" "$PKG_DIR/demo/" || true

echo "[6/6] 复现说明 → reproduce/"
[ -f "$REPO_ROOT/docs/reproduce-guide.md" ] && \
    cp "$REPO_ROOT/docs/reproduce-guide.md" "$PKG_DIR/reproduce/"

# 生成清单
cat > "$PKG_DIR/README.txt" <<EOF
MiniCPM & 昇腾推理优化与应用创新挑战赛 - 赛道一 子赛道A (llama.cpp-omni)
提交版本: $TAG ($DATE)
目录说明:
  code/                 推理适配与性能优化代码（llama.cpp-omni.patch 为相对官方 master 的改动）
  scripts/              build-cann / sync-weights / capture-env / run_perf 等
  benchmark_results/    Daily-Omni / TTS-Seed / Video-MME 结果（命令+参数+原始输出+汇总）
  perf_report/          性能测试报告（RTF/环境/数据/次数/统计/前后对比/资源/异常）
  demo/                 Demo 使用说明 + 演示视频
  reproduce/            复现说明（瓶颈分析/优化方法/性能变化/效果保持/复现步骤/关键技术）
权重不随包提交，按官方规范另行提供。
EOF

cd "$REPO_ROOT/dist" && tar czf "$PKG" "submission_${TAG}_${DATE}" && rm -rf "submission_${TAG}_${DATE}"
echo "DONE: $REPO_ROOT/dist/$PKG ($(du -h "$REPO_ROOT/dist/$PKG" | cut -f1))"
