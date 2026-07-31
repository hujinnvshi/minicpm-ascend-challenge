# 操作手册（Ops Guide）

本文件沉淀参赛相关的可执行操作步骤，按优先级排序。

## 0. 时间线检查点（2026）

| 节点 | 日期 | 状态 |
|------|------|------|
| 报名截止 | 08-14 | ✅ 已报名通过（2026-07-31） |
| 提交截止 | 08-17 | ⏳ |
| 复现评审 | 08-31 | |
| 颁奖 | 09-04 | |

## 1. 注册 API key（✅ 已注册，待开通额度）

1. 打开 https://platform.modelbest.cn/console/（ModelBest 开放平台）
2. 注册账号（手机号/邮箱）—— 已完成 2026-07-31
3. 控制台申请 API key —— 已完成，正式 key：
   sk-live-Pi-Z6P3cWWtRpq2Faz-x8uWr3MYhES7re0pVnWxNG30
   ⚠️ 当前状态：调用报 insufficient_quota（"账号未开通计费，请联系管理员开通并分配额度"）
   → 需在控制台完成：实名认证 + 开通计费/领取免费额度
4. 开发期可用官方公开 key 先行：
   sk-live-kmwPsO1yz9kJfbp8c6az72I-BjfZBX-5V5CmI9yTsXw
   （注意：公开 key 为"currently available"状态，正式提交前必须换正式 key）

## 2. 比赛报名（⏳ 入口待确认）

1. 注册 OpenBMB 账号：http://ascend.openbmb.cn（页面当前挂载其他比赛，账号体系通用）
2. 进飞书答疑群确认报名入口：assets/feishu-group-qr.png
3. 每天盯官网，页面更新后立即报名
4. 报名信息准备：队名、成员（≤3 人）、赛道选择（创新应用）

## 3. API 调用速查

### 3.1 文本对话
```bash
curl -X POST "https://api.modelbest.cn/v1/chat/completions" \
  -H "Authorization: Bearer <API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"model":"MiniCPM-O-4.5-9B","messages":[{"role":"user","content":"你好"}]}'
```

### 3.2 图片理解（base64 data URL）
```bash
# 图片转 base64 后放入 image_url.url（data:image/png;base64,...）
curl -X POST "https://api.modelbest.cn/v1/chat/completions" \
  -H "Authorization: Bearer <API_KEY>" -H "Content-Type: application/json" \
  -d '{"model":"MiniCPM-O-4.5-9B","messages":[{"role":"user","content":[
    {"type":"text","text":"描述这张图片"},
    {"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}]}]}'
```

### 3.3 视频理解（video_url，base64 data URL）
```bash
# 同上格式，type 改为 video_url，url 前缀 data:video/mp4;base64,...
```

### 3.4 Realtime 全双工（WebSocket）
```
wss://minicpmo45.modelbest.cn/v1/realtime?mode=video    # 视频全双工，会话5min/有效对话~90s
wss://minicpmo45.modelbest.cn/v1/realtime?mode=audio    # 音频全双工，会话10min/有效对话~8min
```
- 会话时长限制：video 5 分钟（有效对话~90 秒）/ audio 10 分钟（有效对话~8 分钟）
- 模式连接时确定不可切换；session_id 由服务端生成（rt_ 开头）
- 客户端参考：OpenBMB/MiniCPM-o-Demo realtime-protocol 分支
  static/duplex/lib/realtime-session.js

### 3.5 模型列表
| 模型 ID | 能力 |
|---------|------|
| MiniCPM-O-4.5-9B | 文本/图像/视频 + 实时全双工（比赛指定模型） |
| MiniCPM-V-4.5-9B | 文本/图像/视频 |
| MiniCPM-V-4.6-1B | 文本/图像/视频 |
| MiniCPM-V-4.6-Thinking | 推理链（message.reasoning） |

## 4. 实测基线（2026-07-31，公开 key）

- 文本对话：200 OK
- 图片理解（101KB PNG）：4.1s 响应，OCR 准确
- 响应头无 rate limit 字段，未发现显式限流
- 后端 vllm-0.24.0

## 5. 本地兜底部署（如需展示部署能力）

- 模型：openbmb/MiniCPM-o-4_5-gguf（HuggingFace，16 种量化规格）
- 框架：llama.cpp-omni（官方高性能推理框架，<12GB 内存）
- 目标机：secs（172.16.49.6，EPYC 224C / 1TiB RAM）
- 注意：CPU 全双工 RTF>1（慢于实时），仅作展示

## 6. 风险清单

| 风险 | 等级 | 缓解 |
|------|------|------|
| 公开 key 随时失效 | 中 | 尽快注册正式 key（已注册，待开通额度） |
| 报名入口未上线 | 中 | 飞书群确认 + 每天盯官网 |
| Realtime 会话限时 | 低 | 演示脚本按 90 秒设计 |
| API 免费额度政策变化 | 低 | 关注官方公告 |
| 赛道二"统一昇腾环境运行"要求不明 | 高 | 邮件 contact@openbmb.cn 或飞书群确认 Demo 运行方式 |

## 7. 提交规范要点

- 完整部署说明 + 运行脚本 + 必要配置（可复现）
- 能稳定运行于官方统一昇腾环境
- 文件命名：字母、数字、下划线、中划线（避免中文/特殊字符/空格）
- 材料按赛道清单齐备（赛道二：Demo/Web Demo/App + PPT + 项目说明 + 演示视频）
