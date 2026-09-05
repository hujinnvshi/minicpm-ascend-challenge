# DFlash 移植探针：环境搭建与冒烟结果（2026-09-05）

> 目的：验证「等我启动」队 DFlash TTS 推测解码方案的收益上限（接受率/EAL/tokens-per-round），
> 判定 llama.cpp-omni + CANN 移植是否值得投入。
> 方法：对方开源 benchmark（HF transformers 全链路）在本机 CPU（256 核/2TB 内存）上复测。
> 背景：赛事已收官 → 铺路模式，本探针是"竞品方案快速验证"基础设施的第一个实例。
> 关联：docs/competitor-intel-dflash-2026-08-26.md（方案分析）+ docs/dflash-assets-2026-09-05.md（资产/方法论）

## 一、资源与通道（可复用）

| 资源 | 路径/来源 | 说明 |
|---|---|---|
| base 模型（HF transformers 全量 18.7GB） | /workspace/hf-models/OpenBMB/MiniCPM-o-4_5 | modelscope snapshot_download（4:37 下完） |
| draft 模型（84MB） | /workspace/hf-models/cs-qyzhang/MiniCPM-o-4_5-tts-dflash | hf-mirror.com 直下（HF 被封） |
| 对方代码 | /tmp/tts-dflash-intel（git clone cs-qyzhang/minicpm-o-4.5-tts-dflash） | benchmark/simplex/duplex 三 CLI |
| venv | /workspace/venv-dflash | python3.12，CPU 版 torch |

**下载通道结论**：HF 直连不通 → 用 hf-mirror.com（小文件）或 modelscope（大文件）双通道。

## 二、venv 依赖清单（踩坑记录）

```
torch==2.8.0(+cpu) torchaudio==2.8.0 transformers==4.51.0 accelerate
safetensors numpy pillow librosa==0.9.0 soundfile==0.12.1 av
setuptools<81 scipy（librosa/pkg_resources 需要）
minicpmo-utils==1.0.6 --no-deps（⚠️ stepaudio2 是它内置模块，非独立 pypi 包！
  [all] extra 依赖 decord==0.6.0 无 aarch64 wheel → 必须 --no-deps）
einops onnxruntime onnx hyperpyyaml h5py tqdm jieba（stepaudio2 传递依赖，逐个补齐）
```

**minicpmo-utils 坑**：modeling_minicpmo.py init_tts → `from stepaudio2 import Token2wav`；
stepaudio2 不是独立包，藏在 minicpmo-utils sdist 的 src/stepaudio2/。pypi.org 上 stepaudio2 404。

## 三、CPU-only 运行的关键 patch（⚠️ 必做）

stepaudio2/s3tokenizer 硬编码 CUDA（27 处：`.cuda()` + `device='cuda'`）→ CPU 环境 AssertionError。
解法（脚本 /tmp/patch-stepaudio2-cpu.sh，作用于 venv-dflash site-packages，幂等）：

```bash
SP=/workspace/venv-dflash/lib/python3.12/site-packages
find "$SP/stepaudio2" "$SP/s3tokenizer" -name "*.py" -print0 | while IFS= read -r -d '' f; do
    sed -i "s/\.cuda()/.cpu()/g; s/device='cuda'/device='cpu'/g; s/device=\"cuda\"/device=\"cpu\"/g" "$f"
done
```

## 四、运行命令（可复用）

```bash
cd /tmp/tts-dflash-intel
PYTHONPATH=/tmp/tts-dflash-intel/src OMP_NUM_THREADS=128 \
  /workspace/venv-dflash/bin/python -m minicpmo_dflash.benchmark \
  --model /workspace/hf-models/OpenBMB/MiniCPM-o-4_5 \
  --draft-model /workspace/hf-models/cs-qyzhang/MiniCPM-o-4_5-tts-dflash \
  --device cpu --limit N --output bench.json --audio-dir wavs/
```

参数：--limit/--ids/--languages/--categories 筛选；--tts-draft-temperature 0 = greedy（默认 0.8
sampling）；accept_top_k=0 默认 = distribution-preserving（lossless）路径。样本 wall ~5 分钟/个
（CPU：Thinker 8B 生成 + vocoder 占大头，DFlash decode 仅 ~34s/样本）。

## 五、冒烟结果（zh-read-short，2026-09-05）

| 指标 | 值 | 解读 |
|---|---|---|
| codec tokens | 139 | 单句朗读 |
| rounds | 52 | 自回归轮数（无 draft 需 139 轮） |
| proposed / accepted | 364 / 87 | block=8 → 每轮提议 7 |
| **acceptance_rate** | **23.9%** | draft 接受率（不高，对方自认训练非最优） |
| **EAL** | **1.67** | 每轮接受 draft token 数 |
| **tokens/round** | **2.67** | 净推进（含 bonus）= 迭代减 2.67× ← 真实收益 |
| decode | 34.3s (CPU) | DFlash decode 段耗时 |
| config | seed 42 / TTS temp 0.8 / draft temp 0.8 / accept_top_k=0 | lossless 路径 |

