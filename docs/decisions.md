# 决策记录（Decision Log）

记录参赛过程中的关键决策与依据。时间倒序。

## 2026-08-21 决策：官方分支更新 b06198f —— 归帧溯源 + 新 RTF 口径 + 新提交规范，必适配

**背景**：赛事群 2026-08-21 通知（排行榜上线 + 测评分支更新 + 鼓励提前提交）。官方 bench/huawei 更新至 b06198f（2026-08-19 "refine rtf test" #100），新增 SUBMISSION_GUIDE.md（submission.zip 四件套 + §1.2 架构级复核通道）+ run_validity.py（batch_validity 契约）+ omni.cpp 归帧溯源（src_cnt/turn_id/producer_seq）+ 新 RTF 口径（core 帧 pooled）+ 任务顺序 rts 优先 + Video-MME 分层采样。

**关键结论**：
1. 不移植 b06198f 归帧 → batch_validity 必挂（SRC_CNT_MISSING/SPEAK_NO_WAV 等）→ 无 RTF 成绩。**必做**。
2. 我方 omni.cpp 与官方 c9785cc 仅差 102 行（diag/实验开关，默认=官方行为）；3-way merge 零冲突，合并后 diff vs b06198f 恰为 102 行。
3. evaluation/ 我方无本地改动（= c9785cc 官方树），直接 rsync b06198f 即可。
4. 新 RTF 口径：Σ core 帧 compute / Σ audio（pooled）；core 帧硬性 n_samples=24000/sample_rate=24000/非尾帧 TTS 恰 26 token；实时资格 t2w_dequeue oldest_wait_ms<1s 且无跨 src 积压 —— P1.7 深队列与此冲突，架构级改动须重验 realtime_eligible。
5. 提交规范重写：submission.zip = README.md + demo.mp4 + llama.cpp-omni.zip（git archive，bench/huawei 基线，status clean）+ integration-support.zip；打包脚本需重构（当前 code/llama.cpp-omni 无独立 .git，用 staging git 仓库方案）。
6. 策略：safe 版（b06198f 归帧 + 我方 delta）先适配自测 → 提前提交探路（官方鼓励）；P1.7 恢复走 §1.2 复核通道作第二版候选。
7. 环境：2026-08-21 工作区 glusterfs 只读（写入 EROFS）→ 记录暂存 /root/repo-sync-pending，本脚本恢复后落地。

**详见**：[announcement-2026-08-21-official-update.md](announcement-2026-08-21-official-update.md)

## 2026-08-06 决策（P5）：vocoder overlap 流水线实验 — 未达 0.34，回退

**背景**：极限分析理论下限 0.34（C 重叠）。尝试冲 0.34（不破坏 P3/P4）。

**过程**：
1. P5-1 拆 push_tokens_window → push_tokens_only/vocoder_only（保留原函数，bit-精确）。
2. P5-2 t2w_thread 流水线（t2m N ‖ vocoder N-1 async + future + 写 wav lambda + 循环尾/break）。
3. 顺序修正（t2m 先 ‖ vocoder async，future.get 后）。
4. 校验：overlap 生效但 T2W 仅 540→500ms（-40ms），RTF 0.58 = off 0.58（没达 0.34）。

**决策**：
1. **不 merge**（p3-safe-opt/main 保持 P3/P4 RTF 0.57 不破坏）。
2. 根因：vocoder 24 threads(CPU) 与 t2m NPU(CPU 调度) **CPU 竞争** → 弱 overlap。极限 0.34 假设"完全并行"实测不成立。
3. p5 实验 commit `eb93d70` 保留（未来 CPU 亲和细分参考：vocoder 独占 NUMA node + t2m 调度别核）。
4. **RTF 0.57 是红线内 + CPU 物理实际高位**（P5 + NPU化两条突破路均受阻：CPU 竞争 / CANN 无 CNN）。

**详见**：[experiments.md](experiments.md) P5、[perf-ceiling-analysis.md](perf-ceiling-analysis.md)（0.34 理论 → P5 实测 CPU 竞争）

## 2026-08-06 决策（P4）：threads 24 + NUMA node6 绑核（运行时配置，RTF 0.64→0.57）

**背景**：P3（vocoder 16 threads）后 RTF 0.64。逐个击破优化方向（NUMA / threads 微调 / C 异步 / NPU化）。

