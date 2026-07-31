# Daily-Omni 精度 Benchmark 调研（2026-07-31）

来源：官方开源仓 Lliar-liar/Daily-Omni（已 clone 至 code/daily-omni/）
数据集：https://huggingface.co/datasets/liarliar/Daily-Omni（Videos.tar + qa.json，未下载，约几十 GB，910C 上需要时再拉）

## 评测口径（官方比赛会用类似方式）

- 任务：音视频问答，4 选 1（A/B/C/D），随机基线 25%
- 输入：xxx_video.mp4 + xxx_audio.wav + Question + Choice[4]
- Prompt 模板（固定）：
  "Your task is to accurately answer multiple-choice questions based on the given video and audio together. Select the single most accurate answer from the given choices. Question: {q} Choices: {choices} Your answer should be a capital letter representing your choice: A, B, C, or D. Don't generate any other text."
- 输出解析：extract_choice_letter（首字符或独立 ABCD）→ 与 Answer 比对
- 指标：准确率 = 答对数 / 总数
- 模态开关：--input_mode all|visual|audio（all = 视频+音频）
- 数据样例（qa_example.json）：
  {"Type": "AV Event Alignment", "Question": "Which audio statement accompanies the first appearance of the ... sign?", "Choice": ["A. ...", "B. ...", "C. ...", "D. ..."], "Answer": "C", "Explaination": "..."}

## 官方脚本形态（910C 上可参考）

- test_model/<模型>/testmodel.py：transformers PyTorch 本地跑（Qwen2.5-Omni/Qwen3-Omni/VideoLLaMA2/Ola 等）
  - Qwen3-Omni 版与 MiniCPM-o 4.5 结构最近（Qwen3-8B 基座），代码可直接参考
  - generation：thinker_max_new_tokens、thinker_do_sample=False（贪心）、return_audio=False（只要文本答案）
- test_model_api/：API 方式（gemini/gpt4o/deepseek），main_tester.py + test_config.py，支持 parallel 模式、重试、帧提取（SECONDS_PER_FRAME_GPT4O=2）

## 对比赛的意义

1. 官方在 910C 上测 MiniCPM-o 4.5 时，输入输出格式大概率与此一致（QA + 选项 + 首字母解析）
2. llama.cpp-omni 侧需要能跑"视频/音频输入 → 文本答案输出"：
   - 方式 A：omni-cli 视觉模式（视频帧）+ Whisper 音频 → 文本 QA（需验证 llm_debug 输出格式）
   - 方式 B：llama-omni-server HTTP API 多模态问答（与 Demo 链路同接口）
3. 4090 预跑可行性：可以先用 example_videos/（3 个示例视频）+ qa_example.json 跑 3-5 条，验证链路能出 ABCD 答案
   - 权重：vision/audio 模块 GGUF 已就位
   - 注意：llama.cpp-omni 的 Whisper ASR 模块对 30s 音频支持有限，Daily-Omni 音频是长段，需验证截断行为
4. TTS-Seed 与 Video-MME 类似：TTS-Seed 测语音生成质量（WER/SIM），Video-MME 测视频理解（MCQ）——具体脚本等官方 starter kit

## 待办

- [ ] 910C 上拉取 Daily-Omni 数据集（hf mirror 或 modelscope 版）
- [ ] 用 llama-omni-server API 预写 Daily-Omni 适配脚本（qa.json → 请求 → 解析 → 汇总）
- [ ] 4090 上先用 example_videos 验证链路
