# HiDevLab 算力申请

> 2026-07-31 更新：官方飞书指南（https://modelbest.feishu.cn/wiki/PeStwWCA1i0ptXkqh9scu5AynUe）要点已并入，
> 完整提交物清单见 submission-checklist.md

## 文件/权重传输方式（2026-07-31 用户手册确认）

HiDevLab 体验 IDE **未开放直接 SSH/FTP 上传**，传输通道按优先级：

1. **910C 环境内 ModelScope 直拉**（首选，权重 15-30G 一条 wget 搞定）
   环境如有外网：sh scripts/sync-weights.sh pull-on-910C
   需先确认环境外网通不通（curl modelscope.cn）
2. **WebIDE 文件夹上传**（代码/patch/脚本等小文件，权重不现实）
   WebIDE 文件树右键上传或拖拽
3. **VS Code 连接后拖拽**（openLiBing Remote-SSH 通道，速度取决于通道带宽，
   小文件可用；连接步骤见用户手册 1.4）
4. 环境内 git clone（代码路径：GitHub/GitCode 均支持，手册第 3 章）

要点：
- VS Code 用 Remote-SSH 插件连接（openLiBing 封装，非用户可直连的 22 端口）
- 仅支持创建 1 个 IDE 环境；断开即停止计时但保存挂载目录数据
- 挂载目录 /user_data 持久化，所有权重/产物必须放挂载目录下

## 官方流程要点（飞书指南 7/28）

- 审核约需 3 日，尽早申请（已申请）
- 流程：华为账号登录 → 体验IDE → 创建环境 → 申请权限 → 审核通过后配置环境
- 环境配置：算力类型=昇腾910C / 镜像=推荐镜像列表（CANN 9.1.0-beta1 系列，A 赛道） / 配置规格
- 卡时规则：1NPU=100h、2NPU=50h、4NPU=25h（总卡时与规格负相关）
- 挂载目录 /user_data 持久化，数据必须放挂载目录下
- B 赛道镜像（与我们无关）：quay.io/ascend/vllm-omni:v0.25.0-a3 需自定义拉取

用途：赛道一（高性能推理优化 - llama.cpp-omni 子赛道）910C 算力申请
平台：https://hidevlab.huawei.com（华为计算创新实验室，官方算力提供站点）
账号：已注册（2026-07-31）
密码：真实值保存在 docs/.secrets.local（git 忽略，本地安全位置）
审批通知页：https://hidevlab.huawei.com/personal-center/noticeManagement
（个人中心-通知管理，查看算力申请审批结果）
状态：✅ 算力申请已获批（2026-07-31）——单卡 910C，镜像 CANN 9.1.0-beta1
环境访问方式：待确认（SSH / Web IDE / 平台入口）

## 算力环境使用规范（官方，2026-07-31）

- 卡时配额：每人初始 100 卡时，需关注剩余用量，避免超额影响作业
- /workspace：服务器本地目录，高 IO，适合代码编译，容量上限 300GB
- /user_data：大容量共享目录，适合数据集/大文件等静态文件

## 省卡时策略（重要）

- 权重文件：secs 下载完成 → 传入 910C /user_data（不在 910C 上直接下载）
- 代码编译：910C 上用 /workspace 编译（CANN 后端必须在目标机编）；
  本地/secs 的 CPU 版仅用于流程学习与参数试验
- 910C 只跑：基准测试、量化档位扫描、优化验证（开卡即测，测完即关）

## 项目背景

本人当前正在参与"MiniCPM & 昇腾推理优化与应用创新挑战赛"
（由面壁智能 OpenBMB 联合华为昇腾生态发起，2026 年 7-9 月），
以个人开发者身份报名赛道一：高性能推理优化（llama.cpp-omni 子赛道），
项目由 OpenBMB 与昇腾生态主导，参与方包括全球高校学生开发者与
AI 开发者团队。

## 资源用途

需要申请昇腾 910C 算力（单卡）进行 MiniCPM-o 4.5 全模态模型的
推理开发调试与性能优化，具体包括：
- llama.cpp-omni 推理框架在 910C 上的模型适配与跑通
- GGUF 量化档位调优（在精度降幅 ≤2pp 约束下降低 RTF）
- RTF / TTFT 等实时交互指标优化与 Benchmark 评测
- 性能测试报告与复现材料产出（赛事提交物）

## 华为方接口人

无（如赛事群内有指定接口人，再补充姓名/邮箱）

## 填写注意

1. 用途写清"赛事算力申请"，官方对比赛有专属通道，审批更快
2. 如表单有"队伍名称/参赛编号"字段，填报名后的参赛信息
3. 接口人没有就写"无"，不要编造
