#!/usr/bin/env python3
"""setup-videomme-videos.py - 从官方 Video-MME videos_chunked_*.zip 解压评测所需视频（评审环境复现用）

官方 Video-MME 视频以 20 个 chunk zip 预置（/workspace/shared_assets/datasets/lmms-lab/Video-MME/），
zip 内文件名 = YouTube ID.mp4。评测管道 (evaluation/videomme/eval_cpp_config.py) 按
VIDEO_DATA_DIR/<videoID>.mp4 取帧。

用法:
  python3 setup-videomme-videos.py \
      --zip-dir <官方zip目录> \
      --out-dir <VIDEO_DATA_DIR> \
      --parquet <子集parquet 可选, 缺省=解压全部900个视频> \
      --dry-run    (只看缺哪些, 不解压)

示例（评审环境, 与 docs/videomme-baseline-clarification.md 的 99q 子集口径一致）:
  python3 setup-videomme-videos.py \
      --zip-dir /workspace/shared_assets/datasets/lmms-lab/Video-MME \
      --out-dir benchmark/video-mme-cookbook/diag/videomme99_data \
      --parquet benchmark/video-mme-cookbook/diag/videomme_subset_99q.parquet
"""
import argparse
import glob
import os
import shutil
import sys
import zipfile


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip-dir", required=True, help="官方 Video-MME 数据集目录(含 videos_chunked_*.zip)")
    ap.add_argument("--out-dir", required=True, help="输出目录 = 评测 VIDEO_DATA_DIR")
    ap.add_argument("--parquet", default=None, help="子集 parquet(含 videoID 列); 缺省解压全部 mp4")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # 1) 目标 videoID 列表
    vids = None
    if args.parquet:
        try:
            import pandas as pd
        except ImportError:
            print("FATAL: --parquet 需要 pandas (pip install pandas)", file=sys.stderr)
            return 1
        df = pd.read_parquet(args.parquet)
        col = "videoID" if "videoID" in df.columns else "video_id"
        vids = sorted(df[col].unique().tolist())
        print(f"[setup] parquet {os.path.basename(args.parquet)}: {len(vids)} 个唯一视频")
    else:
        print("[setup] 无 parquet, 解压全部 mp4")

    # 2) 建立 zip 索引 (id -> (zip, entry))
    zips = sorted(glob.glob(os.path.join(args.zip_dir, "videos_chunked_*.zip")))
    if not zips:
        print(f"FATAL: {args.zip_dir} 下没有 videos_chunked_*.zip", file=sys.stderr)
        return 1
    idx: dict = {}
    for zp in zips:
        with zipfile.ZipFile(zp) as z:
            for n in z.namelist():
                if n.endswith(".mp4"):
                    idx[os.path.basename(n)[:-4]] = (zp, n)
    print(f"[setup] 索引 {len(idx)} 个 mp4 (来自 {len(zips)} 个 zip)")

    # 3) 比对缺哪些
    os.makedirs(args.out_dir, exist_ok=True)
    have = {f[:-4] for f in os.listdir(args.out_dir) if f.endswith(".mp4")}
    need = [v for v in (vids or sorted(idx)) if v not in have]
    missing_in_zip = [v for v in need if v not in idx]
    if vids and missing_in_zip:
        print(f"WARN: {len(missing_in_zip)} 个视频不在 zip 中: {missing_in_zip[:8]}...", file=sys.stderr)
    print(f"[setup] 已有 {len(have)} / 需要 {len(vids or idx)} / 待解压 {len(need)}")

    if args.dry_run:
        return 0

    # 4) 解压
    for v in need:
        zp, entry = idx[v]
        with zipfile.ZipFile(zp) as z, \
             z.open(entry) as src, \
             open(os.path.join(args.out_dir, v + ".mp4"), "wb") as dst:
            shutil.copyfileobj(src, dst)
    print(f"[setup] DONE: {args.out_dir} 现有 {len(os.listdir(args.out_dir))} 个 mp4")
    return 0


if __name__ == "__main__":
    sys.exit(main())