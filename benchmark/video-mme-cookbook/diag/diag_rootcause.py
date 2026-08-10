"""
多帧退化根因对比：N1 帧(正常) vs N2 帧(退化) 的 logits / embed NaN。
用法:
  OMNI_DEBUG_LOGITS=1 OMNI_DEBUG_NAN=1 python diag_rootcause.py [N1=5] [N2=6] [NQ=1]
  OMNI_DIAG_OUT=./out  # rc-log-<N>.log 输出目录（默认当前目录）

判读（看 cli-log 的 [DBGLOGITS] / [DBGNAN]）:
- [DBGLOGITS] maxlogit=nan  → LLM 后端数值溢出 NaN
- [DBGLOGITS] maxlogit 正常 + argmax='_' + p_argmax≈1 → softmax 塌缩（非 NaN）
- [DBGNAN] emb_nan=1        → vision encoder 输出 NaN（根因在 vision）
- [DBGNAN] emb_nan=0 + logits nan → vision 正常, NaN 在 LLM
"""
import sys, os, shutil, logging, re
import pandas as pd

COOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, COOK)
import eval_cpp_config
import eval_cpp_video_prep
from eval_cpp_cli_client import OmniCliClient
from eval_cpp_pipeline import extract_answer

DIAG = os.environ.get("OMNI_DIAG_OUT", ".")
os.makedirs(DIAG, exist_ok=True)
N1 = int(sys.argv[1]) if len(sys.argv) > 1 else 5
N2 = int(sys.argv[2]) if len(sys.argv) > 2 else 6
NQ = int(sys.argv[3]) if len(sys.argv) > 3 else 1

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("rc")

df = pd.read_parquet(eval_cpp_config.PARQUET_PATH).head(NQ)
CLILOG = os.path.join(COOK, "log", "cli_gpu0.log")

summary = []
for nf in [N1, N2]:
    log.info(f"===== {nf} 帧 =====")
    client = OmniCliClient(gpu_id=0)
    if not client.wait_ready():
        log.error("CLI not ready"); continue
    row = df.iloc[0]
    vid = row["video_id"]
    video_path = f"{eval_cpp_config.VIDEO_DATA_DIR}/{row['videoID']}.mp4"
    opts = row["options"].tolist() if hasattr(row["options"], "tolist") else list(row["options"])
    prompt = eval_cpp_config.USER_PROMPT_TEMPLATE.format(question=row["question"], options="\n".join(opts))
    GT = row["answer"]
    frames = eval_cpp_video_prep.prepare_video_frames(video_path, vid, max_num_frames=nf)
    raw = client.infer(frames, prompt, qid=row["question_id"])
    pred = extract_answer(raw)
    eval_cpp_video_prep.cleanup_frames(vid)
    client.close()
    shutil.copy(CLILOG, f"{DIAG}/rc-log-{nf}.log")
    txt = open(f"{DIAG}/rc-log-{nf}.log", errors="ignore").read()
    nan_inf = bool(re.search(r"\b(nan|inf|NaN|Inf|INF)\b", txt))
    dbglog = [l.strip() for l in txt.split("\n") if "DBGLOGITS" in l][:4]
    dbgnan = [l.strip() for l in txt.split("\n") if "DBGNAN" in l][:8]
    log.info(f"  GT={GT} Pred={pred!r} raw={raw[:25]!r}")
    log.info(f"  cli-log 含 nan/inf 字样={nan_inf}（注：默认 log 不打印 logits 数值，以 [DBGLOGITS] 为准）")
    for l in dbgnan:
        log.info("  " + l)
    for l in dbglog:
        log.info("  " + l)
    summary.append((nf, pred, raw[:25]))

print("\n===== 根因对比 =====")
for nf, pred, raw in summary:
    flag = "✅正常" if pred in {"A", "B", "C", "D"} else "❌退化"
    print(f"[{nf}帧] {flag} Pred={pred!r} raw={raw!r}")
print(f"\n判读：看 {DIAG}/rc-log-{N1}.log（正常）vs rc-log-{N2}.log（退化）的 [DBGLOGITS] maxlogit 是否 nan")
