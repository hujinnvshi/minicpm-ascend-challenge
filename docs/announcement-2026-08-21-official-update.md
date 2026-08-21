# 官方重要通知（2026-08-21）：排行榜上线 + 测评分支更新 + 提前提交说明

> **来源**：赛事群 `@所有人` 通知（2026-08-21，选手转发）。本文为**逐字留档 + 影响分析**。
> **配套先例**：`docs/bench-huawei-branch-notice.md`（2026-08-11 统一测评分支发布通知）。
> **性质**：⭐ 强制——本次分支更新引入**新 RTF 口径 + 有效性校验 + 新提交规范**，不适配则提交无 RTF 成绩。
> 设备停用数日后恢复，本文同时补记录此期间官方分支新增提交 `b06198f`（2026-08-19）。
> ⚠️ 2026-08-21 记录时工作区 glusterfs 挂载点**只读**（写入 EROFS，读取正常），本文暂存 /root，存储恢复后移入 `docs/` 并 git 提交。

---

## 一、通知原文（逐字）

> 📢 【重要通知】llama.cpp-omni 赛道排行榜上线 & 测评分支更新 & 提前提交说明
>
> 各位 llama.cpp-omni 子赛道的参赛选手大家晚上好！以下三项重要更新同步给大家：
>
> 🔹 **评测排行榜现已上线**
> llama.cpp-omni 赛道评测排行榜已正式上线，选手提交通过评测后可查看实时排名。所有提交将在官方统一评测环境中按顺序依次执行，评测结果将每2-3天更新至排行榜，请各位选手留意官网榜单动态。
> 🔗 排行榜地址：https://ascend.openbmb.cn/leaderboard
>
> 🔹 **统一测评分支更新**
> 为统一 RTF 测评口径、提升测评公平性和代码复现效率，现已在统一测评分支上完成更新：
> 📌 测评分支：https://github.com/tc-mb/llama.cpp-omni/tree/bench/huawei
> 📖 评测说明：evaluation/README.md
> 📦 提交说明：SUBMISSION_GUIDE.md
> 本次更新优化了双工链路归帧逻辑，修复了部分评测问题，并补充完善了 RTF 计算方式、人工复核说明及提交规范。
> 此前未适配统一流程的提交已由评测人员人工适配和复核，后续提交建议尽量适配最新版测评流程。
>
> 🔹 **鼓励提前提交与结果自测**
> 为帮助各参赛队伍更好地评估方案、降低最终提交的不确定性，我们鼓励大家在正式截止前提前提交作品，先行查看官方评测结果。
> 本赛道评测方法已全程公开，选手可基于公开方法自行复现评测流程。若您的自测结果与官方评测结果存在偏差，欢迎随时联系组委会发起共同审核，我们将与您一起排查差异原因，确保评测结果的准确与公平。
>
> 请各位选手对照最新测评分支和提交说明完成适配与自测后再提交评测。如有疑问，可在群内反馈。预祝大家取得好成绩！🚀

## 二、官方分支变更清单（c9785cc → b06198f，2026-08-19 "refine rtf test" #100）

