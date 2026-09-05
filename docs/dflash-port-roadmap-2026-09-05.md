# DFlash 推测解码移植执行路线图（最后优化路径，2026-09-05 定稿）

> 定位：赛事收官后最后一条（也是收益最大的一条）未走优化路径 = **TTS 自回归推测解码（DFlash）**。
> 本文是把 4 篇知识文档收敛成**可执行蓝图**：谁来做、按什么顺序、用什么工具、怎么算通过。
> 知识链：docs/competitor-intel-dflash-2026-08-26.md（方案）→ docs/dflash-probe-2026-09-05.md
> （复测/A-B/复盘）→ docs/dflash-assets-2026-09-05.md（资产/自训/通用范式）→ 本文（执行）。
> 状态：**探针已通过（tokens/round 2.67 / CPU A/B 1.75×）→ 待执行 P1（GGUF 化）**。

## 一、为什么这是最后一条路径（背景与目标）

- 910C agent 决赛 P0 计划（8/29）明确 spec decode = decode/tts 段 -30% 潜在（"高复杂度"未实现）；
  8/31 截止前无时间窗口 → 赛事期理性放弃（复盘见 probe 文档 §十）
- 榜首"等我启动"0.4234 大概率已用同类技术（8/25 快照 + DFlash 开源分享）
- 我们 9/5 CPU 复测确认：draft 接受率 23.9% / tokens-per-round 2.67（与对方官方自测 2.55 吻合）、
  lossless（accept_top_k=0 distribution-preserving）、**decode 段 A/B 实测加速 1.75×**
- **目标**：在 v8.7（RTF 0.519，910C 官方环）基础上集成 DFlash → 总 RTF **0.48-0.50**
  （tts 段 0.102 几乎纯自回归：26 步×4.2ms/步 ≈ 109ms/帧，是 DFlash 的理想作用面）

## 二、收益依据（已实测 vs 待实测）

| 数据 | 值 | 来源 | 状态 |
|---|---|---|---|
| tokens/round（单样本 zh-read-short）| 2.67 | 本机 CPU 复测 | ✅ 实测 |
| tokens/round（对方官方 20 套件 overall）| 2.5516 | 对方 training.md §5.5 | ✅ 对方实测 |
| CPU decode 加速（A/B 同文本）| 1.75× | 本机 A/B（每轮成本系数 1.54×）| ✅ 实测 |
| 910C tts 段单步 decode | 4.2ms/token（225 kernel×15μs）| gitcode CONTEXT（S17-4 探针）| ✅ 实测 |
| 910C 每轮成本系数（draft+8-token 验证 vs 单步）| 1.5-2.0×（估）| — | ⏳ 移植后实测 |
| v8.7 + DFlash 总 RTF | ~0.476（系数 1.5）/ ~0.495（系数 2.0）| 推算 | ⏳ 移植后实测 |

## 三、资产盘点（全部就绪）

| 资产 | 位置 | 说明 |
|---|---|---|
| draft 模型 | /workspace/hf-models/cs-qyzhang/MiniCPM-o-4_5-tts-dflash/（84MB）| sha256 见 assets 文档；hf-mirror 可重下 |
| base 模型（HF 全量）| /workspace/hf-models/OpenBMB/MiniCPM-o-4_5/（18.7GB）| modelscope 可重下 |
| 对方代码（参考实现）| /workspace/hf-models/third-party/tts-dflash-intel/ | benchmark/simplex + draft.py 自包含加载 |
| GGUF tts 模型（Talker，移植目标 verifier）| 910C / 本机 shared_assets（只读）| MiniCPM-o-4_5-tts.gguf F16 |
| CPU 复测 venv | /workspace/venv-dflash | 依赖清单见 probe §二 |
| 验证工具 | 910C rts 官方 harness + bypass runner | preserved_assets/run_rts_bypass.sh（gitcode）|
| 精度数据 | seed-zh 全量 WER 2020 条 / ASV 链路 | 910C（gitcode session 文档）|

## 四、移植路径（5 阶段，每阶段有门禁；无时间压力，质量优先）

### P0：Talker 权重提取与结构核对（0.5-1 天）
- 目标：从 GGUF（或 HF base）提取 Talker（20 层 768 / vocab 6562）为可独立加载的 verifier，
  核对与 draft config 的映射（draft 的 embedding/lm_head 冻结拷贝自 Talker，须逐字段一致）
- 工具：llama.cpp convert / safetensors→GGUF；对照对方 training.md §5.2 提取规则
  （emb_code.0→embed_tokens、head_code.0→lm_head、norm→model.norm、+1 mask row id 6562）
- 产出：verifier 权重 + 字段映射表（含 t2d/d2t identity 核对）
- 门禁：draft 权重与 verifier 的 embed/lm_head 逐值一致（torch.allclose，bf16 容差）

### P1：draft GGUF 化 + llama.cpp 架构扩展（3-5 天，主体工作量）
- 目标：llama.cpp 能加载并前向 draft（DFlashDraftModel = 4 层 Qwen3-768 + KV-injection + mask）
- 步骤：
  1. 写 convert 脚本：draft safetensors（config.json/config.py/model.safetensors）→ GGUF 新架构
  2. llama.cpp 注册新架构 DFlashDraftModel（model.h/cpp 新类）：
     - 标准部分（4 层 Qwen3：attn/ffn/rms）可复用现有 qwen3 实现
     - 自定义部分：aux fc（verifier hidden 压缩 [5 层×768 → draft hidden]）+ KV-injection
       （fc 输出注入每层 K/V）+ mask token 处理 + block 双向 attention
  3. 权重加载验证：gguf dump 对齐 + CPU 前向 vs transformers 参考输出（logits 对齐，rel err <1e-3）
