#!/bin/bash
# setup-tts-asv.sh - TTS-Seed ASV/SIM 评测的 WavLM-large 权重准备（评审环境复现用）
#
# 背景: evaluation/run_eval.py 的 ensure_s3prl_cache() 读 env WAVLM_LARGE_PT 指向本地 pt,
#       并 symlink 到 s3prl 缓存 (~/.cache/s3prl/download/<sha256(url)>.wavlm_large.pt)。
#       权重 1.2GB 不随提交包分发, 本脚本负责获取。
# 来源优先级: ① 同机已有副本 (benchmark/seed-tts-eval/sv/wavlm_large_s3prl.pt)
#             ② hf-mirror.com (国内镜像, 官方 URL 的镜像; HF 官方域名在本环境被封)
# 校验: 文件大小 >= 1.2GB (1,261,971,771 字节为已知好副本)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SV_DIR="$REPO_ROOT/benchmark/seed-tts-eval/sv"
PT="$SV_DIR/wavlm_large_s3prl.pt"
URL_HF="https://huggingface.co/s3prl/converted_ckpts/resolve/main/wavlm_large.pt"
URL_MIRROR="https://hf-mirror.com/s3prl/converted_ckpts/resolve/main/wavlm_large.pt"
MIN_BYTES=1200000000   # ~1.2GB

mkdir -p "$SV_DIR"

if [ -f "$PT" ] && [ "$(stat -c %s "$PT")" -gt "$MIN_BYTES" ]; then
    echo "[setup-tts-asv] 已有本地副本: $PT ($(du -h "$PT" | cut -f1))"
else
    echo "[setup-tts-asv] 本地无副本, 从 hf-mirror 下载 wavlm_large.pt ..."
    echo "  URL: $URL_MIRROR"
    if command -v wget >/dev/null; then
        wget -q --show-progress -O "$PT" "$URL_MIRROR"
    elif command -v curl >/dev/null; then
        curl -fL --progress-bar -o "$PT" "$URL_MIRROR"
    else
        echo "FATAL: 需要 wget 或 curl"; exit 1
    fi
    SIZE=$(stat -c %s "$PT" 2>/dev/null || echo 0)
    if [ "$SIZE" -lt "$MIN_BYTES" ]; then
        echo "FATAL: 下载文件异常 ($SIZE bytes < $MIN_BYTES). 镜像 URL 可能变更, 可手工从"
        echo "  $URL_HF"
        echo "  下载后放到 $PT"
        rm -f "$PT"; exit 1
    fi
    echo "[setup-tts-asv] 下载完成: $PT ($(du -h "$PT" | cut -f1))"
fi

# s3prl 缓存文件名 = sha256(官方URL).wavlm_large.pt (与 evaluation/run_eval.py S3PRL_WAVLM_URL 一致)
FNAME="$(python3 -c "import hashlib;print(hashlib.sha256(b'$URL_HF').hexdigest()+'.wavlm_large.pt')")"
DST="$HOME/.cache/s3prl/download/$FNAME"
mkdir -p "$(dirname "$DST")"
if [ -e "$DST" ] && [ ! -L "$DST" ]; then
    echo "[setup-tts-asv] s3prl 缓存已有实文件, 跳过"
elif [ -L "$DST" ]; then
    echo "[setup-tts-asv] s3prl 缓存已是符号链接, 跳过"
else
    ln -s "$(realpath "$PT")" "$DST"
    echo "[setup-tts-asv] 已链到 s3prl 缓存: $DST"
fi

echo "[setup-tts-asv] 完成。评测前请确保 env 设置:"
echo "  export WAVLM_LARGE_PT=$PT"
echo "  (并参照 benchmark/tts-seed-convert/run-tts.env 配置其余 TTS 评测环境)"