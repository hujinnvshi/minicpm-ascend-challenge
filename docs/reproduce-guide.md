# 复现说明（初稿）

目标：评审人员按本文档在官方统一昇腾环境（单卡 910B3 + CANN 9.1.0-beta.3
镜像；厂家授权 910B3 替代 910C，见 docs/env-scan.md）中 30 分钟内复现本方案的全部结果。

## 1. 环境要求

- 硬件：昇腾 910B3 单卡（厂家授权替代 910C，64GB HBM）
- 系统：官方统一镜像（CANN 9.1.0-beta.3，兼容官方 beta1 要求）
- 预置权重（只读）：/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/（全套 11 档+全模块，免下载）
- 依赖：cmake ≥3.24、g++ ≥11、python3（analyze 脚本）

## 2. 代码获取

- 代码库：llama.cpp-omni（tc-mb/llama.cpp-omni，master）
- 本方案改动：
  1. 无源码改动（TTS n_ctx 缩容实验无效，已回退）
  2. 配置：Q4_K_M 量化 + -c 8192（ctx-size）
- 提交物包含：构建脚本、评测脚本、配置、本说明

## 3. 构建

```bash
git clone https://github.com/tc-mb/llama.cpp-omni.git
cd llama.cpp-omni
# CANN 后端构建（910B3；图模式 USE_ACL_GRAPH 在 910B 不支持，故不开启）
cmake -B build -DCMAKE_BUILD_TYPE=Release \
      -DGGML_CANN=ON \
      -DCANN_INSTALL_DIR=$ASCEND_TOOLKIT_HOME
cmake --build build --target llama-omni-cli llama-omni-perf-duplex -j
# 或直接用脚本: bash scripts/build-cann.sh
```

## 4. 模型权重

- 来源：官方环境预置（只读，免下载）：/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/
- 文件：MiniCPM-o-4_5-Q4_K_M.gguf + audio/tts/vision/token2wav 全模块（另有 11 档可选）
- 备选：bash scripts/sync-weights.sh pull 从 ModelScope 下载到 /workspace/user_data/

## 5. 评测（RTF）

```bash
cd llama.cpp-omni
BUILD_DIR=$PWD/build tools/omni/perf/run_perf.sh \
  -m /workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
  -ngl 99 -c 8192
# 输出：tools/omni/output/perf_report.md（含 TTS RTF、P95 等全部指标）
```

## 6. 精度验证

- Daily-Omni：cd code/daily-omni && python run_pipeline.py（脚本与 baseline/ 官方基线对照已就位）
- TTS-Seed / Video-MME：待官方 starter kit 补充（Daily-Omni 可先行）

## 7. 复现检查清单

- [ ] 构建无报错
- [ ] run_perf.sh 正常出报告
- [ ] llm_debug/llm_text.txt 输出内容正常（防乱码）
- [ ] 报告指标在本文档范围内（±10% 环境波动）
