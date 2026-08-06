#!/usr/bin/env python3
"""TTS-Seed 生成脚本：用 llama-omni-server (turn_based WS /backend) 批量生成 TTS wav。

自建 WS 客户端（ping_interval=None 避免 keepalive timeout）。每条新 session（ref 不同）+
HTTP /sessions/{id}/close 同步释放（server 仅 1 个 active session）。
- ref 音频(prompt-wavs, 24kHz) → 16kHz float32 PCM → base64 → session.init voice.tts_ref_audio
- input.append(messages=[user:target], streaming=False, use_tts_template=True) → response.done.audio(base64 f32 PCM)
- 产物 gen/{locale}/{utt}.wav + manifest.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
import numpy as np
import scipy.signal
import soundfile as sf
import websockets

REPO = Path(__file__).resolve().parents[2]
SEED_ROOT = REPO / "benchmark" / "seed-tts-eval" / "seedtts_testset"


def load_meta(locale: str, limit: int) -> list[dict]:
    meta = SEED_ROOT / locale / "meta.lst"
    rows: list[dict] = []
    for line in meta.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if len(parts) < 4:
            continue
        rows.append({"utt": parts[0].strip(), "ref_text": parts[1].strip(),
                     "wav_rel": parts[2].strip(), "target": parts[3].strip()})
        if len(rows) >= limit:
            break
    return rows


def ref_to_b64_f32_16k(wav_path: Path) -> tuple[str, int]:
    data, sr = sf.read(str(wav_path), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if int(sr) != 16000:
        data = scipy.signal.resample(data, int(len(data) * 16000 / int(sr))).astype("float32")
    return base64.b64encode(data.astype(np.float32).tobytes()).decode("ascii"), len(data)


def _ws_url(base_url: str, path: str = "/backend") -> str:
    p = urlsplit(f"{base_url.rstrip('/')}/{path.lstrip('/')}")
    scheme = "ws" if p.scheme == "http" else ("wss" if p.scheme == "https" else p.scheme)
    return urlunsplit((scheme, p.netloc, p.path, p.query, p.fragment))


class WSClient:
    """轻量 WS 客户端：ping_interval=None 禁 keepalive（避免长生成时 WS 被 ping 超时关）。"""
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.ws = None
        self.session_id: str | None = None

    async def connect_init(self, payload: dict) -> dict:
        self.ws = await websockets.connect(_ws_url(self.base), max_size=128 * 1024 * 1024,
                                           ping_interval=None, ping_timeout=None)
        await self.ws.send(json.dumps({"type": "session.init", "payload": payload}))
        ev = await self._recv()
        if ev.get("type") not in ("session.created", "initialized"):
            raise RuntimeError(f"init failed: {ev}")
        self.session_id = ev.get("session_id")
        return ev

    async def push(self, inp: dict) -> None:
        await self.ws.send(json.dumps({"type": "input.append", "input": inp}))

    async def _recv(self) -> dict:
        raw = await self.ws.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def wait_done(self, timeout: float = 180.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            ev = await self._recv()
            t = ev.get("type")
            if t == "response.done":
                return ev.get("text"), ev.get("audio"), ev.get("metrics"), None
            if t in ("error", "session.closed"):
                return None, None, None, ev
        return None, None, None, {"error": "timeout"}

    async def aclose(self) -> None:
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None


async def run_one(base_url: str, target: str, ref_b64: str):
    """单条：新 session（带 ref）→ push → response.done → HTTP /sessions/{id}/close 同步释放。"""
    cli = WSClient(base_url)
    try:
        await cli.connect_init({"mode": "turn_based", "use_tts": True,
                                "voice": {"tts_ref_audio": ref_b64, "ref_audio": ref_b64}})
    except Exception:
        await cli.aclose()
        raise
    try:
        await cli.push({"messages": [{"role": "user", "content": target}],
                        "streaming": False, "use_tts_template": True})
        text, audio_b64, metrics, err = await cli.wait_done()
    except Exception as e:
        text, audio_b64, metrics, err = None, None, None, {"error": f"{type(e).__name__}: {e}"}
    # HTTP close：server-omni.cpp 该端点同步 omni_prepare_for_reuse + session_mgr.close（释放 active session）
    if cli.session_id:
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(f"{cli.base}/sessions/{cli.session_id}/close", json={"reason": "done"})
                r.raise_for_status()
        except Exception:
            pass
    await cli.aclose()
    return text, audio_b64, metrics, err


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--locale", default="zh")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=22500)
    ap.add_argument("--sample-rate", type=int, default=24000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = Path(args.out) if args.out else REPO / "benchmark" / "seed-tts-eval" / "gen" / args.locale
    out.mkdir(parents=True, exist_ok=True)
    rows = load_meta(args.locale, args.limit)
    print(f"loaded {len(rows)} rows, locale={args.locale}, out={out}, assume_sr={args.sample_rate}", flush=True)

    base_url = f"http://{args.host}:{args.port}"
    # warmup：首条 omni 预热（实测首条易出空音频 text=''），丢弃
    if rows:
        try:
            rp0 = SEED_ROOT / args.locale / rows[0]["wav_rel"]
            rb0, _ = ref_to_b64_f32_16k(rp0)
            await run_one(base_url, "你好，这是预热。", rb0)
            print("warmup done", flush=True)
        except Exception as e:
            print(f"warmup err (ignored): {e}", flush=True)
        await asyncio.sleep(1.0)
    manifest: list[dict] = []
    ok = 0
    for i, row in enumerate(rows):
        ref_path = SEED_ROOT / args.locale / row["wav_rel"]
        rec: dict = {"idx": i, "utt": row["utt"], "target": row["target"],
                     "ref_text": row["ref_text"], "ref_path": str(ref_path),
                     "sample_rate": args.sample_rate}
        try:
            ref_b64, _ = ref_to_b64_f32_16k(ref_path)
            t0 = time.time()
            text, audio_b64, metrics, err = await run_one(base_url, row["target"], ref_b64)
            elapsed = time.time() - t0
        except Exception as e:
            text, audio_b64, metrics, err, elapsed = None, None, None, {"error": f"{type(e).__name__}: {e}"}, 0.0
        rec["gen_text"] = text
        rec["elapsed_s"] = round(elapsed, 2)
        if err:
            rec["error"] = err
            print(f"[{i}] {row['utt']} FAILED err={err}", flush=True)
        elif not audio_b64:
            rec["error"] = "no_audio"
            print(f"[{i}] {row['utt']} NO AUDIO text={text!r}", flush=True)
        else:
            arr = np.frombuffer(base64.b64decode(audio_b64), dtype=np.float32)
            wav_path = out / f"{row['utt']}.wav"
            sf.write(str(wav_path), arr, args.sample_rate)
            rms = float(np.sqrt(np.mean(arr ** 2)))
            rec.update(gen_path=str(wav_path), n_samples=len(arr),
                       dur_s=round(len(arr) / args.sample_rate, 2), rms=round(rms, 5), metrics=metrics)
            ok += 1
            print(f"[{i}] {row['utt']} ok dur={len(arr)/args.sample_rate:.2f}s rms={rms:.4f} text={text!r}", flush=True)
        manifest.append(rec)
        (out / "manifest.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in manifest) + "\n", encoding="utf-8")
        await asyncio.sleep(1.0)  # 礼让 server 释放 active session
    print(f"DONE {ok}/{len(manifest)} -> {out/'manifest.jsonl'}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
