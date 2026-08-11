"""
Track B 诊断对比: torch_npu/HF 参考实现 vs llama.cpp-omni,同 20 题、同 prompt、64帧、greedy。
隔离"视觉 encoder/预处理"变量 —— 若 Track B ≫ 50%,坐实 llama.cpp 视觉为框架上限。
"""
import os, sys, time, glob, tempfile, subprocess, ast, csv
os.environ.setdefault("ASCEND_RT_VISIBLE_DEVICES", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
COOK = "/workspace/user_data/claude_code/minicpm-ascend-challenge/benchmark/video-mme-cookbook"
sys.path.insert(0, COOK)
from eval_cpp_pipeline import extract_answer          # 同 llama.cpp-omni 的答案抽取
from eval_cpp_config import USER_PROMPT_TEMPLATE      # 同 prompt(隔离视觉变量)
import pandas as pd

MODEL = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5"
VIDEOS = "/workspace/user_data/verify-ascend-2026-08-10/videomme-data"
SEL = os.path.join(COOK, "diag/selected_questions.csv")
OUT = os.path.join(COOK, "diag/trackb_accuracy_20q.csv")
NF = 64

def log(*a): print(*a, flush=True)

def extract_frames(video_path, n):
    tmp = tempfile.mkdtemp(prefix="tb_acc_")
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-i",video_path,"-vf","fps=1","-q:v","2",
                    os.path.join(tmp,"f%05d.jpg")], check=True)
    files = sorted(glob.glob(os.path.join(tmp,"f*.jpg")))
    if len(files) > n:
        idx = [int(i*(len(files)-1)/(n-1)) for i in range(n)] if n > 1 else [0]
        files = [files[i] for i in idx]
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
log(f"running {len(pick)} questions @ {NF} frames (torch_npu/HF, greedy, max_slice_nums=1)...")

with open(OUT,"w",newline="") as f:
    w=csv.writer(f); w.writerow(["duration","videoID","question_id","GT","pred","correct","raw"])
    for i, row in pick.iterrows():
        vp = os.path.join(VIDEOS, f"{row['videoID']}.mp4")
        opts = ast.literal_eval(row['options']) if isinstance(row['options'],str) else list(row['options'])
        try:
            fr = extract_frames(vp, NF)
            prompt = USER_PROMPT_TEMPLATE.format(question=row['question'], options="\n".join(map(str,opts)))
            raw = chat([*fr, prompt]) or ""
            pred = extract_answer(raw)
            correct = (pred == str(row['answer']))
        except Exception as e:
            raw=f"ERR:{type(e).__name__}:{e}"; pred=""; correct=False
        w.writerow([row['duration'],row['videoID'],row['question_id'],row['answer'],pred,int(correct),str(raw)[:80]])
        log(f"[{i+1}/{len(pick)} {row['duration']} {row['question_id']}] GT={row['answer']} pred={pred!r} {'✅' if correct else '❌'}")

res = pd.read_csv(OUT)
log(f"\n===== Track B (torch_npu/HF) @ {NF}帧 greedy, {len(res)}题 =====")
log(f"ALL: {int(res['correct'].sum())}/{len(res)} = {100*res['correct'].mean():.1f}%")
for d in ['short','medium','long']:
    s=res[res.duration==d]; log(f"  {d}: {int(s['correct'].sum())}/{len(s)}")
log(f"对照 llama.cpp-omni(同20题 64帧 greedy): 10/20 = 50.0%  (short 4/7, medium 3/7, long 3/6)")
