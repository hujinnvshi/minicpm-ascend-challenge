# 提交物清单与测评流程（2026-07-31 官网评审更新）

> 来源：官网赛事详情页（ascend.openbmb.cn/competition）7/31 更新 + 官方算力申请指南（飞书）

## 一、测评流程（5 步，全部通过才排名）

1. **框架与环境检查** — 确认使用指定框架（llama.cpp-omni），能在官方昇腾环境部署运行
2. **Benchmark 精度评测** — Daily-Omni / TTS-Seed / Video-MME，相对官方基线降幅 ≤2pp
3. **Demo 可用性验证** — 接入官方 Demo（github.com/OpenBMB/MiniCPM-o-Demo）完成端到端功能、流式输出、稳定性测试。**仅能跑 Benchmark 无法接入 Demo 的方案不满足准入**
4. **性能评测** — 统一硬件/环境/模型/输入/脚本下测 RTF，越低越好
5. **工程复现审查** — 按提交代码/配置/脚本/视频/复现文档在官方环境重跑；无法复现/缺文件/结果明显不一致按规则处理

## 二、精度准入细节

- 例：基线精度 85% → 优化后不得低于 83%；基线 70% → 不得低于 68%
- 以下情况不能进入性能排名：精度降幅超范围 / 核心能力明显下降 / 输出结果异常 / 无法完成指定 Benchmark / 修改模型行为导致结果失去可比性
- 不同框架用各自官方基线，不跨框架比较

## 三、Demo 可用性检查项（8 条）— 已验证通过（2026-08-06，详见 `benchmark/demo-evidence/README.md`）

- [x] 1. 模型服务正常启动 — 3 端口 LISTEN + `/health` ok
- [x] 2. Demo 正常连接推理服务 — worker 注册 + 心跳 + capabilities 全
- [x] 3. 音视频文本输入正常处理 — 文本多轮 OK；音视频 capabilities 支持 + 页面可达（深度双工可选）
- [x] 4. 模型输出完整 — 完整文本响应（"你好，我是Qwen…"等）
- [x] 5. 流式语音输出连续 — Voice Response + Streaming + TTS init/decode 日志
- [x] 6. 无明显卡顿/中断/异常退出 — LLM 正常 end token + session close + log 无 error
- [x] 7. 完整交互流程 — 端到端 文本→文本+语音（首轮 24s 含懒加载 / 稳态 366ms）
- [x] 8. 连续运行稳定 — 多轮 3 轮连续稳定，进程不崩

## 四、最终提交内容清单（对照自查）

### 1. 完整代码与配置
- [x] 推理适配与性能优化代码(6 cann 补丁 + P1.7 队列 + P3 vocoder + P6 extract 加固 + P7)
- [x] llama.cpp-omni 相关配置(build-cann,CANN 9.1.0-beta.3,F16)
- [x] 服务启动脚本(`scripts/serve.sh`)
- [x] Benchmark 执行脚本(`scripts/benchmark.sh` + `benchmark/{daily-omni,video-mme,seed-tts-eval}/`)
- [x] Demo 启动脚本(`scripts/demo.sh`)
- [x] 依赖与环境配置文件(`docs/cann-patches.md` + `docs/reproduce-guide.md` §1)

### 2. Benchmark 评测结果（3 个全要）
- [x] Daily-Omni 结果(`benchmark/daily-omni/result.json` + `daily_omni_test.py`;单帧/低帧 6.7%/12.5%,**多帧(8帧)触发模型退化**——已做交错打包+whisper KV 修复(commit `c9d9499`)均生效但未解高帧,真因在视觉路径;**已问组委会**多帧配置/门槛,见 `organizer-inquiry-email.md`)
- [x] TTS-Seed 结果(`benchmark/seed-tts-eval/gen/zh/result.json`;WER 0.20 官方同口径达标 ✅;SIM 0.84 base-plus,**官方 UniSpeech SV 口径本地不可实现**——`wavlm_large_finetune.pth` 是 UniSpeech GRP variant,s3prl 标准 WavLM 不兼容,见 `docs/asv-official-plan.md` C 实证;已问组委会 Q5,见 `organizer-inquiry-final.md`)
- [x] Video-MME 结果(`benchmark/video-mme-cookbook/` CookBook 官方 pipeline + ccec build `llama-omni-eval-cli` 跑通;smoke 0/2 **多帧退化**(910B4/CANN 硬件级,context 40960/FA 均不解,见 experiments.md P3);基线 69.0 极可能 910C 实测 — 见 `organizer-inquiry-final.md` Q1/Q3)

