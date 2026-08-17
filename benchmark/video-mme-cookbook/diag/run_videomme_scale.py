"""
VideoMME 分层精度复跑（规模版，官方 CookBook pipeline）。

读 extract_subset.py 持久化的 selected_questions.csv，按帧数曲线 [1,2,5,8,64] 跑全部题：
- 每帧数一个独立 CLI 进程（避免 shared_octx 跨帧数污染，P7 教训）。
- 每题 infer() 内部 reset→prefill 帧→prefill 文本→decode（KV 每题重置，无跨题累积）。
- 逐题追加写 CSV（长跑防丢），结束出 帧数×duration 精度表。

用法:
  source /workspace/user_data/venv-omni/bin/activate
  CUDA_VISIBLE_DEVICES=0 python diag/run_videomme_scale.py ["1,2,5,8,64"]
"""
import os
import sys
import csv
import ast
import traceback
from datetime import datetime

COOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, COOK)
import eval_cpp_config  # noqa: E402
import eval_cpp_video_prep  # noqa: E402
from eval_cpp_cli_client import OmniCliClient  # noqa: E402
from eval_cpp_pipeline import extract_answer  # noqa: E402

import logging  # noqa: E402

DIAG_DIR = os.path.dirname(os.path.abspath(__file__))
SEL_CSV = os.path.join(DIAG_DIR, "selected_questions.csv")
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_CSV = os.path.join(DIAG_DIR, f"results_scale_{TS}.csv")
OUT_SUM = os.path.join(DIAG_DIR, f"results_scale_{TS}_summary.txt")

FRAME_LIST = [int(x) for x in (sys.argv[1] if len(sys.argv) > 1 else "1,2,5,8,64").split(",")]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("scale")
log.info(f"frame sweep={FRAME_LIST}  out={OUT_CSV}")


def load_selected():
    import pandas as pd
    df = pd.read_csv(SEL_CSV)
    rows = []
    for _, r in df.iterrows():
        opts = r["options"]
        try:
            opts = ast.literal_eval(opts) if isinstance(opts, str) else list(opts)
        except Exception:
            opts = [opts]
        rows.append({
            "question_id": str(r["question_id"]),
            "videoID": str(r["videoID"]),
            "duration": str(r["duration"]),
            "question": str(r["question"]),
            "options": [str(o) for o in opts],
            "answer": str(r["answer"]),
        })
    return rows


def write_header():
    with open(OUT_CSV, "w", newline="") as f:
        csv.writer(f).writerow(
            ["frames", "duration", "videoID", "question_id", "GT", "pred", "correct", "degraded", "raw_head", "nframes_actual", "error"]
        )


def append_row(row):
    with open(OUT_CSV, "a", newline="") as f:
        csv.writer(f).writerow(row)


def run_one_frame(nf, rows):
    client = OmniCliClient(gpu_id=0)
    if not client.wait_ready():
        log.error(f"[frames={nf}] CLI not ready, skipping frame count")
        return
    log.info(f"[frames={nf}] CLI ready, running {len(rows)} questions ...")
    n_ok = 0
    for i, q in enumerate(rows, 1):
        video_path = os.path.join(eval_cpp_config.VIDEO_DATA_DIR, f"{q['videoID']}.mp4")
        err = ""
        pred, raw, correct, degraded, nfact = "", "", False, False, 0
        try:
            frames = eval_cpp_video_prep.prepare_video_frames(video_path, q["videoID"], max_num_frames=nf)
            nfact = len(frames) if frames else 0
            if not frames:
                err = "no_frames"
            else:
                prompt = eval_cpp_config.USER_PROMPT_TEMPLATE.format(
                    question=q["question"], options="\n".join(q["options"])
                )
                raw = client.infer(frames, prompt, qid=q["question_id"]) or ""
                pred = extract_answer(raw)
                degraded = len(raw.strip()) > 0 and set(raw.strip()) <= {"_"}
                correct = (pred == q["answer"]) and not degraded
                if correct:
                    n_ok += 1
            eval_cpp_video_prep.cleanup_frames(q["videoID"])
        except Exception as e:
            err = f"{type(e).__name__}:{e}"
            log.warning(f"[frames={nf}] q{i} {q['question_id']} EXCEPTION {err}")
            traceback.print_exc()

        append_row([nf, q["duration"], q["videoID"], q["question_id"], q["answer"],
                    pred, int(correct), int(degraded), raw[:80].replace("\n", " "), nfact, err])
        if i % 10 == 0 or i == len(rows):
            log.info(f"[frames={nf}] {i}/{len(rows)} done (correct so far={n_ok})")
    try:
        client.close()
    except Exception:
        pass
    log.info(f"[frames={nf}] FINISHED correct={n_ok}/{len(rows)}")


def summarize(rows):
    """按 帧数×duration 出精度表。"""
    import pandas as pd
    df = pd.read_csv(OUT_CSV)
    lines = []
    lines.append(f"VideoMME 分层精度复跑  ts={TS}")
    lines.append(f"帧数曲线={FRAME_LIST}  官方 CookBook pipeline (temp={eval_cpp_config.TEMPERATURE}, max_tokens={eval_cpp_config.MAX_TOKENS}, @1fps)")
    lines.append(f"total questions={len(rows)} (short/medium/long 各 {len(rows)//3})")
    lines.append("")
    lines.append(f"{'frames':>7} | {'short':>9} | {'medium':>9} | {'long':>9} | {'overall':>9} | {'degraded%':>9}")
    lines.append("-" * 70)
    for nf in FRAME_LIST:
        sub = df[df["frames"] == nf]
        if len(sub) == 0:
            lines.append(f"{nf:>7} | (no data)")
            continue
        def acc(d):
            s = sub[sub["duration"] == d]
            return f"{int(s['correct'].sum())}/{len(s)}" if len(s) else "-"
        ova = f"{int(sub['correct'].sum())}/{len(sub)}"
        deg = f"{100.0*sub['degraded'].mean():.0f}%"
        lines.append(f"{nf:>7} | {acc('short'):>9} | {acc('medium'):>9} | {acc('long'):>9} | {ova:>9} | {deg:>9}")
    txt = "\n".join(lines)
    with open(OUT_SUM, "w") as f:
        f.write(txt + "\n")
    print("\n" + txt + "\n")
    log.info(f"summary written: {OUT_SUM}")


def main():
    rows = load_selected()
    log.info(f"loaded {len(rows)} selected questions from {SEL_CSV}")
    # 预检视频
    present = {os.path.splitext(f)[0] for f in os.listdir(eval_cpp_config.VIDEO_DATA_DIR) if f.endswith(".mp4")}
    miss = [q["videoID"] for q in rows if q["videoID"] not in present]
    if miss:
        log.warning(f"{len(set(miss))} videos missing, those questions will error: {list(set(miss))[:5]}...")
    write_header()
    for nf in FRAME_LIST:
        run_one_frame(nf, rows)
    summarize(rows)


if __name__ == "__main__":
    main()