**过程**：
1. **NUMA 绑核 node6（CPU192-223）**：vocoder 本地内存，RTF 0.64→0.61（略有效 + 稳定）。
2. **threads 微调 + NUMA 叠加**：24+NUMA 最优 RTF 0.57（vs 16+NUMA 0.61 / 20+NUMA 0.59）。
3. **NUMA 必需性**：24 不绑核 0.72（差，跨 node remote + 抢核）→ taskset 必需。
4. **C（异步重叠）评估**：需跨 window 重构（拆接口 + 双缓冲 + Flow/voc cache 同步），复杂/质量风险；24+NUMA 同收益且不改代码 → 弃 C。

**决策**：
1. **推荐运行时配置 `OMNI_T2W_THREADS=24 + taskset -c 192-223`**（node6）→ RTF 0.57（beat 基线 48%）。
2. **不改默认 kDefaultThreads（16）**——避免不绑核场景 24→0.72（差于默认 16 的 0.64）风险；reproduce-guide 更新推荐配置。
3. 红线：仅 CPU 线程 + NUMA 绑核，不改推理数学 / 不改代码默认。

**详见**：[experiments.md](experiments.md) P4

## 2026-08-06 决策（P3）：vocoder CPU 多线程（kDefaultThreads 8→16）

**背景**：P1.7 后 TTS RTF 0.83（beat 基线 1.087），但 decode 期 NPU 占空比仅 23-29%（空泡多）。plan 模式规划下一步深入优化（诊断 decode 空泡 → 针对性优化）。

**过程（诊断先行）**：
1. ETH_PROBE（OMNI_ETH_PROBE=1）：LLM dec 14ms + emb 7ms（33% LLM 周期）。但 emb 在 LLM t_done 前，**不在 TTS RTF 0.83**。
2. 候选 E（OMNI_TTS_QUEUE 24/32）证伪（ΔRTF<0.03）→ 队列非瓶颈（P1.7 已解耦）。
3. **OMNI_T2W_PROFILE=1 量化 T2W 分段**：定位真因 = **vocoder(CPU hifigan) 591ms 占 T2W 80%**（8 threads，256 核仅用 8，hifigan 非自回归可并行），token2mel(Flow NPU) 144ms 占 20%。
4. msprof --export 未跑通（output 目录问题）但非必需（OMNI_T2W_PROFILE 已定位）。

**决策**：
1. **vocoder 加线程**（kDefaultThreads 8→16，env OMNI_T2W_THREADS 可覆盖）——红线内（CPU 调度，不改数学）。**TTS RTF 0.83→0.62（降 25%）**，vocoder 591→395ms。
2. 弃：候选 E（队列，证伪）、候选 C（vocoder 异步重叠 Flow，边际——vocoder 仍主）、vocoder NPU 化（工程大/红线风险）、emb 7ms（LLM decode 内部同步，红线区）。
3. threads=32 不稳（CPU 调度/NUMA 抖动），16 为最优。
4. 红线守卫：未改推理数学 / 未触 ggml-cann 6 补丁。

**详见**：[experiments.md](experiments.md) P3

## 2026-08-05 决策（P1.7）：诊断先行 + AICore 当 offload 代理 + LLM→TTS 队列解耦

**背景**：P1.6 把双工 LLM model 上 device 后，docs 记"decode AICore 仅 4% / compute 没真走 NPU"，下阶段 P1.7 目标"双工 LLM compute 真走 NPU + LLM P50 <1000ms"。三个诊断方向（device 绑定 / audio encoder / model 释放）嫌疑未定。

**过程**：
1. **走 plan 流程**（EnterPlanMode + Explore duplex compute 路径）。三个 Explore agent 对根因各执一词（device 绑定 / host_buffer / encoder），**第一手日志分析（p16_final.log）推翻全部**：perf-duplex 用 session API（`stream_decode`，与单工同函数、同 ctx_llama、同 CANN backend），decode 本应上 NPU。
2. **AskUserQuestion 两点确认**：① AICore>30% 当 **offload 代理**（非硬门槛；batch=1 自回归 decode 天然低 util）② **先实测诊断再定点修**。
3. **6 组对照实验 + micro-probe 实测**（C-1…C-8）：C-1 证 decode 真在 NPU（burst 60–84%）；C-2（--no-tts）证 LLM 单独 P50 304ms PASS；C-4 Q8_0 不降速（非带宽主导）；C-6/7 TTS 子系统不能下 CPU；**定位真因 = LLM↔TTS 队列容量 1 锁步**。

