#!/usr/bin/env python3
"""Track B 决定性对照:HF/torch_npu @ 同 910B 跑 llama.cpp 空响应的 3 题(EOS 临界型)。

判定:
  - HF 也空 → EOS 临界行为是环境级(910B 数值),框架无关,铁案
  - HF 正常作答 → llama.cpp 数值路径特定
  - 若能取到 scores: 对比首 token EOS vs 答案字母 的 margin(llama.cpp 侧 = 0.63)
prompt 用官方 USER_PROMPT_TEMPLATE(与 C++ eval 完全一致)。
"""
import os, sys, time, glob, tempfile, subprocess
os.environ.setdefault("ASCEND_RT_VISIBLE_DEVICES", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

MODEL = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5"
VDATA = "/workspace/user_data/temp_project/minicpm-ascend-challenge/benchmark/video-mme-cookbook/diag/videomme_domain180_data"
CASES = [("drbi6HK1gSc", "093-1", "D"), ("uoJDGnaVuTg", "097-3", "A"), ("pcO-alfiyEo", "114-1", "D")]
PROMPT_T = ("Carefully read the following question and select the letter corresponding to the correct answer."
            "Highlight the applicable choices without giving explanations.\n{q}\nOptions:\n{opts}")

def log(*a): print(*a, flush=True)

def extract_frames(video_path, n=64):
    tmp = tempfile.mkdtemp(prefix="tb2_")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video_path,
                    "-vf", "fps=1", "-q:v", "2", os.path.join(tmp, "f%05d.jpg")], check=True)
    files = sorted(glob.glob(os.path.join(tmp, "f*.jpg")))
    if len(files) > n:
        idx = [int(i * (len(files) - 1) / (n - 1)) for i in range(n)]
        files = [files[i] for i in idx]
    from PIL import Image
    return [Image.open(f).convert("RGB") for f in files]

t0 = time.time()
log("importing torch/torch_npu ...")
import torch, torch_npu
from transformers import AutoModel, AutoTokenizer, AutoProcessor
log(f"imports {time.time()-t0:.0f}s")
tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
processor = AutoProcessor.from_pretrained(MODEL, trust_remote_code=True)
model = AutoModel.from_pretrained(MODEL, trust_remote_code=True, torch_dtype=torch.float16).to("npu").eval()
log(f"LOADED {time.time()-t0:.0f}s dev={next(model.parameters()).device}")

import pandas as pd
import json as _json
CASES_DATA = {c[1]: c for c in CASES}
cases = _json.load(open("/tmp/trackb_cases.json"))

for row in cases:
    qid = row["qid"]; vid_file = row["videoID"]; gt = row["answer"]
    opts = list(row["options"])
    qtxt = PROMPT_T.format(q=row["question"], opts="\n".join(opts))
    fr = extract_frames(f"{VDATA}/{vid_file}.mp4", 64)
    log(f"\n===== {qid} {vid_file} GT={gt} frames={len(fr)} =====")
    try:
        t = time.time()
        kw = dict(tokenizer=tok, processor=processor, max_new_tokens=100,
                  do_sample=False, omni_mode=False, max_slice_nums=1)
        msg = [{"role": "user", "content": [*fr, qtxt]}]
        try:
            resp = model.chat(image=None, msgs=msg, output_scores=True, return_dict_in_generate=True, **kw)
            scores = getattr(resp, 'scores', None)
            if scores is None and isinstance(resp, tuple) and len(resp) > 1:
                scores = resp[1]
        except TypeError:
            resp, scores = model.chat(image=None, msgs=msg, **kw), None
        log(f"resp={str(resp)[:200]!r} ({time.time()-t:.0f}s)")
        if scores is not None and len(scores):
            import torch as _t
            first = scores[0][0]  # [vocab]
            topv, topi = _t.topk(first, 5)
            names = [tok.convert_ids_to_tokens(int(i)) for i in topi]
            log(f"first-token top5: {list(zip(names, [round(float(v),3) for v in topv]))}")
            for L in "ABCD":
                lid = tok.convert_tokens_to_ids(L)
                if lid is not None and lid >= 0:
                    log(f"  letter {L}: logit={float(first[lid]):.3f}")
    except Exception as e:
        import traceback; traceback.print_exc()
log("\nDONE")
