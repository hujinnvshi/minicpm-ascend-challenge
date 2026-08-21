# 运维交接文档（2026-08-05）

> 用途：用户暂离期间的操作/方案/账号位置交接。任何密钥**值**都不在本文档，只记位置。
> 本机 = **官方 910B3 HiDevLab 云环境**（正式评测环境，非本地 secs）。

## 一、环境身份

| 项 | 值 |
|---|---|
| 角色 | 官方 HiDevLab 910B3 云环境（厂家授权替代 910C），**所有正式数据在此产生** |
| 硬件 | 910B3 单卡 64GB HBM（npu-smi 显示 NPU 1 chip 0）+ 鲲鹏 920 256 核 |
| 系统 | openEuler 24.03 aarch64；CANN 9.1.0-beta.3 |
| 项目根 | `/workspace/minicpm-ascend-challenge`（git main = origin/main） |
| 官方预置（只读） | 权重 `/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/`；数据集 `/workspace/shared_assets/datasets/` |
| Python 环境 | `/workspace/venv-g23/bin/python`（torch 2.13 / transformers 5.14 / jiwer 4.0 / librosa / modelscope 已装；**whisper/funasr/zhconv 未装**） |
| 构建产物 | `code/llama.cpp-omni/build-cann/bin/{llama-omni-cli,llama-omni-perf-duplex,llama-omni-server}` |

## 二、账号与凭证位置（只记位置，值不落盘到任何文档/git）

| 凭证 | 位置 | 说明 |
|---|---|---|
| 千问/DashScope API key | `~/.hermes/auth.json` → `credential_pool.alibaba`（2 条） | Hermes Agent 的 qwen provider 用（config: `~/.hermes/config.yaml` providers.qwen，api=dashscope compatible-mode）。**当前 shell 环境变量里没有** `DASHSCOPE_API_KEY`；若脚本需要，从 auth.json 读取或让用户提供后写入 `.secrets.local`（已 gitignore） |
| GitHub SSH key | `~/.ssh/id_ed25519_github`（+ `.pub`，`~/.ssh/config` 已配） | 仓库远端 `git@github.com:hujinnvshi/minicpm-ascend-challenge.git` 用它 push/pull |
| `.secrets.local` | **本机当前不存在**（.gitignore 已预留） | docs 里提到的"密码存 .secrets.local"约定；需要新建密钥时写这里 |
| HiDevLab 算力 | 已授权（910B3 替代 910C）；卡时规则 1NPU=100h | 申请指南见 `docs/submission-checklist.md` 第七节 |
| 赛事报名 | ✅ 已通过（赛道一 子赛道A llama.cpp-omni） | 见 `docs/competition-research.md` |

⚠️ 纪律：密钥值只允许存在 `~/.hermes/auth.json` 或 `.secrets.local`；不进 docs/、不进 git、不进记忆。

## 三、运行中的服务（2026-08-05 快照）

3 进程 Demo 栈（全部存活，health 均 200）：

| 进程 | PID | 内容 |
|---|---|---|
| gateway | 689645 | `venv-g23/bin/python gateway.py --port 8006 --internal-port 8007 --https`（certs/ 自签证书） |
| backend | 689646 | `llama-omni-server -m .../MiniCPM-o-4_5-F16.gguf -ngl 99`（:22500，HBM ~21G） |
| worker | 690268 | `venv-g23/bin/python worker.py --port 22400 --backend-server-url http://127.0.0.1:22500` |

- 重启全套：按 `docs/reproduce-guide.md` 第 6 节的 4 步命令（gateway → backend → worker → curl 注册）。
- 健康检查：`curl -sk https://127.0.0.1:8006/`；`curl http://127.0.0.1:22500/health`；`curl http://127.0.0.1:22400/health`。
- NPU 监控：`npu-smi info`（AICore/HBM）；细粒度采样 `while sleep 0.5; do npu-smi info -t usages -i 1 | grep -iE 'aicore|hbm bandwidth'; done`。

## 四、常用操作速查

```bash
cd /workspace/minicpm-ascend-challenge
MODEL=/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf
BIN=code/llama.cpp-omni/build-cann/bin

# 1) RTF 官方口径测量（SPEAK→WAV，perf-duplex 36 帧）
$BIN/llama-omni-perf-duplex -m "$MODEL" -c 4096 -ngl 99 \
  --ref-audio code/llama.cpp-omni/tools/omni/assets/default_ref_audio/default_ref_audio.wav \
  --test code/llama.cpp-omni/tools/omni/assets/test_case/duplex_omni_test_case/duplex_omni_test_case_ 36 \
  -o code/llama.cpp-omni/tools/omni/output --out-json code/llama.cpp-omni/tools/omni/output/perf_report.json
python3 code/llama.cpp-omni/tools/omni/perf/analyze_perf.py \
  code/llama.cpp-omni/tools/omni/output/perf_report.json --interval-ms 1000

# 2) RTF 独立复核（我写的，交叉验证 analyze_perf.py）
python3 scripts/verify_rtf.py code/llama.cpp-omni/tools/omni/output/*.json

# 3) 重编译（改 ggml-cann.cpp / omni.cpp 后）
cmake --build code/llama.cpp-omni/build-cann -j$(nproc)
```

