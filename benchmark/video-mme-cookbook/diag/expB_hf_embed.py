#!/usr/bin/env python3
"""实验B HF 侧: 用与 C++ 完全相同的 JPEG(/root/videomme_frames/093/frame_000.jpg)
单图 chat,截 vision_hidden_states → /tmp/hf_vis_embed.npy 供对比。"""
import os
os.environ.setdefault("ASCEND_RT_VISIBLE_DEVICES", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
MODEL = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5"
FRAME = "/root/videomme_frames/093/frame_000.jpg"

def log(*a): print(*a, flush=True)
import torch, torch_npu, numpy as np
from PIL import Image
from transformers import AutoModel, AutoTokenizer, AutoProcessor
tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
processor = AutoProcessor.from_pretrained(MODEL, trust_remote_code=True)
model = AutoModel.from_pretrained(MODEL, trust_remote_code=True, torch_dtype=torch.float16).to("npu").eval()
log("LOADED")

_cap = {}
_orig_gve = model.get_vision_embedding
def _wrap_gve(*a, **k):
    out = _orig_gve(*a, **k)
    try:
        _cap["vhs"] = out
    except Exception:
        pass
    return out
model.get_vision_embedding = _wrap_gve

img = Image.open(FRAME).convert("RGB")
msg = [{"role": "user", "content": [img, "Describe this image in one word."]}]
resp = model.chat(image=None, msgs=msg, tokenizer=tok, processor=processor,
                  max_new_tokens=8, do_sample=False, omni_mode=False, max_slice_nums=1)
log(f"resp={resp!r}")
vhs = _cap.get("vhs")
if vhs is not None:
    t = vhs if isinstance(vhs, torch.Tensor) else vhs[0]
    arr = t.float().cpu().numpy()
    log(f"vision_hidden_states shape={arr.shape} dtype={t.dtype}")
    np.save("/tmp/hf_vis_embed.npy", arr)
    log("SAVED /tmp/hf_vis_embed.npy")
else:
    log("NO vhs captured")
