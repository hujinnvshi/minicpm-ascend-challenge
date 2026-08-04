#!/bin/bash
# sync-weights.sh - 权重准备脚本（910B3 云环境，2026-08-04 修订）
# 用法:
#   bash sync-weights.sh use-shared       # 【首选】打印官方预置权重只读路径，免下载
#   bash sync-weights.sh pull             # 从 ModelScope 下载到 /workspace/user_data（仅 shared_assets 不可用时）
#   bash sync-weights.sh push <user@host> # SSH 直连可用时从外部推送
#
# 路径说明（2026-08-04 实测确认，见 docs/env-scan.md）:
#   持久化挂载: /workspace/user_data（读写，glusterfs 35T）
#   官方预置(只读): /workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/（全套 11 档+全模块）
#   ⚠️ 旧文档里的 /home/ma-user/work/user_data/ 已废弃，实际为 /workspace/user_data

# 官方预置权重（只读，文件命名与下方 FILES 一致，llama-omni-cli -m 直接指向即可）
SHARED_GGUF="/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf"
# 本地下载落点（仅 pull/push 模式用到）
LOCAL_GGUF="/workspace/user_data/MiniCPM-o-4_5-gguf"
MS_BASE="https://modelscope.cn/models/openbmb/MiniCPM-o-4_5-gguf/resolve/master"

# 最小跑通集（Q4_K_M + Q8_0 + 全模块）
# 注：shared_assets 另有 F16/Q6_K/Q5_K_M/Q5_K_S/Q5_1/Q5_0/Q4_K_S/Q4_1/Q4_0 共 11 档
FILES=(
  "MiniCPM-o-4_5-Q4_K_M.gguf"
  "MiniCPM-o-4_5-Q8_0.gguf"
  "audio/MiniCPM-o-4_5-audio-F16.gguf"
  "tts/MiniCPM-o-4_5-tts-F16.gguf"
  "tts/MiniCPM-o-4_5-projector-F16.gguf"
  "token2wav-gguf/encoder.gguf"
  "token2wav-gguf/flow_matching.gguf"
  "token2wav-gguf/flow_extra.gguf"
  "token2wav-gguf/hifigan2.gguf"
  "token2wav-gguf/prompt_cache.gguf"
  "vision/MiniCPM-o-4_5-vision-F16.gguf"
)

use_shared() {
    echo "【首选】官方预置权重（只读，直接用，免下载）"
    if [ -f "$SHARED_GGUF/MiniCPM-o-4_5-Q4_K_M.gguf" ]; then
        echo "  路径: $SHARED_GGUF"
        echo "  可用 LLM 量化档:"
        ls "$SHARED_GGUF"/MiniCPM-o-4_5-*.gguf 2>/dev/null | xargs -n1 basename 2>/dev/null | sed 's/^/    /'
        echo "  全模块: audio/ tts/ vision/ token2wav-gguf/ ✔"
        echo ""
        echo "  用法示例:"
        echo "    llama-omni-cli -m $SHARED_GGUF/MiniCPM-o-4_5-Q4_K_M.gguf -ngl 99 -c 8192 ..."
        echo "  注: 该路径只读，无需复制；如需可写副本: cp -rl $SHARED_GGUF $LOCAL_GGUF"
    else
        echo "  ERROR: 预置权重不在 $SHARED_GGUF，改用 pull 模式下载"
        exit 1
    fi
}

pull() {
    echo "从 ModelScope 下载到 $LOCAL_GGUF（仅 shared_assets 不可用时）"
    mkdir -p "$LOCAL_GGUF"
    cd "$LOCAL_GGUF"
    for f in "${FILES[@]}"; do
        mkdir -p "$(dirname "$f")"
        [ -f "$f" ] && [ "$(stat -c%s "$f" 2>/dev/null || echo 0)" -gt 1000000 ] && { echo "SKIP $f"; continue; }
        wget -c -q "$MS_BASE/$f" -O "$f.tmp" && mv "$f.tmp" "$f" && echo "OK $f" || echo "FAIL $f"
    done
    echo "DONE: $LOCAL_GGUF"
}

push() {
    local target="$1"
    [ -n "$target" ] || { echo "用法: sync-weights.sh push <user@host>"; exit 1; }
    echo "rsync $LOCAL_GGUF → $target:$LOCAL_GGUF/"
    rsync -avP --partial "$LOCAL_GGUF/" "$target:$LOCAL_GGUF/"
    echo "DONE"
}

case "${1:-}" in
    use-shared) use_shared ;;
    pull) pull ;;
    push) push "${2:-}" ;;
    *) echo "用法: $0 use-shared | pull | push <user@host>"
       echo "  首选 use-shared（官方预置权重，免下载）" ;;
esac