- 同步通道 = Git（GitHub 中转）：本地/其他机器 push → 本机 `git pull`；大文件不走 git。决策见 `docs/decisions.md`。
- 提交打包：`bash scripts/package-submission.sh <tag>` —— ⚠️ 有缺陷，见第七节 TODO-1。

## 五、当前进度快照（2026-08-05）

| 项 | 状态 | 证据 |
|---|---|---|
| **RTF（排名指标）** | ✅ SPEAK→WAV e2e **0.825**（beat 官方基线 1.087 ~24%） | `tools/omni/output/p2_rtfspec.json`；独立复核 4 份 JSON 全一致（c1=0.945→c8=0.810/0.802→spec=0.825） |
| 优化链 | ✅ P0 cann 6 补丁 → P1.6 双工上 device → P1.7 队列 1→16（LLM P50 8295→977ms）→ P2 三杠杆证伪（量化/并发/首响天花板），910B 已贴 F16 floor | `docs/experiments.md`、`docs/decisions.md` |
| Demo | ✅ 3 进程栈存活 + 演示视频 `benchmark/demo-video/demo_turnchat.webm` | 上文第三节 |
| **精度 benchmarks** | ❌ **三项零实测数**（唯一准入风险） | 见第六节执行计划 |
| 数据就位 | TTS-Seed testset ✅（zh 2020 条 / en 1088 条，1010+666 个 prompt）；WavLM ckpt ✅（`shared_assets/datasets/CowboyZ/seed-tts-eval/wavlm_large_finetune.pth`）；Video-MME ✅（`lmms-lab/Video-MME/` 84G，10 zip + videomme parquet）；Daily-Omni ❌ Videos.tar 未下 | 实测 ls |

## 六、下一步执行计划（精度准入攻坚，按序）

1. **TTS-Seed（本地可做，最高优先）**
   - 生成：上次尝试失败（`gen/10002287-00000095/run.log` = `Unknown argument: -o`，omni-cli 没有 -o）。
     正确路径：`omni-cli --test <prefix> <n>`（输入需摆成 `prefixNNNN.wav`，输出落 `tools/omni/output/round_XXX/tts_wav/wav_*.wav`，voice clone 用 `--ref-audio`），或走 server HTTP API（`/v1/stream/omni_init` 带 `output_dir`+`voice_audio` → `prefill` → `decode`，见 `server-omni.cpp`）。
   - 评分：`benchmark/seed-tts-eval/eval_ref/seed_tts_eval.py`（vllm-omni 参考版，需移植成独立脚本：WER 用 zh=funasr paraformer-zh / en=whisper-large-v3；SIM 用 WavLM，ckpt 已有，env `SEED_TTS_WAVLM_MODEL` 指向本地）。
   - 依赖：`pip install funasr zhconv`（modelscope 可达）；whisper-large-v3 走 hf-mirror（HF 直连被墙，`hf-mirror.com` 200 可达）或 modelscope 镜像。
   - 预期：F16 不改数学 → ASV≈0.709 / WER≈1.414，过线。
2. **Daily-Omni**：等用户下 Videos.tar（或 hf-mirror/modelscope 拉）；QA 判定可用千问做 judge（config 里 `FILTER_MODEL_1_BASE_URL` 已指 dashscope compatible-mode）。口径见 `docs/daily-omni-notes.md`。
3. **Video-MME**：数据已齐（zip 解压 + videomme parquet）；跑法同 Daily-Omni（视频帧+音频 → MCQ ABCD），官方脚本形态参考 `code/daily-omni/test_model/`。
4. **G5 提交材料**：三项精度数齐后，修 package-submission.sh（见下），出正式提交包。

## 七、已知问题 / TODO（接手先读）

