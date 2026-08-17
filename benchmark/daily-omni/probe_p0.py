#!/usr/bin/env python3
"""P0 探针:在【干净 server】上验证单帧红线是否真的破了。

T1 纯文本 QA(无 video/audio)—— 二进制健康探针(连这都乱码 = binary 坏了)
T2 单帧视频(daily-omni row 0, stack_frames=1)—— P7 守住的单帧红线

判据:输出含 ≥5 个连续 '?' 或空 → GARBLED;否则 NORMAL。
T1/T2 都 NORMAL → 最新 result.json 乱码 = 当时 server 被多帧污染(A1),红线没破。
T1 GARBLED      → binary 本身回归(A2/A3,但代码复核已排除,需深查)。
T1 NORMAL / T2 GARBLED → 单帧视频路径有独立问题(意外,需深查)。
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from daily_omni_test import WSClient, run_one, wait_ready  # noqa: E402

DATA = Path("/workspace/shared_assets/datasets/MTEB/Daily-Omni/data")
BASE = "http://127.0.0.1:22500"


def classify(text):
    if not text or not str(text).strip():
        return "GARBLED(empty)"
    return "GARBLED(?)" if ("?" * 5) in str(text) else "NORMAL"


async def probe_text(q):
    cli = WSClient(BASE)
    await cli.connect_init({"mode": "turn_based", "use_tts": False,
                            "system_prompt": "Answer the multiple-choice question with a single capital letter only."})
    await cli.push({"messages": [{"role": "user", "content": [{"type": "text", "text": q}]}],
                    "streaming": True, "generation": {"max_new_tokens": 32, "length_penalty": 1.0}})
    text, _, err = await cli.wait_done(timeout=120)
    if cli.session_id:
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                await c.post(f"{cli.base}/sessions/{cli.session_id}/close", json={"reason": "done"})
        except Exception:
            pass
    await cli.aclose()
    return text, err


async def main():
    print("[warmup] probing readiness...", flush=True)
    if not await wait_ready(BASE):
        print("server not ready within deadline, abort", flush=True)
        sys.exit(1)

    print("\n=== T1 纯文本探针(无 video/audio) ===", flush=True)
    t, e = await probe_text("What is 2+2? A.3 B.4 C.5 D.6")
    print(f"  text={t!r}", flush=True)
    print(f"  err={e}" if e else "  err=None", flush=True)
    print(f"  >>> {classify(t)}", flush=True)

    print("\n=== T2 单帧视频探针(daily-omni row 0, stack_frames=1) ===", flush=True)
    f = sorted(DATA.glob("test-*.parquet"))[0]
    tbl = pq.read_table(f)
    row = {c: tbl.column(c)[0].as_py() for c in tbl.column_names}
    vb = row["video"]["bytes"] if isinstance(row["video"], dict) else row["video"]
    t, e = await run_one(BASE, vb, row["question"], row["candidates"], stack_frames=1)
    print(f"  text={t!r}", flush=True)
    print(f"  err={e}" if e else "  err=None", flush=True)
    print(f"  gold={row.get('answer')} >>> {classify(t)}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
