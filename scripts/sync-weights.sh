#!/bin/bash
# sync-weights.sh - 权重同步脚本（secs → 910C）
# 用法:
#   bash sync-weights.sh pull-on-910C        # 在 910C 上从 ModelScope 直拉【首选】
#   bash sync-weights.sh push <user@host>    # SSH 直连可用时 secs 推送（官方 QA 确认支持 ssh user@<IP>）
# 路径说明（官方 QA 2026-08-01 确认）:
#   user_data: /home/ma-user/work/user_data/（持久化挂载目录）
#   shared_assets: 官方共享空间（重要数据建议双备份）
# 权重路径: /data/minicpm-omni/weights/MiniCPM-o-4_5-gguf/

SRC="/data/minicpm-omni/weights/MiniCPM-o-4_5-gguf"
MS_BASE="https://modelscope.cn/models/openbmb/MiniCPM-o-4_5-gguf/resolve/master"

# 最小跑通集（Q4_K_M + 全模块）
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

push() {
    local target="$1"
    [ -n "$target" ] || { echo "用法: sync-weights.sh push <user@host>"; exit 1; }
    echo "rsync $SRC → $target:/user_data/MiniCPM-o-4_5-gguf/"
    rsync -avP --partial "$SRC/" "$target:/user_data/MiniCPM-o-4_5-gguf/"
    echo "DONE"
}

pull_on_910c() {
    echo "910C 上直拉 ModelScope（首选路径）"
    mkdir -p /home/ma-user/work/user_data/MiniCPM-o-4_5-gguf
    cd /home/ma-user/work/user_data/MiniCPM-o-4_5-gguf
    for f in "${FILES[@]}"; do
        mkdir -p "$(dirname "$f")"
        [ -f "$f" ] && [ "$(stat -c%s "$f" 2>/dev/null || echo 0)" -gt 1000000 ] && { echo "SKIP $f"; continue; }
        wget -c -q "$MS_BASE/$f" -O "$f.tmp" && mv "$f.tmp" "$f" && echo "OK $f" || echo "FAIL $f"
    done
    echo "DONE"
}

case "${1:-}" in
    push) push "${2:-}" ;;
    pull-on-910C) pull_on_910c ;;
    *) echo "用法: $0 push <user@host> | pull-on-910C" ;;
esac
