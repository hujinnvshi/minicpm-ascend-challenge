# 参赛状态评估（2026-07-31，08-04 更新）

## 结论（2026-08-04 更新）

**910B3 环境就位 + 全链路跑通 + 双工 TTS RTF 0.80 基线成立**（首个 <1，
接近 4090 的 0.75）。硬门槛从"全部未产生"推进到"性能基线已有，精度/Demo 待补"。
最大变量已从"环境到位时间"转为"双工 compute 是否真走 NPU"的结构性问题。

## 一、硬门槛（准入，决定能否进排名）

| 准入项 | 状态 | 说明 |
|---|---|---|
| 精度 ≤2pp | 红 | 3 个 benchmark 零数据，仅调研口径（daily-omni-notes.md）；F16 无损精度理论安全但未实测 |
| Demo 可用 | 黄 | llama-omni-server 后端验证通过（GPU1 全模块加载 11.3G）；worker/gateway/前端/流式/稳定未验证 |
| 可复现 | 黄→绿 | 910B3 全链路跑通（cann 补丁 1-6 落盘 cann-patches.md），复现材料可执行；官方环境复现验证待 910B 重跑 |

## 二、材料完整度（提交物 5 大块）

| 提交物 | 状态 | 说明 |
|---|---|---|
| 代码/配置 | 绿 | llama.cpp-omni 6 补丁 + build-cann.sh + 配置齐（ggml-cann.cpp） |
| Benchmark 结果 | 红→黄 | 3 benchmark 仍零数据，但 Daily-Omni 脚本已在 code/daily-omni/（910B 权重已预置） |
| 性能报告 | 黄 | 8 字段骨架初稿，910B3 实测数据已积累（RTF 0.861/0.99/0.80），缺正式版 |
| Demo | 黄 | 后端验证 + Demo 仓库就位，缺演示视频 + 全链路 |
| 复现说明 | 黄 | 初稿有，910B3 实测可回填 |

## 三、竞争力（排名）

- 910B3 双工 TTS RTF **0.80**（首个 <1，vs 4090 0.75）——接近但未超越
- 910B3 与 910C 同 CANN 栈（9.1.0-beta.3），数据迁移参考价值高
- 关键差异已确认：**cann 不支持 Q4_K_M 量化**（4090 最优档在 910B fallback CPU）
  → LLM 用 F16（精度无损，prefill 13x）；910B 优化路径与 4090 不同，不能照搬
- 待解结构性瓶颈：双工 decode AICore 仅 4%（compute 未真走 NPU）+ LLM P50 8840ms（流水线等待）+
  model 中途释放——解掉任一即可显著下探 RTF

## 四、910B3 六步走（替代 910C；环境已就位）

编译 CANN 版 ✅ → 权重预置 ✅ → 跑官方基线 ✅（P0 全链路 9 用例）→
优化候选（F16/补丁6/P1.6 双工）✅ → 精度 benchmark ⏳ → 正式 RTF 数据 ⏳

## 五、风险

- ~~910C 一直拿不到（最大）~~ → ✅ 已解除：厂家授权 910B3 替代，环境就位（见 env-scan.md）
- benchmark 代码：✅ code/daily-omni/ 已提供 Daily-Omni 完整脚本，不再等 starter kit
- 8/31 截止（赛事方调整后）：时间窗口宽裕，按计划推进
- **新增风险**：双工 compute 未真走 NPU（AICore 4%）——若为 cann 后端算子缺失类问题，
  修复周期不可控；预案：先用"流水线重叠 + 参数调优"守住 0.80，compute 路径作为增量

## 六、08-04 进展评估（详见 session-2026-08-04.md）

**里程碑**：
- 环境基线对齐（910B3 / CANN 9.1.0-beta.3 / 鲲鹏 256 核 / 64G HBM / 权重预置）
- P0 全链路跑通：cann 补丁 1-5（T2W 线程 device 绑定 + SQR 断言）→ T2W RTF 0.861
- P1 战略发现：cann 量化支持有限（Q4_K_M fallback CPU 7.9s）→ F16 战略（NPU 0.58s）
- P1.5 补丁 6（host_buffer 默认 false）→ 单工 LLM 上 NPU（HBM 23.6G + AICore 66%）
- P1.6 双工 model 上 device（use_mmap=false）→ TTS RTF 0.80 PASS

**当前瓶颈（按杠杆排序）**：
1. 双工 decode AICore 仅 4%——compute 没真走 cann 算子（最大杠杆，解了 RTF 可下探 0.6x）
2. LLM P50 8840ms vs avg decode 1448ms——6x 差距 = 流水线等待（audio encoder 串行？），
   4090 已证明流水线是最大 RTF 杠杆，910B 未吃满
3. model 中途释放（t=160 HBM 3481）——chunk 生命周期待查，避免重复加载吃卡时

**下一步（P1.7）**：
1. 查 duplex compute 路径（对照单工成功的 backend 调用链找差异）
2. 流水线重叠分析（msprof/时间戳对齐，找等待段）
3. P2 量化重扫（Q8_0/Q6_K 在 cann 的支持，Q8_0 无 CUDA 乱码 bug 可能可用）
4. model 释放问题排查
