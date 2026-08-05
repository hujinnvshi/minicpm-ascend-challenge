# ggml-cann 代码补丁记录

记录 llama.cpp-omni 的 ggml-cann 后端在 910B3 上为跑通 MiniCPM-o 4.5 全链路所做的代码修复。

**背景**：CANN 多线程下 aclrt API 要求每个工作线程显式绑定 device（`aclrtSetDevice` 是
per-thread）。ggml-cann 的部分 backend 接口漏了 `ggml_cann_set_device`，导致 Token2Wav
（运行在独立线程 `t2w_thread_func_cpp`）在 CANN 后端崩溃：`rtMemcpyAsync failed, the
context is a null pointer / current device: -1`。

**文件**：`code/llama.cpp-omni/ggml/src/ggml-cann/ggml-cann.cpp`
**参照模式**：`ggml_backend_cann_synchronize`(2214) 与 `graph_compute`(2335) 均在 aclrt
调用前 `ggml_cann_set_device(ctx->device)`（该函数带 thread-local 缓存，device 不变时零开销）。

---

## 补丁 1 · set_tensor_async 加 device 绑定

- **位置**：`ggml-cann.cpp:2084`（`ggml_backend_cann_set_tensor_async`）
- **现象**：T2W 线程 host→device 拷贝时 `aclrtMemcpyAsync` 报 *context is a null pointer*，current device: -1
- **原因**：T2W 在独立线程，未继承主线程 device 绑定
- **修复**：`aclrtMemcpyAsync` 前加 `ggml_cann_set_device(cann_ctx->device);`

## 补丁 2 · get_tensor_async 加 device 绑定

- **位置**：`ggml-cann.cpp:2114`（`ggml_backend_cann_get_tensor_async`）
- **现象**：补丁 1 修复后，device→host 回拷会崩（孪生缺陷）
- **修复**：同补丁 1，`aclrtMemcpyAsync` 前加 `ggml_cann_set_device(cann_ctx->device);`

## 补丁 3 · event_record 加 device 绑定

- **位置**：`ggml-cann.cpp:2722`（`ggml_backend_cann_event_record`）
- **现象**：防御性补全——双工模式当前用 std::mutex/cv/atomic 不触发 aclrt event，但 backend 接口应完整，且其他调度路径可能用 event
- **修复**：`aclrtRecordEvent` 前加 `ggml_cann_set_device(cann_ctx->device);`

## 补丁 4 · event_wait 加 device 绑定

- **位置**：`ggml-cann.cpp:2737`（`ggml_backend_cann_event_wait`）
- **修复**：`aclrtStreamWaitEvent` 前加 `ggml_cann_set_device(cann_ctx->device);`

## 补丁 5 · GGML_OP_SQR 断言放宽

- **位置**：`ggml-cann.cpp:1922`（op 分发 SQR case）
- **现象**：`GGML_ASSERT(dst->src[1] == nullptr)` 失败——新版 ggml 图布局里 SQR 的 `src[1]` 非空
- **原因**：CANN 无原生 sqr 算子，原作者用 `aclnn_mul(x,x)` hack（需设 `dst->src[1]=dst->src[0]`），断言过严
- **修复**：删断言，保留 `dst->src[1] = dst->src[0]`（与原 hack 意图一致，仅放宽前置）
- **可选改进（本轮未做）**：改用 `aclnnPowTensorScalar`（`aclnn_pow.h`，exponent=2.0）作干净实现，避免 compute 阶段改图拓扑。后续优化时考虑。

## 补丁 6 · host_buffer 默认 false（让 LLM 权重上 NPU device buffer）

- **位置**：`ggml-cann.cpp:2825`（`ggml_backend_cann_device_get_props`）
- **现象**：llama 标准 offload 把 LLM 权重放 cann host buffer（=CPU pinned RAM），compute 回退 CPU（AICore=0）
- **原因**：`host_buffer = getenv("GGML_CANN_NO_PINNED")==nullptr` 默认 true，llama `make_gpu_buft_list` 据此把 host buffer 加入 buft_list 作权重 fallback
- **修复**：翻转默认——`host_buffer = getenv("GGML_CANN_FORCE_PINNED") != nullptr`（默认 false），LLM 权重用 device buffer 上 NPU HBM。运行时 pinned 传输仍由 `ggml_cann_host_malloc`(1693) 的 `GGML_CANN_NO_PINNED` 控制（未动）
- **验证**：单工 F16 LLM 稳定上 NPU（HBM 23.6G + AICore 66% + prefill 0.77s，不需 env）。**双工 perf-duplex 仍 CPU**（见已知问题 3）