| 文件 | 变更 | 影响 |
|---|---|---|
| `SUBMISSION_GUIDE.md` | **新增**（265 行） | 提交规范重写：submission.zip 四件套、架构级改动复核通道（§1.2）、GGUF 配套变量说明（§9.1） |
| `evaluation/README.md` | +103/-20 | 新 RTF 口径（core 帧 pooled）、有效性检查、自测指引、计时字段契约 |
| `evaluation/config.env` | +68/-7 | 新增 RTS_* 全套配置、VIDEOMME_SAMPLE_RATIO、RTS_TEST_CASE_DIR；RTS_DEVICE_ID 降级为兼容项 |
| `evaluation/run_eval.py` | +420/-24 | --videomme-sample-ratio、pooled 报告、新任务顺序支持等 |
| `evaluation/run_all.sh` | +16/-1 | 任务默认顺序改为 **rts,tts,daily-omni,videomme**（RTF 优先） |
| `evaluation/judge-final/run_validity.py` | **新增**（198 行） | RTS 数据完整性与实时资格判定（data_valid / realtime_eligible） |
| `evaluation/judge-final/run_judge_direct.py` | +245/-38 | 采集新 SSE 字段、有效性接入、输入丢弃计数 |
| `evaluation/judge-final/omni_client/{duplex,media,server}.py` | +79/-21 +6/-3 +46/-9 | 新协议字段透传、wav 完整性轮询 |
| `evaluation/judge-final/runner/duplex_eval_runner.py` | +41/-28 | input_dropped_count 落 meta；输入间不再 full_reinit（改整体重启 server） |
| `evaluation/judge-final/scripts/eval_duplex_e2e_latency.py` | +49/-2 | 解析 t2w_dequeue 事件；frame 聚合 n_tts/n_samples/sample_rates；调 run_validity |
| `evaluation/judge-final/scripts/make_test_case.py` | **新增**（144 行） | 自测输入生成：样例视频按正式参数切 1s WAV/JPG |
| `evaluation/judge-final/tests/test_rts_guardrail.py` | **新增**（224 行） | RTS 守卫测试 |
| `evaluation/videomme/stratified_sampling.py` + test | **新增** | Video-MME 分层采样（duration/domain/sub_category，确定性等距，无随机） |
| `evaluation/videomme/eval_cpp_pipeline.py` | +25/-3 | 采样接入、完整性断言放宽 |
| `tools/omni/omni.h` | +14 | T2WOut 增 src_cnt/turn_id/producer_seq/generated_audio_tokens/generation_ok/enqueue_seq/enqueue_time；last_chunk_timings 增 audio/vision_expected/ok/media_error；两个原子计数器 |
| `tools/omni/omni.cpp` | +305/-36 | **归帧溯源**：LLMOut/TTS/T2W 全程传播 src_cnt/turn_id/producer_seq；TTS 线程只合并同一 src 的队列头连续段；t2w 线程按 src 分批出队、wav 命名 `src_cnt*1000+N`；stage_timing.jsonl 增 tts/t2w/t2w_dequeue 新事件字段；修 t2w_thread_func_cpp 空队列竞态 |
| `tools/server/server-omni.cpp` | +13 | SSE metrics 增 audio_expected/audio_ok/vision_expected/vision_ok/media_error |

> 不可修改文件清单（正式评测用基线覆盖并校验）**未变**：`evaluation/`、`tools/omni/omni-eval-cli.cpp`、`omni-eval-daily-cli.cpp`、`omni-tts-eval.cpp`、`tools/omni/CMakeLists.txt`。omni.cpp / server-omni.cpp / omni.h **不在清单内**（官方自己也在改）。

## 三、新 RTF 口径（速度成绩，与旧口径的关键差异）

### 3.1 定义

```
RTF = Σ core 帧 compute / Σ 对应音频时长        （pooled ratio，非 per-input 平均）
compute = max(VPM, APM) + LLM_prefill + LLM_decode + TTS + token2wav
```

- **core 帧**：每个语音 turn 去掉首帧（冷启动）与含最终 flush 的尾帧后的稳定帧。
- 分子来自 server 上报：`vpm_ms / apm_ms / llm_prefill_ms / cost_llm_ms`（SSE metrics）+ `tts_ms / token2wav_ms`（stage_timing.jsonl）。
- 成绩是**整批 pooled**：Σ 所有合法 core 的 compute / Σ 对应音频，短输入与长输入不等权。
- 单输入自测（3 core 帧）抖动大：基线 F16 core RTF ≈ **1.1~1.2**（自测只验证链路，不预测成绩）。

### 3.2 有效性契约（run_validity.py，全部 fatal 项任一命中 → data_valid=false → 无成绩）

