#!/usr/bin/env python3
"""Video-MME 自证:server 视频多模态 WS → 多选题准确率。

读 parquet(question+options+answer+videoID+duration)→ 从 videos_chunked zip 找 data/<videoID>.mp4
→ server WS turn_based(video base64 + question/choices)→ generated_text → extract A-D → 准确率。
复用 daily-omni 的 WSClient / wait_ready / extract 模式(同 omni 框架限制:单帧视觉 + audio 30s)。
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
import pyarrow.parquet as pq
import websockets

REPO = Path(__file__).resolve().parents[2]
DATA = Path("/workspace/shared_assets/datasets/lmms-lab/Video-MME")

SYSTEM_PROMPT = (
    "You are a multiple-choice question answering assistant. Based on the given video and its audio, "
    "select the single most accurate answer from the given choices. "
    "Output ONLY a single capital letter representing your choice: A, B, C, or D. "
    "Do NOT generate any explanation, reasoning, or other text. "
    "Your entire response must be exactly one character: the letter."
)


def extract_choice_letter(text):
    if not text:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    m = re.search(r"assistant\s*([\s\S]*)$", raw, re.IGNORECASE)
    candidate = m.group(1).strip() if m else raw
    direct = re.match(r"(?i)^\s*([A-D])(?:[\s.\):：]|$)", candidate)
    if direct:
        return direct.group(1).upper()
    ans = re.search(r"(?i)(?:answer|choice|option|correct\s+answer)\s*(?:is|:)\s*[\*\(]{0,2}\s*([A-D])\b", candidate)
    if ans:
        return ans.group(1).upper()
    loose = list(re.finditer(r"(?:[^A-Za-z]|^)([A-D])(?:[^A-Za-z]|$)", candidate, re.IGNORECASE))
    if loose:
        return loose[-1].group(1).upper()
    return None


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
                return ev.get("text"), None
            if t in ("error", "session.closed"):
                return None, ev
        return None, {"error": "timeout"}

    async def aclose(self):
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None


async def wait_ready(base_url, deadline_s=180):
    deadline = time.time() + deadline_s
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        cli = WSClient(base_url)
        try:
            await cli.connect_init({"mode": "turn_based", "use_tts": False, "system_prompt": ""}, timeout=30)
            await cli.aclose()
            print(f"[warmup] server ready (attempt {attempt})", flush=True)
            return True
        except Exception as e:
            print(f"[warmup] not ready (attempt {attempt}): {type(e).__name__}: {e}", flush=True)
            await cli.aclose()
            await asyncio.sleep(5)
    return False


def build_video_index():
    idx = {}
    for z in sorted(DATA.glob("videos_chunked_*.zip")):
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                if n.endswith(".mp4"):
                    idx[Path(n).stem] = (z, n)
    return idx


def load_video_bytes(idx, video_id):
    if video_id not in idx:
        return None
    z, member = idx[video_id]
    with zipfile.ZipFile(z) as zf:
        return zf.read(member)


async def run_one(base_url, video_bytes, user_text, stack_frames=1, max_attempts=3, backoff=2.0):
    video_b64 = base64.b64encode(video_bytes).decode("ascii")
    last_err = None
    for attempt in range(1, max_attempts + 1):
        cli = WSClient(base_url)
        try:
            await cli.connect_init({"mode": "turn_based", "use_tts": False, "system_prompt": SYSTEM_PROMPT})
        except Exception:
            await cli.aclose()
            await asyncio.sleep(backoff * attempt)
            continue
        try:
            await cli.push({"messages": [{"role": "user", "content": [
                {"type": "video", "data": video_b64, "stack_frames": stack_frames},
                {"type": "text", "text": user_text},
            ]}], "streaming": True, "generation": {"max_new_tokens": 32, "length_penalty": 1.0}})
            text, err = await cli.wait_done(timeout=240)
        except Exception as e:
            text, err = None, {"error": f"{type(e).__name__}: {e}"}
        if cli.session_id:
            try:
                async with httpx.AsyncClient(timeout=60) as c:
                    await c.post(f"{cli.base}/sessions/{cli.session_id}/close", json={"reason": "done"})
            except Exception:
                pass
        await cli.aclose()
        if err is None:
            return text, None, attempt
        last_err = err
        reason = str(err.get("reason") or "")
        if reason not in ("video_decode_failed", "video_frame_prefill_failed", "prefill_failed") and "timeout" not in str(err).lower():
            return text, err, attempt
        await asyncio.sleep(backoff * attempt)
    return None, last_err, max_attempts


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=22500)
    ap.add_argument("--stack-frames", type=int, default=1)
    ap.add_argument("--out", default=str(REPO / "benchmark" / "video-mme" / "result.json"))
    args = ap.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    print("building video index over 20 zips...", flush=True)
    idx = build_video_index()
    print(f"index: {len(idx)} videos", flush=True)

    if not await wait_ready(base_url):
        print("server not ready, abort", flush=True); sys.exit(1)

    pqf = DATA / "videomme" / "test-00000-of-00001.parquet"
    t = pq.read_table(pqf)
    rows = [{c: t.column(c)[i].as_py() for c in t.column_names} for i in range(min(args.limit, t.num_rows))]
    print(f"loaded {len(rows)} Video-MME rows", flush=True)

    results = []
    correct = 0
    for i, row in enumerate(rows):
        vid = row["videoID"]
        vb = load_video_bytes(idx, vid)
        if not vb:
            print(f"[{i}] {vid} ({row.get('duration')}) video NOT FOUND, skip", flush=True)
            continue
        gold = (row.get("answer") or "").strip().upper()
        choices = "\n".join(str(o) for o in row["options"])
        user_text = f"Question: {row['question']}\nChoices:\n{choices}"
        text, err, attempts = await run_one(base_url, vb, user_text, args.stack_frames)
        pred = extract_choice_letter(text) if text else None
        is_correct = bool(pred and gold and pred == gold)
        if is_correct:
            correct += 1
        rec = {"idx": i, "video_id": vid, "duration": row.get("duration"), "domain": row.get("domain"),
               "gold": gold, "pred": pred, "correct": is_correct, "attempts": attempts,
               "gen_text": (text or "")[:150]}
        if err:
            rec["error"] = err
        results.append(rec)
        print(f"[{i}] {vid} dur={row.get('duration')} dom={row.get('domain')} gold={gold} pred={pred} "
              f"{'✓' if is_correct else '✗'} att={attempts} text={text!r}"[:200], flush=True)

    acc = correct / len(results) if results else 0
    summary = {"benchmark": "Video-MME", "n": len(results), "correct": correct,
               "accuracy": round(acc, 4), "baseline_official": 69.0, "threshold": 67.0,
               "caveat": "omni 框架限制同 daily-omni(单帧视觉+audio 30s),长视频(medium/long)严重不足;小样本统计意义有限;基线 69.0 来源待确认",
               "items": results}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== Video-MME 准确率: {correct}/{len(results)} = {acc:.1%} "
          f"(基线 69.0%, 准入 ≥67.0%) ===\n-> {args.out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
