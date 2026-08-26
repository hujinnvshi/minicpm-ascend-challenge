# 910C（CANN Lab NPU A3）环境接入指南（2026-08-26）

> 目的：在 CANN Lab 的 NPU A3（910C）环境上拉取本项目 v7 代码，完成构建与验证。
> 用户操作路径：CANN Lab WebIDE/SSH → 按本文逐步执行。

## 0. 环境探测（先做，输出发回本机）

```bash
uname -a
npu-smi info | head -12          # 确认 NPU 型号（A3/910C？）、卡数、HBM
cat /usr/local/Ascend/*/version.cfg 2>/dev/null || echo $ASCEND_TOOLKIT_HOME
ls /dev/davinci*                 # 设备号
nproc                            # CPU 核数（绑核用）
```

## 1. CANN 升级到 9.1.0（若当前是 9.0.0）

```bash
cd /tmp
# 直链（404 则官网 https://www.hiascend.com/developer/download/community/result?module=cann&cann=9.1.0 选 Toolkit/aarch64/run 包）
wget -q "https://ascend-repo.obs.cn-east-2.myhuaweicloud.com/CANN/CANN%209.1.0/Ascend-cann-toolkit_9.1.0_linux-aarch64.run" -O cann-9.1.0.run
chmod +x cann-9.1.0.run
./cann-9.1.0.run --upgrade        # 出现 [upgrade success] 即成功
python -c "import acl; print('ACL OK')"
ls /usr/local/Ascend/*/tools/bisheng_compiler/bin/ccec   # ccec 编译器（构建必需，toolkit 自带）
```

## 2. 拉代码（v7 分支）

```bash
cd /workspace
git clone -b v7-doma-port https://github.com/hujinnvshi/minicpm-ascend-challenge.git
cd minicpm-ascend-challenge
git log --oneline -1    # 期望 f45f67e（v7 最新）
# v7 核心代码：code/llama.cpp-omni/tools/omni/omni.cpp 含 OMNI_VISION_BATCH_ALL（VPM 批量编码）
```

## 3. 模型下载（ModelScope，权重 19GB 全模态）

```bash
mkdir -p /workspace/shared_assets/models/OpenBMB
cd /workspace/shared_assets/models/OpenBMB
# ModelScope CLI（pip install modelscope 后）：
modelscope download --model OpenBMB/MiniCPM-o-4_5-gguf --local_dir ./MiniCPM-o-4_5-gguf
# 或 git lfs：
git lfs install && git clone https://modelscope.cn/models/OpenBMB/MiniCPM-o-4_5-gguf.git
# 校验：MiniCPM-o-4_5-F16.gguf 主模型 + vision/audio/tts/projector/token2wav-gguf 全套
du -sh MiniCPM-o-4_5-gguf
```

## 4. 构建（CANN 9.1.0 + ccec）

```bash
cd /workspace/minicpm-ascend-challenge/code/llama.cpp-omni
source /usr/local/Ascend/cann-9.1.0/bin/setenv.bash 2>/dev/null || source /usr/local/Ascend/ascend-toolkit/set_env.sh
# 复用构建脚本（BUILD_DIR 指定独立目录，不动默认 build-cann）
BUILD_DIR=$PWD/build-910c bash ../../scripts/build-cann.sh
# ⚠️ 脚本只建 cli/perf-duplex；评测还需 server + eval-cli：
cmake --build build-910c --target llama-omni-server llama-omni-eval-cli llama-omni-eval-daily-cli llama-omni-tts-eval -j$(nproc)
# ⚠️ 已知坑：libomni.so 链接缺 ascendcl 时，编辑 build-910c/tools/omni/CMakeFiles/omni.dir/link.txt
#    追加 `-L/usr/local/Ascend/cann-9.1.0/aarch64-linux/devlib -lascendcl` 后重跑 cmake --build
```

## 5. 验证（rts + FA 生效确认）

```bash
cd /workspace/minicpm-ascend-challenge/code/llama.cpp-omni/evaluation
# 环境变量（v7 全配置；EVAL_CONFIG 用本仓库 benchmark/eval-singlecard-910b.env 改路径）
cat > /tmp/eval-910c.env << 'EOF'
export EVAL_SUITE_ROOT=/workspace/minicpm-ascend-challenge/code/llama.cpp-omni/evaluation
export LLAMACPP_ROOT=/workspace/minicpm-ascend-challenge/code/llama.cpp-omni
export EVAL_BIN_DIR=${LLAMACPP_ROOT}/build-910c/bin
export OMNI_SERVER_BIN=${LLAMACPP_ROOT}/build-910c/bin/llama-omni-server
export OMNI_FORCE_FA=1 OMNI_VISION_FA=1 OMNI_NPU_SERIAL=1 OMNI_HEADCODE_THREADS=24 OMNI_T2W_THREADS=24
export GGML_CANN_WEIGHT_NZ=off GGML_CANN_ACL_GRAPH=off
EOF
source /tmp/eval-910c.env
taskset -c <NPU同node核> ./run_all.sh --tasks rts --smoke 2 --no-build
# 判读：
#   1) FA 生效：cpp.log 不应出现 "flash_attn is not compatible with CANN - forcing off"
#   2) batch_validity 双 true（data_valid + realtime_eligible）
#   3) RTF 量级对照：910B2 本机 0.94 / doma 910C 0.54-0.69 / 我们预估 0.63-0.69
# 绑核：cat /sys/bus/pci/devices/<NPU_BDF>/numa_node → 该 node cpulist（scripts/numa-bind.sh 自动）
```

## 6. 910C 特性探针（FA 正常后，重点）

1. **图模式**（最大杠杆 -10.9% 上限）：`bash scripts/build-cann.sh --graph`（USE_ACL_GRAPH 构建）+
   运行时 `GGML_CANN_ACL_GRAPH=1`——验证 aclmdlRIExecuteAsync 是否真省时（910B4 实测不省时，910C 未知）
2. **KV 量化**：grep GGML_OP_QUANTIZE ggml-cann 算子表——CANN 9.1 若有则 decode 带宽 -21% 上限
3. 探针结果回传本机（docs/910c-probe-结果.md），决定 v8 提交内容

## 7. 已知坑速查

| 坑 | 处理 |
|---|---|
| NZ 必须 off | `GGML_CANN_WEIGHT_NZ=off`（官方要求，直跑必须显式 export） |
| FA 默认被 CANN forcing off | 必须 `OMNI_FORCE_FA=1`（llama-context AUTO 保守关闭） |
| EVAL_CONFIG 是替换语义 | 本机 env 必须 source 官方 config.env 为基底再覆盖（benchmark/env 模板已做） |
| libomni 链接缺 ascendcl | link.txt 注入 `-lascendcl`（见 §4） |
| 设备会被平台重分配 | 每次开机先 npu-smi 探测，勿信文档硬件参数 |
| omni_init 超时 | BATCH_WORKER_FAILED 是瞬态，重试即可（模型加载有时 >120s） |

## 8. 需要回传本机的信息

1. npu-smi 输出（型号/算力确认）
2. CANN version.cfg + ccec 确认
3. rts 首次结果（FA 是否生效 + RTF 数字 + batch_validity）
4. 图模式/KV 量化探针结果
