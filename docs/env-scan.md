# 云环境扫描报告（910B3，2026-08-04 实测）

> 本文件是**当前真实运行环境**的权威基线。所有执行性文档（README/workflow/reproduce 等）
> 描述硬件、路径、依赖时以本文件为准。赛题规则原文里的 "910C" 是官方规则，不因此改动；
> 本队**实际评测环境**为 910B3（厂家授权替代 910C，见 decisions.md 2026-08-04）。
>
> 扫描方式：进入厂家云环境后逐项实测（npu-smi / df / lscpu / which / curl 等）。

## 一、结论

环境**优于文档预期**：官方预置了 MiniCPM-o 4.5 全套 11 档量化 + 全模块权重（只读直用，免下载）
与 Daily-Omni benchmark 代码；256 核 CPU + 2TB 内存 + msprof 齐全。少数缺失项
（ffmpeg / docker / ninja / torch / soundfile）均为可装依赖。**权重下载与精度数据准备两大块
工作可直接跳过。**

## 二、硬件

| 项 | 实测值 | 对测试的意义 |
|---|---|---|
| NPU | **910B3 单卡**（NPU1，单 chip），PCI Device ID 0xD802，Product IT21HMDC_Bin6 | 正式环境（厂家授权替代 910C）；单卡 910B ≈ 半颗 910C 算力，RTF 绝对值偏高但选手口径统一 |
| HBM | **64 GB**（空闲，仅占 ~3.4G） | 全模块加载 + KV cache 充裕，ctx-size 可大胆试大 |
| 固件/驱动 | Firmware 9.0.10.0.b057 / npu-smi 25.2.0 | |
| CPU | **鲲鹏 920，256 核，8 NUMA** | 编译飞快（`-j256`）；CPU 侧音频重采样/预处理零瓶颈；NPU 绑 NUMA node6（核 192-223） |
| 内存 | **2 TB**（用 34G，剩 1.9T） | Demo 多进程 / 全模块加载无压力 |
| 运行形态 | **Docker 容器内**（`/.dockerenv` + cgroup=docker） | ⚠️ 容器重建会丢非持久化数据 → **一切产物落 `/workspace/user_data`** |
| 设备节点 | `/dev/davinci1` + `/dev/davinci_manager`（root 可访问） | NPU 设备权限 OK |

## 三、CANN 软件栈

| 项 | 实测值 | 意义 |
|---|---|---|
| CANN | **9.1.0-beta.3**（`ASCEND_TOOLKIT_HOME=/usr/local/Ascend/cann-9.1.0-beta.3`） | 官方要求 beta1，**向上兼容 OK** |
| ACL（C 接口） | `import acl` / `libascendcl.so` OK | 推理运行时可用 |
| aclnn 算子 | **1764 个**算子头文件 | CANN 算子覆盖好，ggml-cann 后端 host fallback 少 |
| **msprof** | ✅ `$ASCEND_TOOLKIT_HOME/bin/msprof` | **瓶颈定位关键工具**（分模块看 LLM/TTS/Token2Wav 耗时） |
| atc | ✅ | 模型转换（ggml-cann 直跑，大概率用不上） |
| **图模式 acl_graph** | ❌ **头文件缺失** | **910B 不支持 `USE_ACL_GRAPH`** → 原计划最大杠杆失效，靠量化+参数+编译三板斧 |
| ATB | `$ATB_HOME_PATH` 预置（Ascend Transformer Boost） | 赛道一 A 用不上，记录备查 |

## 四、系统与工具链

| 项 | 状态 |
|---|---|
| OS / 内核 | openEuler 24.03 LTS-SP3 · aarch64 · kernel 5.10 |
| cmake 3.27.9 / gcc/g++ 12.3.1 / make 4.4.1 / git 2.43 / wget / rsync | ✅ |
| Python 3.12.13 + numpy 2.5.0 + PyYAML | ✅ |
| **ninja** | ❌ 缺（用 `make -j256` 替代，够快） |
| **ffmpeg** | ❌ 缺（**Demo 音视频处理必需，先装**） |
| **docker** | ❌ 缺（官方 Demo 的 docker-compose 跑不了 → **裸机部署** Gateway/Worker/Backend 三进程） |
| **torch / soundfile / librosa / modelscope** | ❌ 缺（perf 脚本/Demo 依赖，按需 `pip install`） |

## 五、网络与镜像

| 项 | 状态 |
|---|---|
| modelscope.cn / github.com / pypi.org | ✅ 全通（200） |
| pip 源 | **华为云镜像** `repo.huaweicloud.com/repository/pypi/simple`（内网快） |
| 出口代理 | VSCODE_PROXY_URI → hicomputing.huawei.com（华为云 HiDevLab 类环境） |

## 六、官方预置资源（重点，改变计划）

### 权重：`/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/`（只读，免下载）

| 类别 | 文件 |
|---|---|
| LLM（**11 档全有**） | F16(16G) · Q8_0(8.2G) · Q6_K(6.3G) · Q5_K_M(5.5G) · Q5_K_S(5.4G) · Q5_1(5.8G) · Q5_0(5.4G) · **Q4_K_M(4.7G)** · Q4_K_S(4.5G) · Q4_1(4.9G) · Q4_0(4.5G) |
| TTS | tts-F16(1.1G) · projector-F16(15M) |
| Audio | audio-F16(630M) |
| Vision | vision-F16(1.1G) |
| Token2Wav | encoder(145M) · flow_matching(438M) · flow_extra(14M) · hifigan2(80M) · prompt_cache(202M) |

