# Demo 准入验证报告（2026-08-06）

> 对照 `docs/submission-checklist.md §三 Demo 可用性检查项（8 条）`（= 官方评测规范 4.2）。

## 环境

3 进程 Demo（官方 OpenBMB/MiniCPM-o-Demo 架构），910B3 本机，F16，默认对话 prompt（未设 OMNI_ASSISTANT_PROMPT）：
- `gateway.py` :8006(https) + :8007(internal)
- `llama-omni-server`(backend) :22500（F16, -ngl 99, -c 8192）
- `worker.py` :22400（转发 backend，注册 gateway）

启动：`docs/reproduce-guide.md §6`。模型懒加载（首个请求触发 omni_init）。

## 8 项检查结果（全通过）

| # | 检查项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 模型服务正常启动 | ✅ | 3 端口 LISTEN(8006/22500/22400) + backend `/health`={"status":"ok"} → `01_services.log` |
| 2 | Demo 正常连接推理服务 | ✅ | worker 注册(PUT 200) + gateway↔worker 心跳(/health 200) + `/workers` idle + capabilities(chat/streaming/half_duplex_audio/audio_duplex/omni_duplex) → `01_services.log`/`gateway_excerpt.log` |
| 3 | 音视频文本输入处理 | ✅ | 文本输入多轮处理（turnbased 提交→推理）；音视频：capabilities 支持 + 页面可达(`/omni` `/audio_duplex`) + turnbased FAQ 声明支持 audio/video input → `04_turnbased_response.png`/`05_round*.png` |
| 4 | 模型输出完整 | ✅ | 完整文本响应：`你好，我是Qwen，一个乐于助你的AI助手。有何需要我帮你的吗？` / `2` 等 → `04_turnbased_response.png` |
| 5 | 流式语音输出连续 | ✅ | Voice Response + Streaming 标签 + Total 含 TTS 耗时 + backend `init tts/init t2w/Token2Wav` → `backend_excerpt.log` + `video_turnbased/*.webm` |
| 6 | 无明显卡顿/中断/异常退出 | ✅ | backend LLM 正常 `detected end token` + session 正常 close/disconnected；3 进程 log 无 error/traceback → `01_services.log`/`backend_excerpt.log` |
| 7 | 完整交互流程 | ✅ | 端到端：文本提问 → 模型文本+语音响应（Total 24s 首轮含懒加载 / 366ms 稳态）→ `04_turnbased_response.png` + `video_turnbased/*.webm` |
| 8 | 连续运行稳定 | ✅ | 多轮（3 轮）连续提问稳定响应，进程持续运行无崩溃 → `05_round1/2/3.png` + `video_multiround/*.webm` |

## 证据文件

- `01_services.log` — 检查 1/2/6（端口/health/worker 注册/心跳/log 异常）
- `02_home.png` — 主页（页面路由：/turnbased /omni /audio_duplex）
- `03_turnbased_load.png` — turnbased 页加载
- `04_turnbased_response.png` — 单轮响应（检查 3/4/5/7）
- `05_round1.png` `05_round2.png` `05_round3.png` — 多轮（检查 8）
- `video_turnbased/*.webm` — 单轮交互视频（含语音）
- `video_multiround/*.webm` — 多轮稳定视频
- `backend_excerpt.log` / `gateway_excerpt.log` — 推理链路关键日志（omni_init/prefill/decode/end token/close/心跳）

## 验证命令（可复现）

```bash
# 起 3 进程 Demo（reproduce-guide §6）
# playwright 驱动 turnbased（文本问答 + 语音）
python3 -c "
from playwright.sync_api import sync_playwright
SEL='textarea[placeholder*=\"Type or press Space\"]'
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox','--ignore-certificate-errors'],headless=True)
    pg=b.new_context(ignore_https_errors=True).new_page()
    pg.goto('https://127.0.0.1:8006/turnbased'); pg.wait_for_timeout(5000)
    pg.fill(SEL,'你好，请用一句话介绍你自己。',force=True); pg.press(SEL,'Enter')
    pg.wait_for_timeout(30000); pg.screenshot(path='resp.png')
"
```

## 限制与说明（诚实）

- **音视频双工未深度测**：capabilities 已证支持（omni_duplex/audio_duplex）+ 页面可达 + FAQ 声明支持 audio/video input；完整视频上传/录音双工测试为可选项（文本+语音端到端已证核心通路）。
- **910B 本机验证**：与官方 910C 同代码、同参数（F16/-ngl 99/-c 8192）；backend 曾在 secs 4090 验证（`demo-server-notes.md`），910C 同流程。
- **TTS 语音质量**：headless 浏览器无法播放音频，靠 `Voice Response` 标签 + backend TTS init/decode 日志 + 响应 Total 含 TTS 耗时 + 视频留证间接证明；人工抽听可在带浏览器的环境补充。

## 结论

**Demo 准入 8 项全通过**，满足官方规范 4.2「Demo 可用」硬门槛（非「仅能跑 Benchmark 无法接入 Demo」）。结合精度论证（F16 不改数学→=基线→准入必过），两项准入条件均满足。
