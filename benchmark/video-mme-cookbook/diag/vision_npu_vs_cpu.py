"""
视觉编码 NPU vs CPU 数值对比诊断（只读 · 非破坏性）。

目的: 判断 910B NPU 的 vision encoder 算子是否有精度 bug。
方法: 同一张图、同一预处理, model.vpm 分别 .to("npu")/.to("cpu") 跑, 对比 last_hidden_state。
  - 绕过 LLM/Resampler (只跑 SiglipVisionTransformer = model.vpm), 最干净
  - max_slice_nums=1 (单切片, 排除 slice/padding 干扰)
  - fp16 为主 (匹配推理); 分层: patch_embedding(Conv2d) 后 vs 完整 vpm 后

判定:
  cos>0.999 & max-abs~1e-2 = 健康(fp16噪声); cos<0.99 或 max-abs~1e0/NaN = NPU算子bug

不改任何源码/权重/二进制 — 只加载模型跑推理对比。venv-trackb(torch_npu)。
"""
import os, subprocess, tempfile, glob
os.environ.setdefault("ASCEND_RT_VISIBLE_DEVICES", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")

MODEL = "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5"
VIDEO = "/workspace/user_data/verify-ascend-2026-08-10/videomme-data/fFjv93ACGo8.mp4"

def log(*a): print(*a, flush=True)

log("importing torch/torch_npu ...")
import torch, torch_npu
import torch.nn.functional as F
from transformers import AutoModel, AutoProcessor
from PIL import Image

# ---- 抽 3 帧(不同时间点) ----
def extract_frames(video, n=3):
    tmp = tempfile.mkdtemp(prefix="vpm_diag_")
    import math
    # 先拿 duration
    dur = float(subprocess.check_output(
        ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",video]).decode().strip())
    frames = []
    for i in range(n):
        t = dur * (i+1) / (n+1)
        out = os.path.join(tmp, f"f{i}.jpg")
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-ss",f"{t:.2f}",
                        "-i",video,"-frames:v","1","-q:v","2","-y",out],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(out):
            frames.append(Image.open(out).convert("RGB"))
    return frames

log("loading model (fp16, cpu initially)...")
processor = AutoProcessor.from_pretrained(MODEL, trust_remote_code=True)
model = AutoModel.from_pretrained(MODEL, trust_remote_code=True, torch_dtype=torch.float16).eval()
log(f"vpm class={type(model.vpm).__name__} | vpm device={next(model.vpm.parameters()).device}")

frames = extract_frames(VIDEO, 3)
log(f"extracted {len(frames)} frames")

def prep(img):
    """单图预处理(max_slice_nums=1) → vpm 输入张量(基于 modeling_minicpmo get_vision_embedding 内部逻辑)。"""
    ip = processor.image_processor.preprocess([img], max_slice_nums=1, return_tensors="pt")
    pixel_values_list = ip["pixel_values"]
    tgt_sizes = [torch.tensor(s) for s in ip["tgt_sizes"][0]]
    all_pv = []
    for pixel_values in pixel_values_list:
        all_pv.extend([i.flatten(end_dim=1).permute(1, 0) for i in pixel_values])
    tgt_sizes_t = torch.vstack([t for t in tgt_sizes if isinstance(t, torch.Tensor)]).type(torch.int32)
    max_patches = int((tgt_sizes_t[:, 0] * tgt_sizes_t[:, 1]).max())
    all_pv = torch.nn.utils.rnn.pad_sequence(all_pv, batch_first=True, padding_value=0.0)
    B, L, _ = all_pv.shape
    return all_pv, tgt_sizes_t, max_patches, B, L

def run_full_vpm(device, all_pv, tgt_sizes_t, max_patches, B, L):
    model.vpm.to(device)
    dtype = model.vpm.embeddings.patch_embedding.weight.dtype
    all_pv_d = all_pv.permute(0, 2, 1).reshape(B, 3, -1, L).type(dtype).to(device)
    mask = torch.zeros((B, 1, max_patches), dtype=torch.bool, device=device)
    for i in range(B):
        mask[i, 0, :tgt_sizes_t[i][0] * tgt_sizes_t[i][1]] = True
    tgt_sizes_d = tgt_sizes_t.to(device)
    with torch.inference_mode():
        out = model.vpm(all_pv_d, patch_attention_mask=mask, tgt_sizes=tgt_sizes_d).last_hidden_state
    return out.float().cpu()

def cmp(name, a, b):
    a, b = a.float(), b.float()
    diff = (a - b).abs()
    cos = F.cosine_similarity(a.flatten().unsqueeze(0), b.flatten().unsqueeze(0)).item()
    has_nan = torch.isnan(a).any().item() or torch.isnan(b).any().item()
    log(f"  {name:22s} max-abs={diff.max().item():.5f}  mean-abs={diff.mean().item():.6f}  "
        f"cos={cos:.6f}  NaN={has_nan}")

log("\n========== 路径A: vpm NPU vs CPU 特征对比 (fp16) ==========")
for i, img in enumerate(frames):
    log(f"\n--- frame {i} ---")
    all_pv, tgt_sizes_t, max_patches, B, L = prep(img)
    log(f"  B={B} L={L} max_patches={max_patches}")
    out_npu = run_full_vpm("npu", all_pv, tgt_sizes_t, max_patches, B, L)
    out_cpu = run_full_vpm("cpu", all_pv, tgt_sizes_t, max_patches, B, L)
    cmp("full_vpm_last_hidden", out_npu, out_cpu)

log("\n========== 判定 ==========")
log("cos>0.999 & max-abs~1e-2 = 健康(NPU vision算子无bug, fp16噪声)")
log("cos<0.99 或 max-abs~1e0/NaN = NPU vision算子有bug → 代码层面可能有路径")