**结论 / 决策**：
1. **AICore>30% 当 offload 代理**，不当地对门槛——batch=1 decode memory-bound 天然 util 低，用"decode 期 AICore burst + HBMbw 高"证明 NPU 在算即可（P1.6"AICore 4%"是采样伪影，纠正 docs）。
2. **诊断先行**（runtime 实测 > 静态推理）——三个 agent 的静态结论全错，npu-smi 实测 + micro-probe 才定位真因。沉淀为方法论（rigor-verify-loop）。
3. **修复 = LLM→TTS 队列 1→16 解耦**（`tools/omni/omni.cpp` omni_init，env `OMNI_TTS_QUEUE` 可覆盖）——一行改动，**LLM P50 8295→977ms（8.5×，<1000 达标）**，TTS RTF 0.80 不回归，quality-neutral。
4. **未达 exit 0 诚实记录**：LLM P95 1014ms（临界）+ 首响 1493ms（T2W ~700ms floor）→ exit 2。冲 exit 0 的下阶段方向 = **T2W 提速（n_timesteps，破 prompt_cache 绑定）或 NPU 多流并发**（decode 期 NPU 平均仅 ~23%，硬件 85% 空闲——是执行串行，非算力不足）。
**详见**：[experiments.md](experiments.md) P1.7、[cann-patches.md](cann-patches.md) 已知问题3（已纠正）

## 2026-08-04 决策：子赛道独立评审 + 奖金调整（官方公告）

**背景**：官方公告确认 vLLM-Omni 与 llama.cpp-omni 作为两个独立子赛道，
分别评审、分别排名；面壁追加 90,000 元增设冠军名额，总奖金 406k → 496k。

**对赛道一（llama.cpp-omni）的影响**：
- 我们不再与 vLLM-Omni 参赛者混排——竞争对手范围缩小到只用
  llama.cpp-omni 框架的队伍，排位逻辑更清晰
- llama.cpp-omni 子赛道奖项：冠 1（90k）/ 亚 1（50k）/ 季 1（27k）= 3 奖
- 奖位变少（原性能赛道 6 奖 → 本子赛道 3 奖），但对手也同比例收窄
- 结论：参赛策略不变，仍专注 llama.cpp-omni 子赛道；奖项结构变化
  不影响 RTF 优化主线

## 2026-08-04 决策：本地 ↔ 910B 同步通道 = Git（GitHub 中转）

**背景**：星宇 910B（无公网入站地址）原计划 Cloudflare Tunnel 打通本地 SSH。
实施中发现华为云封了 cloudflared 出站端口（UDP 7844 QUIC 不通，TCP 443 到
边缘也可能受限），隧道方案受阻。

**结论**：放弃 SSH 隧道，改用 Git 仓库（GitHub 远端）作为本地 ↔ 910B 的
唯一同步通道。

**理由**：
1. 910B 出站 443 已验证可达（curl github.com 通），git clone/push 走 HTTPS/SSH 443 无阻碍
2. 不依赖任何隧道/端口放行，平台无感知
3. 项目本就全部版本化在 git 仓库（/opt/minicpm-ascend-challenge，已推 GitHub）
4. 同步内容即仓库内容：代码、脚本、文档、实验结果——天然一致

**工作流**：
- 本地：编辑 → commit → push origin main
- 910B：git pull → 执行/测试 → 结果写回 docs/、benchmark_results/ → commit → push
- 冲突处理：各端改不同文件；同文件冲突以本地为准，手动合并
- 大文件（权重 GGUF）：不走 git，走 ModelScope/对象存储（git 只同步代码与文档）

**隧道后续**：Cloudflare Tunnel 方案保留为备选（端口放行后可复用已建好的
asc-910b 隧道 8eb69525 + ssh.asc910b.opengood.cc CNAME），当前不依赖。

## 2026-08-04 决策（P1.6）：双工 LLM model 上 device（use_mmap=false 突破），compute/流水线下阶段

