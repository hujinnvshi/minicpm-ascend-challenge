# 视频交错打包改动记录 + 回滚方案（ws_handler.cpp）

> 创建：2026-08-07。记录 `code/llama.cpp-omni/tools/server/ws_handler.cpp` 的多帧视频交错打包改动（+123/-14）、实测效果、与分档回滚方案。
> 回滚基准 commit：`4e2e4f6`（改动前的原始 STACKED 打包）。
> 相关：`docs/experiments.md` P7 重验 / Runtime 复测 / 最终结论。

---

## 0. 一句话现状

为修 Daily-Omni 多帧退化改了两处真实 bug（**交错打包** + **whisper KV 跨段清理**），都**实现+验证生效**且**保留**（gated、单帧红线逐字节不变）。但 runtime 实测：两个修复**都没解决 8 帧崩溃**（clean server 1/2 帧连贯、8 帧必崩）。8 帧崩溃根因在更深的视觉路径（官方"视觉未验证"），非本批改动能解。**改动安全保留，回滚随时可做（见 §4）。**

---

## 1. 改动清单（4 项，全部在 `ws_handler.cpp`）

### 改动 A — `ExtractedVideoMedia` struct 新增字段
- 位置：`ws_handler.cpp` ~`struct ExtractedVideoMedia`（原 ~383 行）
- 内容：新增 `struct VideoTimestep { frame_path; audio_seg_path; }`；`ExtractedVideoMedia` 增加 `std::vector<VideoTimestep> timesteps;`
- 用途：承载交错打包的"1 帧 + 1s 音频"时间步对。仅 n_frames>1 时填充；单帧为空。

### 改动 B — `extract_video_mp4_media` 抽取改 1fps + N×1s 音频段
- 位置：`ws_handler.cpp` `extract_video_mp4_media()`（原 ~392-488 行）
- 内容：
  1. 帧抽取 ffmpeg 命令在 `n_frames>1` 时加 `-vf fps=1`（1fps 采样，frame_i ≈ 第 i 秒）。`n_frames==1` 命令**逐字节不变**。
  2. 新增块：`n_frames>1` 时，循环 i=0..N-1，对每帧配对 1s 音频段 `ffmpeg -ss <i> -i <video> -t 1 -vn -ac 1 -ar 16000 -c:a pcm_f32le audio_%03d.wav`，组 `VideoTimestep` 推入 `timesteps`。帧缺失则跳过该步；段失败则 audio_seg 留空（消费端 `has_audio` 容忍）。
- 用途：产出交错打包所需的 N 个时间步素材。单帧路径不进此块。

### 改动 C — 交错 prefill 门控 + 编排
- 位置：`ws_handler.cpp` 视频循环（原 ~944）+ prefill 块（原 ~1006-1026）
- 内容：
  1. 循环前声明 `std::vector<VideoTimestep> interleave_timesteps;`；视频循环内把 `video.timesteps` 收集进去（段文件 push 进 `turn_temp_paths` 保证清理）。
  2. prefill 块加 env 门控：`const char* il = getenv("OMNI_VIDEO_INTERLEAVE"); bool video_interleave = !interleave_timesteps.empty() && !(il && std::string(il)=="0");`（**stack_frames>1 默认 ON；=0 强制旧 STACKED 路径**）。
  3. **交错路径**：`vision_set_max_slice_nums(ctx_vision, 0)`（每帧无 slice）→ 循环 N 次 `stream_prefill(seg_i, frame_i, ++msg_counter, /*max_slice*/0, "")` → `vision_set_max_slice_nums(ctx_vision, -1)`（恢复默认）→ 末尾 `stream_prefill("","", ++msg_counter, 0, prompt)`（问题文本独立项，**修了 consumer 在视觉项丢 user_text 的 bug**）。
  4. **旧路径（else）**：原 1007-1026 代码**逐字节保留**（单帧红线）。
- 用途：把多帧视频按 `<image>frame_i</image><|audio_start|>1s_seg_i<|audio_end|>` 时间步交错喂入（= minicpm-interleave 训练布局）。

### 改动 D — whisper KV 跨段清理
- 位置：`ws_handler.cpp` 交错循环内，每个 `stream_prefill` 之前
- 内容：`if (octx->ctx_audio) audition_whisper_clear_kv_cache(octx->ctx_audio);`
- 用途：让每个 1s 音频段独立编码（不承接前段的流式 KV）。`audition_whisper_clear_kv_cache` 声明于 `audition.h:182`，ws_handler 已在别处（~220 行）调过。
- ⚠️ 实测：**生效（日志确认 KV 不再累积）但未解 8 帧崩溃**——见 §3。

---

## 2. 门控与红线

- **运行时门控**：`OMNI_VIDEO_INTERLEAVE`
  - 默认（未设/非"0"）：stack_frames>1 走交错路径。
  - `=0`：强制走旧 STACKED 路径（逐字节等同改动前）。**零代码回滚开关**。
