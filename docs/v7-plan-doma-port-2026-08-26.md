# v7 方案论证：doma 优化移植（2026-08-26）

> 依据：docs/competitor-intel-doma-2026-08-26.md（情报）+ /tmp/doma-intel/（补丁全文）。
> 原则：大胆求证、小心实现；**不破坏当前环境/数据**（实验分支 + 独立 build 目录 + env 默认 off + 全量可回退）。

## 一、候选方案矩阵（910B4 可移植性 × 收益 × 风险）

| # | 方案 | 来源 | 实现位置 | 910B4 预估收益 | 风险 | 工作量 |
|---|---|---|---|---|---|---|
| 1 | **VPM 同尺寸 batch 编码** | doma patch_vpm_batch.patch（原自 zs213118） | omni.cpp `encode_image_with_vision_chunks` +45 行 | encode 0.359→~0.29（-17~24%，他们 910C 实测 -24%）→ **RTF -5~7%** | 低（输出按序切分；他们 videomme/daily 50 题 0 翻转） | 0.5-1 天 |
| 2 | **t2m 冗余 CONT 消除** | doma sprint13（ADD_MUL 子集） | token2wav-impl.cpp `ggml_cont_if_needed` helper + 234 站点替换 | t2m -3.9% → **RTF -2.5~5%** | 极低（bit-identical；env 默认 off 零行为变化） | 0.5-1 天 |
| 3 | **TTS FA（正确路径）** | doma sprint5 | omni.cpp:4331 `tts_ctx_params.flash_attn_type=ENABLED` + env | tts 0.275→~0.255（-7%）→ **RTF -1.5~3%** | ⚠️ 中：双工路径可能破坏流式（他们 config.env 注记 "8 SPEAK/4轮 vs 27/5轮"）→ 必须 SPEAK 数验证 | 0.5 天 |
| 4 | head_code NPU | doma sprint3 | omni.h/cpp 新模块（ggml mul_mat [768,6562]） | 与 v6 CPU 并行版 A/B 才知道（NPU launch 开销可能抵消） | 中：top1 一致但非 bit-identical（max_abs 0.009） | 1-2 天 |
| 5 | 4 步 flow | doma 本轮 | omni.cpp env 读取 + prompt_cache 重建 | t2w -2% → RTF -0.5~1% | 中高：我们 CLOSED 过（5 步拐点）；doma 修复=env 读取 + prompt_cache 匹配 | 1 天 |
| 6 | LLM layer cap 30 | doma sprint17/18 | llama.cpp/qwen3.cpp | decode -17% → RTF -3~4% | **高：改推理数学（破我们自定红线）；精度全量验证 5 天不够** | 2-3 天 |

## 二、推荐组合（v7 核心 = 方案 1 + 2 + 3）

| 组合 | 预估 910B4 RTF | 说明 |
|---|---|---|
| 方案 1+2 | 1.166 → **~1.05-1.10**（-6~10%） | 低风险高确定性 |
| 方案 1+2+3 | → ~1.03-1.08 | 方案 3 需 SPEAK 数验证通过才开 |

官方 910C 出分预期：v6 ~0.69-0.73 → v7 ~0.62-0.68（若 910C 上收益等比）→ 排名第 7-8 名（对照 zz 0.6869 / 等我启动 0.751）。

## 三、验证计划（每方案，严格执行）

1. **实验分支** `v7-doma-port`（基于 review-optimize 当前 HEAD，不碰 main/工作区现状）
2. **独立构建目录** `code/llama.cpp-omni/build-v7/`（不动 build-cann = v6 产物）
3. **分布分离**：官方 rts 口径 ≥3 次独立 run vs v6 基线（1.139/1.151/1.181/1.186，中位 1.166）——零重叠才采纳
4. **精度门禁**：
   - 方案 1：videomme 10/10 逐字节一致（我们现有验证法）
   - 方案 2：wav 20/20 逐字节一致（--seed 固定，最强形式）
   - 方案 3：SPEAK 数核对（破坏流式即否决）+ logits 逐位一致
5. **batch_validity 双 true** 每 run 检查
6. 组合验证：最终配置 3+ run + 精度门禁

## 四、时间预算（截止 8/31 剩 5 天）

- 8/26-27：方案 1 移植 + 验证（预算 1 天）
- 8/27-28：方案 2 移植 + 验证（预算 1 天，可与 1 串行）
- 8/28：方案 3 移植 + SPEAK 数验证
- 8/29：组合验证 + v7 打包（README 哈希顺带修正为 1dd42b7）
- 8/30：提交 v7（v6 出分后可对照；v7 包含 v6 全部优化，替换无损）
- 缓冲：8/31

## 五、红线与风险控制

- 不改 evaluation/、不改官方 eval-cli、不改计时字段（官方不可改清单）
- 所有新 env 默认 off（与 doma 一致）→ 官方默认行为零变化
- 不改推理数学（方案 6 明确排除——我们自定红线，5 天验证不动精度风险）
- 每次验证通过即 git 提交（可回退点）
- 若方案 1/2 中任一验证失败 → 只提交通过项；都不通过 → 放弃 v7，维持 v6（现有成绩不受影响）

## 六、待确认

1. 方案 3（TTS FA）双工流式风险：先小实验验证 SPEAK 数，破坏即否决
2. 方案 4/5 是否做：方案 4 与 v6 CPU 并行版 A/B 成本高收益未知；方案 5 我们 CLOSED 过——**默认不做**，除非 1+2+3 完成后还有时间
3. build-v7 磁盘空间确认（build-cann 已有 ~10-30G，需检查剩余空间）
