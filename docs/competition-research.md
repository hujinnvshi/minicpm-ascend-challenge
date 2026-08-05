# 比赛调研报告

调研日期：2026-07-31
信息来源：官方公众号文章、MindSpore 活动页（图片 OCR）、官网、GitHub/魔乐社区

## 主办与背景

面壁智能 OpenBMB 联合华为昇腾生态发起，围绕 MiniCPM-o 4.5 全模态模型
（9B，视觉+语音+文本端到端统一建模，"边看、边听、主动说"），
在昇腾 NPU 生态中探索高效推理、低延迟交互和真实应用落地。

## 赛道一：高性能推理优化（奖金 36.1 万 / 8 奖）

面向 AI Infra / 推理部署 / 编译优化 / 算子优化开发者。
硬件：昇腾 910C。两个独立子赛道（vLLM-Omni 与 llama.cpp-omni），
**分别评审、分别排名**（2026-08-04 官方公告确认）：

- llama.cpp-omni 子赛道：重点优化每个音频 chunk 的 RTF（实时率）
- vLLM-Omni 子赛道：重点优化 RTF、TTFT（首 token 响应）、TTFP（首个音频包输出）

精度约束：在 Daily-Omni、TTS-Seed、Video-MME 等 Benchmark 上，
优化后相对对应框架基线的精度降幅不超过 2 个百分点。

评分关注：模型推理适配 / TTFT 首响速度 / 单 chunk latency / E2E latency /
吞吐与并发 session / 资源利用率与稳定性 / 精度损失控制 / 部署与复现质量。

提交物：完整代码与环境配置、模型服务及 Demo 启动脚本、Benchmark 评测脚本与结果、
性能测试报告、优化前后效果与性能对比、部署使用及复现说明、Demo 演示视频。
最终成绩以主办方在官方统一环境中的复现与评测结果为准。

奖项（2026-08-04 调整，面壁追加 9 万增设冠军名额，总奖金 406k → 496k）：

llama.cpp-omni 子赛道（我们所在）：
- 冠军 1 位：90,000 元
- 亚军 1 位：50,000 元
- 季军 1 位：27,000 元
- 小计：167,000 元 / 3 奖

vLLM-Omni 子赛道：
- 冠军 1 位：90,000 元
- 亚军 1 位：50,000 元
- 季军 2 位：27,000 元/位
- 小计：194,000 元 / 4 奖

## 赛道二：创新应用（奖金 13.5 万 / 6 奖）

基于 MiniCPM-o 4.5 全模态能力构建可运行、可展示、可体验的 Demo。
面向 AI 产品开发者、多模态交互设计师、学生创新团队、应用工程团队。

鼓励方向：实时问答 / 伴随式助手 / 视觉语音交互 / 端侧应用 /
多模态场景理解 / 教育、办公、创作、生活服务等应用场景。

提交物：可运行 Demo / Web Demo / App、PPT、项目说明、演示视频。

奖项：
- 冠军 1 位：55,000 元
- 亚军 2 位：25,000 元/位
- 季军 3 位：10,000 元/位

## 赛事规则

- 面向个人开发者与开发团队，团队 ≤3 人
- 开放实时榜单，每队每天最多提交 3 次
- 所有作品须接受统一 MindSpore/昇腾环境复现验证，方可进入有效排名
- 奖金税前，获奖作品须满足赛事规则、提交要求和复现要求
- 获奖不足时按实际评审结果核减奖项及奖金

## 参赛要求（官方原文，2026-07-31 获取）

- 可复现：提供完整部署说明、运行脚本与必要配置
- 统一环境运行：提交内容需能在官方指定昇腾环境中运行
- 材料完整：按所选赛道提交全部必须材料
- 规范命名：文件命名建议使用字母、数字、下划线与中划线