### 3. 性能测试报告（至少包含)
- [x] RTF（含统计口径)— SPEAK→WAV e2e,中位 0.68(P8 三次 0.84/0.68/0.58)
- [x] 测试环境(910B4 / CANN 9.1.0-beta.3 / F16)
- [x] 测试数据(perf-duplex 36 帧 duplex_omni_test_case)
- [x] 测试次数(P8 ≥3 次:0.84/0.68/0.58 中位 0.68)
- [x] 统计方式(analyze_perf.py 按时间戳匹配 SPEAK↔audio 轮)
- [x] 优化前后对比(P1.7 队列解耦 8.5× + P3 vocoder 多线程,见 §6)
- [x] 资源使用情况(HBM ~24G / AICore burst 60-84%)
- [x] 异常情况说明(CANN Q4_K_M 不支持 / P1.6 误判澄清 / VideoMME 崩溃)

### 4. 可运行 Demo
- [x] Demo 使用说明(reproduce-guide §6 + demo.sh)
- [x] 启动与访问方式(3 进程,https://127.0.0.1:8006/)
- [x] 核心交互流程(8 项检查全过,benchmark/demo-evidence/)
- [x] 演示视频(benchmark/demo-video/demo_turnchat.webm)

### 5. 优化与复现说明
- [x] 原始性能瓶颈分析(experiments P0–P5 + perf-ceiling-analysis)
- [x] 采用的优化方法(cann 6 补丁 + P1.7 队列 + P3 vocoder + P6/P7 video)
- [x] 各项优化带来的性能变化(experiments P1.7 RTF 0.83→P3 0.64→P4 0.57)
- [x] 效果保持情况(F16 不改推理数学,RTF 0.57–0.68 < 1.087)
- [x] 完整复现步骤(reproduce-guide + scripts/)
- [x] 关键技术说明(cann-patches + decisions + optimization-methodology)

## 五、提交要求

- 可复现：完整部署说明 + 运行脚本 + 必要配置
- 统一环境运行：需能在官方指定昇腾环境中运行
- 材料完整：按赛道提交全部必须材料
- 规范命名：字母、数字、下划线、中划线
- 正式硬件/镜像/版本/提交规范以官方公告与 starter kit 为准

## 六、时间线（更新）

- 提交开启：**2026-08-01 12:00**（赛道一）
- 报名截止：2026-08-14
- 提交截止：2026-08-31（赛事方 08-04 调整，原 08-17）
- 统一复现评审：2026-08-31
- 结果：2026-09-04；奖金：2026-10-01

## 七、算力申请指南要点（官方飞书文档 7/28 更新）

- 链接：https://modelbest.feishu.cn/wiki/PeStwWCA1i0ptXkqh9scu5AynUe
- 官方 user guide：https://hidevlab.huawei.com/support/userGuide
- **审核需约 3 日，尽早申请**（我们已申请）
- 流程：注册/登录华为账号 → hidevlab.huawei.com/home → 【体验IDE】→【创建环境】→ 弹窗【申请权限】→ 审核通过后 → 环境配置窗口选【算力类型】(昇腾910C) /【镜像】/【配置规格】→【确认】→ 环境【已就绪】
- **卡时规则**：1NPU = 100h，2NPU = 50h，4NPU = 25h（总卡时 = 100h 与规格相关）
- **挂载目录**：数据放挂载目录下才持久化（/user_data）
- **镜像选择**：
  - 赛道一 A（llama.cpp-omni）→ 推荐镜像列表选 CANN 9.1.0-beta1 系列（实测环境预装 9.1.0-beta.3，兼容）
  - 赛道一 B（vLLM-Omni）→ 不在推荐列表，自定义镜像填 quay.io/ascend/vllm-omni:v0.25.0-a3
- 自定义镜像地址填写不规范会提示

## 八、新确认的官方信息来源

- 赛事官网：https://ascend.openbmb.cn/competition（排行榜页面已上线）
- 算力申请指南（飞书）：https://modelbest.feishu.cn/wiki/PeStwWCA1i0ptXkqh9scu5AynUe
- 官方 Demo 仓库：https://github.com/OpenBMB/MiniCPM-o-Demo
- 联系邮箱：contact@openbmb.cn
