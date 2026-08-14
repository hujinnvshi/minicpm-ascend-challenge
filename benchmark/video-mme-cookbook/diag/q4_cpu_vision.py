#!/usr/bin/env python3
"""题N CPU vision 诊断:绕过 eval client 的 300s 超时,直接驱动 eval-cli 的 stdin/stdout JSONL。

背景:Omni_BACKEND_DEVICE=CPU 让 vision 走 CPU(LLM 仍 NPU),单帧 ~13.8s,
64 帧 ≈ 15min > eval client INFER_TIMEOUT=300s,client 必杀进程。本脚本自控超时。

用法: q4_cpu_vision.py [qidx_0based]   默认 3 = 99q 子集第 4 题(NPU vision 下全 \n 退化题)
对照: NPU vision 题4 = GT C / Pred '' / Raw 全 '\n'(2026-08-14 实测)
"""
import sys, os, json, subprocess, time

REPO = "/workspace/user_data/temp_project/minicpm-ascend-challenge"
os.environ.setdefault("PARQUET_PATH", f"{REPO}/benchmark/video-mme-cookbook/diag/videomme_subset_99q.parquet")
os.environ.setdefault("VIDEO_DATA_DIR", f"{REPO}/code/llama.cpp-omni/evaluation/appendix/videomme99/data")
os.environ.setdefault("LLAMA_CLI_BIN", f"{REPO}/code/llama.cpp-omni/build/bin/llama-omni-eval-cli")
sys.path.insert(0, f"{REPO}/code/llama.cpp-omni/evaluation/videomme")

from eval_cpp_config import PARQUET_PATH, VIDEO_DATA_DIR, USER_PROMPT_TEMPLATE, LLAMA_CLI_BIN, CTX_SIZE
import pandas as pd
from eval_cpp_video_prep import prepare_video_frames
from eval_cpp_pipeline import extract_answer

MODEL = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"

qidx = int(sys.argv[1]) if len(sys.argv) > 1 else 3
df = pd.read_parquet(PARQUET_PATH).head(qidx + 1)
row = df.iloc[-1]
print(f"[q{qidx+1}] video={row['videoID']} GT={row['answer']}", flush=True)

video_path = f"{VIDEO_DATA_DIR}/{row['videoID']}.mp4"
frames = prepare_video_frames(video_path, row["video_id"])
print(f"[q{qidx+1}] {len(frames)} frames", flush=True)

opts = row["options"]
opts = opts.tolist() if hasattr(opts, "tolist") else list(opts)
prompt = USER_PROMPT_TEMPLATE.format(question=row["question"], options="\n".join(opts))

env = dict(os.environ)
if os.environ.get("Omni_BACKEND_DEVICE"):
    env["Omni_BACKEND_DEVICE"] = os.environ["Omni_BACKEND_DEVICE"]  # 设了才传: CPU=vision CPU;不设=NPU vision
log = open("/tmp/q4_cpu_cli.log", "w")
cli = subprocess.Popen(
    [LLAMA_CLI_BIN, "-m", MODEL, "-c", str(CTX_SIZE), "-ngl", "999",
     "--max-slice-nums", "0", "--n-predict", "100",
     "--temp", "0.0", "--top-p", "0.8", "--top-k", "100",
     "--repeat-penalty", "1.02", "--seed", "42"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, env=env, text=True, bufsize=1)

ready = False
for line in cli.stdout:
    if '"ready"' in line:
        ready = True
        break
print(f"[cli ready={ready}]", flush=True)

t0 = time.time()
req = json.dumps({"type": "infer", "id": f"q{qidx+1}", "frames": frames, "prompt": prompt,
                 "max_slice_nums": 0, "n_predict": 100})
cli.stdin.write(req + "\n"); cli.stdin.flush()
for line in cli.stdout:
    if '"result"' in line:
        r = json.loads(line)
        raw = r.get("response", "")
        print(f"[{(time.time()-t0)/60:.1f}min] ok={r.get('ok')} Raw={raw!r}", flush=True)
        print(f"RESULT GT={row['answer']} Pred={extract_answer(raw or '')!r}", flush=True)
        break
try:
    cli.stdin.write('{"type":"quit"}\n'); cli.stdin.flush(); cli.wait(timeout=60)
except Exception:
    cli.kill()
print("DONE", flush=True)