**背景**：P1.6 深查双工 LLM offload，加双探针（LLAMA ngl + CANN alloc result）定位。
**突破**：perf-duplex `use_mmap=false` + 补丁6 host_buffer → 双工 LLM model **上 device**（HBM 23.6G + alloc 14.4G 成功 err=0 + AICore 峰值 66%）。之前"HBM 3481=model CPU"是采样时机误判。
**成果**：双工 **TTS RTF 0.80 PASS**（首个 <1，接近 4090 0.75）。
**新瓶颈**：decode 中 AICore 仅 4%（model 在 device 但 NPU 几乎没算）+ LLM P50 8840ms（含等待，疑似 audio encoder/流水线）+ model 后续释放。offload 成功但 compute/流水线是独立新问题。
**下阶段**：查 duplex LLM compute 为何 AICore 4%（graph_compute backend / duplex_llm_thread_func）+ duplex 流水线瓶颈（audio encoder/encoder 线程）。
**详见**：[experiments.md](experiments.md) P1.6

## 2026-08-04 决策（P1.5）：host_buffer 默认 false——单工 LLM 上 NPU，双工待 duplex 修复

**背景**：P1.5 改 cann `host_buffer` 默认 false（补丁 6）试图稳定双工 LLM offload。
**结论**：
1. **单工成功**：host_buffer 默认 false 让 omni-cli 单工 F16 LLM 稳定上 NPU（HBM 23.6G + AICore 66% + prefill 0.77s，不需 env）
2. **双工未解**：perf-duplex 双工 LLM 仍 CPU（HBM 3482），根因在 `duplex_llm_thread_func` 计算路径（非 host_buffer）
**下阶段**：深查 `duplex_llm_thread_func` 让双工 LLM 上 NPU（双工评测基线前提）
**详见**：[cann-patches.md](cann-patches.md) 补丁 6 + 已知问题 3、[experiments.md](experiments.md) P1.5

## 2026-08-04 决策（P1 诊断）：910B cann 量化算子缺失 → LLM 改用 F16

**背景**：perf-duplex 双工基线全 FAIL，诊断确认 LLM 在 CPU（AICore=0、HBM 3.4G）。深查发现 cann 后端对 Q4_K_M 量化算子不支持（fallback CPU，prefill 7.9s），对 F16 支持（prefill 0.58s、NPU）；且 cann host_buffer cap 默认让 LLM 落 host buffer（CPU）。
**结论**：
1. 910B 上 LLM 必须用 **F16**（cann 支持、上 NPU），非 Q4_K_M（cann 不支持、CPU）
2. 4090 上"量化是 RTF 主杠杆"在 910B **失效**——量化优化策略需重估（P2 重扫各档 cann 支持）
3. F16 perf-duplex **TTS RTF 0.99**（首个与 4090 实验002/016 的 0.75 横向比的有效基线，同量级实时）
**残留**：F16 **双工模式** LLM 仍未稳定上 NPU（单工 F16 上 NPU、双工不上；`GGML_CANN_NO_PINNED=1` 双工不稳）。下阶段攻克双工 offload。
**详见**：[cann-patches.md](cann-patches.md) 已知问题、[experiments.md](experiments.md) P1

## 2026-08-04 决策：910B3 作为正式评测环境（厂家授权替代 910C）

**背景**：厂家 HiDevLab 910C 资源紧张，通知用 910B3 替代；厂家说明"1 颗 910C 本质就是 2 颗 910B"。
**结论**：当前云环境（910B3 单卡，64GB HBM）即正式评测环境，所有提交数据在此产生，不再等 910C。
**影响**：
1. RTF 绝对值会高于按 910C 给的基线（单卡 910B ≈ 半颗 910C 算力），但选手口径统一即公平
2. 图模式 USE_ACL_GRAPH 在 910B 不支持（acl_graph 头文件缺失）→ 砍掉原计划最大杠杆，靠量化+参数+编译
3. 复现说明、性能报告等所有"环境"字段统一改为 910B3 + CANN 9.1.0-beta.3
**详见**：[环境扫描报告](env-scan.md)

## 2026-08-04 决策：复用官方预置资源（权重 + benchmark 代码）

**背景**：进入云环境后做完整环境扫描。
**发现**：
1. `/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/` 预置全套 11 档量化 + 全模块权重（只读直用，免下载）
2. `code/daily-omni/` 含 Daily-Omni benchmark 完整代码（run_pipeline.py + baseline/），原"等 starter kit"作废
3. CANN 9.1.0-beta.3 预装（>官方 beta1 要求，兼容）；msprof/atc 可用；鲲鹏 256 核 + 2TB 内存
4. 缺：ffmpeg / docker / ninja / torch / soundfile / librosa（Demo 与 perf 脚本依赖，按需装）
**结论**：P0 权重下载步骤删除；P2 量化扫描扩到 11 档；P6 Demo 改裸机部署 + 补 ffmpeg。
**详见**：[环境扫描报告](env-scan.md)

