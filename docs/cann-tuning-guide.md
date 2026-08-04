# CANN 场景性能调优指南（910C）

更新：2026-07-31
基于 llama.cpp-omni ggml/src/ggml-cann/ 源码确认

## 一、编译/构建层

```bash
# CANN 后端编译（910C 上执行）
cmake -B build-cann -DCMAKE_BUILD_TYPE=Release \
      -DGGML_CANN=ON \
      -DCANN_INSTALL_DIR=<CANN路径>   # 或设环境变量 ASCEND_TOOLKIT_HOME
      -DUSE_ACL_GRAPH=ON              # ACL 图模式，默认 OFF；910C 支持，910B 实测不支持(头文件缺失)

cmake --build build-cann --target llama-omni-cli -j
```

- 编译时自动检测 SoC 类型（npu-smi info 解析 → Ascend910C）
- USE_ACL_GRAPH 图编译 + 算子融合，减 kernel 启动开销（910C 上的大杠杆）
- ⚠️ 910B3 实测不支持图模式（acl_graph 头文件缺失，编译 FATAL_ERROR）→ 本环境不用
- 310P 同样不支持图模式；仅 910C 完整支持

## 二、运行时配置

| 项 | 说明 |
|----|------|
| GGML_CANN_DISABLE_BUF_POOL_CLEAN | CANN 内存池清理行为控制 |
| ASCEND_GLOBAL_LOG_LEVEL | 跑分时设 WARN/ERROR，日志开销影响 RTF |
| aclrtSetDevice | NPU 设备绑定 |
| HBM 大页 | 代码用 ACL_HBM_MEM_HUGE，默认已开 |

## 三、量化策略

- LLM 主模型：Q8_0 → Q4_K_M 逐档测（CANN 算子对不同量化支持不同，必须 910C 重测）
- audio/tts/vision/token2wav：保持 F16（小模块，量化收益低、精度风险高）
- 4090 预筛结果只当候选，不作结论

## 四、Profiling

- msprof：CANN 官方 profiler，算子级耗时/带宽
- npu-smi info：实时利用率
- 官方 perf-duplex.cpp + benchmark.py：分模块瓶颈定位
  （LLM decode / TTS / Token2Wav 哪段占大头就优化哪段）

## 五、调优工作流

1. 官方工具跑基线 → 记录 RTF + 分模块耗时
2. msprof 定位热点
3. 针对性优化：量化档位 → ACL 图模式 → 运行时参数 → 算子级
4. 复测对比 → 保留有效项 → 循环

## 六、优先级

1. USE_ACL_GRAPH=ON（编译开关，一次开启）
2. 量化档位扫描（每档一次 benchmark）
3. 运行时参数（ctx/chunk/KV cache/线程）
4. 算子级优化（时间允许才做）