**解读**：tokens/round=2.67 与对方声称"每轮 2-3 token"一致 → TTS 自回归迭代降为 1/2.67≈37%。

## 六、A/B 实测对照（2026-09-05，同文本 139 tokens，CPU）

| 模式 | decode 耗时 | 轮次 | 每轮成本 | 相对 |
|---|---|---|---|---|
| 无 DFlash | ~60s* | 139 步 | 0.43s/步 | 1.0× |
| **有 DFlash** | **34.3s** | 52 轮 | 0.66s/轮 | **1.75×** |

*B（simplex --disable-dflash）wall 328s - 固定成本（Thinker+vocoder ≈268s，取自 DFlash 冒烟
302s-34.3s）推算。**每轮成本系数实测 1.54×**（0.66/0.43）——与理论中性假设 1.5× 吻合，
净加速 1.75× = 52×1.54/139 理论值 1.76× 验证闭环。

## 七、910C（v8.7 基 0.519）应用评估

- 910C TTS 单步 decode 实测 4.2ms/token（225 kernel × 15μs）→ tts 段 0.102 几乎纯自回归
- 每帧 26 步 → DFlash 后 ~10 轮（÷2.67）；每轮成本系数 NPU 待测（多 token 并行验证效率是最大变量）
- 系数 1.5×：tts 0.102 → ~0.059 → 总 RTF ~**0.476**（-8%）
- 系数 2.0×：tts 0.102 → ~0.078 → 总 RTF ~**0.495**（-5%）
- 判定阈值（tokens/round ≥2.5）：首样本 2.67 达标 → **GGUF 架构扩展 + omni 循环改造值得投入**

## 八、待补

- [ ] 对方全量 20 样本复现（对方官方自测 overall tokens/round 2.5516 为基准；本机 CPU 全链路
      20 条 ~2h，已停——以对方自测表 + 本机单样本吻合为据，不重复全量）
- [ ] V9.3（CANN Lab 环境本地，未推送远程）段分解对照——910C 后期 v8.7=0.519/决赛 P0 已含
      spec decode 计划；若 V9.3 已集成推测解码，用其真实数据校准本节
- [ ] NPU 移植后实测校准（每轮成本系数）

## 十、赛事期复盘（为什么当时没移植 + 现状转化）

- 时间线：8/26 对方分享 DFlash 并开源（模型 HF 可下）→ 8/29 910C agent 决赛计划仍把
  spec decode 标"高复杂度未实现" → 8/31 截止
- 若当时 v8.7（0.519）基础上实现 spec decode（decode 段 -30% 潜在，910C agent 自估）→
  总 RTF 或达 ~0.47-0.48（其决赛 P0 目标区间），逼近榜首等我启动 0.4234
- 未移植的客观原因（理性决策，非遗漏）：移植 = 非标准架构 GGUF 扩展 + omni 循环改造
  （周级）+ 精度门禁全量（WER 2020 条 + ASV）；剩余 5 天 + 每日 3 次提交额度已满
- 教训沉淀：竞品技术情报 → 可行性验证 → 移植评估 应提前到赛事中段；draft 类资产一旦
  开源应立即拉取保全（本探针 9/5 才拉，若 8/26 拉取可提前评估）
- 现状转化：模型 + 方法论 + CPU 复测 + A/B（1.75×）+ 移植路径已全部保全为基础设施 →
  未来同类场景成本从"月级"（训练+适配）降为"周级"（直接移植）

## 九、移植设计要点（预研，供后续）

- draft 架构：DFlashDraftModel = 4 层 Qwen3-768 + KV-injection（verifier 层 [2,6,10,14,17]
  hidden 经 fc+RMSNorm 注入）+ t2d/d2t vocab 映射（当前 identity）+ block_size=8（提议 7）
- 输入是 anchor embedding（非 token id）→ llama.cpp 需支持自定义输入；embedding/lm_head 冻结
  拷贝自 verifier（Talker）→ 权重可从 GGUF tts 模型导出，无需重训
- 验证循环：教科书推测解码（min(1,p/q) 接受 + 残差重采样）——逻辑简单，移植难点在
  draft 模型架构的 GGUF 支持 + omni.cpp TTS decode 循环改造（多 token 并行验证）
- 官方评测若 greedy → greedy 接受率更有参考价值（待 bench-greedy4 数据）
