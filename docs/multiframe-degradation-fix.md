# 多帧退化根因定位与修复确认（2026-08-11）— 代码级闭环

> **状态**：✅ **已定位 + 已确认可解**。多帧退化是 llama.cpp-CANN 后端 **attention 掩码实现缺陷**（`-Inf` 进 F16 加法致溢出 NaN），**不是 910B 硬件上限**；上游 `bench/huawei` 分支已修，在我们这台 910B 上实测 **64 帧不再退化**。无需 910C。
> **作者**：会话 2026-08-11（bench-huawei-adapt 分支）。配套：`bench-huawei-branch-notice.md`（官方分支通知）、`multiframe-degradation-repro.md`（复现指南）。

---

## TL;DR

| 维度 | 结论 |
|---|---|
| **根因** | 我们 fork 的 `aclnn_ops.cpp` 把含 `-Inf` 硬掩码的 F16 mask 原样当作 additive `pseShift` 喂给 `FusedInferAttentionScoreV2` → `-Inf` 进 F16 加法 → softmax 溢出 NaN → 长多步 prefill 累积 → logits 全 NaN → 输出 `_` |
| **修复** | 上游 `bench/huawei` 的写法：`LtScalar(thresh=-1e4)` 把 `-Inf` 拆成 **BOOL 硬掩码** + 有限偏置 `Clamp` 到 **±1e4** → 不溢出 |
| **确认** | 同一台 910B、同模型、同 64 帧：我们 fork `0/2` 退化(`_`)；**上游 eval-cli `2/2` 有效答案**（无退化） |
| **硬件** | 910B 完全够用。Track B（transformers+torch_npu）在同一块 910B 上 8/64 帧均协调 → 硬件无事，bug 在后端 |
| **合规** | 修复点 `aclnn_ops.cpp` 在 `ggml-cann/`，**不在官方不可改文件清单**（README §5 明示"优化应放在...后端算子"）|

---

## 一、现象（被修正前的旧结论）

VideoMME / Daily-Omni 多帧输入时模型输出 100 个 `_`（token id 30，NaN 的 argmax 指纹），精度 0%。帧数梯度实测（99 题，官方 CookBook pipeline，我们 fork）：

| 帧数 | overall | degraded | 说明 |
|---|---|---|---|
| 1 | 42.4% | 0% | 正常（>25% 随机）|
| 2 | 40.4% | 0% | 正常 |
| 5 | 18.2% | 53% | 过渡（short 0%退化 / long 100%退化——**随时长加重**）|
| 8 | 0% | 100% | 全崩 |
| 64 | 0% | 100% | 全崩（官方口径）|

**旧结论**（`performance-report.md` §10 / `experiments.md` P2.5）：定位 NaN 在 CANN 后端 `llama_decode` 多步 prefill 累积溢出，vision/audio/输入 embd 全干净，判断为"910B/CANN 框架级 bug"。**方向对，但未到算子级**；本日推进到 attention 算子的确切缺陷。

---

## 二、根因（代码级）

文件：`ggml/src/ggml-cann/aclnn_ops.cpp`，`FusedInferAttentionScoreV2` 调用前的 **Step 3（attention mask / pseShift 构造）**。

### 我们 fork 的写法（缺陷）— 约 L3960
```cpp
// Step 3: create the PSEShift tensor if needed
//         this tensor is considered as mask (f16) in the llama.cpp
...
if (src3 != nullptr) {
    // 直接把 src3（含 -Inf 的 F16 mask）构造成 bcast_pse_tensor
    acl_tensor_ptr acl_mask_f16_trunc_tensor = ggml_cann_create_tensor(
        src3->data, ACL_FLOAT16, sizeof(uint16_t), trunc_pse_ne, trunc_pse_nb, GGML_MAX_DIMS);
    ...  // 直接 broadcast 成 pseShift（maxBias==0 用 stride=0 技巧，否则 alloc+repeat）
}
```
→ **`-Inf`（硬掩码位置）作为 F16 加性偏置原样进 `pseShiftOptional`**。F16 加法 `-Inf + score` → softmax `exp(-Inf)=0`，但 `-Inf` 算术在 F16 下经多步累积会产生 NaN（`-Inf - (-Inf)` 等）→ **prefill 越长、mask 越大、`-Inf` 条目越多 → NaN 概率越高**。这解释了"帧数/时长越多越退化"。