---

## 验证

- **重编**：`cmake --build build-cann --target ggml-cann -j256` → `libggml-cann.so` 更新，退出 0
- **device 覆盖**：`grep -c ggml_cann_set_device ggml-cann.cpp = 24`（backend 接口全覆盖，无盲点）
- **全链路**：`llama-omni-cli -m Q4_K_M --omni --test 9`，9 输入全 prefill，退出 0，23 wav，T2W RTF mean=0.861（87% chunk 实时），wav RMS 无静音，LLM 视觉语义正常
- 详见 [experiments.md](experiments.md) P0 实验条目

---

## 已知问题（P1 诊断发现，非代码 patch）

### 1. cann host_buffer cap 致 LLM 落 CPU（**单工已修，见补丁 6**）
- **现象**：llama 标准 offload（ngl=99）把 LLM 权重放 cann host buffer（=CPU pinned RAM），compute 回退 CPU（AICore=0、HBM 3.4G）
- **根因**：`device_get_props` 的 `host_buffer` 默认 true，llama 据此把 host buffer 加入 buft_list 作权重 fallback
- **修复（补丁 6）**：`host_buffer` 默认 false → **单工 LLM 稳定上 NPU**（HBM 23.6G + AICore 66% + prefill 0.77s，不需 env）
- **残留**：双工 LLM compute 未真走 NPU（见已知问题 3，P1.6 已让 model 上 device 但 compute AICore 仅 4%）

### 3. ~~双工 LLM compute 未走 NPU~~ → **P1.7 澄清：一直在 NPU，AICore 4% 是采样伪影；真因是 LLM↔TTS 队列锁步**

- **P1.6 误判**：以为 decode 中 AICore 仅 4% = "compute 没真走 NPU / graph_compute 路径问题"。
- **P1.7 实测推翻**：复跑 P1.6 + npu-smi 0.5s 细粒度采样，decode 活跃窗口 **AICore 峰值 60–84%、HBM 带宽 50%** —— decode **一直在 NPU**（memory-bound，权重流式）。"AICore 4%" 是 2min 窗口时间均值伪影（含 prefill 空闲 + 帧间等待 + drain 阶段）。**offload 从未失败**，graph_compute / device 绑定均正常。
- **P50 8840ms 真因**：`omni.cpp` LLM→TTS-model 队列 `TTSThreadInfo(1)`（容量=1）强制 LLM 与 TTS-model（同 NPU 上的第二个自回归 decoder）严格 1:1 锁步 → 每帧 decode 墙钟叠加 TTS-model decode 时间 → 1.4s/帧 > 1s → 积压 → P50 8.3s。**非 compute 路径、非 audio encoder、非 model 释放**（model 维持 HBM 36%，未释放）。
- **P1.7 修复**：队列 1→16（`tools/omni/omni.cpp` omni_init，env `OMNI_TTS_QUEUE` 可覆盖）→ **LLM P50 8295→977ms（8.5×，<1000 达标）**，TTS RTF 0.80 不回归，quality-neutral（token 序列逐字相同）。
- **残留（非 LLM compute）**：LLM P95 1014ms（临界）+ 首响 1493ms（T2W ~700ms floor）。冲 exit 0 需 T2W 提速或 NPU 多流并发（decode 期 NPU 平均仅 ~23%，硬件有余量但当前串行）。
- **详见**：[experiments.md](experiments.md) P1.7、[decisions.md](decisions.md) P1.7 决策

> ⚠️ 提醒（给后续诊断）：判断"NPU 是否在算"必须用**细粒度 npu-smi 采样（≤0.5s）+ 与 [prof] decode 时间戳对照**，不能看单次或粗均值；`npu-smi info -t usages -i 1` 的 `Aicore Usage Rate` + `HBM Bandwidth Usage Rate` 是决定性指标（HBMbw 高=真在 NPU 算）。

### 2. cann 量化算子缺失（Q4_K_M）
- **现象**：Q4_K_M LLM 在 cann 上 compute 回退 CPU（AICore=0）；F16 LLM 在 cann 上正常（NPU，prefill 0.58s，13x）。vision/audio/tts/token2wav 均 F16 故一直正常
- **结论**：cann 后端对 Q4_K_M 量化算子不支持/缺，对 F16 支持
- **影响**：910B 上"量化优化"失效（4090 最优的 Q4_K_M 在 910B fallback CPU）→ LLM 改用 F16
- **待评估**：Q6_K/Q5/Q8_0 等其他量化档在 cann 的支持情况（P2 重扫；Q8_0 在 CUDA 是乱码 bug，cann 可能正常且支持）
