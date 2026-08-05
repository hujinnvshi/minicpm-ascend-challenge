#!/usr/bin/env python3
"""Verify SPEAK->WAV e2e RTF from perf-duplex JSON reports (independent recompute)."""
import json, sys
from collections import defaultdict

for path in sys.argv[1:]:
    try:
        d = json.load(open(path))
    except Exception as e:
        print(path, 'ERR', e); continue
    frames = d.get('frames', []); chunks = d.get('audio_chunks', [])
    sf = defaultdict(list)
    for f in frames:
        if f.get('is_speak'):
            sf[f.get('speak_turn_id')].append(f)
    tc = defaultdict(list)
    for c in chunks:
        tc[c.get('audio_turn_id')].append(c)
    for tid in sorted(sf):
        fs = sf[tid]
        tp = min(f['t_push_ms'] for f in fs)
        cs = tc.get(tid, [])
        if not cs: continue
        last = max(c['t_complete_ms'] for c in cs)
        dur = sum(c['duration_s'] for c in cs)
        wall = (last - tp) / 1000
        p50s = sorted(f.get('ms_total', 0) for f in fs)
        p50 = p50s[len(p50s)//2] if p50s else 0
        print(f"{path.split('/')[-1]}: e2eRTF={wall/dur:.3f} (wall={wall:.2f}s audio={dur:.2f}s) LLM_ms_total_P50={p50:.0f}ms")
