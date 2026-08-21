#!/usr/bin/env python3
"""空响应复现:直驱 eval-cli(JSONL 协议),完整捕获 stderr 供 decode 行为分析。

用法: empty_repro.py <video_id 补零3位>
"""
import sys, os, json, subprocess, time

REPO = "/workspace/minicpm-ascend-challenge"
SUBSET = os.environ.get("REPRO_PARQUET", f"{REPO}/benchmark/video-mme-cookbook/diag/videomme_subset_domain180.parquet")
VDIR   = os.environ.get("REPRO_VDATA", f"{REPO}/benchmark/video-mme-cookbook/diag/videomme_domain180_data")
os.environ.setdefault("LLAMA_CLI_BIN", f"{REPO}/code/llama.cpp-omni/build/bin/llama-omni-eval-cli")
sys.path.insert(0, f"{REPO}/code/llama.cpp-omni/evaluation/videomme")
from eval_cpp_config import USER_PROMPT_TEMPLATE, LLAMA_CLI_BIN

import pandas as pd
from eval_cpp_video_prep import prepare_video_frames

MODEL = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf"
vid = sys.argv[1]
df = pd.read_parquet(SUBSET)
g = df[df['video_id'].astype(str) == vid]
row = g.iloc[0]
print(f"[{vid}] {row['videoID']}.mp4 {row['domain']}/{row['duration']} GT={row['answer']}", flush=True)

video_path = f"{VDIR}/{row['videoID']}.mp4"
# 帧临时目录 → 本地盘(NFS 96%满,写帧会 ENOSPC; save_frames_as_jpg 的 tmp_dir 是 import 时绑定的默认参数 → patch __defaults__)
import eval_cpp_video_prep as _evp
os.makedirs("/root/videomme_frames", exist_ok=True)
_evp.save_frames_as_jpg.__defaults__ = ("/root/videomme_frames", 95)
frames = prepare_video_frames(video_path, row["video_id"])
print(f"[{vid}] {len(frames)} frames", flush=True)

opts = row["options"]; opts = opts.tolist() if hasattr(opts, "tolist") else list(opts)
prompt = USER_PROMPT_TEMPLATE.format(question=row["question"], options="\n".join(opts))

env = dict(os.environ)  # 不设 Omni_BACKEND_DEVICE → NPU vision(与失败轮一致)
log = open(f"/tmp/empty_debug_{vid}.log", "w")
cli = subprocess.Popen(
    [LLAMA_CLI_BIN, "-m", MODEL, "-c", "40960", "-ngl", "999",
     "--max-slice-nums", "0", "--n-predict", "100",
     "--temp", "0.0", "--top-p", "0.8", "--top-k", "100",
     "--repeat-penalty", "1.02", "--seed", "42"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, env=env, text=True, bufsize=1)
for line in cli.stdout:
    if '"ready"' in line: break
print(f"[cli ready]", flush=True)

t0 = time.time()
cli.stdin.write(json.dumps({"type": "infer", "id": vid, "frames": frames, "prompt": prompt,
                            "max_slice_nums": 0, "n_predict": 100}) + "\n")
cli.stdin.flush()
for line in cli.stdout:
    if '"result"' in line:
        r = json.loads(line)
        print(f"[{(time.time()-t0):.0f}s] ok={r.get('ok')} response={r.get('response')!r}", flush=True)
        break
try:
    cli.stdin.write('{"type":"quit"}\n'); cli.stdin.flush(); cli.wait(timeout=60)
except Exception: cli.kill()
print(f"stderr log: /tmp/empty_debug_{vid}.log", flush=True)
