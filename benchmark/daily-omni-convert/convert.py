#!/usr/bin/env python3
"""
Daily-Omni parquet → 官方评测 jsonl + 独立音视频文件 转换脚本。

输入: shared_assets/datasets/MTEB/Daily-Omni/data/test-*.parquet (10 分片, 音视频内嵌)
输出: {DATASET_DIR}/daily_omni.jsonl + {DATASET_DIR}/{video_id}_video.mp4/.wav

字段映射 (官方 evaluation/daily-omni/eval_cpp_pipeline.py 期望, 大小写敏感):
  VideoPath  <- parquet video.path          (PascalCase!)
  WavPath    <- parquet audio.path          (PascalCase!)
  video_id   <- video_id
  question   <- question
  choices    <- candidates   (保留 "A. " 前缀; pipeline build_prompt 会再加一层对齐官方)
  gt_answer  <- answer[0]    (单字母 A/B/C/D; parquet answer 是完整文本 "B. xxx")

音视频按 video_id 去重 (684 唯一视频 / 1196 题); bytes 直接 write, 无需解码。
"""
import os, sys, json, glob, random

import pandas as pd

SRC = "/workspace/shared_assets/datasets/MTEB/Daily-Omni/data"
DATASET_DIR = "/workspace/user_data/claude_code/minicpm-ascend-challenge/benchmark/daily-omni-data"
JSONL = os.path.join(DATASET_DIR, "daily_omni.jsonl")


def log(*a):
    print(*a, flush=True)


def main():
    os.makedirs(DATASET_DIR, exist_ok=True)
    shards = sorted(glob.glob(os.path.join(SRC, "test-*.parquet")))
    if not shards:
        sys.exit(f"[ERR] 找不到 parquet 分片: {SRC}")
    log(f"找到 {len(shards)} 个 parquet 分片")

    # 只读需要的列, 省内存
    cols = ["video_id", "video", "audio", "question", "candidates", "answer"]
    df = pd.concat([pd.read_parquet(f, columns=cols) for f in shards], ignore_index=True)
    log(f"总题数: {len(df)} | 唯一视频: {df['video_id'].nunique()}")

    # ---- 提取音视频 (按 video_id 去重, 已存在则跳过支持断点续跑) ----
    seen = set()
    n_mp4 = n_wav = 0
    for _, row in df.iterrows():
        vid = row["video_id"]
        if vid in seen:
            continue
        seen.add(vid)
        vp = row["video"]["path"]
        ap = row["audio"]["path"]
        vpath = os.path.join(DATASET_DIR, vp)
        apath = os.path.join(DATASET_DIR, ap)
        # 保证子目录存在 (path 可能含子目录)
        os.makedirs(os.path.dirname(vpath), exist_ok=True)
        os.makedirs(os.path.dirname(apath), exist_ok=True)
        if not os.path.exists(vpath):
            with open(vpath, "wb") as f:
                f.write(row["video"]["bytes"])
            n_mp4 += 1
        if not os.path.exists(apath):
            with open(apath, "wb") as f:
                f.write(row["audio"]["bytes"])
            n_wav += 1
    log(f"媒体写出: mp4 新增 {n_mp4} / wav 新增 {n_wav} (去重视频共 {len(seen)})")

    # ---- 写 jsonl (每题一行) ----
    bad = 0
    with open(JSONL, "w") as f:
        for _, row in df.iterrows():
            ans = row["answer"]
            gt = ans[0] if (isinstance(ans, str) and ans and ans[0] in "ABCD") else ""
            if not gt:
                bad += 1
            rec = {
                "video_id": str(row["video_id"]),
                "VideoPath": row["video"]["path"],
                "WavPath": row["audio"]["path"],
                "question": row["question"],
                "choices": list(row["candidates"]),
                "gt_answer": gt,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(f"写出 jsonl: {JSONL} ({len(df)} 行, gt_answer 异常 {bad})")

    # ---- 校验 ----
    with open(JSONL) as f:
        lines = f.readlines()
    mp4s = glob.glob(os.path.join(DATASET_DIR, "**", "*.mp4"), recursive=True)
    wavs = glob.glob(os.path.join(DATASET_DIR, "**", "*.wav"), recursive=True)
    log(f"\n=== 校验 ===")
    log(f"jsonl 行数: {len(lines)} (期望 {len(df)})")
    log(f"mp4 数: {len(mp4s)} | wav 数: {len(wavs)} (期望 {len(seen)})")
    random.seed(42)
    for i in random.sample(range(len(lines)), min(3, len(lines))):
        r = json.loads(lines[i])
        ok_gt = r["gt_answer"] in "ABCD"
        ok_ch = len(r["choices"]) == 4 and all(c[:2] in ("A.", "B.", "C.", "D.") for c in r["choices"])
        vok = os.path.exists(os.path.join(DATASET_DIR, r["VideoPath"]))
        aok = os.path.exists(os.path.join(DATASET_DIR, r["WavPath"]))
        log(f"  抽检题#{i}: video_id={r['video_id']} gt={r['gt_answer']!r}(字母={ok_gt}) "
            f"choices={len(r['choices'])}项(前缀={ok_ch}) video存在={vok} audio存在={aok}")
    if len(lines) == len(df) and len(mp4s) == len(seen) and len(wavs) == len(seen) and bad == 0:
        log("转换完成 ✓ 全部校验通过")
    else:
        log(f"[WARN] 校验有异常 (行数/文件数/gt), 请检查")


if __name__ == "__main__":
    main()
