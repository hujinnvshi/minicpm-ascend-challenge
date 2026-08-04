# 赛事准备路线图（2026-07-31 版）

## 当前状态盘点

| 项 | 状态 |
|----|------|
| 赛道 | 赛道一 llama.cpp-omni 子赛道（已定） |
| 算力 | HiDevLab 910B3 已就位（厂家授权替代 910C，1 颗 910C = 2 颗 910B） |
| 源码 | llama.cpp-omni 本地 + secs 均已编译（CPU 版） |
| 权重 | secs 下载中（Q4_K_M/Q8_0 + 全模块，~14GB+） |
| 报名 | ⏳ 未报名（8/14 截止） |
| starter kit / 精度 benchmark 脚本 | ⏳ 待向官方确认 |

## 一、不依赖 910C 的准备（现在推进，占满等待期）

### A. secs 跑通 CPU 推理全流程（权重下载完成后立即做）
1. 文本对话测试（llama-omni-cli -m ...）
2. 视觉测试（图片输入）
3. 音频/TTS 测试（语音生成，验证 token2wav 链路）
4. 跑 --test benchmark，拿 CPU 版 RTF 基线
   → 目的：学会模型加载、CLI 参数、benchmark 方法与 RTF 统计，
     910C 上只是换后端重跑

### B. 文档精读（每篇半小时）
1. docs/ops.md CANN 部分（算子支持矩阵、构建开关）
2. docs/build.md（CANN 后端编译选项）
3. docs/docker.md（llama-omni-server 部署，提交物需要 Demo 可复现）
4. 官方技术报告 arxiv 2604.27393（llama.cpp-omni 设计 + RTF 数据）
5. examples/ 下 benchmark 相关示例

### C. benchmark 方法论准备
1. 设计 RTF 测试脚本：固定输入集 × 多轮 → 均值/P50/P95
2. 测试用例集：中文/英文、短句/长句、纯文本/带视觉
3. 精度验证方法：待 starter kit 确认（Daily-Omni 等怎么跑）

### D. 参赛材料模板
1. 性能报告模板（环境/基线/优化项/前后对比表）
2. 复现说明模板（部署步骤/依赖/脚本）
3. Demo 演示准备（llama-omni-server + WebRTC 前端）

### E. 报名（用户，8/14 截止）
- OpenBMB 账号 + ascend.openbmb.cn 报名
- 飞书群确认：能否同时提交两子赛道无关；starter kit 获取方式

## 二、910C 到位后的执行序列（按优先级）

1. 环境确认：npu-smi info、CANN 版本、镜像预装内容
2. 权重入库：secs → /user_data（大容量共享目录）
3. /workspace 编译 CANN 版 llama-omni-server + cli
4. 跑通基线 → 记录基线 RTF（Q4_K_M 起步）
5. 量化档位扫描：Q8_0 → Q6_K → Q5_K_M → Q4_K_M → Q4_K_S → Q3（
   每档 RTF + 精度，红线 ≤2pp）
6. 参数优化：ctx-size、线程、chunk 大小、KV cache、滑动窗口 stride
7. 编译参数：Release、march、CANN 开关组合
8. 完整 benchmark 数据 + 性能报告 + 复现材料

## 三、时间轴（倒排）

| 日期 | 事项 |
|------|------|
| 8/02 前 | 权重下载完 + secs CPU 全流程跑通 + RTF 基线（CPU） |
| 8/05 前 | 文档精读 + benchmark 脚本就绪 + 材料模板 |
| 8/10 前 | 910C 基线 + 量化扫描（如算力可用） |
| 8/14 | 报名截止 |
| 8/14-8/16 | 参数优化 + 报告撰写 |
| 8/31 | 提交截止（赛事方调整后，原 8/17） |

## 四、需要用户/官方确认

- [ ] 910C 环境访问信息（SSH/Web IDE、镜像名）
- [ ] 报名（8/14 前）
- [ ] starter kit 获取（含精度 benchmark 脚本）
- [ ] 提交材料清单细节（官方公告）