### 上游 bench/huawei 的写法（修复）— 约 L3905
```cpp
// Step 3: attention mask / position encoding for FusedInferAttentionScoreV2.
// llama.cpp src3 is an additive F16 mask that may mix -Inf (hard mask) with finite
// biases (ALiBi / test masks). Split: -Inf -> BOOL attenMask; finite values -> pseShift.
...
if (src3 != nullptr) {
    // 1) BOOL 硬掩码：mask < -1e4 的位置（即 -Inf）
    float thresh = -1.0e4f;
    GGML_CANN_CALL_ACLNN_OP(ctx, LtScalar, acl_mask_f16_trunc_tensor, thresh_s, atten_mask_tensor /*ACL_BOOL*/);
    // 2) 有限偏置 -> pseShift，并 Clamp 到 ±1e4（杜绝 F16 溢出）
    GGML_CANN_CALL_ACLNN_OP(ctx, Clamp, bcast_pse_tensor, min_s(-1e4), max_s(1e4), bcast_pse_tensor);
}
```
→ **`-Inf` 走 BOOL `attenMaskOptional`（正确的非加性硬掩码），有限偏置走 `pseShift` 且被钳位** → `-Inf` 永不进加法 → 不溢出。

---

## 三、确认证据

### 证据 A：Track B 对照（transformers + torch_npu，同一台 910B）
同一块 910B、同 MiniCPM-o 4.5 F16，换 PyTorch 后端跑（`diag/trackb_videomme_test.py`）：

| 帧数 | llama.cpp-CANN（我们 fork） | torch_npu（Track B） |
|---|---|---|
| 8 | 全时长 100% 退化，0/99 | **全时长 0% 退化、协调**（medium 答对）|
| 64（官方口径）| 全时长 100% 退化，0/99 | **全时长 0% 退化、协调**（medium 答对）|

→ 硬件没问题；变量是后端。（环境：venv-trackb，torch 2.12.0+torch_npu 2.12.0+transformers 4.51.0，CANN 9.1.0-beta.1，die0 锁定。）

### 证据 B：上游 eval-cli 64 帧 smoke（决定性）
用上游 `bench/huawei` 的 ggml-cann（含修复）构建 `llama-omni-eval-cli`，在同一台 910B 跑同一个 64 帧 smoke：

```
GGML_CANN_WEIGHT_NZ=off LLAMA_CLI_BIN=…/build-huawei/bin/llama-omni-eval-cli \
  python smoke_test.py 2

[001-1] GT=C  Pred='A'  Raw='A'        ← 有效答案（非 _）
[001-2] GT=A  Pred='A'  Raw='A'        ← 有效答案（非 _）
Smoke test done: 2/2 produced a valid A/B/C/D answer
```

**前后对比：**

| 跑法 | 64 帧 smoke |
|---|---|
| 我们 fork（旧 attention，NZ 任意）| `0/2`，`Raw='___...'`（退化）|
| 我们 fork + `WEIGHT_NZ=off` | `0/2`（仍退化——NZ 非因）|
| **上游 eval-cli（修复后）+ `WEIGHT_NZ=off`** | **`2/2` 有效答案，无退化** ✅ |

> 注：`2/2` 指"无退化、产出合法 A/B/C/D"；其中 1/2 答对（2 题样本无统计意义，**真实精度由全量 `run_all.sh` 定**）。关键点是 `_` 退化消失。

---

## 四、调查链（逻辑闭环）

```
现象：多帧输出 _ / 0%
  │
  ├─ Track B：同 910B + torch_npu，8/64 帧协调  → 硬件无事，bug 在 llama.cpp-CANN 后端
  │
  ├─ 证伪 WEIGHT_NZ：env 确达二进制(env=os.environ.copy())，NZ off 仍退化(8/64帧) → NZ 非因
  │    （README 的 NZ 警告针对另一种轻微症状，非本 NaN）
  │
  ├─ diff 上游 bench/huawei：aclnn_ops.cpp 差 181 行(74 上游独有/107 我们独有)
  │    → 上游独有 = attention Step3 的 -Inf→BOOL 拆分 + ±1e4 Clamp
  │
  ├─ 读代码：我们 fork 把 -Inf F16 mask 原样进 pseShift → F16 溢出 NaN（机制成立）
  │
  ├─ 构上游 eval-cli（ccec + 补 -lascendcl 解链接） 
  │
  └─ 64 帧 smoke：上游 2/2 协调  → 根因确认 ✅
```

### 证伪的旧假设（诚实记录）
| 旧假设 | 证伪方式 | 结论 |
|---|---|---|
| context 过小(4096/8192) | 官方 pipeline `ctx=40960` 仍退化（P3）| ❌ 非因 |
| flash_attn / softmax | 开启仍退化 | ❌ 非因 |
| 喂法/打包 | 官方 CookBook pipeline 也退化 | ❌ 非因 |
| 编译器（gcc→ccec）| ccec 干净编仍退化 | ❌ 非因 |
| `GGML_CANN_WEIGHT_NZ=on`（README 警告）| NZ=off 实测仍退化（本日）| ❌ 非本退化之因（是另一种轻微症状）|
| 910B 硬件上限 | Track B + 上游 eval-cli 在同 910B 协调 | ❌ 硬件无事 |
| **attention 掩码 -Inf F16 溢出** | 上游拆分+钳位后同 910B 64 帧 2/2 协调 | ✅ **根因** |