> 文件命名与 `sync-weights.sh` 完全一致 → **`-m` 直接指向只读路径即可跑，无需下载/复制/软链**。
> P2 量化扫描可从原 6 档扩到 11 档（成本仅多几次 benchmark）。

### Benchmark 代码：`code/daily-omni/`
含 `run_pipeline.py` / `qa.json` / `baseline/`（官方基线对照）/ `test_model/` / `requirements.txt`
→ 正好是**精度准入三个 benchmark 之一（Daily-Omni）**的运行代码。原"等 starter kit"作废。

### 通用数据集：`/workspace/shared_assets/datasets/`（非赛事指定，仅开发自检）
MMMU / MMLU / LLaVA-Instruct-150K / alpaca —— **不能替代**官方 Daily-Omni/TTS-Seed/Video-MME，
但可用于开发期精度 sanity check（防优化掉精度却不知道）。

## 七、现有产物盘点（`code/`，父仓库快照，无独立 .git）

| 仓库 | 大小 | 状态 |
|---|---|---|
| llama.cpp-omni | 159M | 源码在位（含 `ggml/src/ggml-cann/`），**未编译**（无 build 目录） |
| MiniCPM-o-Demo | 30M | 官方 Demo 源码在位 |
| daily-omni | 36M | Daily-Omni benchmark 代码 |
| perf 工具 | — | `tools/omni/perf/`：`run_perf.sh`（带 `--build` 自动编译）+ `perf-duplex.cpp` + `analyze_perf.py` + `DUPLEX_PROFILING.md` |

## 八、对测试的影响（环境特征 → 测试环节）

| 环境特征 | 帮到哪个环节 | 怎么用 |
|---|---|---|
| 预置全套权重 | P0 链路 / P2 量化扫描 | `-m /workspace/shared_assets/.../MiniCPM-o-4_5-Q4_K_M.gguf` 直接跑；P2 扫 11 档 |
| daily-omni 代码 | P5 精度 | 跑 `run_pipeline.py` 出 Daily-Omni 精度，对照 `baseline/` |
| msprof | P1 基线 / 全程瓶颈定位 | 分模块看 LLM/TTS/Token2Wav 哪段占 RTF 大头 |
| 256 核 + 2TB 内存 | P3 参数调优 / P6 Demo | ctx-size 大胆上调；Demo 三进程 + 前端并发无压力 |
| 1764 aclnn 算子 | P2/P3 | CANN 后端算子命中率高，少 host fallback |
| 通用 datasets | P5 开发自检 | 优化前后跑 MMMU/MMLU 看精度有无跌 |
| 华为云 pip 镜像 | 补依赖 | `pip install soundfile librosa` 秒装 |

## 九、发现的坑 + 建议

| # | 坑 | 影响 | 建议 |
|---|---|---|---|
| 1 | **图模式不支持** | 少最大优化杠杆 | P4 砍掉；靠量化+参数+编译；报告写"910B 已知约束" |
| 2 | **ffmpeg/docker 缺** | Demo 卡住 | P6 前装 ffmpeg；Demo 改裸机部署（不用 docker-compose） |
| 3 | **torch/soundfile/librosa 缺** | perf/Demo | 按需 `pip install`（先看 requirements.txt） |
| 4 | **脚本路径不对齐** | sync-weights 跑废 | `/home/ma-user/work/user_data` → `/workspace/user_data`（已修） |
| 5 | **容器会重建** | 丢数据 | 编译产物/报告/配置全落 `/workspace/user_data`，别放 `/root`、`/tmp` |
| 6 | **三仓库是父仓快照** | 不能 git pull 上游 | 快照够用；要更新上游需重新 clone |
| 7 | **version.cfg 读不到** | build-cann 版本检查 | 已改：优先 `$ASCEND_TOOLKIT_HOME`，缺失时从目录名推断 |

## 十、基于扫描结果，原计划修订

| 阶段 | 原计划 | 修订后 |
|---|---|---|
| P0 | 下载权重 14GB | ❌ 删 → 直接用 shared_assets 只读路径 |
| P2 | 扫 6 档量化 | ✅ 扩到 11 档 |
| P4 | 试编图模式 | ❌ 砍（910B 不支持） |
| P5 | benchmark 脚本待写 | ✅ daily-omni 代码现成，先跑通 |
| P6 | docker-compose 部署 Demo | ✅ 改裸机部署 + 先装 ffmpeg |
| 新增 | — | ✅ 补依赖（ffmpeg + perf/Demo 的 python 包） |

## 附：关键路径速查

```
项目根:        /workspace/minicpm-ascend-challenge
权重(只读):    /workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/
持久化(读写):  /workspace/user_data/   (glusterfs 35T，编译产物/报告落此)
CANN:          /usr/local/Ascend/cann-9.1.0-beta.3
perf 工具:     code/llama.cpp-omni/tools/omni/perf/run_perf.sh
benchmark:     code/daily-omni/run_pipeline.py
```

常用命令：
```bash
npu-smi info                              # NPU 状态
python3 -c "import acl; print('ok')"      # CANN 运行时自检
ls /workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/   # 预置权重
bash scripts/sync-weights.sh use-shared   # 打印预置权重路径（免下载）
```
