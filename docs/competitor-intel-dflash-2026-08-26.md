# 竞品技术情报：「等我启动」队 TTS DFlash 推测解码方案（2026-08-26）

> 来源：赛事群分享（"等我启动"队，排行榜在册 0.751）+ 开源仓库完整分析
> 状态：赛事已收官（8/26 确认）→ 本文作为**技术资产**归档，供未来优化/参赛复用
> 分析日期：2026-08-26。开源材料：模型 cs-qyzhang/MiniCPM-o-4_5-tts-dflash (HF) /
> 代码 cs-qyzhang/minicpm-o-4.5-tts-dflash (GitHub) / 训练日志 wandb.ai/cs-qyzhang-hust
> 📎 知识链（按时间）：本文（方案分析）→ docs/dflash-probe-2026-09-05.md（CPU 复测验证）
> → docs/dflash-assets-2026-09-05.md（资产保全 + 自训方法论）

## 一、问题洞察（与我们一致）

Talker（MiniCPM-o 4.5 TTS 解码器）：20 层 Llama 架构 / hidden 768 / vocab 6562 audio codec
token（id 6561=EOS）。每帧 26 audio token 需自回归 26 步，每步串行 NPU kernel + 6562 宽 head
投影 → 小模型却是最高推理时延段（我们 v6@910B4 tts 0.275 占 24%；v8@910C 图模式后 0.121 占 17%）。

## 二、方案机制（DFlash block-diffusion drafter，speculators 框架实现）

1. **推测解码结构**：draft 每轮单次前向填 block_size-1=7 个推测 token（block_size=8：
   [anchor, MASK×7]，块内双向 attention，可看 anchor 前全部 context）→ verifier 单次前向
   验证整块 → 接受最长正确前缀 + 1 bonus token。实测平均每轮接受 2-3 token（26 步 → ~10 轮）。
2. **关键设计 A（embedding-fed）**：draft 输入不是 token id 而是 verifier 每位置 input embedding
   ——Talker 输入 = emb_text(token)+projector_semantic(thinker_hidden)（L2 norm）或
   emb_code[0](audio_code)，token-id 框架学不到真实表征。训练样本直接携带 per-position embedding。
3. **关键设计 B（KV-injection）**：verifier 多层 hidden 经 fc+RMSNorm 压缩注入 draft 每层 K/V；
   embedding/lm_head/verifier_norm 冻结拷贝自 verifier；可训练仅 fc+2 norms+N draft layers。
4. **Lossless 保证**：distribution-preserving speculative sampling（默认 accept-top-k=0）：
   draft 从 q=softmax(logits/T) 提议，verifier 以 min(1,p/q) 接受，拒绝后从残差 max(0,p-q)
   重采样 → **输出分布与原 Talker 数学等价**（非 lenient top-k/threshold 模式）。
5. **训练**：5 个开源中英文语料 teacher-forcing 记录 input_embeds/hidden_states/codec 轨迹 →
   训练（vllm-omni 记录、Code2Wav 跳过）。作者自认训练非最优（接受率有提升空间）。

## 三、与我们优化路线的关系（正交可叠加）

| 路线 | 砍的维度 | 我方状态 |
|---|---|---|
| Flash Attention | 单步 matmul 耗时 | ✅ v4-v6 |
| head_code 行间并行 | head 投影 CPU 耗时 | ✅ v6 |
| NPU 串行锁 | 并发排队 | ✅ v5 |
| VPM batch | encode 段 | ✅ v7 |
| 图模式 | kernel launch 次数 | ✅ v8（tts 0.218→0.121） |
| **DFlash 推测解码** | **自回归迭代次数本身** | ❌ 未触及 ← 唯一正交剩余维度 |

v8@910C tts 段 0.121 中 26 步串行 decode 仍是主体 → DFlash 砍迭代到 ~1/3，与图模式叠加，
预估 tts 段 -30~50%、总 RTF -5~8%（0.724 → ~0.67）。Talker 的 embed/lm_head 冻结拷贝
意味着**无需重训即可在 llama.cpp 侧接入**（仅需 GGUF 权重 + 解码循环改造）。

