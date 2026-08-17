"""
VideoMME 分层视频子集提取（规模精度复跑用）。

- 分层确定性选取 short/medium/long 各 N 个视频的全部题（≈99 题）。
- 扫描 20 个 videos_chunked zip 建 videoID→zip 映射，提取缺失视频到 VIDEO_DATA_DIR。
- 持久化 selected_questions.csv + selected_videos.txt，供 run_videomme_scale.py 复用
  （保证“选片”与“跑”用完全一致的视频集）。

用法:
  source /workspace/user_data/venv-omni/bin/activate
  python diag/extract_subset.py
"""
import os
import sys
import csv
import shutil
import zipfile
import logging

COOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, COOK)
import eval_cpp_config  # noqa: E402  (loads .env → PARQUET_PATH / VIDEO_DATA_DIR)

import pandas as pd  # noqa: E402

# 各 duration 取的视频数（11+11+11=33 视频 × 3 题 ≈ 99 题，等量分层便于按 duration 报精度）
PER_DURATION_VIDEOS = {"short": 11, "medium": 11, "long": 11}
DIAG_DIR = os.path.dirname(os.path.abspath(__file__))
SEL_CSV = os.path.join(DIAG_DIR, "selected_questions.csv")
SEL_VIDS = os.path.join(DIAG_DIR, "selected_videos.txt")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("extract")


def select(df: pd.DataFrame) -> pd.DataFrame:
    """确定性分层选取：每个 duration 取前 N 个 videoID 的全部题。"""
    parts = []
    for dur, nv in PER_DURATION_VIDEOS.items():
        vids = list(df[df["duration"] == dur]["videoID"].unique()[:nv])
        sub = df[df["videoID"].isin(vids)]
        parts.append(sub)
        log.info(f"{dur}: {len(vids)} videos → {len(sub)} questions")
    sdf = pd.concat(parts).reset_index(drop=True)
    return sdf


def build_zip_map(video_ids, zip_glob_dir):
    """扫所有 zip，返回 {videoID: zip_path}（只含需要的 videoID）。"""
    from glob import glob
    wanted = set(video_ids)
    zmap = {}
    zips = sorted(glob(os.path.join(zip_glob_dir, "videos_chunked_*.zip")))
    log.info(f"scanning {len(zips)} zips for {len(wanted)} videos ...")
    for zp in zips:
        if not wanted:
            break
        try:
            with zipfile.ZipFile(zp) as z:
                for name in z.namelist():
                    if not name.endswith(".mp4"):
                        continue
                    vid = os.path.splitext(os.path.basename(name))[0]
                    if vid in wanted and vid not in zmap:
                        zmap[vid] = (zp, name)
                        wanted.discard(vid)
        except Exception as e:
            log.warning(f"zip read fail {zp}: {e}")
    return zmap, wanted  # wanted = 仍未找到的


def main():
    parquet = eval_cpp_config.PARQUET_PATH
    vdir = eval_cpp_config.VIDEO_DATA_DIR
    log.info(f"PARQUET={parquet}")
    log.info(f"VIDEO_DATA_DIR={vdir}")
    os.makedirs(vdir, exist_ok=True)

    df = pd.read_parquet(parquet)
    sdf = select(df)
    video_ids = list(dict.fromkeys(sdf["videoID"].tolist()))  # 去重保序
    log.info(f"selected total: {len(sdf)} questions, {len(video_ids)} videos")

    # 持久化选择（run 脚本读这两个文件）
    sdf[["question_id", "videoID", "duration", "task_type", "question", "options", "answer"]].to_csv(
        SEL_CSV, index=False, quoting=csv.QUOTE_MINIMAL
    )
    with open(SEL_VIDS, "w") as f:
        f.write("\n".join(video_ids) + "\n")
    log.info(f"wrote {SEL_CSV} + {SEL_VIDS}")

    # 已存在的跳过
    present = {os.path.splitext(f)[0] for f in os.listdir(vdir) if f.endswith(".mp4")}
    missing = [v for v in video_ids if v not in present]
    log.info(f"videos present={len(set(video_ids) & present)} missing={len(missing)}")
    if not missing:
        log.info("all selected videos already present ✓")
        return

    # 找 zip（从 parquet 同级的 Video-MME 目录）
    zip_dir = os.path.dirname(os.path.dirname(parquet))  # .../Video-MME/
    zmap, not_found = build_zip_map(missing, zip_dir)
    if not_found:
        log.error(f"NOT FOUND in any zip ({len(not_found)}): {not_found}")
        log.error("→ 这些视频题会在 run 时被跳过，或需手动补数据。")

    # 提取（zipfile 单成员解压 → 展平到 VIDEO_DATA_DIR/{videoID}.mp4）
    tmp = os.path.join(vdir, "_extract_tmp")
    ok, fail = 0, 0
    for vid in missing:
        if vid not in zmap:
            fail += 1
            continue
        zp, member = zmap[vid]
        dst = os.path.join(vdir, f"{vid}.mp4")
        try:
            with zipfile.ZipFile(zp) as z:
                z.extract(member, path=tmp)
            src = os.path.join(tmp, member)
            shutil.move(src, dst)
            ok += 1
        except Exception as e:
            log.error(f"extract fail {vid}: {e}")
            fail += 1
    shutil.rmtree(tmp, ignore_errors=True)
    log.info(f"extracted ok={ok} fail={fail}")

    # 终检
    present2 = {os.path.splitext(f)[0] for f in os.listdir(vdir) if f.endswith(".mp4")}
    missing2 = [v for v in video_ids if v not in present2]
    log.info(f"FINAL: present={len(set(video_ids) & present2)}/{len(video_ids)} still_missing={len(missing2)}")
    if missing2:
        log.warning(f"still missing: {missing2}")


if __name__ == "__main__":
    main()
