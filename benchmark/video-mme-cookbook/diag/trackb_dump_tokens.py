#!/usr/bin/env python3
"""HF 侧 093-1 prefill token 序列 dump(与 C++ 逐位 diff 用)。
外层 model.generate 收 input_ids;保存 token 字符序列到 /tmp/hf_093_tokens.txt
"""
import os, sys, time, glob, tempfile, subprocess, json
os.environ.setdefault("ASCEND_RT_VISIBLE_DEVICES", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

MODEL = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5"
VDATA = "/workspace/user_data/temp_project/minicpm-ascend-challenge/benchmark/video-mme-cookbook/diag/videomme_domain180_data"
PROMPT_T = ("Carefully read the following question and select the letter corresponding to the correct answer."
            "Highlight the applicable choices without giving explanations.\n{q}\nOptions:\n{opts}")

def log(*a): print(*a, flush=True)

def extract_frames(video_path, n=64):
    tmp = tempfile.mkdtemp(prefix="tb3_")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video_path,
                    "-vf", "fps=1", "-q:v", "2", os.path.join(tmp, "f%05d.jpg")], check=True)
    files = sorted(glob.glob(os.path.join(tmp, "f*.jpg")))
    if len(files) > n:
        idx = [int(i * (len(files) - 1) / (n - 1)) for i in range(n)]
        files = [files[i] for i in idx]
    from PIL import Image
    return [Image.open(f).convert("RGB") for f in files]

import torch, torch_npu
from transformers import AutoModel, AutoTokenizer, AutoProcessor
tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
processor = AutoProcessor.from_pretrained(MODEL, trust_remote_code=True)
model = AutoModel.from_pretrained(MODEL, trust_remote_code=True, torch_dtype=torch.float16).to("npu").eval()
log("LOADED")

_cap = {}
_orig_gen = model.generate
def _gen_wrap(*a, **k):
    if "input_ids" in k:
        _cap["input_ids"] = k["input_ids"]
    return _orig_gen(*a, **k)
model.generate = _gen_wrap

row = json.load(open("/tmp/trackb_cases.json"))[0]  # 093-1
opts = list(row["options"])
qtxt = PROMPT_T.format(q=row["question"], opts="\n".join(opts))
fr = extract_frames(f"{VDATA}/{row['videoID']}.mp4", 64)
log(f"frames={len(fr)}")

msg = [{"role": "user", "content": [*fr, qtxt]}]
resp = model.chat(image=None, msgs=msg, tokenizer=tok, processor=processor,
                  max_new_tokens=100, do_sample=False, omni_mode=False, max_slice_nums=1)
log(f"resp={resp!r}")

ids = _cap.get("input_ids")
if ids is not None:
    toks = tok.convert_ids_to_tokens(ids[0].tolist())
    with open("/tmp/hf_093_tokens.txt", "w") as f:
        f.write("\n".join(toks))
    log(f"SAVED {len(toks)} tokens → /tmp/hf_093_tokens.txt")
    # 打印非 <image> 占位的结构骨架(前80 + 模板关键段)
    skel = [t for t in toks if "image" not in t]
    log(f"骨架预览(前60 非 image tokens): {' '.join(skel[:60])}")
    log(f"...尾部(后80): {' '.join(skel[-80:])}")
else:
    log("NO input_ids captured!")
