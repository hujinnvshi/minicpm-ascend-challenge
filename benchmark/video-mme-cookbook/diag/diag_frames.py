"""
多帧退化诊断：单帧红线 + 帧数梯度（找退化阈值）。
用法: python diag_frames.py "1,2,4,5,6,7,8,16,32" [NQ=2]

要点:
- 显式传 max_num_frames（prepare_video_frames 的 max_num_frames 是默认参数, def 时绑定 64,
  monkey-patch 模块级 MAX_NUM_FRAMES 无效, 必须显式传参）。
- 每帧数用独立 OmniCliClient 进程, 避免 shared_octx 被多帧退化污染影响后续帧数结果（P7 教训）。
- 双 die 设备: smoke 走 device0, 命令带 CUDA_VISIBLE_DEVICES=0（见 CLAUDE.md 红线）。
"""
import sys, os, logging
import pandas as pd

COOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 本脚本在 cookbook/diag/ → parent=cookbook
sys.path.insert(0, COOK)
import eval_cpp_config
import eval_cpp_video_prep
from eval_cpp_cli_client import OmniCliClient
from eval_cpp_pipeline import extract_answer

FRAME_LIST = [int(x) for x in sys.argv[1].split(",")]
NQ = int(sys.argv[2]) if len(sys.argv) > 2 else 2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("diag")

df = pd.read_parquet(eval_cpp_config.PARQUET_PATH).head(NQ)
log.info(f"diag start: frames={FRAME_LIST} questions={NQ}")

results = {}
for nf in FRAME_LIST:
    client = OmniCliClient(gpu_id=0)
    if not client.wait_ready():
        log.error(f"frames={nf}: CLI not ready, skip")
        results[nf] = [("ERR", "ERR", "cli", 0, False)]
        continue
    preds = []
    for _, row in df.iterrows():
        vid = row["video_id"]
        video_path = f"{eval_cpp_config.VIDEO_DATA_DIR}/{row['videoID']}.mp4"
        frames = eval_cpp_video_prep.prepare_video_frames(video_path, vid, max_num_frames=nf)
        opts = row["options"].tolist() if hasattr(row["options"], "tolist") else list(row["options"])
        prompt = eval_cpp_config.USER_PROMPT_TEMPLATE.format(question=row["question"], options="\n".join(opts))
        raw = client.infer(frames, prompt, qid=row["question_id"])
        pred = extract_answer(raw)
        degraded = set(raw.strip()) <= {"_"}
        preds.append((row["answer"], pred, raw[:40], len(frames), degraded))
        eval_cpp_video_prep.cleanup_frames(vid)
    client.close()
    results[nf] = preds
    log.info(f"[frames={nf}] " + " | ".join(f"GT={g} Pred={p!r} deg={d}" for g, p, _, _, d in preds))

print("\n===== 多帧退化阈值汇总 =====")
print(f"{'frames':>7} | {'valid':>6} | {'实际帧数':>8} | 详情")
for nf, preds in results.items():
    ok = sum(1 for g, p, _, _, _ in preds if p in {"A", "B", "C", "D"})
    nfactual = preds[0][3] if preds else "?"
    detail = " ".join(f"GT{g}→{p!r}" for g, p, _, _, _ in preds)
    flag = "✅正常" if ok == len(preds) else ("⚠️部分" if ok > 0 else "❌退化")
    print(f"{nf:>7} | {ok}/{len(preds):<4} | {nfactual:>8} | {flag} {detail}")
