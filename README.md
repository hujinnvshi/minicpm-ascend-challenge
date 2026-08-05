# MiniCPM & 昇腾推理优化与应用创新挑战赛 — 筹备仓库

本地筹备记录与资料归档。

## 比赛速览

- 主办：面壁智能 OpenBMB 联合华为昇腾生态
- 模型：MiniCPM-o 4.5（9B 全模态，视觉+语音+文本端到端）
- 硬件：昇腾 910B3（厂家授权替代 910C，正式评测环境；实测见 docs/env-scan.md）
- 奖金：40.6 万（含税）/ 12 个奖

## 关键时间线（2026）

| 节点 | 日期 |
|------|------|
| 报名开放 | 07-13 |
| 提交开启 | 07-20 |
| 报名截止 | 08-14 |
| 提交截止 | 08-31（赛事方 08-04 调整，原 08-17） |
| 复现评审 | 08-31 |
| 颁奖 | 09-04 |
| 奖金到账 | 10-01 |

## 赛道

- 赛道一 高性能推理优化：llama.cpp-omni / vLLM-Omni 两个子赛道，
  优化 RTF / TTFT / TTFP，精度降幅 ≤2pp
- 赛道二 创新应用：基于全模态能力做可运行 Demo

详见 docs/competition-research.md

## 目录结构

- docs/competition-research.md  比赛调研（赛道/奖项/时间线/规则/报名）
- docs/env-scan.md             910B3 云环境扫描报告（当前真实环境基线，权威）
- docs/cann-patches.md         ggml-cann 6 补丁 + 已知问题（优化必读）
- docs/experiments.md          实验记录（P0-P1.6 数据，4090/910B3）
- docs/decisions.md            决策链（时间倒序，技术路线演变）
- docs/optimization-methodology.md  RTF 优化方法论（思维链 + 检查清单）
- docs/session-2026-08-04.md   0804 工作日志
- docs/reproduce-guide.md      复现说明（评审用）
- docs/api-test.md              官方 API 实测记录 + 注册入口
- docs/ops-guide.md             操作手册（注册步骤/API 调用速查/风险清单）
- docs/ops-handoff.md           运维交接文档（环境/账号位置/运行服务/操作速查/TODO，2026-08-05）
- assets/                       官方资料（海报、时间线、奖项、飞书群二维码）
- notes/                        筹备过程记录（可选）
