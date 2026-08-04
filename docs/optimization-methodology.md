# RTF 优化方法论（llama.cpp-omni / 昇腾 910B）

> 可复用的推理性能优化思维链。核心原则：**用数据定位瓶颈，不凭感觉调参**。
> 案例对照：2026-08-04 的 910B 攻坚（cann 6 补丁 + F16 战略 + 单工 LLM 上 NPU）。

## 0. 一句话思维链

**目标(RTF<1) → 拆三段 → 找最慢 → 抓最大杠杆 → 选对手段(从大到小) → npu-smi+质量验证 → 不越红线**

## 1. 北极星：一个公式

```
RTF = 一个音频 chunk 的生成耗时 ÷ 这个 chunk 的音频时长
RTF < 1  即实时（生成快于播放）
```

全程只为一件事：让"生成时间"短于"音频时间"。其余全是手段，别把手段当目标。

## 2. 链路拆解：三段

音频 chunk 生成走三步：

```
LLM 解码(语义) → TTS(音频 token) → Token2Wav(波形)
RTF = (LLM + TTS + T2W 耗时) ÷ 音频时长
```

> 比喻：做一道菜 = 备料 → 烹调 → 装盘，总时长要短于客人等待。拆开才知道哪步慢。

## 3. 瓶颈定位：找最慢那段

不平均用力。两件武器：
- **perf-duplex**：分模块计时（LLM/TTS/T2W 各占多少）
- **npu-smi**：看 HBM/AICore，确认真在 NPU 算（戳穿"数字降了但实际在 CPU"的假象）

**关键洞察：不同硬件，瓶颈位置不同**——
- 4090：LLM 快(145ms)，瓶颈在 TTS/T2W
- 910B：LLM 在 CPU(9133ms)，瓶颈在"LLM 没上 NPU"

照搬 4090 的优化（量化）在 910B 会扑空。优化要因"机"制宜。

## 4. 杠杆排序：先抓最大头

```
优化收益 = 该段占比 × 可降幅度
```

先攻占比大且可降的。910B 实例：
- LLM 在 CPU(慢 ~10x) → 让它上 NPU = **最大杠杆**（单工 prefill 7.9s→0.77s）
- TTS/T2W 已在 NPU → 参数微调 = 小杠杆
- 图模式 910B 不支持 = **0 杠杆，砍掉**

> 比喻：先修高速公路（LLM 上 NPU），再调红绿灯（参数）。顺序错则事倍功半。

## 5. 手段工具箱（从大到小，按层试）

永远从第 1 层往下试——**上层一个开关抵下层一堆参数**。

| 层 | 手段 | 910B 实例 |
|---|---|---|
| 1 后端/部署 | 权重放对的设备（offload/host_buffer） | host_buffer 默认 false → LLM 上 NPU |
| 2 量化档 | 选**后端支持**的 | cann 支持 F16，不支持 Q4_K_M → 用 F16 |
| 3 编译开关 | 图模式/优化 | USE_ACL_GRAPH 910B 不支持（砍） |
| 4 运行时参数 | ctx-size / chunk / 线程 | ctx 8192（4090 经验） |
| 5 算子级 | 改 cann 算子 | 最难，最后（如 SQR 补丁） |

## 6. 验证三件套（防自欺）

1. **npu-smi 看 HBM/AICore**：确认真在 NPU 算。今天靠它戳破"LLM 在 CPU 却以为在优化"
2. **质量检查**：RTF 低但乱码 = 负优化。4090 Q8_0 教训：RTF 0.32 是 bug 不是性能
3. **同口径对比**：perf-duplex 双工 vs perf-duplex 双工（跨硬件）；单工 vs 双工不可比

## 7. 三条红线（碰了出局）

- 精度降幅 ≤2pp（Daily-Omni/TTS-Seed/Video-MME）
- Demo 接官方 MiniCPM-o-Demo 可用
- 材料完整可复现

> 优化不能牺牲这些。F16 选它不只因为快，还因精度无损（守红线）。

---

## 8. 910B 案例对照（2026-08-04 闭环）

| 层 | 发生 |
|---|---|
| 目标 | RTF<1（双工实时） |
| 拆 | LLM + TTS + T2W |
| 定位 | npu-smi 戳穿：LLM 在 CPU（AICore=0、HBM 3.4G） |
| 杠杆 | LLM 上 NPU = 最大头（~10x） |
| 手段 | cann 补丁（device 绑定让 T2W 上 NPU + host_buffer 让 LLM 上 NPU）+ F16 |
| 验证 | npu-smi 确认单工 LLM 真上 NPU（HBM 23.6G + AICore 66%） |
| 红线 | F16 无损精度 ✅ |
| 遗留 | 双工 LLM 还没上 NPU（duplex 路径，下阶段 P1.6） |

**精髓**：从"全 FAIL"一路找到 host_buffer + 量化缺失 + duplex 路径三层根因，靠的是每层都用实测数据说话、不假设。

---

## 9. 每次优化前过一遍的检查清单

- [ ] 目标明确：RTF<1？攻哪段？
- [ ] 瓶颈已用 perf-duplex + npu-smi 定位（不是猜）
- [ ] 杠杆排序：先最大头
- [ ] 手段从大到小试（后端 → 量化 → 编译 → 参数 → 算子）
- [ ] 验证三件套：npu-smi（真上 NPU）+ 质量（不乱码）+ 同口径（可比）
- [ ] 红线：精度 / Demo / 复现
- [ ] 单变量 + 多次取均值（防噪声）
- [ ] 落盘：cann-patches / experiments / decisions

## 10. 910B 专属注意事项

- **cann 量化支持有限**：Q4_K_M fallback CPU → LLM 用 F16（待 P2 扫其他档）
- **图模式 USE_ACL_GRAPH 不支持**（acl_graph 头文件缺失）
- **多线程 device 绑定**：cann 要求 per-thread `aclrtSetDevice`，T2W/event 等独立线程需补（见 cann-patches 补丁 1-4）
- **host_buffer 默认**：false（补丁 6）让 LLM 用 device buffer 上 NPU
- **双工 duplex 路径独立**：单工 LLM 上 NPU ≠ 双工上 NPU（duplex_llm_thread_func 待解）
- **单 NPU 限制**：并行 worktree 推理须串行，并行收益在编译/分析/验证设计
