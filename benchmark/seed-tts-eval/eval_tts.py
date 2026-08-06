#!/usr/bin/env python3
"""TTS-Seed 评测脚本：对 gen_tts.py 产物算 SIM(WavLM cosine) + 中文 WER(paraformer+jiwer)。

复用 benchmark/seed-tts-eval/eval_ref/seed_tts_eval.py 的纯算法函数（复制，绕开 vllm/vllm_omni import）。
口径：与 Bytedance seed-tts-eval/run_wer.py 对齐（paraformer-zh + zhconv + jiwer 字符级）。
SIM 用 microsoft/wavlm-base-plus（非官方 fine-tuned SV checkpoint，数值仅供内部一致性，不直接比基线 0.709）。

env:
  SEED_TTS_WAVLM_MODEL  WavLM 模型（本地路径或 HF id；HF 封 → 预下到本地用 modelscope）
  SEED_TTS_SIM_DEVICE   SIM 设备（默认 cpu）
  SEED_TTS_EVAL_DEVICE  ASR 设备（默认 cpu）
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import string
import threading
from pathlib import Path
from typing import Any

import numpy as np

# =============================================================================
# 复用自 eval_ref/seed_tts_eval.py（纯函数，去掉 vllm 依赖）。来源行号标注。
# =============================================================================

_lock = threading.Lock()
_device: str | None = None
_wavlm_model = None
_wavlm_processor = None
_wavlm_device: str | None = None
_zh_paraformer = None


def _get_eval_device() -> str:  # seed_tts_eval.py:120
    explicit = os.environ.get("SEED_TTS_EVAL_DEVICE", "").strip()
    if explicit:
        return explicit
    try:
        import torch
        return "cuda:0" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _punctuation_all() -> str:  # seed_tts_eval.py:132
    from zhon.hanzi import punctuation
    return punctuation + string.punctuation


def _jiwer_wer(reference: str, hypothesis: str) -> float:  # seed_tts_eval.py:138
    try:
        from jiwer import compute_measures
        return float(compute_measures(reference, hypothesis)["wer"])
    except ImportError:
        import jiwer
        out = jiwer.process_words(reference, hypothesis)
        return float(out.wer)


def process_one_official(hypo: str, truth: str, lang: str):  # seed_tts_eval.py:154
    raw_truth, raw_hypo = truth, hypo
    truth_n, hypo_n = truth, hypo
    for x in _punctuation_all():
        if x == "'":
            continue
        truth_n = truth_n.replace(x, "")
        hypo_n = hypo_n.replace(x, "")
    truth_n = truth_n.replace(" ", " ")
    hypo_n = hypo_n.replace(" ", " ")
    if lang == "zh":
        truth_n = " ".join([x for x in truth_n])
        hypo_n = " ".join([x for x in hypo_n])
    elif lang == "en":
        truth_n = truth_n.lower()
        hypo_n = hypo_n.lower()
    else:
        raise ValueError(f"unsupported lang {lang!r}")
    return _jiwer_wer(truth_n, hypo_n), raw_truth, raw_hypo


def _audio_path_to_f32_16k(path: str) -> np.ndarray:  # seed_tts_eval.py:215
    import scipy.signal
    import soundfile as sf
    data, sr = sf.read(path, dtype="float32", always_2d=True)
    mono = np.mean(data, axis=1).astype(np.float32)
    if int(sr) == 16000:
        return mono
    target_len = max(1, int(len(mono) * 16000 / int(sr)))
    return scipy.signal.resample(mono, target_len).astype(np.float32)


def _ensure_wavlm_sim() -> None:  # seed_tts_eval.py:227
    global _wavlm_model, _wavlm_processor, _wavlm_device
    with _lock:
        if _wavlm_model is not None:
            return
        from transformers import AutoFeatureExtractor, AutoModel
        mid = os.environ.get("SEED_TTS_WAVLM_MODEL", "microsoft/wavlm-base-plus").strip() or "microsoft/wavlm-base-plus"
        _wavlm_device = os.environ.get("SEED_TTS_SIM_DEVICE", "").strip() or _get_eval_device()
        print(f"[wavlm] loading {mid!r} on {_wavlm_device} (base-plus, NOT official fine-tuned SV — SIM for internal consistency only)", flush=True)
        _wavlm_processor = AutoFeatureExtractor.from_pretrained(mid)
        _wavlm_model = AutoModel.from_pretrained(mid).to(_wavlm_device)
        _wavlm_model.eval()


def _wavlm_prepare_waveform(wav):  # seed_tts_eval.py:247
    max_sec = float(os.environ.get("SEED_TTS_WAVLM_MAX_SECONDS", "30"))
    cap = int(max_sec * 16000)
    w = np.asarray(wav, dtype=np.float32).reshape(-1)
    if len(w) == 0:
        return w
    if len(w) > cap:
        w = w[:cap].copy()
    min_samples = int(os.environ.get("SEED_TTS_WAVLM_MIN_SAMPLES", "4000"))
    if len(w) < min_samples:
        w = np.pad(w, (0, min_samples - len(w)), mode="constant")
    return w


def _wavlm_mean_embedding_f32_16k(wav):  # seed_tts_eval.py:263
    import torch
    _ensure_wavlm_sim()
    w = _wavlm_prepare_waveform(wav)
    if len(w) == 0:
        return None
    try:
        inputs = _wavlm_processor(w, sampling_rate=16000, return_tensors="pt", padding=False, return_attention_mask=True)
    except TypeError:
        inputs = _wavlm_processor(w, sampling_rate=16000, return_tensors="pt", padding=False)
    iv = inputs["input_values"].to(_wavlm_device)
    am = inputs.get("attention_mask")
    if am is not None:
        am = am.to(_wavlm_device)
    with torch.inference_mode():
        out = _wavlm_model(iv, attention_mask=am)
        h = out.last_hidden_state
        v = h.mean(dim=1).squeeze(0).float().cpu().numpy()
    n = float(np.linalg.norm(v))
    if not np.isfinite(n) or n < 1e-8:
        return None
    return (v / n).astype(np.float32)


def _cosine_similarity_unit_vectors(a, b) -> float:  # seed_tts_eval.py:302
    return float(np.dot(a, b))


def _ensure_zh_asr() -> None:  # seed_tts_eval.py:420
    global _zh_paraformer, _device
    with _lock:
        if _zh_paraformer is not None:
            return
        from funasr import AutoModel
        _device = _get_eval_device()
        print(f"[zh-asr] loading paraformer-zh on {_device} (funasr, first run downloads from modelscope)", flush=True)
        try:
            _zh_paraformer = AutoModel(model="paraformer-zh", device=_device)
        except TypeError:
            _zh_paraformer = AutoModel(model="paraformer-zh")


def _transcribe_zh_wav_path(wav_path: str) -> str:  # seed_tts_eval.py:478
    import zhconv
    _ensure_zh_asr()
    with _lock:
        res = _zh_paraformer.generate(input=wav_path, batch_size_s=300)
    transcription = res[0]["text"] if res else ""
    return zhconv.convert(transcription, "zh-cn").strip()


# =============================================================================
# 主逻辑
# =============================================================================

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="gen/{locale}/manifest.jsonl")
    ap.add_argument("--locale", default="zh")
    ap.add_argument("--out", default=None, help="result.json 输出路径")
    ap.add_argument("--baseline-sim", type=float, default=0.709)
    ap.add_argument("--baseline-wer", type=float, default=1.414)
    ap.add_argument("--no-sim", action="store_true")
    ap.add_argument("--no-wer", action="store_true")
    args = ap.parse_args()

    sim_on = not args.no_sim
    wer_on = not args.no_wer and args.locale == "zh"
    rows = [json.loads(l) for l in Path(args.manifest).read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"manifest: {len(rows)} rows | SIM={sim_on} WER={wer_on}", flush=True)

    results = []
    for i, rec in enumerate(rows):
        gen_path = rec.get("gen_path")
        if not gen_path or not Path(gen_path).is_file():
            print(f"[{i}] {rec.get('utt')} SKIP (no gen_path)", flush=True)
            continue
        out_rec: dict[str, Any] = {
            "utt": rec.get("utt"), "target": rec.get("target"),
            "gen_text": rec.get("gen_text"), "gen_path": gen_path,
        }
        if sim_on:
            try:
                e_ref = _wavlm_mean_embedding_f32_16k(_audio_path_to_f32_16k(rec["ref_path"]))
                e_gen = _wavlm_mean_embedding_f32_16k(_audio_path_to_f32_16k(gen_path))
                if e_ref is not None and e_gen is not None:
                    out_rec["sim"] = round(_cosine_similarity_unit_vectors(e_ref, e_gen), 4)
            except Exception as e:
                out_rec["sim_error"] = f"{type(e).__name__}: {e}"
        if wer_on:
            try:
                hyp = _transcribe_zh_wav_path(gen_path)
                wer, _, _ = process_one_official(hyp, rec["target"], "zh")
                out_rec["asr"] = hyp
                out_rec["wer"] = round(wer, 4)
            except Exception as e:
                out_rec["wer_error"] = f"{type(e).__name__}: {e}"
        print(f"[{i}] {rec.get('utt')} sim={out_rec.get('sim')} wer={out_rec.get('wer')} "
              f"asr={out_rec.get('asr','')[:40]!r}", flush=True)
        results.append(out_rec)

    sims = [r["sim"] for r in results if "sim" in r]
    wers = [r["wer"] for r in results if "wer" in r]
    summary = {
        "locale": args.locale,
        "n_total": len(rows),
        "n_evaluated": len(results),
        "n_sim": len(sims),
        "sim_mean": round(statistics.fmean(sims), 4) if sims else None,
        "sim_median": round(statistics.median(sims), 4) if sims else None,
        "n_wer": len(wers),
        "wer_mean": round(statistics.fmean(wers), 4) if wers else None,
        "wer_median": round(statistics.median(wers), 4) if wers else None,
        "baseline_sim_official": args.baseline_sim,
        "baseline_wer_official": args.baseline_wer,
        "caveat": "SIM 用 microsoft/wavlm-base-plus（非官方 fine-tuned SV checkpoint），数值不直接可比基线 0.709，仅供内部一致性；WER 与官方同口径（paraformer+zhconv+jiwer）可比。",
        "items": results,
    }
    out_path = Path(args.out) if args.out else Path(args.manifest).with_name("result.json")
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 汇总 =====")
    print(f"SIM: n={len(sims)} mean={summary['sim_mean']} median={summary['sim_median']} (基线 0.709, 口径偏差)")
    print(f"WER: n={len(wers)} mean={summary['wer_mean']} median={summary['wer_median']} (基线 1.414, 同口径可比)")
    print(f"-> {out_path}")


if __name__ == "__main__":
    main()