---

## 五、构建复现（确认实验）

```bash
CANN=${ASCEND_TOOLKIT_HOME:-/usr/local/Ascend/cann-9.1.0-beta.1}
source "$CANN/bin/setenv.sh"
ASCENDCL_DIR=$(dirname $(find "$CANN" -name libascendcl.so | head -1))
cd /workspace/user_data/llama.cpp-omni-upstream   # 上游 bench/huawei 浅克隆
CCEC="$CANN/tools/bisheng_compiler/bin/ccec"
cmake -B build-huawei -S . -DCMAKE_BUILD_TYPE=Release -DGGML_CANN=ON \
  -DCANN_INSTALL_DIR="$CANN" -DSOC_TYPE=Ascend910 \
  -DCMAKE_C_COMPILER="$CCEC" -DCMAKE_CXX_COMPILER="$CCEC" \
  -DCMAKE_EXE_LINKER_FLAGS="-lstdc++ -lm -lpthread -ldl -L$ASCENDCL_DIR -lascendcl" \
  -DCMAKE_SHARED_LINKER_FLAGS="-lstdc++ -lm -L$ASCENDCL_DIR -lascendcl" \
  -DCMAKE_MODULE_LINKER_FLAGS="-lstdc++ -lm"
cmake --build build-huawei -j"$(nproc)" --target llama-omni-eval-cli
# 产物：build-huawei/bin/llama-omni-eval-cli

# 64 帧 smoke（同一台 910B）
cd <our repo>/benchmark/video-mme-cookbook
LLAMA_CLI_BIN=/workspace/user_data/llama.cpp-omni-upstream/build-huawei/bin/llama-omni-eval-cli \
GGML_CANN_WEIGHT_NZ=off ASCEND_RT_VISIBLE_DEVICES=0 CUDA_VISIBLE_DEVICES=0 \
  <venv-omni>/bin/python smoke_test.py 2
# 预期：2/2 有效 A/B/C/D（不再 _）
```

> 构建要点：①必须用 ccec（系统 gcc 链接失败）；②上游 eval-cli 链接需显式 `-lascendcl`（`libomni.so` 引用 `aclrtGet/SetDevice`，否则 `ld.lld: undefined reference`）。
> 踩坑：单 NPU 一次只一个 torch_npu 进程（CANN init 并发会死锁）；双 die 需 `ASCEND_RT_VISIBLE_DEVICES=0` 锁 die0。

---

## 六、影响与后续

1. **多帧精度在 910B 可达**：VideoMME/Daily-Omni 不再是"0% 退化"死局——采用上游 attention 修复即可出真实精度数。**无需 910C**。
2. **官方 bench/huawei 分支自带修复**：切过去即自动解决（这解释了官方为何敢标"目标 Ascend 910"）。
3. **准入路径打通**：VideoMME/Daily-Omni 精度项从"框架受限、待赛方豁免"变为"可达，跑通即过"。
4. **后续**（见 task #9 / 集成 plan）：
   - 以 `bench/huawei` 为基线，接入官方 `evaluation/` + 冻结 eval CLI + 修复后的 ggml-cann；
   - 我们的优化补丁（`ggml-cann.cpp` device 绑定、`omni.cpp` 队列解耦 P1.7）叠加其上（均不在不可改清单）；
   - 跑 `./run_all.sh --smoke 2` → 全量精度复跑。

---

## 七、相关文档与产物

- `docs/bench-huawei-branch-notice.md` —— 官方统一测评分支通知（逐字留档 + 影响 + Track B 上下文）
- `docs/multiframe-degradation-repro.md` —— 复现/对比指南（基于外部 CookBook，待对齐到官方分支）
- `docs/performance-report.md` §10 —— 旧结论"910B4 框架级 bug"（本日推进到 attention 算子级，且证明可解）
- `docs/experiments.md` P2.5 / P3 —— NaN 逐层诊断（输入干净，NaN 在 `llama_decode` 内部 → 即本 attention 路径）
- `benchmark/video-mme-cookbook/diag/trackb_videomme_test.py` —— Track B 对照脚本
- 上游参考克隆：`/workspace/user_data/llama.cpp-omni-upstream`（`bench/huawei`, commit `c9785cc`）