| 检查 | 条件 |
|---|---|
| INPUT_CHUNK_DROPPED | 输入 chunk 被丢弃数 > 0 |
| SRC_CNT_MISSING / SRC_CNT_NOT_FOUND / SRC_CNT_MISMATCH | tts/t2w 事件必须带 src_cnt；src_cnt 必须存在于输入帧；chunk 的 stage_cnt == cnt |
| MEDIA_AUDIO_MISSING / MEDIA_VISION_MISSING | audio/vision_expected 时 audio/vision_ok 必须 true（模态编码静默失败判定） |
| SPEAK_NO_WAV | mode=SPEAK 的帧必须产出 t2w(wav) 事件 |
| WAV_INTEGRITY_MISMATCH | judge 轮询到的 wav 与 C++ 事件报告一致 |
| DUPLICATE_WAV_ID | wav 文件名全局唯一 |
| CORE_* 六连 | core 帧：mode=SPEAK、n_chunk=n_tts=n_wav=1、**n_samples=24000、sample_rate=24000** |
| **TTS_NONFINAL_TOKEN_COUNT_NOT_26** | 非尾帧 TTS 必须恰好生成 **26 个 audio token** |
| TTS_GENERATION_FAILED | generation_ok=false |
| T2W_MIXED_SRC_BATCH | t2w_dequeue 的 distinct_src_cnt > 1 |
| NEGATIVE_CAUSAL_LATENCY | 因果延迟 < -5ms |

### 3.3 实时资格（realtime_reasons 任一命中 → realtime_eligible=false → 无成绩）

| 检查 | 条件 |
|---|---|
| T2W_CROSS_SRC_QUEUE_BACKLOG | 出队后队列仍残留其他 src 的项 |
| T2W_QUEUE_DEADLINE_MISS | 出队时 oldest_wait_ms ≥ send_interval_ms（=1000ms） |

> ⚠️ **与 P1.7 的直接冲突点**：P1.7 队列解耦（LLM 超前 TTS 多帧）若造成 T2W 队列积压跨 src / 等待超 1s，会直接命中上面两条 → **架构级改动必须重新验证实时资格**，不能只看 RTF。

### 3.4 正式评测配置（与本地 config.env 的差别）

- 输入：**不公开的预切分音视频片段**（1s WAV/JPG），本地自测用 `judge-final/scripts/make_test_case.py` 从公开样例视频 omni_duplex1.mp4 生成。
- `RTS_ASSIGNMENT_MODE=rotating_groups`（多卡轮换，每输入每卡各跑一次；单卡自测只能用 round_robin+1 轮）。
- `RTS_MIN_CORE_FRAMES` 取**远高于**模板 3 的值，靠多输入池化满足。
- 相邻输入之间**整体重启 server**（状态隔离，不是清 KV）。
- 以下变量正式评测会被替换成固定值，本地改动不影响线上：RTS_TEST_CASE_DIR / RTS_SEND_INTERVAL_S / RTS_PAD_* / RTS_MODEL_LOAD_SLEEP_S / RTS_MIN_CORE_FRAMES / RTS_MAX_RETRIES / EVAL_SEED / GGML_CANN_WEIGHT_NZ / GGML_CANN_ACL_GRAPH。
- 计时字段契约：保持 vpm_ms/apm_ms/llm_prefill_ms/cost_llm_ms（SSE）+ tts_ms/token2wav_ms（stage_timing.jsonl）兼容即自动接入评分；架构级改动无法兼容时走 SUBMISSION_GUIDE §1.2 材料复核。

## 四、新提交规范（SUBMISSION_GUIDE.md 要点）

```
submission.zip（唯一提交物，外层不得套选手名/日期目录）
├── README.md              优化说明/构建运行/复现步骤/结果说明（§4 逐节要求）
├── demo.mp4               完整演示视频（启动+连接+至少一次完整交互，通用 MP4）
├── llama.cpp-omni.zip     git archive --prefix=llama.cpp-omni/ HEAD（只含 tracked）
└── integration-support.zip  MiniCPM-o Demo 等仓库外支持代码（顶层 integration-support/ + 自带 README）
```

- **基线**：必须以官方 `bench/huawei` 为开发基线；提交前 `git status --short` 必须无输出；`git log -1 --oneline` 写入提交说明。
- **禁含**：.git/、build/、模型权重、优化后 GGUF、评测数据、生成结果、日志、venv、密钥、.DS_Store/macOS 元数据。
- 量化模型/GGUF 转换要求 → 外层 README §9.1 表格说明（角色/来源/量化类型/SHA-256/放置路径/转换命令），不得只写"使用量化模型"。
- **架构级改动（§1.2）**：涉及调度架构、事件/帧编号、阶段划分、计时上报的改动，须在外层 README 提供补充复核材料：调度设计、帧编号规则、自定义 RTF 测量方法、与官方口径逐项对应、干净环境复现命令、基线对比。复核时间可能长于常规提交。
- 环境变量：必须在外层 README 逐项列明（官方默认值/提交值/作用）；**官方 8-11 表态"提交可上传环境变量"已落地**（README 明确"若后端优化需要开启，可在提交时一并上传自己的环境变量"）。
- 不合格示例（§8）：成对 ._ 文件、直接压缩工作区、带权重、README 缺可执行步骤、口径与官方不一致且无 §1.2 材料等。

