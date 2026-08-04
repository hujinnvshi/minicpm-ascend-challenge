# 参赛状态评估（2026-07-31）

## 结论

材料链路 ≈80% 就绪，但决定获奖的 3 个关键数据（910C RTF / 精度 / Demo 全链路）全部未产生。
尚不满足获奖要求，但已具备获奖所需的全部准备。差距全部是执行性的，唯一变量是 910C 环境到位时间。

## 一、硬门槛（准入，决定能否进排名）

| 准入项 | 状态 | 说明 |
|---|---|---|
| 精度 ≤2pp | 红 | 3 个 benchmark 零数据，仅调研口径（daily-omni-notes.md）；Q4_K_M 理论安全但未实测 |
| Demo 可用 | 黄 | llama-omni-server 后端验证通过（GPU1 全模块加载 11.3G）；worker/gateway/前端/流式/稳定未验证 |
| 可复现 | 黄 | 复现说明初稿 + build-cann.sh/sync-weights.sh 备好；官方环境跑通未发生 |

## 二、材料完整度（提交物 5 大块）

| 提交物 | 状态 | 说明 |
|---|---|---|
| 代码/配置 | 绿 | llama.cpp-omni patch + build-cann.sh + 配置齐 |
| Benchmark 结果 | 红→黄 | 3 benchmark 仍零数据，但 Daily-Omni 脚本已在 code/daily-omni/（待跑） |
| 性能报告 | 黄 | 8 字段骨架初稿，缺 910C 正式数据 |
| Demo | 黄 | 后端验证 + Demo 仓库就位，缺演示视频 + 全链路 |
| 复现说明 | 黄 | 初稿有，缺 910C 实测验证 |

## 三、竞争力（排名）

- 唯一性能锚点：4090 Q4_K_M + ctx8192 = RTF 0.75（3 次复现一致）
- 910C 预期：LLM 段算力 1.5-2x 提升，TTS/Token2Wav 段未知，0.75 不能外推
- 关键未知：官方 910C 基线 RTF / CANN 下量化档最优性（Q8_0 坑可能不存在）/ USE_ACL_GRAPH 收益

## 四、910C 六步走（30 卡时预算）

编译 CANN 版 → 权重入 /user_data → 跑官方基线 → 验证 4090 候选 → 精度 benchmark → 正式 RTF 数据

## 五、风险

- ~~910C 一直拿不到（最大）~~ → ✅ 已解除：厂家授权 910B3 替代，环境就位（见 env-scan.md）
- benchmark 代码：✅ code/daily-omni/ 已提供 Daily-Omni 完整脚本，不再等 starter kit
- 8/31 截止（赛事方调整后）：时间窗口宽裕，按计划推进
