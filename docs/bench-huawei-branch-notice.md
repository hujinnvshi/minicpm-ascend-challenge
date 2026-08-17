# 官方统一测评分支发布通知（2026-08-11）— llama.cpp-omni 子赛道

> **来源**：赛事群 `@所有人` 通知（2026-08-11）。本文为**逐字留档 + 影响分析**，便于追溯。
> **性质**：⭐ 强制准入 —— "请所有参赛队伍务必基于此分支进行开发与自测"，正式评测会校验。
> **与本通知强相关的刚得结论**：Track B 对照实验（同日）已**证明 910B 硬件无退化问题，退化是 llama.cpp-CANN 后端软件 bug**（见文末"相关上下文"）。这让本通知第 2 条成为当前信息量最大的待验证点。

---

## 一、通知原文（逐字）

> @所有人 【重要通知】llama.cpp-omni 子赛道统一测评分支已发布
>
> 各位选手好，为方便大家验证优化效果并统一后续测评标准，现已提供 llama.cpp-omni 子赛道统一测评分支，请所有参赛队伍务必基于此分支进行开发与自测：
>
> 📌 测评分支：https://github.com/tc-mb/llama.cpp-omni/tree/bench/huawei
>  📖 评测说明：详见仓库中 evaluation/README.md
>
> 关键提醒：
> - 环境要求：推荐 Linux aarch64 + Ascend 910，需预装 CANN Toolkit、CMake、Python 3.10+、ffmpeg、rubberband 等。
> - 上传前必须自测：在裸机上至少跑通一次 `./run_all.sh --smoke 2`，确认四个任务均成功。
> - 不可修改文件（正式评测会校验，修改将不计入成绩且可能触发校验失败）：
>   - `evaluation/` 目录
>   - `tools/omni/omni-eval-cli.cpp`
>   - `tools/omni/omni-eval-daily-cli.cpp`
>   - `tools/omni/omni-tts-eval.cpp`
>   - `tools/omni/CMakeLists.txt`
> - Ascend 平台注意：F16 权重默认关闭 `GGML_CANN_WEIGHT_NZ` 和 `GGML_CANN_ACL_GRAPH`（config.env 中已默认配置）。
>
> 请大家尽快切换到该分支进行验证，如有问题可在群内反馈。祝比赛顺利！

---

## 二、关键事实抽取

| 项 | 内容 |
|---|---|
| **分支** | `tc-mb/llama.cpp-omni` `bench/huawei`（https://github.com/tc-mb/llama.cpp-omni/tree/bench/huawei） |
| **评测说明** | 仓库内 `evaluation/README.md` |
| **自测命令（硬门槛）** | `./run_all.sh --smoke 2`，**四任务全成功**才能上传 |
| **目标硬件** | "推荐 Linux aarch64 + **Ascend 910**"（= 我们的 910B） |
| **环境依赖** | CANN Toolkit、CMake、Python 3.10+（我们 3.12 ✅）、ffmpeg（✅）、**rubberband**（⚠️ 待确认装没装） |
| **默认 flag** | F16；`GGML_CANN_WEIGHT_NZ`=off；`GGML_CANN_ACL_GRAPH`=off（config.env 默认） |
| **不可改文件** | `evaluation/`、`tools/omni/omni-eval-cli.cpp`、`omni-eval-daily-cli.cpp`、`omni-tts-eval.cpp`、`tools/omni/CMakeLists.txt` |

---

## 三、对当前情况的影响分析（关键）

### 1. 填上了我们一直缺的"官方评测脚本"，且是强制的
此前 `session-2026-08-05.md` / `organizer-inquiry-final.md` 反复记载的阻塞"**等官方 llama.cpp-omni benchmark 评测脚本**"——**就是这个分支的 `evaluation/` + `run_all.sh`**。从"可选自证"升级为"强制准入 + 正式校验"。

### 2. ⭐ 与 Track B 结论正面碰撞 —— 当前信息量最大的待验证点
官方评测分支走的就是我们刚证明**有退化 bug 的同一条 llama.cpp-CANN 后端**，且通知明确目标硬件 = "Ascend 910"（我们的 910B）。只有两种可能：
- **(a) 官方在 910 上跑通了** → 分支里带了让 910 不退化的配置/代码，我们本地构建差了某个东西（首选嫌疑：`GGML_CANN_WEIGHT_NZ`，见第 5 条）。**切过去可能让退化直接消失。**
- **(b) 官方其实在 910C 验证、910 也会退化** → `--smoke 2` 在我们机上会挂在多帧任务，届时我们有**铁证**（Track B 证硬件没事 + 官方 smoke 在 910 挂）找赛方。