## 五、我们现状 vs 新要求（差距清单）

| # | 项 | 现状（2026-08-21 本地） | 差距 | 动作 |
|---|---|---|---|---|
| 1 | omni.cpp 归帧溯源（src_cnt/turn_id/producer_seq 传播、TTS 同 src 合并、T2W 按 src 分批、wav 命名、t2w_dequeue 事件） | ❌ 无（= c9785cc + 102 行自研 diag/实验改动，10378 行注释自曝"src_cnt 永远停在 0，wav 无法归帧"） | 必挂 SRC_CNT_MISSING/SPEAK_NO_WAV 等 | 3-way merge：base c9785cc + official b06198f + 我方 102 行 |
| 2 | server-omni.cpp SSE 新字段（audio/vision_expected/ok/media_error） | ❌ 无（有 vpm_ms/apm_ms 等旧字段） | 判 MEDIA_*_MISSING 缺数据 | 直接取官方 b06198f 版（我方无改动） |
| 3 | omni.h T2WOut/last_chunk_timings 新字段 | ❌ 无（我方仅 5 行差异） | 同上 | 3-way merge |
| 4 | evaluation/ 同步到官方 b06198f | ❌ = c9785cc 官方树（我方无本地改动，差异全是官方自身变更） | 校验=旧基线对比失败；本地无 run_validity/make_test_case | rsync 官方 b06198f evaluation/（保留 gitignored 产物） |
| 5 | 任务顺序 | ⚠️ 本地 videomme,daily-omni,tts,rts | 官方 rts,tts,daily-omni,videomme（rts 优先） | 随 evaluation/ 同步自动解决 |
| 6 | benchmark/*.env（EVAL_CONFIG 覆盖） | ⚠️ 旧 config.env schema | 新 RTS_*/VIDEOMME_SAMPLE_RATIO 键需适配 | 按新 schema 更新 eval-smoke-local.env 等 |
| 7 | 打包脚本 package-submission.sh | ❌ 旧规范（tar.gz + code/scripts/benchmark/docs 七目录） | 新规范 submission.zip 四件套 + git archive + 外层 README | 重写；llama.cpp-omni.zip 需从"官方基线+我方改动"的干净 git 树生成（当前 code/llama.cpp-omni 无独立 .git） |
| 8 | 外层 README.md / demo.mp4 / integration-support.zip | ⚠️ 素材有（docs/reproduce-guide.md、benchmark/demo-evidence、demo-video、code/MiniCPM-o-Demo）但未按 §4/§5/§6 整理 | 需按规范成文/成片/成包 | 打包阶段完成 |
| 9 | 自测闭环（新 harness） | ❌ 旧 harness 跑过（08-15 sessions 残留） | 需 make_test_case + run_all.sh --smoke 2 + batch_validity 双 true | Phase 2 |
| 10 | RTF 成绩口径 | ⚠️ 旧数字（NZ=off e2e 1.06 speak 8 / perf-duplex 口径）已不适用 | 新口径 = core 帧 pooled，需重测 | Phase 3 |

## 六、影响判断与策略

### 必做（不做 = 无 RTF 成绩）
1. **移植官方 b06198f 归帧逻辑**到本地 omni.cpp/server-omni.cpp/omni.h（差距 #1-3）。我们与官方 c9785cc 的差异仅 102 行（诊断开关 + OMNI_T2W_STEPS + image_id 门控 + 系统提示，默认行为=官方），冲突面小；P1.7 队列解耦已于 `90017f1 对齐官方` 回退，不在当前树。
2. **evaluation/ 同步**官方 b06198f（差距 #4），更新 benchmark/*.env（#6）。
3. **新 harness 自测**：make_test_case.py + run_all.sh --smoke 2（rts 优先），`batch_validity.data_valid && realtime_eligible == true`（#9）。
4. **新口径 RTF 复测**（NZ=off、独占、≥3 次中位），与官方基线（样例 core RTF 1.1~1.2）对比（#10）。