- 工具：llama.cpp convert 框架 / gguf-py / ggml CPU 后端（先用 CPU 验证正确性，再上 CANN）
- 门禁：同输入 CPU logits 与对方 transformers 实现一致（torch 参考在 venv-dflash）

### P2：omni.cpp TTS decode 循环改造（2-3 天）
- 目标：Talker 自回归循环支持推测解码（draft 提议 → verifier 整块并行验证 → 接受/残差重采样）
- 改动点（omni.cpp TTS decode 段 + 新模块 headcode-npu 旁）：
  1. draft 单次前向填块：anchor = 上一验证 token 的 input embedding（非 token id！
     需复刻 emb_text+projector / emb_code[0] 的输入构造）——**这是最大机制差异点**
  2. verifier 整块验证：一次前向算 block 内所有位置的 logits（多 token 并行 prefill，
     复用 FA contiguity 修复解锁的路径）
  3. 接受逻辑：greedy = token 相等比较；sampling = min(1,p/q) + 残差重采样（speculative.py 参考）
  4. batch_validity 语义保持：产物 token 序列不变（26 token/帧），只改迭代组织
- env 设计：OMNI_TTS_DFLASH=1（默认关=官方行为）+ draft 模型路径 + block_size 参数
- 门禁：同 seed 同输入，DFlash on vs off 的 wav 逐字节一致（greedy）/分布一致（sampling）

### P3：CANN 适配 + 精度门禁（1-2 天）
- draft/验证前向切 CANN 后端（图模式）；draft 4 层可评估 CPU vs NPU 部署（小模型 CPU 可能更快）
- 精度门禁（沿用纪律，全量）：seed-zh 全量 WER（2020 条，<1.56 且 vs 基线无劣化）+
  ASV（SIM ≥0.689 基线对照）+ rts batch_validity 四字段全 true + core wav 逐字节（greedy 环）
- 工具：910C 官方 harness（EVAL_CONFIG + run_all.sh）+ bypass runner

### P4：性能验证与定稿（1 天）
- rts 5 轮 pooled RTF vs v8.7 基线（0.5188）→ 分布零重叠才采纳
- 段分解确认：tts 段实际收益 + 每轮成本系数实测（校准推算）
- 若 RTF 达 0.48-0.50 → 定稿存档（代码分支 + README + 数据）；未达 → 按 §七决策门

## 五、关键技术细节（实现必读）

1. **embedding-fed 输入**：draft anchor 槽收 verifier input embedding 而非 token id——
   训练侧（对方）记录的是 emb_text+projector_semantic(thinker_hidden)（L2-norm）逐位求和 +
   边界 <text_eos>/<audio_bos> + emb_code[0](audio_code)。推理侧需完整复刻此输入构造链
2. **KV-injection**：verifier 层 {2,6,10,14,17} 的 hidden 经 fc+RMSNorm 压缩注入 draft 每层
   K/V——draft 前向需要 verifier 中间层 hidden（每轮先跑一次 verifier 拿 aux hidden？NO——
   对方实现：aux_history 来自已接受的 verifier 前向结果缓存，逐轮累积，不重复前向）
3. **block 双向 attention**：draft 块内 MASK 位置互相可见（非因果）——需自定义 attention mask
4. **vocab 映射**：draft vocab 6563（6562 codec + mask），t2d/d2t 当前 identity——scatter 保公式
5. **验证并行化**：verifier 8-token 验证 = 多 token prefill（sequence-major K/V）→
   make_bsnd_contiguous 已覆盖的路径；若走 FA 需确认非 PA 场景 contiguity
6. **参考实现**：对方 speculative.py（DFlashDecoder/accept/residual）+ draft.py（propose）
   已备份 /workspace/hf-models/third-party/tts-dflash-intel/——逻辑照抄，语言翻译

## 六、验证矩阵（每阶段门禁汇总）

| 阶段 | 验证 | 通过标准 |
|---|---|---|
| P0 | 权重字段映射 | embed/lm_head 逐值一致 |
| P1 | CPU logits 对齐 | 与 transformers 参考 rel err <1e-3 |
| P2 | wav 一致性 | DFlash on/off 逐字节一致（greedy）/ 分布一致（sampling）|
| P3 | 精度全量 | WER ≈基线（<1.56）且无劣化 + ASV ≥0.689 基线对照 + batch_validity 全 true |
| P4 | 性能 | ≥3 run 分布零重叠 vs v8.7 0.5188；目标 0.48-0.50 |

## 七、风险与决策门

| 风险 | 等级 | 缓解 |
|---|---|---|
| draft 输入构造链复杂（embedding-fed）| 高 | P0 先做字段映射核对；CPU 参考逐层对齐 |
| CANN 多 token 验证成本超预期（系数 >2）| 中 | P4 实测；系数 >2.5 → 收益 <15% → 停止 |
| draft CPU vs NPU 部署权衡 | 低 | 4 层小模型，两路都测 |
| 精度门禁不过（数值路径差异）| 中 | greedy 环逐字节定位；lossless 理论保证下多为实现 bug |
| 与 v8.7 headcode NPU/conv_mm 交互 | 低 | 独立 env 门控默认关；组合后重跑门禁 |

**决策门**：P1 完成时若 CPU logits 无法对齐（rel err 持续 >1e-3）→ 停止并归档（记录原因）；
P4 实测系数 >2.5 → 停止（收益不达预期，存档数据）。

## 八、里程碑与记录约定

- 每阶段完成：git 提交（独立分支 dflash-port）+ docs 更新（本文件勾选）
- 资产/数据/坑：追加到 probe/assets 文档（沿用高密度表格体例）
- V9.3 对照：若 910C V9.3 推上来（可能已含 spec decode），先对照再决定是否仍走本路线
