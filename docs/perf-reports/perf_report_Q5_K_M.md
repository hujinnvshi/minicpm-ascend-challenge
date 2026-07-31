```
================================================================
MiniCPM-o 双工可行性报告
================================================================
LLM           : /data/minicpm-omni/weights/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q5_K_M.gguf
Vision backend: metal   use_tts: True   media_type: 2
n_threads     : -1   采样率: 24000Hz
进帧间隔(基准): 1000 ms

帧数: 36  (SPEAK 17 / LISTEN 19)

[1] LLM 判定延迟 (push -> LISTEN/SPEAK, ms_total)
    P50 133.5ms | P95 166.1ms | max 171.1ms | avg decode 138.0ms
    判据: P95(166.1ms) < 进帧间隔(1000ms)  => PASS

[匹配] SPEAK 轮 <-> 音频轮 (按时间戳，非下标对齐)
    SPEAK 轮: 2 | 音频轮: 2 | 匹配成功: 2

[2] 首响延迟
    e2e  = SPEAK 首帧 push -> 该轮首 wav（硬判据）
    tts  = SPEAK 首帧 t_done(LLM完成) -> 首 wav（仅展示）
    speak#0/audio#0: e2e 496ms | tts 329ms (push@5000 done@5168 wav@5497)
    speak#1/audio#1: e2e 410ms | tts 248ms (push@29000 done@29162 wav@29410)
    e2e P50 453ms | P95 492ms
    tts P50 288ms | P95 324ms
    判据: 首响 e2e P95 < 进帧间隔(1000ms) => PASS

[3] 音频 RTF
    TTS RTF = (末 wav - LLM t_done) / 音频时长  （硬判据，需 < 1.0）
    e2e RTF = (末 wav - 首帧 push) / 音频时长  （仅展示，含 LLM 等待）
    speak#0/audio#0: 音频 13.88s | TTS wall 13.07s RTF 0.94 | e2e wall 13.23s RTF 0.95
    speak#1/audio#1: 音频 2.64s | TTS wall 2.07s RTF 0.78 | e2e wall 2.23s RTF 0.85
    平均 TTS RTF: 0.86 | 平均 e2e RTF: 0.90
    判据: 平均 TTS RTF < 1.0 => PASS

[4] 单个 wav chunk 时长分布 (验证「一帧!=1s音频」)
    chunk 数: 17 | 总音频 16.52s
    时长 min 0.64s | P50 1.00s | max 1.04s
    轮末 (is_final) 时长: ['1.04s', '0.64s']
    说明: 满窗 chunk ≈1.0s，轮末 remainder 在 (0,1.0]s；单帧产出的音频量取决于该帧说了多少字。

================================================================
  [PASS] LLM 判定实时性 (P95<间隔)
  [PASS] 首响 e2e (<间隔)
  [PASS] TTS RTF (<1.0)
----------------------------------------------------------------
  最终判定: 该机器可支撑双工
================================================================
```