### 应做（提交规范要求）
5. **打包脚本重写**为 submission.zip 四件套；llama.cpp-omni.zip 用 staging git 仓库方案：`git clone official bench/huawei → 覆盖我方 merged 代码 → 提交 → git archive`（满足"bench/huawei 基线 + git HEAD + status clean"）。
6. 外层 README（§4 结构）、demo.mp4 整理、integration-support.zip（MiniCPM-o Demo）。
7. **提前提交探路**（官方明确鼓励；用户既定策略：先提交一版拿反馈再调整）。注意排行榜需登录态查看，数据 2-3 天更新。

### 策略性机会（可选，风险自担）
8. **P1.7 队列解耦 + T2W 24 线程 + NUMA 绑核**（历史机制 RTF 0.57-0.59，NZ=on 污染作废但机制有效）在 **NZ=off + 新 harness** 下重新评估：走 SUBMISSION_GUIDE §1.2 架构级复核通道（官方正式开放）。**风险**：T2W_CROSS_SRC_QUEUE_BACKLOG / T2W_QUEUE_DEADLINE_MISS（§3.3）——深队列若造成 T2W 积压跨 src 或等待>1s 则实时资格直接失效。**缓解**：safe 版先提交探路，P1.7 作为第二版；验证以 realtime_eligible=true 为前提，再谈 RTF。
9. **Video-MME**：官方新增确定性分层采样（VIDEOMME_SAMPLE_RATIO，0.5=450 视频/1350 题）。正式评测可能用采样而非全量 2700 → 我们 63.3%±5.7pp（270 合池）的申诉口径需按采样逻辑重新对齐；采样是确定性算法（无随机），与我们手动合池的口径**不同**。

## 七、行动计划（待用户批准后执行）

| Phase | 内容 | 产出/验收 |
|---|---|---|
| 0 | 本记录落盘 + decisions.md + CLAUDE.md 更新 + git 提交 | ✅ 本文档 |
| 1 | 移植官方 b06198f：evaluation/ rsync + omni.cpp/h/server 3-way merge（git merge-file） | diff 收敛，仅保留我方 102 行 delta |
| 2 | 构建（llama-omni-server + eval targets）+ make_test_case.py + run_all.sh --smoke 2（rts 优先） | batch_validity 双 true；四任务通过 |
| 3 | 官方口径 RTF 复测：NZ=off、独占、taskset 绑 NUMA、≥3 次中位；对比官方基线 1.1~1.2 | RTF 数字 + 与基线对比 |
| 4 | 打包重构：staging git 仓库方案 + 外层 README（§4）+ demo.mp4 整理 + integration-support.zip + 自检清单（SUBMISSION_GUIDE §8） | submission.zip 四件套通过自检 |
| 5 | 提前提交探路 → 记录赛方反馈 | 排行榜/邮件反馈 |
| 6 | （可选）P1.7 恢复 + §1.2 复核材料 + realtime_eligible 验证 | 第二版提交候选 |

**风险**：设备恢复后 NPU/CPU 可能被并行会话占用（先查）；glusterfs 只读（已确认，写入 EROFS，remount 无权限）——Phase 1-4 需存储恢复后才能在本机执行；新 harness 首次全量跑耗时长（rts 优先，TTS SIM 单进程 CPU）。

## 八、附录

- 官方树本地镜像：`/root/official-tmp`（git clone --depth 15 --branch bench/huawei，含 c9785cc..b06198f 全量对比能力）。
- 本地 git fetch 失败原因：工作区在 glusterfs（fuse.glusterfs rw 挂载）上 `.git/FETCH_HEAD` 写入报 EROFS；workaround = clone 到 /root（overlay 本地盘）再 diff/rsync。
- 排行榜：https://ascend.openbmb.cn/leaderboard （SPA，API 在 /api/*，数据需登录态；`/api/get_submit_status` 匿名可通）。评测结果 2-3 天刷新一次。
- 官方 README 原文关键句："自测只验证流程，不预测成绩"；"样例视频是公开的链路验证素材，不是最终测试集，针对它做特化没有意义"。


