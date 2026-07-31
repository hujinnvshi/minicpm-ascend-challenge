```
================================================================
MiniCPM-o 双工可行性报告
================================================================
LLM           : /data/minicpm-omni/weights/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q6_K.gguf
Vision backend: metal   use_tts: True   media_type: 2
n_threads     : -1   采样率: 24000Hz
进帧间隔(基准): 1000 ms

帧数: 36  (SPEAK 10 / LISTEN 26)

[1] LLM 判定延迟 (push -> LISTEN/SPEAK, ms_total)
    P50 127.9ms | P95 160.2ms | max 188.6ms | avg decode 133.0ms
    判据: P95(160.2ms) < 进帧间隔(1000ms)  => PASS

[匹配] SPEAK 轮 <-> 音频轮 (按时间戳，非下标对齐)
    SPEAK 轮: 4 | 音频轮: 4 | 匹配成功: 4

[2] 首响延迟
    e2e  = SPEAK 首帧 push -> 该轮首 wav（硬判据）
    tts  = SPEAK 首帧 t_done(LLM完成) -> 首 wav（仅展示）
    speak#0/audio#0: e2e 519ms | tts 362ms (push@5000 done@5157 wav@5519)
    speak#1/audio#1: e2e 363ms | tts 217ms (push@10000 done@10146 wav@10363)
    speak#2/audio#2: e2e 429ms | tts 240ms (push@17000 done@17189 wav@17429)
    speak#3/audio#3: e2e 423ms | tts 264ms (push@30000 done@30159 wav@30423)
    e2e P50 426ms | P95 505ms
    tts P50 252ms | P95 347ms
    判据: 首响 e2e P95 < 进帧间隔(1000ms) => PASS

[3] 音频 RTF
    TTS RTF = (末 wav - LLM t_done) / 音频时长  （硬判据，需 < 1.0）
    e2e RTF = (末 wav - 首帧 push) / 音频时长  （仅展示，含 LLM 等待）
    speak#0/audio#0: 音频 2.44s | TTS wall 2.08s RTF 0.85 | e2e wall 2.24s RTF 0.92
    speak#1/audio#1: 音频 2.60s | TTS wall 2.13s RTF 0.82 | e2e wall 2.28s RTF 0.88
    speak#2/audio#2: 音频 1.80s | TTS wall 1.07s RTF 0.59 | e2e wall 1.26s RTF 0.70
    speak#3/audio#3: 音频 1.44s | TTS wall 1.05s RTF 0.73 | e2e wall 1.21s RTF 0.84
    平均 TTS RTF: 0.75 | 平均 e2e RTF: 0.83
    判据: 平均 TTS RTF < 1.0 => PASS

[4] 单个 wav chunk 时长分布 (验证「一帧!=1s音频」)
    chunk 数: 10 | 总音频 8.28s
    时长 min 0.44s | P50 0.92s | max 1.00s
    轮末 (is_final) 时长: ['0.60s', '0.60s', '0.80s', '0.44s']
    说明: 满窗 chunk ≈1.0s，轮末 remainder 在 (0,1.0]s；单帧产出的音频量取决于该帧说了多少字。

================================================================
  [PASS] LLM 判定实时性 (P95<间隔)
  [PASS] 首响 e2e (<间隔)
  [PASS] TTS RTF (<1.0)
----------------------------------------------------------------
  最终判定: 该机器可支撑双工
================================================================
```