## 2026-08-04 信息更新：赛事终止日调整

赛事方通知终止日调整为 2026-08-31（原提交截止 08-17）。按提交截止 = 8/31 倒排计划。
⚠️ 以官方最终公告为准（待最终确认是提交截止还是复现评审日调整）。

## 2026-07-31 决策：放弃赛道二，专注赛道一（llama.cpp-omni）

**背景**：时间紧（提交 8/17），双赛道并行稀释精力。
**报名状态**：✅ 已通过（2026-07-31，赛道一 llama.cpp-omni 子赛道）

**结论**：放弃赛道二（创新应用），全力投入赛道一
（高性能推理优化 - llama.cpp-omni 子赛道）。

**理由**：
1. 参赛核心目标是借比赛学习昇腾推理优化，赛道一学习价值最高
2. 官方提供 HiDevLab 910C 算力，硬件无阻碍
3. 双线并行风险：两个都可能做不好；单线专注更符合时间现实
4. 赛道二方向已调研完整，如未来需要可随时重启（文档已沉淀）

**倒排计划**：
- 7/31-8/03 等算力审批 + 本地编译 llama.cpp-omni CPU 版 + 下 GGUF + 读文档
- 8/04-8/10 910C 跑通基线 + 量化档位扫描
- 8/11-8/14 深度优化（KV cache/并行/chunk 参数）+ benchmark 完整数据
- 8/15-8/17 性能报告 + 材料收尾（8/17 提交截止）

**优化目标定位**：基线 + 2-3 项工程优化（量化/编译/运行时参数），
不做算子级深度优化（时间不允许）。

## 2026-07-31 决策（修正）：赛道一重新评估中

**背景**：官方统一昇腾环境仅用于复现验证，不提供开发期环境；
本地无昇腾 910C NPU 资源。

**结论**：放弃赛道一（高性能推理优化），选择赛道二（创新应用）。

**理由**：
1. 赛道一需要 AI Infra 内核能力（算子/编译/引擎调优）+ 910C 硬件，
   无 NPU 资源且 2.5 周从零上手不现实，陪跑概率极高
2. 赛道二考察可运行 Demo + 工程完整度 + 产品化表达，
   与本团队工程/部署/运维能力匹配
3. 官方提供免费 API + 开源 Demo 代码，开发环境无阻碍（详见 api-test.md）

## 2026-07-31 决策：技术路线 = 官方免费 API 为主

- 主链路：官方 API（Chat Completions 轮次对话/图片理解 + Realtime 全双工）
- 兜底：本地 CPU 部署 llama.cpp-omni 量化版（secs，<12GB 内存），
  仅作部署能力展示与离线兜底，不承担实时主路径
- 演示约束：Realtime video 模式有效对话约 90 秒，演示脚本按此设计

## 2026-07-31 决策（修正）：赛道一重新评估中

**背景更新**：官方通过 HiDevLab 平台提供赛道一算力——
单卡 910C 统一评测；报名后需在 HiDevLab 注册账号申请比赛卡时资源；
llama.cpp-omni 与 vLLM-Omni 子赛道需选择不同镜像版本。
→ 硬件障碍解除，赛道一可行性需重新评估（用户对赛道一感兴趣）。

**评估要点**：
- 优势：官方提供 910C 卡时；用户工程部署能力强，llama.cpp-omni 子赛道
  偏工程优化（编译/量化/调度），比 vLLM-Omni（偏算子/框架内核）更匹配
- 风险：2.5 周内跑通基线+有效优化挑战大；优化效果不确定
- 待确认：HiDevLab 算力申请流程、审核时长、额度；算力申请指南文档
- 策略候选：赛道一（llama.cpp-omni）冲刺 + 赛道二保底（若规则允许同时参赛）

## 2026-07-31 决策：场景推荐 = 机房/服务器智能巡检助手（待确认）

