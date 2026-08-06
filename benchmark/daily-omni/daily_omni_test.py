#!/usr/bin/env python3
"""Daily-Omni 自证：server 视频多模态 WS → 多选题准确率。

读 parquet(video+question+candidates+answer) → server WS turn_based(video base64 mp4 + question) → generated_text → extract A-D → 准确率。
server 用 ffmpeg 解码 mp4(ws_handler.cpp extract_video_mp4_media) → frames → vision encoder。

prompt(复用 daily-omni adapter test_utils.py 格式):
- system: "只输出 A/B/C/D"
- user: video + "Question: ... Choices: ..."
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
import pyarrow.parquet as pq
import websockets

REPO = Path(__file__).resolve().parents[2]
DATA_ROOT = Path("/workspace/shared_assets/datasets/MTEB/Daily-Omni/data")

SYSTEM_PROMPT = (
    "You are a multiple-choice question answering assistant. Based on the given video and its audio, "
    "select the single most accurate answer from the given choices. "
    "Output ONLY a single capital letter representing your choice: A, B, C, or D. "
    "Do NOT generate any explanation, reasoning, or other text. "
    "Your entire response must be exactly one character: the letter."
)


# ---- 答案提取(对齐官方 testmodel.py + 对 thinking 输出更宽容) ----
def extract_choice_letter(text):
    if not text:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    match = re.search(r"assistant\s*([\s\S]*)$", raw, re.IGNORECASE)
    candidate = match.group(1).strip() if match else raw
    # 1) 开头直接 [A-D](理想:模型只输出字母)
    direct = re.match(r"(?i)^\s*([A-D])(?:[\s.\):：]|$)", candidate)
    if direct:
        return direct.group(1).upper()
    # 2) "answer/choice/option is X" / "X is correct"(thinking 后的明确答案)
    ans = re.search(r"(?i)(?:answer|choice|option|correct\s+answer)\s*(?:is|:)\s*[\*\(]{0,2}\s*([A-D])\b", candidate)
    if ans:
        return ans.group(1).upper()
    # 3) 末尾独立 [A-D](最终答案常在末尾;避免误提 choices 里的选项字母)
    loose = list(re.finditer(r"(?:[^A-Za-z]|^)([A-D])(?:[^A-Za-z]|$)", candidate, re.IGNORECASE))
    if loose:
        return loose[-1].group(1).upper()
    return None


def normalize_gold(gold):
    g = (gold or "").strip().upper()
    if len(g) == 1 and g in "ABCD":
        return g
    m = re.search(r"([ABCD])\b", g)
    return m.group(1).upper() if m else None


# ---- WSClient(复用 gen_tts.py 模式,改 use_tts=false + video input) ----
def _ws_url(base_url, path="/backend"):
    p = urlsplit(f"{base_url.rstrip('/')}/{path.lstrip('/')}")
    scheme = "ws" if p.scheme == "http" else ("wss" if p.scheme == "https" else p.scheme)
    return urlunsplit((scheme, p.netloc, p.path, p.query, p.fragment))


class WSClient:
    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        self.ws = None
        self.session_id = None

    async def connect_init(self, payload, timeout=150):
        self.ws = await websockets.connect(_ws_url(self.base), max_size=256 * 1024 * 1024,
                                           ping_interval=None, ping_timeout=None)
        await self.ws.send(json.dumps({"type": "session.init", "payload": payload}))
        ev = await asyncio.wait_for(self._recv(), timeout=timeout)
        if ev.get("type") not in ("session.created", "initialized"):
            raise RuntimeError(f"init failed: {ev}")
        self.session_id = ev.get("session_id")
        return ev

    async def push(self, inp):
        await self.ws.send(json.dumps({"type": "input.append", "input": inp}))

    async def _recv(self):
        raw = await self.ws.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def wait_done(self, timeout=240):
        deadline = time.time() + timeout
        while time.time() < deadline:
            ev = await self._recv()
            t = ev.get("type")
            if t == "response.done":
                return ev.get("text"), ev.get("metrics"), None
            if t in ("error", "session.closed"):
                return None, None, ev
        return None, None, {"error": "timeout"}

    async def aclose(self):
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None


async def run_one(base_url, video_bytes, question, candidates, stack_frames=1):
    """单条: server WS turn_based(video mp4 base64 + question/choices) → generated_text。"""
    video_b64 = base64.b64encode(video_bytes).decode("ascii")
    choices_text = "\n".join(str(c) for c in candidates)
    user_text = f"Question: {question}\nChoices:\n{choices_text}"
    cli = WSClient(base_url)
    try:
        await cli.connect_init({"mode": "turn_based", "use_tts": False, "system_prompt": SYSTEM_PROMPT})
    except Exception:
        await cli.aclose()
        raise
    try:
        await cli.push({"messages": [{"role": "user", "content": [
            {"type": "video", "data": video_b64, "stack_frames": stack_frames},
            {"type": "text", "text": user_text},
        ]}], "streaming": True, "generation": {"max_new_tokens": 32, "length_penalty": 1.0}})
        text, metrics, err = await cli.wait_done(timeout=240)
    except Exception as e:
        text, metrics, err = None, None, {"error": f"{type(e).__name__}: {e}"}
    # HTTP close 释放 server active session
    if cli.session_id:
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                await c.post(f"{cli.base}/sessions/{cli.session_id}/close", json={"reason": "done"})
        except Exception:
            pass
    await cli.aclose()
    return text, err


# ---- 就绪探测 + 瞬态重试 (治本: 防启动初期 omni_context 懒加载 / ffmpeg 瞬态失败) ----
# /health 恒返回 ok 且不反映模型加载状态,不能作就绪门槛;改用真实 WS session.init 探针。
# 仅对瞬态错误重试;确定性错误(invalid_json / omni_init_failed / mode_mismatch /
# missing_audio / empty_messages 等)重试无意义,立即放弃。

TRANSIENT_REASONS = {
    "video_decode_failed",
    "video_frame_prefill_failed",
    "prefill_failed",
    "system_prefill_failed",
    "activate_failed",
}


def _is_transient(err):
    """True if err looks like a transient / network / readiness failure worth retrying."""
    if not err:
        return False
    reason = str(err.get("reason") or "").lower()
    etype = str(err.get("type") or err.get("error") or "").lower()
    if reason in TRANSIENT_REASONS:
        return True
    return any(k in etype for k in ("timeout", "closed", "connection", "refused", "reset"))


async def wait_ready(base_url, deadline_s=180):
    """Probe readiness via a throwaway turn_based session (triggers omni_context lazy load)."""
    deadline = time.time() + deadline_s
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        cli = WSClient(base_url)
        try:
            await cli.connect_init({"mode": "turn_based", "use_tts": False, "system_prompt": ""},
                                   timeout=30)
            await cli.aclose()
            print(f"[warmup] server ready (attempt {attempt})", flush=True)
            return True
        except Exception as e:
            print(f"[warmup] not ready yet (attempt {attempt}): {type(e).__name__}: {e}",
                  flush=True)
            await cli.aclose()
            await asyncio.sleep(5)
    return False


async def run_one_with_retry(base_url, video_bytes, question, candidates,
                             max_attempts=3, backoff=2.0, stack_frames=1):
    """run_one with transient-only retry. Each attempt uses a fresh WSClient + session.

    Returns (text, err, attempts); err is None on success.
    """
    last_text, last_err = None, None
    for attempt in range(1, max_attempts + 1):
        try:
            text, err = await run_one(base_url, video_bytes, question, candidates,
                                      stack_frames=stack_frames)
        except Exception as e:
            text, err = None, {"error": f"{type(e).__name__}: {e}"}
        if err is None:
            return text, None, attempt
        if not _is_transient(err):
            return text, err, attempt
        last_text, last_err = text, err
        if attempt < max_attempts:
            await asyncio.sleep(backoff * attempt)  # linear backoff 2s, 4s
    return last_text, last_err, max_attempts


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=22500)
    ap.add_argument("--out", default=str(REPO / "benchmark" / "daily-omni" / "result.json"))
    ap.add_argument("--stack-frames", type=int, default=1,
                    help="视频采帧数; 默认1 —— 实测 stack_frames>=2 触发 omni 输出 audio token 流(乱码),见 experiments.md P7")
    args = ap.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    print(f"probing readiness at {base_url} ...", flush=True)
    if not await wait_ready(base_url):
        print("server not ready within deadline, abort", flush=True)
        sys.exit(1)
    # 读 parquet(跨 shards 攒 limit 条)
    rows = []
    for f in sorted(DATA_ROOT.glob("test-*.parquet")):
        t = pq.read_table(f)
        for i in range(t.num_rows):
            rows.append({c: t.column(c)[i].as_py() for c in t.column_names})
            if len(rows) >= args.limit:
                break
        if len(rows) >= args.limit:
            break
    print(f"loaded {len(rows)} Daily-Omni rows", flush=True)

    results = []
    correct = 0
    for i, row in enumerate(rows):
        video_field = row["video"]
        video_bytes = video_field["bytes"] if isinstance(video_field, dict) else video_field
        gold = normalize_gold(row["answer"])
        text, err, attempts = await run_one_with_retry(base_url, video_bytes,
                                                       row["question"], row["candidates"],
                                                       stack_frames=args.stack_frames)
        pred = extract_choice_letter(text) if text else None
        is_correct = bool(pred and gold and pred == gold)
        if is_correct:
            correct += 1
        rec = {"idx": i, "video_id": row.get("video_id", ""), "gold": gold, "pred": pred,
               "gen_text": (text or "")[:150], "correct": is_correct, "attempts": attempts}
        if err:
            rec["error"] = err  # may carry server diagnostic.message (ffmpeg rc/stderr)
        results.append(rec)
        print(f"[{i}] {row.get('video_id','')} gold={gold} pred={pred} "
              f"{'✓' if is_correct else '✗'} att={attempts} text={text!r}"[:200], flush=True)

    acc = correct / len(results) if results else 0
    summary = {"benchmark": "Daily-Omni", "n": len(results), "correct": correct,
               "accuracy": round(acc, 4), "baseline_official": 0.795, "threshold": 0.775,
               "caveat": "F16 不改推理数学 → 预期≈基线 79.5%; 小样本统计意义有限",
               "items": results}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== Daily-Omni 准确率: {correct}/{len(results)} = {acc:.1%} "
          f"(基线 79.5%, 准入 ≥77.5%) ===\n-> {args.out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
