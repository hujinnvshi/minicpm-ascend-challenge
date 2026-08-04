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

---

## 验证

- **重编**：`cmake --build build-cann --target ggml-cann -j256` → `libggml-cann.so` 更新，退出 0
- **device 覆盖**：`grep -c ggml_cann_set_device ggml-cann.cpp = 24`（backend 接口全覆盖，无盲点）
- **全链路**：`llama-omni-cli -m Q4_K_M --omni --test 9`，9 输入全 prefill，退出 0，23 wav，T2W RTF mean=0.861（87% chunk 实时），wav RMS 无静音，LLM 视觉语义正常
- 详见 [experiments.md](experiments.md) P0 实验条目

---

## 已知问题（P1 诊断发现，非代码 patch）

### 1. cann host_buffer cap 致 LLM 落 CPU（offload 失败根因）
- **现象**：llama 标准 offload（ngl=99）把 LLM 权重放 cann host buffer（=CPU pinned RAM），compute 回退 CPU——推理时 AICore=0、HBM 仅 3.4G（LLM 4.7G 不在 NPU），prefill 7.9s / decode 350ms（4090 是 65ms / 38ms）
- **根因**：`ggml-cann.cpp:2826` `device_get_props` 中 `host_buffer = getenv("GGML_CANN_NO_PINNED")==nullptr` → 默认 true，llama `make_gpu_buft_list` 据此优先用 host buffer type（`ggml_backend_cann_host_buffer_type`，其 alloc 走 CPU：ggml-cann.cpp:1726）
- **配置绕过**：`GGML_CANN_NO_PINNED=1`（host_buffer=false，LLM 用 device buffer 上 HBM）。**单工生效**（F16 prefill 0.58s、HBM 8996），**双工 perf-duplex 不稳**（时而 HBM 3482 仍 CPU）
- **诊断证据**：device 枚举正确（dev_count=2，CANN0 type=GPU 进 gpus，devices 不空，ngl=99）；alloc 探针确认 LLM 无 ~4.7G cann device alloc（走 host buffer）
- **待修**：稳定双工 offload（改 cann `host_buffer` 默认 / 查双工 omni_init 的 buffer 选择路径）

### 2. cann 量化算子缺失（Q4_K_M）
- **现象**：Q4_K_M LLM 在 cann 上 compute 回退 CPU（AICore=0）；F16 LLM 在 cann 上正常（NPU，prefill 0.58s，13x）。vision/audio/tts/token2wav 均 F16 故一直正常
- **结论**：cann 后端对 Q4_K_M 量化算子不支持/缺，对 F16 支持
- **影响**：910B 上"量化优化"失效（4090 最优的 Q4_K_M 在 910B fallback CPU）→ LLM 改用 F16
- **待评估**：Q6_K/Q5/Q8_0 等其他量化档在 cann 的支持情况（P2 重扫；Q8_0 在 CUDA 是乱码 bug，cann 可能正常且支持）