## 四、我方历史判定复盘（8/22 CLOSED → 铺路模式重开）

experiments.md:1067「投机采样/并行解码：需 draft 模型（无）+ CANN 不支持 speculative → 关闭」：
- 障碍 1「无 draft」：✅ 已消除——对方开源训练好的权重（含 t2d/d2t，免训练数据直接推理）。
  自训对我们仍不可行（无 GPU 训练环境），但直接采用可行。
- 障碍 2「CANN 不支持 speculative」：部分消除——llama.cpp 通用 speculative 够不着 omni.cpp
  自定义 TTS decode 循环（仍成立，需 omni 内自实现）；但验证阶段依赖的多 token 并行 prefill
  已由我方 v8 FA contiguity 修复（aclnn_ops.cpp make_bsnd_contiguous）解锁。
- 对方 demo = HF transformers + NVIDIA，**未移植 llama.cpp-omni/CANN** → 移植空白仍是机会。

## 五、移植技术路径（llama.cpp-omni + CANN，铺路模式无时间压力版）

1. **draft GGUF 化**：block-diffusion + KV-injection 非标准架构 → 需扩展 llama.cpp
   （新架构注册 + ggml 自定义图 + safetensors→GGUF 转换脚本）。工作量主体。
2. **omni.cpp TTS decode 循环改造**：draft 单次前向填块（anchor emb + MASK）→ verifier
   整块并行验证（复用已修复的 FA 多 token prefill 路径）→ min(1,p/q) 接受 + 残差重采样。
   需保持 batch_validity 语义（非尾帧恰 26 audio token 不变——推测解码只改迭代组织不改产物）。
3. **采样语义对齐**：官方 TTS 评测若用确定性解码 → greedy 验证逐字节一致门禁；若 sampling →
   distribution-preserving 保证指标（WER/SIM）不变。两种都要验证。
4. **验证门禁（沿用纪律）**：同 seed A/B 端到端 wav 逐字节一致（greedy）/ 分布一致（sampling）
   + batch_validity 全 true + ≥3 run 分布零重叠。
5. **合规**：draft license 待查（HF 页）；引入第三方模型需在 README 声明（原声明
   "未使用第三方代码"将不再成立）；赛事已收官则无提交合规压力，纯技术验证。

## 六、铺路模式验证计划（建议顺序，均无时间压力）

1. [探针] 下载 draft 权重（HF 被封 → hf-mirror/modelscope 通道）→ 架构/大小/license 确认
2. [收益上限] 接受率测量：接受率只取决于 draft 质量与 verifier 分布，与部署框架无关 →
   对方 benchmark.py 可 CPU 小样本跑（Talker 300M 前向 CPU 秒级），或 910C 上 transformers CPU 模式
3. [移植] 接受率 ≥2.5 → GGUF 架构扩展 + omni 循环改造（预算以周计，非赛事冲刺）
4. [验证] 上述门禁全套

## 七、竞争含义（归档参考）

- 对方在榜 0.751 应不含 dflash（或早期版）；我方 v8 0.7237 预期已优于该分
- 对方若完成 llama.cpp/CANN 移植，TTS 段 -30~50% → 潜在 ~0.65 以下——本方案是未来同类赛事
  的已知最强对手路径，移植储备的价值 = 差距不拉大甚至反超
- 对方自认训练非最优 → 接受率天花板未到（block 8 只接受 2-3），数据/方法改进空间存在

## 附：关键资源

- draft 模型：https://huggingface.co/cs-qyzhang/MiniCPM-o-4_5-tts-dflash
- 代码（已 clone 本地 /tmp/tts-dflash-intel，含 benchmark/duplex/simplex 三 CLI + training.md）：
  https://github.com/cs-qyzhang/minicpm-o-4.5-tts-dflash
- 训练日志：https://wandb.ai/cs-qyzhang-hust/MiniCPM%20o%204.5%20tts%20dflash
- 依赖：speculators 框架（Z Lab block-diffusion）；运行时 transformers 4.51 + torch（NVIDIA）