限制与说明：
- 两个赛道均需在统一昇腾环境中完成复现验证
- 提交内容需可复现、可解释，并能在官方统一环境中稳定运行
- 正式硬件、镜像、版本与提交规范以官方公告与 starter kit 为准
- 疑问联系：contact@openbmb.cn

⚠️ 待确认问题：赛道二 Demo 的"统一昇腾环境运行"具体要求——
Demo 是否必须整体跑在官方昇腾环境？官方环境是否提供 MiniCPM-o 4.5
推理服务（API/预装）？建议邮件 contact@openbmb.cn 或飞书群确认。

## 时间线（2026）

| 节点 | 日期 |
|------|------|
| 报名开放 | 07-13 |
| 作品提交开启 | 07-20 |
| 报名截止 | 08-14 |
| 提交截止 | 08-31（赛事方调整后） |
| 统一环境复现 + 联合评审 | 08-31 |
| 公布结果 / 颁奖 | 09-04 |
| 奖金到账 | 10-01 |

## 报名方式

- 官网：http://ascend.openbmb.cn（注意：2026-07-31 检查时该站 SPA 挂载的是
  "2026 稀疏算子加速大奖赛"，MiniCPM 比赛页可能即将上线或已下线，需持续关注）
- 飞书答疑群二维码：assets/feishu-group-qr.png
- 官方发布页：https://www.mindspore.cn/activities/zh/2026-7-13
- 线下 Meetup 解读：2026-07-23 北京站（已结束）

## 开发环境情况（2026-07-31 确认）

官方统一昇腾环境仅用于**复现验证**，不提供开发期环境（赛道一需自备 910C，
对无 NPU 资源者基本不可行）。

但 MiniCPM-o 4.5 官方生态对赛道二完全开放：

1. **免费 API**：OpenBMB 官方提供 MiniCPM-V 4.5/4.6 与 MiniCPM-o 4.5 的免费
   API 访问（2026-05-17 发布），MiniCPM-V 4.6 还有公开免费 key。
   Demo 可直接接入，零算力成本。
2. **免费在线体验**：官方在线 Demo（PC + 手机端），无需注册。
3. **开源完整 Demo 代码**：OpenBMB/MiniCPM-o-Demo（GitHub），含
   Frontend + Gateway + Worker + Backend 完整架构，Docker 部署，
   后端可选 PyTorch 版或 llama.cpp-omni C++ 版，可直接二次开发。
4. **本地部署兜底**：llama.cpp-omni 量化版官方宣称部署内存 <12GB，
   本机 secs（AMD EPYC 224C / 1TiB RAM）CPU 推理完全可行；
   PyTorch 无损版需 ≥28GB 显存 GPU。
5. **端侧安装包**：Comni 桌面端（Windows/macOS）一键安装，可作参考。

结论：赛道二开发环境无阻碍，技术路线 = 官方免费 API（主）+ 本地 CPU
部署 llama.cpp-omni（兜底/展示部署能力）。

## 关键资源链接

- 赛事官网：https://ascend.openbmb.cn/competition
- MindSpore 发布页：https://www.mindspore.cn/activities/zh/2026-7-13
- 昇腾推理开发：https://www.hiascend.com/cn/developer/inference
- MiniCPM-o 4.5 仓库：https://github.com/OpenBMB/MiniCPM-V
- MiniCPM-o Demo：https://github.com/OpenBMB/MiniCPM-o-Demo
- GGUF 量化权重：https://huggingface.co/openbmb/MiniCPM-o-4_5-gguf
- vLLM-Omni 部署指南：https://docs.vllm.ai/projects/vllm-omni/
- 魔乐社区（国内镜像）：ModelScope

## 下一步待办（TBD）

- [ ] 确认官网报名入口可用性（官网当前挂着别的比赛，需盯）
- [ ] 申请官方免费 API key（API Guide 在 MiniCPM-V 仓库）
- [ ] 确定参赛赛道（倾向赛道二）与组队
- [ ] 选定 Demo 场景（候选：DB/运维多模态助手）
