# 优化流程体系规范（2026-08-16 定稿）

> 定位：本仓库所有优化/评测/提交动作的统一流程框架。**有层次、逐步推进、无破坏性**。
> 适用：赛道一·子赛道 A（llama.cpp-omni），910B3 单卡 + CANN 9.1.0-beta.3。

---

## 〇、总原则

1. **合规优先**：任何优化不得触碰红线（见 §一），违规数据一律作废并重新测量。
2. **证据先行**：结论必须附原始证据（json/log/命令），无证据不下结论。
3. **单一事实源**：文档数字以最新定论为准（时间倒序决策链），旧数字标注作废原因。
4. **无破坏性**：不删除验证中产物；改动先提交可回退；并行冲突先检测后动作。
5. **分层推进**：按 §三 的层次由低到高探索，每层有明确门禁（§二），不越层。

---

## 一、合规红线（所有动作的前提，违反=数据作废）

| # | 红线 | 依据/执行 |
|---|---|---|
| R1 | **不可改官方文件**：`evaluation/`（含 config.env）、`tools/omni/omni-eval-cli.cpp`、`omni-eval-daily-cli.cpp`、`omni-tts-eval.cpp`、`CMakeLists.txt` | 改前 `git diff official/bench/huawei -- <path>` 自查；本机适配一律走 `EVAL_CONFIG` 覆盖（benchmark/*.env） |
| R2 | **NZ 纪律**：官方要求 `GGML_CANN_WEIGHT_NZ=off`（空串/换行复读异常）；off 只经官方路径注入 | 一切直跑必须显式 `export GGML_CANN_WEIGHT_NZ=off`，否则数据作废 |
| R3 | **不改推理数学**：仅流水线/调度层优化；精度降幅 ≤2pp | 优化前后同口径精度 A/B 验证（WER/Accuracy） |
| R4 | **不做量化**：Q4_K_M 不支持 / Q8_0 无收益（910B dequant-bound） | 模型保持 F16 |
| R5 | **口径一致性**：RTF 用官方 SPEAK→WAV e2e 口径（全链路含 vpm/apm/llm/tts/t2w） | 不允许"部分环节"报法（复现审查"结果明显不一致"风险） |

---

## 二、评测门禁（每个优化动作的入口检查）

```
[G1] 环境独占     NPU+CPU 无并行会话占用（ps 查 eval/perf 进程、load 正常）
[G2] 基线先行     同配置基线 ≥3 次取中位（RTF 差 <0.03 视噪声）
[G3] 质量门禁     优化候选必须过精度验证（WER/ASV/Accuracy 与基线可比）
[G4] 证据落盘     json/log 归档 + docs/experiments.md 记录（含作废标注）
[G5] 可回退       git 提交先行；配置变更可一键还原
```

---

## 三、优化层次（由低到高，逐层推进，每层门禁通过才进下一层）

```
L1 配置层（已完成，穷尽）──────────────────────────────────────
    NZ on/off、OMNI_T2M_DEVICE、ACL_GRAPH、OPERATOR_FUSION、
    PREFILL_USE_GRAPH —— 5 变体 A/B 收益 ≤1.6%（噪声级）
    状态：CLOSED（2026-08-15，experiments §十一）

L2 参数层（当前可推进）────────────────────────────────────────
    候选：Token2Wav flow-matching n_timesteps（steps 9，赛道 B 先例 -6%）
          首 codec chunk 帧数自适应（赛道 B 先例）
    门禁：可调性验证 → 质量 A/B（WER 逐位一致才保留）→ 环境独占测 RTF
    风险：steps 减少 = 生成近似（R3 红线边界），必须 WER 门禁 + 报告披露
    状态：PENDING（待有设备/算力时执行）

L3 架构层（已部分探索）────────────────────────────────────────
    P6 overlap 已探（共享 ggml 进程内 async 不可行——bit 不精确）；
    vocoder 独立进程/共享内存形态未验证（理论 0.34-0.42）
    门禁：同 L2 + 稳定性（连续 3 轮无异常）+ 内存/资源审计
    状态：HOLD（投入产出比低，优先级低于 L2）

L4 内核层（未探索，最高风险）──────────────────────────────────
    ggml-cann 算子级优化（CANN kernel 选择/融合）
    门禁：同 L2 + 全量回归（不可改文件不变）
    状态：HOLD（当前 decode 456ms/chunk 已是 NPU 推理速度主导，
           内核优化空间有限且风险最高）
```

---

## 四、提交物管理（无破坏性执行）

```
[1] 打包     scripts/package-submission.sh（exclude 语义固定，见脚本注释）
[2] 验证     12 项断言脚本（不可改 5 路径=官方 / 零缺失 / 无残留 /
             词表 / Makefile / 最新数字）——对稳定副本验证（防 rm -rf 竞态）
[3] 稳定副本  /tmp/pkg-final.tar.gz（打包后立即拷贝，验证用副本）
[4] 提交     变更即 commit（Signed-off-by: opengoodhw）+ push
[5] 文档同步  submission-checklist 材料清单数字 = 最新定论（单一事实源）
```

---

## 五、并行会话冲突协议（多 agent 协作）

```
- 评测/打包前：ps 查 [l]lama-omni-eval / [g]enerate_cpp / [e]xtract 进程
  + git status 查 index.lock / 未提交改动
- 冲突时：错峰执行（等待 or 换窗口），不强杀对方进程（D 状态杀不掉）
- 不可改文件：对方若改动，git checkout official 还原 + 重验
- 根级 cmake 产物：已 gitignore（2ebb9e6），不提交
```

---

## 六、当前状态与下一步（2026-08-16）

```
已完成：L1 穷尽、精度三项（Daily ✅ TTS ✅ Video 申诉中）、自测四任务、
         Demo 交互、合规、材料 12/12 验证、提交物就绪
待推进（按序）：
  1. 邮件发送（Q1-Q6，触发赛方反馈）——用户手动，0 成本
  2. 提前提交当前包（探路）——用户手动
  3. L2 参数层（Token2Wav steps A/B）——待设备
  4. 复现演练（评审环境）——待设备
  5. 截止前按反馈更新包
```