1. **package-submission.sh 会生成空 patch**（提交风险）：`code/llama.cpp-omni/` 不是独立 git 仓库（被外层仓库整体跟踪 3420 文件），脚本里 `git diff` 拿不到相对官方上游的改动。修法二选一：(a) 添加官方 llama.cpp-omni upstream remote 后 `git diff upstream/main`；(b) 直接整树打包（体积大但最稳）。
2. **仓库根部有垃圾空文件** `"30%（compute"`（0 字节，未跟踪，疑似误输入产物）——可删。
3. **certs 私钥在 git 里**：`code/MiniCPM-o-Demo/certs/{cert,key}.pem` 被跟踪且运行时会自签重新生成（git status 常显 modified）。自签证书风险低，但提交前确认是否 untrack。
4. **omni-cli 没有纯 TTS 生成入口**：seed-tts 批量生成要么改造 --test（把 prompt-wav 当输入、把目标文本注入 prompt），要么写 server API 驱动脚本。这是 TTS-Seed 的第一个工程问题。
5. perf-duplex 的 exit 2（LLM P95/首响）是**工具内更严门槛，非官方排名指标**，别再投入（P2 已证伪三个方向，见 decisions.md 2be2e5e/2235547/bd18e2d）。官方只看 SPEAK→WAV RTF。

## 八、红线（评审 5 步，任一失败出局）

1. 精度降幅 ≤2pp（三 benchmark）→ 当前唯一零数据项，最优先。
2. Demo 接官方 MiniCPM-o-Demo 可用 → ✅ 已满足（保持进程存活/可重启）。
3. 性能统一口径 RTF → ✅ 0.825 < 1.087。
4. 材料完整 5 大块 → 缺精度结果 + 提交包脚本待修。
5. 官方环境可复现 → reproduce-guide.md 已对齐 910B3；提交前全清单走一遍。

## 九、关键文档索引

- `docs/eval-spec.md` 官方评测规范（08-05 版，口径权威）
- `docs/performance-report.md` 性能报告（提交物）
- `docs/reproduce-guide.md` 复现说明（提交物）
- `docs/experiments.md` P0–P2 实验全链
- `docs/decisions.md` 决策链（时间倒序）
- `docs/cann-patches.md` 6 补丁细节
- `docs/status-assessment.md` 状态评估（08-05 P1.7 纠正版置顶）
- `docs/submission-checklist.md` 官方清单 + 算力申请

## 十、新设备补充（2026-08-10，910B / CANN beta.1）

新分配设备的核心验证结论，与上文（旧环境 beta.3）配套。完整记录见 `docs/session-2026-08-10-newenv.md`；产物在 `/workspace/user_data/verify-ascend-2026-08-10/`。

**关键 gotcha（容器重建后必读）**：
1. **双die device 锁定**：双 die = dev0+dev1，dev1 不可用。perf/duplex **必须** `ASCEND_RT_VISIBLE_DEVICES=0 CUDA_VISIBLE_DEVICES=0`，否则跑到 dev1 在 `aclnn_repeat_interleave` 崩溃（exit139）。npu-smi 查询用 `-i 5`，binary 用 dev0。
2. **aarch64 Python 降级**：pandas3/pyarrow25/numpy2.5 段错误 → 用 numpy1.26.4/pandas2.2.3/pyarrow16.1.0。venv 在 `/workspace/user_data/venv-omni`（旧 venv-g23 不存在），freeze 见 `verify-ascend-2026-08-10/stage1/requirements-frozen.txt`。
3. **build 命令**：`bash scripts/build-cann.sh "$REPO/code/llama.cpp-omni"`（传 REPO 参）+ `cmake --build ... --target llama-omni-eval-cli`（脚本只构 cli+perf-duplex）。

**结果**：RTF 中位 0.52（< 1.087）✅；Video-MME smoke 0/2（情形B，beta.1 也退化）。git tag `verify-ascend-910B-cann-beta1-20260810`。

## 2026-08-21 工作区路径迁移（赛事方要求直接使用 /workspace）

- **旧路径**：`/workspace/user_data/temp_project/minicpm-ascend-challenge`（vol_bigfile 卷 98% 满 + EROFS 只读，git 无法提交/推送）
- **新路径**：`/workspace/minicpm-ascend-challenge`（overlay 可写盘，赛事方"直接使用 /workspace 路径"要求）
- **模型/数据集**：仍走 `/workspace/shared_assets`（只读共享区，不复制，徐帅 8-19 通知第 1 条）
- **git**：完整 .git 已迁移（HEAD=1adbd1c，origin=git@github.com:hujinnvshi/minicpm-ascend-challenge.git），旧位置 git 因卷只读停用
- **旧位置处置**：暂留不删，待卷恢复写权限后按 announcement-2026-08-21 §9.2 清单清理（删重复视频 2.7G + build 产物 + 非赛事目录）
- **注意**：并行 Claude Code 会话若仍引用旧路径，以本路径为准；build-cann 未复制，重建见 `scripts/build-cann.sh`
