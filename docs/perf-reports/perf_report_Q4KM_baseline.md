```
================================================================
MiniCPM-o 双工可行性报告
================================================================
LLM           : /data/minicpm-omni/weights/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_M.gguf
Vision backend: metal   use_tts: True   media_type: 2
n_threads     : -1   采样率: 24000Hz
进帧间隔(基准): 1000 ms

帧数: 36  (SPEAK 12 / LISTEN 24)

[1] LLM 判定延迟 (push -> LISTEN/SPEAK, ms_total)
    P50 144.7ms | P95 214.2ms | max 218.2ms | avg decode 152.8ms
    判据: P95(214.2ms) < 进帧间隔(1000ms)  => PASS

[匹配] SPEAK 轮 <-> 音频轮 (按时间戳，非下标对齐)
    SPEAK 轮: 4 | 音频轮: 4 | 匹配成功: 4

[2] 首响延迟
    e2e  = SPEAK 首帧 push -> 该轮首 wav（硬判据）
    tts  = SPEAK 首帧 t_done(LLM完成) -> 首 wav（仅展示）
    speak#0/audio#0: e2e 523ms | tts 304ms (push@3000 done@3218 wav@3523)
    speak#1/audio#1: e2e 329ms | tts 193ms (push@8000 done@8136 wav@8329)
    speak#2/audio#2: e2e 410ms | tts 232ms (push@15000 done@15178 wav@15410)
    speak#3/audio#3: e2e 425ms | tts 251ms (push@30000 done@30174 wav@30425)
    e2e P50 417ms | P95 508ms
    tts P50 242ms | P95 296ms
    判据: 首响 e2e P95 < 进帧间隔(1000ms) => PASS

[3] 音频 RTF
    TTS RTF = (末 wav - LLM t_done) / 音频时长  （硬判据，需 < 1.0）
    e2e RTF = (末 wav - 首帧 push) / 音频时长  （仅展示，含 LLM 等待）
    speak#0/audio#0: 音频 2.60s | TTS wall 2.09s RTF 0.80 | e2e wall 2.31s RTF 0.89
    speak#1/audio#1: 音频 3.24s | TTS wall 2.32s RTF 0.71 | e2e wall 2.45s RTF 0.76
    speak#2/audio#2: 音频 3.28s | TTS wall 2.15s RTF 0.66 | e2e wall 2.33s RTF 0.71
    speak#3/audio#3: 音频 2.80s | TTS wall 2.11s RTF 0.75 | e2e wall 2.28s RTF 0.82
    平均 TTS RTF: 0.73 | 平均 e2e RTF: 0.79
    判据: 平均 TTS RTF < 1.0 => PASS

[4] 单个 wav chunk 时长分布 (验证「一帧!=1s音频」)
    chunk 数: 12 | 总音频 11.92s
    时长 min 0.76s | P50 1.00s | max 1.28s
    轮末 (is_final) 时长: ['0.76s', '1.24s', '1.28s', '0.80s']
    说明: 满窗 chunk ≈1.0s，轮末 remainder 在 (0,1.0]s；单帧产出的音频量取决于该帧说了多少字。

================================================================
  [PASS] LLM 判定实时性 (P95<间隔)
  [PASS] 首响 e2e (<间隔)
  [PASS] TTS RTF (<1.0)
----------------------------------------------------------------
  最终判定: 该机器可支撑双工
================================================================
```
