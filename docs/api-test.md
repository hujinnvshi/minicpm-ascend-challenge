# MiniCPM-o 4.5 官方 API 实测记录

日期：2026-07-31
key 来源：OpenBMB 官方文档公开免费 key（docs/api.md）

## API 接入信息

- Base URL: https://api.modelbest.cn/v1
- Chat API: POST /chat/completions（OpenAI 兼容）
- Realtime API: wss://minicpmo45.modelbest.cn/v1/realtime?mode=video|audio
- 免费公开 key: sk-live-kmwPsO1yz9kJfbp8c6az72I-BjfZBX-5V5CmI9yTsXw
- 模型 ID: MiniCPM-V-4.5-9B / MiniCPM-V-4.6-1B / MiniCPM-V-4.6-Thinking / MiniCPM-O-4.5-9B

## 实测结果

1. 文本对话（MiniCPM-O-4.5-9B）：200 OK，正常
2. 图片理解（时间线图 101KB PNG）：200 OK，耗时 4.1s，OCR 识别准确
3. 响应头无 rate limit 字段，未发现显式 RPM/TPM 限流
4. 后端：vllm-0.24.0

## Realtime 会话时长限制

| 模式 | 单会话时长 | 有效对话时长 |
|------|-----------|-------------|
| video 全双工 | 5 分钟 | ~90 秒 |
| audio 全双工 | 10 分钟 | ~8 分钟 |

- 模式连接时确定，中途不可切换
- session_id 由服务端生成（rt_ 开头），客户端不需要传

## 结论与约束

- 主链路走官方 API：Chat Completions（轮次对话/图片理解）+ Realtime（全双工演示）
- 演示脚本须在 90 秒有效对话内完成核心交互
- 公开 key 为"currently available"状态，正式参赛前申请正式 key
- 本地 CPU（secs，llama.cpp-omni 量化版 <12GB 内存）作兜底与部署能力展示，
  不承担实时交互主路径（CPU 全双工 RTF>1）

## 注册入口

- API key 申请（正式 key）：https://platform.modelbest.cn/console/（ModelBest 开放平台，
  注册账号后控制台申请 key）
- 比赛报名：http://ascend.openbmb.cn（OpenBMB 比赛平台；2026-07-31 时页面挂载的是
  "2026 稀疏算子加速大奖赛"，MiniCPM 比赛页待官网更新或飞书群确认）

## 参考代码

- Realtime 客户端封装: OpenBMB/MiniCPM-o-Demo realtime-protocol 分支
  static/duplex/lib/realtime-session.js
- 全双工 Demo 页面: static/omni/（video）、static/audio-duplex/（audio）
