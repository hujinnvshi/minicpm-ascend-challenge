"""
Track B 对照实验: HF/torch_npu + @1fps均匀【96帧】 vs baseline 64帧。
目的: 隔离"帧数 64→96"是否是 gap(50%→69%) 的杠杆(对齐 vLLM ≤96帧)。
- 同 20 题、同 prompt、同 greedy、同 max_slice_nums=1, 仅帧数 64→96。
- fps=1 抽帧(短视频<96则取全部), uniform 到 96: medium/long 受益, short 不变(帧不够)。
- 若 overall 涨→帧数是杠杆; 若仍~50%→帧数非主因(gap 是采样算法/视觉/环境)。
"""
import os, sys, time, glob, tempfile, subprocess, ast, csv
os.environ.setdefault("ASCEND_RT_VISIBLE_DEVICES", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
COOK = "/workspace/user_data/claude_code/minicpm-ascend-challenge/benchmark/video-mme-cookbook"
sys.path.insert(0, COOK)
from eval_cpp_pipeline import extract_answer
from eval_cpp_config import USER_PROMPT_TEMPLATE
import pandas as pd

MODEL = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5"
VIDEOS = "/workspace/user_data/verify-ascend-2026-08-10/videomme-data"
SEL = os.path.join(COOK, "diag/selected_questions.csv")
OUT = os.path.join(COOK, "diag/trackb_uni96_20q.csv")
NF = 96   # ★ 唯一变量: 64 → 96

def log(*a): print(*a, flush=True)

def extract_frames(video_path, n):
    tmp = tempfile.mkdtemp(prefix="tb_u96_")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-i",video_path,"-vf","fps=1","-q:v","2",
                    os.path.join(tmp,"f%05d.jpg")], check=True)
    files = sorted(glob.glob(os.path.join(tmp,"f*.jpg")))
    if len(files) > n:
        idx = [int(i*(len(files)-1)/(n-1)) for i in range(n)] if n > 1 else [0]
        files = [files[i] for i in idx]
    log(f"    [{os.path.basename(video_path)}] fps1抽到{len(glob.glob(os.path.join(tmp,'f*.jpg')))}帧→用{len(files)}帧")
    from PIL import Image
    return [Image.open(f).convert("RGB") for f in files]

log("importing torch/torch_npu + loading model (fp16 → npu)...")
import torch, torch_npu
from transformers import AutoModel, AutoTokenizer, AutoProcessor
tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
processor = AutoProcessor.from_pretrained(MODEL, trust_remote_code=True)
model = AutoModel.from_pretrained(MODEL, trust_remote_code=True, torch_dtype=torch.float16).to("npu").eval()
log("LOADED")

def chat(content):
    msgs=[{"role":"user","content":content}]
    return model.chat(image=None, msgs=msgs, tokenizer=tok, processor=processor,
                      max_new_tokens=16, do_sample=False, omni_mode=False, max_slice_nums=1)

df = pd.read_csv(SEL)
pick = pd.concat([df[df.duration=='short'].head(7), df[df.duration=='medium'].head(7), df[df.duration=='long'].head(6)]).reset_index(drop=True)
log(f"running {len(pick)} questions @ {NF}帧 (torch_npu/HF, greedy, fps=1+uniform96)...")

with open(OUT,"w",newline="") as f:
    w=csv.writer(f); w.writerow(["duration","videoID","question_id","GT","pred","correct","raw","nframes"])
    for i, row in pick.iterrows():
        vp = os.path.join(VIDEOS, f"{row['videoID']}.mp4")
        opts = ast.literal_eval(row['options']) if isinstance(row['options'],str) else list(row['options'])
        try:
            fr = extract_frames(vp, NF); nf=len(fr)
            prompt = USER_PROMPT_TEMPLATE.format(question=row['question'], options="\n".join(map(str,opts)))
            raw = chat([*fr, prompt]) or ""
            pred = extract_answer(raw)
            correct = (pred == str(row['answer']))
        except Exception as e:
            raw=f"ERR:{type(e).__name__}:{e}"; pred=""; correct=False; nf=0
        w.writerow([row['duration'],row['videoID'],row['question_id'],row['answer'],pred,int(correct),str(raw)[:80],nf])
        log(f"[{i+1}/{len(pick)} {row['duration']} {row['question_id']}] GT={row['answer']} pred={pred!r} nf={nf} {'✅' if correct else '❌'}")

res = pd.read_csv(OUT)
log(f"\n===== Track B (HF) @ {NF}帧 greedy, {len(res)}题 =====")
log(f"ALL: {int(res['correct'].sum())}/{len(res)} = {100*res['correct'].mean():.1f}%")
for d in ['short','medium','long']:
    s=res[res.duration==d]; log(f"  {d}: {int(s['correct'].sum())}/{len(s)}")
log(f"对照 baseline @64帧: 10/20=50.0% (short4/7 medium3/7 long3/6)")
log(f"对照 vLLM @96帧(全量2700): short80.3 medium70.3 long59.2 overall69.96")
