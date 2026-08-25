#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
910C 理论仿真外推：v6 配置在 910C 的 RTF 预测 + 910C 特性收益上限
数据源：
  - v6 段耗时（910B4 实测，2026-08-24 rts 全量）：session-2026-08-24.md / papers-p0-probe-2026-08-24.md
  - 排行榜 10 队分数（910C 真实数据点，2026-08-24 21:17 刷新实测）
  - 8/24 榜首外推先例（skill：2x 算力/带宽，encode 0.359→0.15 等）
口径：core 帧 pooled RTF = Σ compute / Σ audio，compute = max(VPM,APM)+prefill+decode+tts+t2w
"""
import json

# ---------- 1. v6 段耗时（910B4 实测） ----------
seg_910b4 = {
    "encode(max VPM/APM)": 0.359,   # VPM 主导 ~220ms 计算 + launch
    "llm_prefill": 0.017,
    "llm_decode": 0.241,            # FA 后，带宽下限主导 13.7ms/tok
    "tts": 0.275,                   # head 并行后：CPU head 3.1ms/步 + NPU 6.9ms/步
    "token2wav": 0.257,             # NPU Flow + CPU vocoder
}
rtf_v6_910b4 = sum(seg_910b4.values())
print(f"v6 RTF @910B4 模型合计 = {rtf_v6_910b4:.3f}（实测 1.166，差 {abs(rtf_v6_910b4-1.166):.3f}）")

# ---------- 2. 排行榜（910C 真实数据点，校准用） ----------
lb = [
    ("猫和老鼠", 0.5308), ("jsy", 0.5659), ("牛牛酱今天吃什么", 0.6487),
    ("等我启动", 0.751), ("doma", 0.7528), ("EVA", 0.8533),
    ("自由探索", 0.9578), ("问题不大", 1.0581), ("且听龙吟", 1.0642), ("NoOneAhead", 1.0925),
]
# 910B4 官方默认（零调优）实测 = 1.71（2026-08-21）；910C 轻优化 ≈ 榜尾 1.05-1.09
rtf_910b4_default = 1.71
rtf_910c_light = 1.0925  # 榜尾（保守取最慢）
calib_factor = rtf_910b4_default / rtf_910c_light
print(f"\n[校准] 910C vs 910B4 总体加速系数 = {calib_factor:.2f}x（默认配置 1.71/1.0925）")

# ---------- 3. 场景外推 ----------
# 每段加速因子：段特性分类
#   launch/固定成本主导（VPM：~700op×0.32ms）：对算力/带宽不敏感 → 低加速
#   带宽主导（decode/t2w）：带宽 2x → 中加速
#   算力+带宽混合（tts/encode）：2x 算力 → 中高加速
scenarios = {
    "悲观（固定成本不减，2x 只作用于算力/带宽项）": {
        "encode(max VPM/APM)": 1.3, "llm_prefill": 1.5, "llm_decode": 1.7,
        "tts": 1.5, "token2wav": 1.5,
    },
    "中性（2x 算力/带宽全段生效）": {
        "encode(max VPM/APM)": 1.8, "llm_prefill": 2.0, "llm_decode": 2.0,
        "tts": 2.0, "token2wav": 1.8,
    },
    "乐观（2x + 固定成本减半，8/24 外推先例）": {
        "encode(max VPM/APM)": 2.4, "llm_prefill": 2.0, "llm_decode": 2.0,
        "tts": 2.3, "token2wav": 2.4,
    },
}
# 校准后场景：把中性场景按 calib_factor 归一（910C 实际总体加速 1.57x 而非 2x）
print("\n=== 场景外推（v6 配置在 910C）===")
preds = {}
for name, fac in scenarios.items():
    rtf = sum(v / fac[k] for k, v in seg_910b4.items())
    preds[name] = rtf
    rank = sum(1 for _, s in lb if s < rtf) + 1
    print(f"{name}: RTF≈{rtf:.3f} → 排行榜第 {rank} 名（榜首 0.531 / 第3 0.649 / 第5 0.753）")

# 用校准系数修正中性场景（910C 实测总体加速 1.57x vs 模型 2x）
print(f"\n[校准修正] 中性场景按实际 1.57x 缩比: RTF≈{rtf_v6_910b4/calib_factor:.3f} → 第 {sum(1 for _,s in lb if s < rtf_v6_910b4/calib_factor)+1} 名")

# ---------- 4. 910C 特性收益上限（敏感性，逐特性"如果生效"） ----------
print("\n=== 910C 特性收益上限（独立生效假设，910B4 基线上叠加）===")
base = dict(seg_910b4)
def show(name, new_segs):
    r = sum(new_segs.values())
    print(f"{name}: RTF {rtf_v6_910b4:.3f} → {r:.3f}（-{(1-r/rtf_v6_910b4)*100:.1f}%）")

# KV 量化：decode 带宽项 -35%（INT8 KV 读取省 30-40%），decode 60% 带宽敏感
kv = dict(base); kv["llm_decode"] = 0.241 * (1 - 0.6*0.35)
show("KV 量化 INT8（decode 带宽 -21%）", kv)

# 图模式：VPM launch 摊薄 50%（~700op×0.32ms → 0.16ms/op）
graph = dict(base); graph["encode(max VPM/APM)"] = 0.359 * 0.65
show("图模式（VPM 段 -35%，launch 摊薄）", graph)

# FP8 权重：decode+prefill 权重带宽 -50%（16bit→8bit），decode 40% 权重带宽敏感
fp8 = dict(base); fp8["llm_decode"] = 0.241 * (1 - 0.4*0.5); fp8["llm_prefill"] = 0.017 * 0.7
show("FP8 权重（decode 权重带宽 -20%）", fp8)

# Q8 硬件反量化：权重读取 -50% 且 910C 反量化单元快（对手证据），decode 权重带宽 40%
q8 = dict(base); q8["llm_decode"] = 0.241 * (1 - 0.4*0.5); q8["llm_prefill"] = 0.017*0.7
show("Q8 硬件反量化（同 FP8 带宽项）", q8)

# 组合：全部特性生效（上限）
combo = dict(base)
combo["encode(max VPM/APM)"] = 0.359*0.65
combo["llm_decode"] = 0.241 * (1-0.6*0.35) * (1-0.4*0.5)
combo["llm_prefill"] = 0.017*0.7
show("组合全开（上限）", combo)

# ---------- 5. 榜首差距分解 ----------
print("\n=== vs 榜首 0.5308 差距分解（中性场景）===")
fac = scenarios["中性（2x 算力/带宽全段生效）"]
our_910c = {k: v/fac[k] for k, v in seg_910b4.items()}
print(f"我们（910C 中性）: { {k: round(v,3) for k,v in our_910c.items()} } Σ={sum(our_910c.values()):.3f}")
print(f"榜首 0.5308 隐含段构成（8/24 外推先例）: encode 0.15/decode 0.12/tts 0.12/t2w 0.07 ≈ 0.46-0.55")
gap = sum(our_910c.values()) - 0.5308
print(f"差距 ≈ {gap:.3f}（主要来源：encode {our_910c['encode(max VPM/APM)']-0.15:.3f} + tts {our_910c['tts']-0.12:.3f} + t2w {our_910c['token2wav']-0.07:.3f}）")
