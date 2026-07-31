# 复现说明（初稿）

目标：评审人员按本文档在官方统一昇腾环境（单卡 910C + CANN 9.1.0-beta1
镜像）中 30 分钟内复现本方案的全部结果。

## 1. 环境要求

- 硬件：昇腾 910C 单卡
- 系统：官方统一镜像（CANN 9.1.0-beta1）
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
# CANN 后端构建（910C）
cmake -B build -DCMAKE_BUILD_TYPE=Release \
      -DGGML_CANN=ON \
      -DCANN_INSTALL_DIR=<CANN路径> \
      -DUSE_ACL_GRAPH=ON
cmake --build build --target llama-omni-cli llama-omni-perf-duplex -j
```

## 4. 模型权重

- 来源：ModelScope openbmb/MiniCPM-o-4_5-gguf
- 文件：MiniCPM-o-4_5-Q4_K_M.gguf + audio/tts/vision/token2wav 全模块
- 放置：/user_data/MiniCPM-o-4_5-gguf/（官方大容量目录）

## 5. 评测（RTF）

```bash
cd llama.cpp-omni
BUILD_DIR=$PWD/build tools/omni/perf/run_perf.sh \
  -m /user_data/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf \
  -ngl 99 -c 8192
# 输出：tools/omni/output/perf_report.md（含 TTS RTF、P95 等全部指标）
```

## 6. 精度验证

- 待官方 starter kit 提供 Daily-Omni 等 benchmark 脚本后补充

## 7. 复现检查清单

- [ ] 构建无报错
- [ ] run_perf.sh 正常出报告
- [ ] llm_debug/llm_text.txt 输出内容正常（防乱码）
- [ ] 报告指标在本文档范围内（±10% 环境波动）