**候选场景对比**：
| 场景 | 全模态体现 | 演示直观度 | 差异化 | 工程量 |
|------|-----------|-----------|--------|--------|
| 机房/服务器智能巡检 | 强（看状态灯+语音+主动提醒） | 强（现场摄像头演示） | 中高（运维专业深度） | 中 |
| DBA 报错截图助手 | 中（截图+语音） | 中 | 高（DB 行业） | 低 |
| 教育/生活通用助手 | 强 | 强 | 低（同质化） | 中 |

**推荐**：机房/服务器智能巡检助手
- "边看边听主动说"正好是 MiniCPM-o 4.5 招牌能力，评委秒懂全模态
- 真实机房（cvknode/secs）是现成演示场地
- 结合运维背景可做专业深度（状态灯识别、告警处理知识库）

**MVP 范围**（2.5 周）：
- Web 界面：视频/摄像头画面 + 语音对话 + 文本记录
- 核心闭环：看（画面理解）→ 听（语音提问）→ 说（语音回答/主动提醒）
- 故障知识库：服务器状态灯、常见告警、数据库报错处理

**未决事项**：场景最终确认；官方 API 免费额度/限流长期稳定性

## 2026-08-22 决策：VPM(ViT) Flash Attention（OMNI_VISION_FA）—— 确认采纳，RTF -2.1%，精度零翻转

**背景**：v4 提交后评测排队（等待调度），深挖"数据结构和 NPU/CPU 结构"优化空间。发现 VPM 视觉编码器（vision.cpp build_attn）有 TODO 但未实现 FA，而 LLM 的 FA（OMNI_FORCE_FA）已验证 -59% decode。VPM 360ms 恒定是 encode 段（0.44s）主体。

**验证过程**（2026-08-22，全部官方口径 rts --smoke 2 / videomme --smoke 10，NZ=off 官方路径）：
1. VPM FA 分支（vision.cpp build_attn，env `OMNI_VISION_FA` 门控，默认关=官方行为）：ViT 27 层 + resampler 的 attention 走 ggml_flash_attn_ext（布局对齐 llama-graph.cpp build_attn_mha；v 需 permute(0,2,1,3)+F16 cast；n_batch>1 回退 mul_mat）。
2. 两次崩溃修复：cont_3d nelements 断言（reshape 尺寸用成员 n_embd 错——resampler d_head/heads 与 ViT 不同，改用 q->ne[0]*q->ne[2] 动态计算）。
3. **性能**：encode 0.4519→0.4149（-8.2%），vpm_ms 360.8→343.3（-4.9%），core RTF 1.401→1.3717/1.3814（-2.1%，2 次独立 run 稳定）。
4. **精度**：videomme 10/10 输出逐字节一致（VPM FA on/off，LLM FA 均开）；batch_validity 全 true。
5. **证伪项**（同批验证，全部回退）：
   - TTS ResiLM FA（voxcpm2_runtime.cpp use_flash_attn）：tts 段无改善（stage_ms cost_tts 341→363 略负）→ 关闭回退。
   - TTS 队列 1→16（OMNI_TTS_QUEUE）：RTF 1.386 无收益；q_before 恒=1（LLM 受输入节奏限制而非 TTS 反压，队列空转）→ 关闭回退。
   - **官方 RTF 口径认知（重大）**：core RTF = Σ各段耗时/Σaudio（compute_total=vpm+apm+llm_prefill+cost_llm+tts+token2wav 之和），非墙钟 → **跨帧重叠/多流并发在官方口径下收益≈0**（重叠段的耗时仍被相加）→ B-2 NPU 多流并发路线关闭。
   - KV cache 量化（--cache-type-k q8_0）：CANN 后端无 GGML_OP_QUANTIZE 算子，KV 量化走 CPU quantize+dequant（带宽不减反增）→ 关闭。
   - T2W 24 线程不绑核（910B4）：t2w 0.2758→0.2717（略优，旧机"24 不绑核变差"结论在 910B4 不成立）→ README 的 OMNI_T2W_THREADS=24 声明安全。

**决策**：采纳 VPM FA（vision.cpp 单文件改动 + OMNI_VISION_FA=1 env 随提交上传）。v5 提交包 = v4 四件套 + vision.cpp（README 文件清单 4→5）+ env 表加 OMNI_VISION_FA=1。预期官方 RTF 1.40→~1.37（同口径 -2%）。

**详见**：experiments.md 2026-08-22 节；原始产物 evaluation/output/20260822_011106（A1）、20260822_011706/012018（videomme A/B）。