---

## 九、徐帅通知（2026-08-19 20:30）：共享模型优先 + user_data 清理摸底（追加留档）

> 来源：赛事群，徐帅（平台侧人员）2026-08-19 20:30：
>
> 1. **优先使用共享模型**：请尽量加载 `/workspace/shared_assets` 目录下的共享模型，避免在个人目录重复存储模型文件，以节省磁盘空间。
> 2. **清理 `/workspace/user_data` 旧数据**：请大家检查自己的 `/workspace/user_data` 下主要存放那些内容？是模型权重还是数据集信息？后续我们可根据实际情况规划更合理的存储策略。

### 9.1 与只读故障的关联（重要假设）

- vol_bigfile 卷 df 显示 **98% 使用率**（22T/23T，剩 605G）；平台 8-19 发消息要求清理；8-17~8-21 之间卷 rw 挂载点变为 EROFS 只读。
- **假设：卷只读与平台侧管理动作（配额管控/维护/冻结）相关**，清理 user_data 可能是恢复写权限的前提之一，或至少是恢复后必做项。
- 行动建议：**直接向徐帅询问 vol_bigfile 卷只读状态与恢复预期**（他即平台侧对接人），同时给出本机内容盘点以示配合。

### 9.2 user_data 内容盘点（2026-08-21 实测）

| 位置 | 内容 | 量级 | 可清理性 |
|---|---|---|---|
| `temp_project/minicpm-ascend-challenge/code/llama.cpp-omni/evaluation/appendix/` | videomme99 视频(2.7G)/videomme/seedtts_testset_zh/Step-Audio-2-mini(token2wav ONNX)/wavlm_large_finetune.pth | ~10G | 数据副本，shared_assets 有同源数据 |
| `benchmark/video-mme-cookbook/diag/videomme99_data/` | **与 appendix/videomme99/data 完全重复的 7 个视频** | 2.7G | ⭐ 删一份即省 2.7G |
| `benchmark/daily-omni-data/` | Daily-Omni 转换数据 | ~2.7G | 可保留（评测用）或换软链 |
| `benchmark/seed-tts-eval/sv/` | wavlm-large + wavlm_large_s3prl.pt（SV 打分权重） | ~2G | 可重下（hf-mirror），保留也可 |
| `seedtts_testset/` | Seed-TTS zh 测试集（转换后） | 1.2G | 评测必需，保留 |
| `s3prl/` | SIM backbone 源码 | 190M | 评测必需，保留 |
| `temp_project/minicpm-ascend-challenge/code/llama.cpp-omni/build*` | 构建产物（build + build-cann） | 未量化（通常 10-30G） | ⭐ 可重建，最优先清理候选 |
| `venv-tts/` `venv-trackb/` | Python venv（TTS 评测/轨道B） | 未量化（通常 2-8G） | venv-tts 重建有坑（见 docs/tts-seed-eval.md），暂留 |
| `temp_project/` 其他（Astro_Starlight_GitHubPages 15831 文件、kunpengxunlian、hermesagent、codegraph、vllm-omni） | 历史项目 | 未知 | ⭐ 非赛事内容，确认后清理 |
| **模型权重（GGUF）** | **无**——模型全部在 `/workspace/shared_assets/models/`，user_data 下无重复 gguf（find >200M 无 .gguf） | — | 已符合徐帅第 1 条要求 |

### 9.3 回复徐帅草稿

> 收到。我们 `/workspace/user_data` 下主要是**评测数据集与中间产物**，无重复模型权重（模型均加载 `/workspace/shared_assets` 共享目录）。
> 构成：① 赛事 repo 及构建产物（build 目录可重建，已列入清理）；② 三个评测数据集副本（Video-MME 切片 / Daily-Omni / Seed-TTS，部分与 shared_assets 同源，确认后可改软链）；③ 评测依赖（s3prl / wavlm / token2wav ONNX）。
> 发现一处数据重复（videomme99 视频存了两份，2.7G），已列入删除清单。待卷恢复写权限后执行清理。
> 另：近期 `/workspace/user_data` 挂载点变为只读（写入报 EROFS），无法删除/提交，请协助确认 vol_bigfile 卷状态及恢复预期。
