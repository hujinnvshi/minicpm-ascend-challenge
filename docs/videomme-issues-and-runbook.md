# Video-MME 已探明问题与复测手册(2026-08-15,供跨环境同步复测)

> 目的:另一台测试环境同步本仓库后,按本手册自检环境 → 复现基准 → 复测验证。
> 全部结论与原始数据见 `docs/experiments.md` 2026-08-14/15 各节;分支 `review-optimize`(最新)或 `videomme-discussion`(诊断链完整)。

---

## 一、已探明问题清单(按影响排序)

### P0 · `GGML_CANN_WEIGHT_NZ` 必须 off(官方强制,漏配即数据污染)

- **症状**:空串响应、全`\n`复读、精度大幅下滑(我们实测:非KB 51.7%→66.7%,空响应 16%→0)。
- **根因**:ggml-cann 代码默认 `on`(ggml-cann.cpp:1286/1554 `value_or("on")`);`config.env` 的 off **只经 `run_eval.sh/run_all.sh` 官方路径生效**。任何直跑(直接起 `eval_cpp_pipeline.py`)若未显式 export,即跑在官方明令禁止的配置上。
- **官方原文**:evaluation/README FAQ:"必须保持 GGML_CANN_WEIGHT_NZ=off,否则可能出现空串、换行复读等异常输出"。
- **处理**:①官方评测一律走 `run_eval.sh`(自动加载 config.env);②必须直跑时,完整 export(见 §三 env 清单)。
- **教训**:我们 08-14 一整天的直跑数据(60q/180q/99q A/B/全部微测)全部因此作废,曾据此得出多个错误结论。

### P1 · NUMA 绑核因机器而异(影响 RTF,不影响精度)

- **症状**:照抄旧机 `taskset -c 192-223` → 新机 RTF 0.57 退化到 0.68。
- **处理**:先查 NPU 所在 node:`cat /sys/bus/pci/devices/$(npu-smi查到的bus)/numa_node` → 绑该 node 的 CPU(本机 node2=64-95;旧机 node6=192-223)。仓库有 `scripts/numa-bind.sh` 自动探测。

### P2 · `ASCEND_RT_VISIBLE_DEVICES` 必须锁 die0

- die1 在 RoPE `aclnn_repeat_interleave` 崩溃 exit139(项目已知)。所有评测/性能命令前置 `ASCEND_RT_VISIBLE_DEVICES=0 CUDA_VISIBLE_DEVICES=0`。

### P3 · `/workspace/user_data` 是 NFS(35T,96% 满)

- **症状**:批量写帧 `OSError: No space left on device`(小文件可写,批量失败)。
- **处理**:帧目录用本地盘。本仓库已将 `evaluation/videomme/tmp_frames` 软链至 `/root/frames_local`;测试视频解压到 `/root/` 下。

### P4 · 定向解压 zip 的断链坑

- 首次解压若被超时杀断,会留下 0 字节文件;断点续跑按"文件存在"跳过 → 坏文件进评测(0 帧)。**处理**:解压后校验文件数与大小(zip 内 entry 有原始大小可对)。

### P5 ·(历史,已定性)协议差异与数值特性 —— 诊断结论,非修复项

- 官方引擎 prefill 与 HF 参考协议存在差异(无 `<image_id>` 帧编号、多带语音克隆系统提示)—— 在 NZ=off 正确配置下**不影响作答**(093 答 'D' 正确);image_id 补齐等改法在 KB99 实测**有害**(35.4%/28.3% vs 基线 53.5%),已关闭。探针保留 env 门控(`OMNI_IMAGE_ID/OMINI_TEXT_CHAT_SYS/OMINI_DEBUG_TOPK/OMNI_DEBUG_PREFILL/Omni_DUMP_EMBED`),默认零影响,官方评测勿开。
- vision embedding 与 HF 实现级等价(cos 0.9992);HF 在同 KB 子集 ≈50% 与 llama.cpp 打平。

---

## 二、当前基准数据(NZ=off 官方口径,910B3 新机 npu id=7)

| 批次 | 样本 | 结果 |
|---|---|---|
| KB99(0812 官方路径,两次) | 99 题 | 51.5% / 53.5%(1/99 空) |
| 非KB 批1(五域×3) | 45 题 | 66.7%(0 退化) |
| 非KB 批2(独立) | 45 题 | 60.0%(0 退化) |
| KB45(新鲜) | 45 题 | 44.4%(0 退化;vs 0812 同题 46.7%,复现性 96%) |
| **非KB 合并** | n=90 | **63.3% ± 10pp** |
| **全量域加权估计** | | **~57.7% ± 17.6pp**(轨迹 62.4→60.0→57.7 收敛) |
| 题型分层 135 题(12类按占比) | **69.6%**,零退化 | **合池 n=270: 63.3%±5.7pp(域加权 64.2%/题型加权 61.4%)→ 真值 ~63%±6pp** |

复现性:跨日跨构建逐题同答案 96%。

## 三、复测环境自检 + 运行清单

```bash
# 1. 环境自检
npu-smi info                    # 卡数与 id(本机 id=7;记下 bus-id)
npu-smi info -l                 # Total Count 应为 1
cat /sys/bus/pci/devices/<bus>/numa_node   # NPU 所在 NUMA node → 绑该 node CPU
cat $ASCEND_TOOLKIT_HOME/version.cfg 2>/dev/null || ls /usr/local/Ascend/  # CANN 版本(记录!)

# 2. 官方路径冒烟(自动加载 config.env,NZ 正确)
cd code/llama.cpp-omni/evaluation && ./run_all.sh --tasks videomme --smoke 2

# 3. 直跑子集复测(必须完整 export!)
cd code/llama.cpp-omni
source /usr/local/Ascend/cann-9.1.0-beta.3/set_env.sh
export ASCEND_RT_VISIBLE_DEVICES=0 CUDA_VISIBLE_DEVICES=0
export LD_LIBRARY_PATH=/usr/local/Ascend/cann-9.1.0-beta.3/aarch64-linux/lib64:/usr/local/Ascend/driver/lib64:$LD_LIBRARY_PATH
export LLM_MODEL_PATH=/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf
export LLAMA_CLI_BIN=$PWD/build/bin/llama-omni-eval-cli
export TEMPERATURE=0.0 SAMPLER_SEED=42 ASCEND_SLOG_PRINT=0
export GGML_CANN_WEIGHT_NZ=off GGML_CANN_ACL_GRAPH=off    # ← P0!漏了全白测
export PARQUET_PATH=<子集.parquet> VIDEO_DATA_DIR=<视频目录>
taskset -c <NPU同node的CPU段> /workspace/venv-g23/bin/python3 evaluation/videomme/eval_cpp_pipeline.py --num-gpus 1
# 结果: evaluation/videomme/output/output_videomme_cpp.json(官方 scorer 仅全量可算 Overall)
```

子集 parquet 已入库:`benchmark/video-mme-cookbook/diag/videomme_subset_{nz36,nz36b,kb45,typestrat}.parquet`(视频从 zip 定向解压,见 P3/P4)。

## 四、给复测环境的验证判据

1. **NZ 配置正确性**:smoke 输出应**零空串/零纯换行**;若有 → 查 NZ env 是否传导。
2. **基准对齐**:同子集分数与 §二 相差 >5pp → 环境差异信号(记录 CANN 版本/机器)。
3. **确定性**:抽 3 题重跑应逐字节一致(>96% 同答案为正常,个别边界题可翻)。
4. 数据回传:`output_videomme_cpp.json` + 环境信息(npu-smi/version.cfg/内核),入库后合成跨环境对照。