- **单帧红线**：stack_frames==1 时 `interleave_timesteps` 为空 → `video_interleave=false` → 走原 else 分支，**逐字节不变**。已 clean-server 实测：stack-frames 1 输出连贯（"woman...skincare"）。
- **无推理数学改动**：只动输入打包/编排 + 音频 KV 清理；视觉/音频编码器、LLM 消费 emit 顺序、`prefill_with_emb` 全未改。

---

## 3. 实测效果（每个 case 干净 server，因退化会污染 shared_octx）

| case | 结果 |
|---|---|
| stack-frames 1（红线回归） | ✅ 连贯 |
| stack-frames 2（interleave，改动 A+B+C） | ✅ 连贯（"C. Logo transition sound effect"）——多图低帧**能用**，相对旧 STACKED 是进步 |
| stack-frames 8（interleave，改动 A+B+C） | ❌ `?`×40 崩溃 |
| stack-frames 8（+ 改动 D whisper KV 清理） | ❌ 仍 `?`×40 崩溃（KV 清理生效但非真因） |

**结论**：改动 A+B+C 修了打包布局（2 帧能用 + 修了 user_text 丢弃）；改动 D 修了 KV 累积（语义更正确）。**两者都是真实改进、保留**。但**都没解 8 帧/高帧崩溃**——根因在更深的 turn_based 多 `<image>` 视觉路径（官方 910C 指南"视觉模态未验证"），非 server 层可修。

---

## 4. 回滚方案（三档，由轻到重）

### 档位 1 — 运行时关闭（零代码、即时、推荐先用）
不回退代码，仅设环境变量强制旧路径：
```bash
OMNI_VIDEO_INTERLEAVE=0   # 启动 llama-omni-server 前 export
```
效果：所有请求走改动前的 STACKED 打包（逐字节等同 `4e2e4f6`）。单帧本就不受影响。
适用：A/B 对比、或交错路径在生产中出问题时立即降级。**无需 rebuild。**

### 档位 2 — 仅回退改动 D（whisper KV 清理）
保留交错打包，只撤销 KV 清理（仅当怀疑 KV 清理引发副作用时）：
- 编辑 `ws_handler.cpp`，删掉交错循环内 `if (octx->ctx_audio) audition_whisper_clear_kv_cache(...);` 那一块（见 §1 改动 D）。
- `cmake --build code/llama.cpp-omni/build-cann --target llama-omni-server -j$(nproc)` 重 build。
- 其余不变。

### 档位 3 — 全部回退（回到改动前 STACKED）
撤销 A+B+C+D，回到 `4e2e4f6` 的 ws_handler.cpp：
```bash
# 若本批改动已提交为某 commit X：
git revert <X>                           # 生成回滚 commit
# 若尚未提交（当前就是未提交状态）：
git checkout 4e2e4f6 -- code/llama.cpp-omni/tools/server/ws_handler.cpp
cmake --build code/llama.cpp-omni/build-cann --target llama-omni-server -j$(nproc)
```

### 回滚后验证（任一档位）
1. 重 build（档位 1 不用）+ 重启 `scripts/serve.sh`。
2. `python3 benchmark/daily-omni/daily_omni_test.py --stack-frames 1 --limit 1` → 应连贯（单帧红线）。
3. （档位 3）`--stack-frames 8 --limit 1` → 应复现旧 STACKED 行为（多帧退化）。

---

## 5. 关键代码位置（快速导航）

- `ws_handler.cpp` `struct ExtractedVideoMedia` / `VideoTimestep` — 改动 A
- `ws_handler.cpp` `extract_video_mp4_media()` — 改动 B（`-vf fps=1` + 1s 段循环）
- `ws_handler.cpp` 视频循环 + prefill 块 `video_interleave` 门控 — 改动 C
- `ws_handler.cpp` 交错循环内 `audition_whisper_clear_kv_cache` — 改动 D
- 只读参考（**未改**）：`omni.cpp:5036-5138`（消费三分支）、`omni.cpp:498-587`（`encode_image_with_vision_chunks`）、`omni.cpp:10590-10647`（stream_prefill 异步路）、`audition.cpp:1514-1541`（whisper KV iter 累积逻辑）、`audition.h:182`（`audition_whisper_clear_kv_cache` 声明）

---

## 6. 未决（不在本批改动范围）

8 帧/高帧崩溃的真正根因（turn_based 多 `<image>` 视觉路径）**未解**。方向见 `docs/experiments.md` P7 重验「最终结论」：问赛事方子赛道 A 多帧/视觉官方配置（`official-clarification-request.md` Q1）+ 如实报告框架视觉限制。可选深度诊断：找 2~8 帧精确阈值、测纯多图（无 audio）是否也崩、查 `vision_backend` 实际跑在 NPU 还是 CPU。
