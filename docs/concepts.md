# 概念梳理（AI 推理入门，面向赛道一）

## 一、模型基础层
- 模型推理：用训练好的模型对新输入做预测（比赛只做推理，不碰训练）
- 参数(9B)：模型内部数字，90 亿个，决定能力
- 权重：参数文件，推理时加载（GGUF 文件就是权重）
- Token：文本/音频最小处理单元
- LLM：大语言模型，只处理文本（MiniCPM-o 的大脑 = Qwen3-8B）

## 二、全模态概念（MiniCPM-o 特有）
- 全模态(Omni)：一个模型同时处理文本+图像+音频+视频
- 编码器：输入 → 向量。SigLip2(视觉)、Whisper(音频)
- TTS：文本转语音（CosyVoice2），比赛 RTF 测的就是它生成的音频
- Token2Wav/Vocoder：音频 token → 最终波形
- 流式(Streaming)：边生成边输出
- 全双工(Full-Duplex)：同时听和说、互不阻塞

## 三、推理过程
- Prefill：一次性处理输入 → 占首响延迟
- Decode：逐 token 生成输出 → RTF 大头
- KV Cache：缓存历史计算避免重复 → 调大提速吃显存
- TTFT：首 token 时间
- Chunk：音频小段，一段段生成，赛题按 chunk 测 RTF

## 四、性能指标
- RTF（核心）：生成耗时 ÷ 音频时长，<1 即实时
- 延迟 / 吞吐 / P50 / P95

## 五、量化（最大优化杠杆）
- 量化：高精度 → 低精度权重，更快更省内存
- F16 → INT8(Q8_0) → INT4(Q4_K_M)：精度递减、速度递增
- Q4_K_M 命名：Q=量化, 4=4bit, K=K-quant 算法, M=中等
- 精度损失红线：≤2 个百分点

## 六、硬件与生态
- GPU(CUDA) vs NPU(CANN)：两套生态，代码大部分通用
- 显存：模型必须装入显存
- 算子(Kernel)：矩阵乘等基本运算
- 图模式：算子序列编译成图，省调度（910C 用 USE_ACL_GRAPH）
- 后端(Backend)：CPU/CUDA/CANN/Metal 同框架多硬件实现

## 七、比赛名词
- 官方镜像：预装 CANN 9.1.0-beta1 的容器（统一复现环境）
- Benchmark：标准化测试
- 复现：别人照说明跑出一样结果
- Starter kit：官方起始代码包

## 八、MiniCPM-o 4.5 五模块链路
VPM(视觉) → APM(音频) → LLM(Qwen3-8B) → TTS(语音token) → Token2Wav(波形)
音频输出路径：LLM 想好说什么 → TTS 转语音码 → Token2Wav 合成声音
RTF = 链路各段耗时之和 ÷ 音频时长
