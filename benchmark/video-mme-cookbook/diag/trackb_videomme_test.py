"""
赛道B 对照测试：MiniCPM-o 4.5 via transformers + torch_npu @ 910B。
决定性问题：同样的 64 帧视频 prefill，PyTorch/torch_npu 后端是否也退化（输出 `_`/NaN），
还是正常？→ 区分"llama.cpp-CANN 后端 bug" vs "910B 硬件上限"。

阶段（一次加载跑完，摊销 CANN init 慢启动）：
  A 文本生成（LLM 骨干 on NPU）
  B 单图 chat（视觉路径 on NPU）
  C 8帧 / 64帧 视频 MCQ（退化测试本体）
"""
import os, sys, time, glob, tempfile, subprocess, csv, ast
os.environ.setdefault("ASCEND_RT_VISIBLE_DEVICES", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

MODEL = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5"
VIDEOS = "/workspace/user_data/verify-ascend-2026-08-10/videomme-data"
SEL = "/workspace/user_data/claude_code/minicpm-ascend-challenge/benchmark/video-mme-cookbook/diag/selected_questions.csv"

def log(*a): print(*a, flush=True)

def extract_frames(video_path, n):
    tmp = tempfile.mkdtemp(prefix="tb_frm_")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video_path,
                    "-vf", "fps=1", "-q:v", "2", os.path.join(tmp, "f%05d.jpg")], check=True)
    files = sorted(glob.glob(os.path.join(tmp, "f*.jpg")))
    if len(files) > n:
        if n > 1:
            idx = [int(i * (len(files) - 1) / (n - 1)) for i in range(n)]
        else:
            idx = [0]
        files = [files[i] for i in idx]
    from PIL import Image
    return [Image.open(f).convert("RGB") for f in files]

def is_degraded(s):
    s = (s or "").strip()
    if not s:
        return True
    if set(s) <= {"_", "\n", " ", "?"}:
        return True
    # 高重复（同一 token 串 ≥6 次且无实质内容）
    return len(s) > 12 and len(set(s)) <= 3

# ---------- load ----------
t0 = time.time()
log("importing torch/torch_npu ...")
import torch, torch_npu
from transformers import AutoModel, AutoTokenizer, AutoProcessor
log(f"imports done {time.time()-t0:.0f}s")

log("loading tokenizer/processor/model (fp16 → npu) ...")
tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
processor = AutoProcessor.from_pretrained(MODEL, trust_remote_code=True)
model = AutoModel.from_pretrained(MODEL, trust_remote_code=True, torch_dtype=torch.float16).to("npu").eval()
log(f"LOADED {time.time()-t0:.0f}s | class={type(model).__name__} | dev={next(model.parameters()).device}")

def chat(content, max_new=64):
    msgs = [{"role": "user", "content": content}]
    t = time.time()
    resp = model.chat(image=None, msgs=msgs, tokenizer=tok, processor=processor,
                      max_new_tokens=max_new, do_sample=False, omni_mode=False,
                      max_slice_nums=1)  # 统一切片数，避免多图 patch 维度不齐
    return resp, time.time() - t

# ---------- Stage A: text-only ----------
log("\n=== Stage A: text-only generate ===")
try:
    r, dt = chat("What is 2+3? Reply with only the number.", max_new=8)
    log(f"A resp={r!r} ({dt:.1f}s) degraded={is_degraded(r)}")
except Exception as e:
    log(f"A FAILED: {type(e).__name__}: {e}")

# ---------- Stage B: single image ----------
log("\n=== Stage B: single-image chat ===")
try:
    import pandas as pd
    df = pd.read_csv(SEL)
    row = df.iloc[0]
    vp = os.path.join(VIDEOS, f"{row['videoID']}.mp4")
    fr = extract_frames(vp, 1)
    r, dt = chat([fr[0], "Describe this image in one short sentence."], max_new=40)
    log(f"B resp={r!r} ({dt:.1f}s) degraded={is_degraded(r)}")
except Exception as e:
    log(f"B FAILED: {type(e).__name__}: {e}")

# ---------- Stage C: 8-frame & 64-frame VideoMME MCQ ----------
log("\n=== Stage C: multi-frame VideoMME (degradation test) ===")
import pandas as pd
df = pd.read_csv(SEL)
# 1 short + 1 medium + 1 long = 3 题，每题测 8帧 和 64帧（够判退化 + 时长依赖）
sample = list(df[df.duration == "short"].head(1).itertuples()) + \
         list(df[df.duration == "medium"].head(1).itertuples()) + \
         list(df[df.duration == "long"].head(1).itertuples())
for nf in [8, 64]:
    log(f"\n--- frames={nf} ---")
    for row in sample:
        vp = os.path.join(VIDEOS, f"{row.videoID}.mp4")
        try:
            fr = extract_frames(vp, nf)
            opts = ast.literal_eval(row.options) if isinstance(row.options, str) else list(row.options)
            qtxt = f"{row.question}\n" + "\n".join(f"{chr(65+i)}. {o}" for i, o in enumerate(opts)) + \
                   "\n\nReply with only the letter of the correct answer."
            r, dt = chat([*fr, qtxt], max_new=16)
            log(f"[f={nf} {row.duration} {row.question_id}] GT={row.answer} resp={r!r} ({dt:.1f}s) degraded={is_degraded(r)} pred_match={(r or '').strip()[:1]==row.answer}")
        except Exception as e:
            log(f"[f={nf} {row.duration} {row.question_id}] FAILED: {type(e).__name__}: {e}")

log("\nALL DONE")