→ **切分支 + 跑 smoke，是现在单一最该做的动作**，同时回答"官方路径在 910 通不通 / 退化还在不在 / flag 对不对"三个问题。

### 3. 不可改文件清单 —— 重塑修复边界
- ✅ 我们的优化落点（`ggml-cann.cpp` 6 补丁、`omni.cpp` 队列解耦 P1.7）**都不在禁改清单**，合规。
- ⚠️ 我们此前用的是**外部 `OpenSQZ/MiniCPM-V-CookBook` 的 eval-cli**，官方分支有自己的、**冻结的** `omni-eval-cli.cpp` 等。**之前 P3 / scaled VideoMME 复跑走的是非官方 eval 路径**——退化结论（在后端层，与 eval 驱动无关）仍成立，但**正式精度数必须用官方分支重出**。

### 4. `./run_all.sh --smoke 2` 是新硬门槛
四任务全成功才能上传。若多帧退化未解，可能 smoke 即挂——倒计时式优先级。

### 5. 立刻要查的线索：`GGML_CANN_WEIGHT_NZ` 默认关
`ACL_GRAPH` 我们已知 910B 不支持；但 **`WEIGHT_NZ`（CANN native 权重格式）默认关**——数值/格式相关 flag。若我们本地构建把它开着，可能是退化诱因之一。切分支后第一时间核对 `config.env` 与本地 build flag 的差异。

---

## 四、相关上下文：Track B 对照实验（2026-08-11，同日，决定性）

用 **transformers + torch_npu**（PyTorch 后端）在同一台 910B 上跑同一个 MiniCPM-o 4.5 F16，对照 llama.cpp-CANN：

| 帧数 | llama.cpp-CANN（我们原路径） | torch_npu / transformers（Track B） |
|---|---|---|
| 8 帧 | 全时长 100% 退化（`_` / logits NaN），0/99 | **全时长 0% 退化、输出协调，medium 答对** |
| **64 帧（官方口径）** | 全时长 100% 退化，0/99 | **全时长 0% 退化、输出协调，medium 答对** |

→ **同一块 910B、同模型、同输入（含官方 64 帧）：llama.cpp-CANN 全崩，PyTorch 后端全协调。** 证明**退化是 llama.cpp-CANN 后端软件 bug，非 910B 硬件上限**（"910C 不退化"推断也更可能是软件栈差异，非硅片差异）。
- 环境：venv-trackb（torch 2.12.0 + torch_npu 2.12.0 + torchvision 0.27.0 + transformers 4.51.0）；CANN 9.1.0-beta.1；die0 锁定。
- 脚本/日志：`benchmark/video-mme-cookbook/diag/trackb_videomme_test.py`、`diag/trackb_test.log`。
- **意义翻倍**：带着"硬件没问题、是后端 bug"的确证去切官方分支——若官方分支在 910 能跑，修复点必在分支与本地构建的差异里（diff 即得），而非瞎猜。

---

## 五、下一步（优先级）

1. **切到 `bench/huawei`**，读 `evaluation/README.md`，接入官方 `evaluation/` + 冻结 eval CLI。
2. **核对 build flag**：`GGML_CANN_WEIGHT_NZ` / `GGML_CANN_ACL_GRAPH` 是否与 config.env 默认一致；补 `rubberband` 依赖。
3. **跑 `./run_all.sh --smoke 2`**：
   - 过 → 退化大概率随之解决，进正式精度复跑。
   - 挂多帧 → 用 Track B 铁证 + smoke 日志找赛方，口径从"推断"升级为"实测"。
4. 把不可改文件清单纳入提交前自检（确保我们的改动不落在 `evaluation/` / eval CLI 上）。

---

## 六、相关文档

- `docs/eval-spec.md` —— 评测规范（基线/准入，本分支是其落地实现）
- `docs/organizer-inquiry-final.md` —— 此前向赛方的询问（Q1 910B/910C、Q3 多帧退化；本分支发布后部分问题可能已有答案）
- `docs/multiframe-degradation-repro.md` —— 多帧退化复现/对比指南（基于外部 CookBook，需对齐到本官方分支）
- `docs/performance-report.md` §10 —— 多帧退化结论（"910B4 框架级 bug"，现被 Track B 坐实为后端 bug）
- `docs/session-2026-08-05.md` —— 此前"等官方评测脚本"阻塞，本分支解除
