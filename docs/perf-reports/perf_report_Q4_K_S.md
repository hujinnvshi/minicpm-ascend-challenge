```
================================================================
MiniCPM-o 双工可行性报告
================================================================
LLM           : /data/minicpm-omni/weights/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-Q4_K_S.gguf
Vision backend: metal   use_tts: True   media_type: 2
n_threads     : -1   采样率: 24000Hz
进帧间隔(基准): 1000 ms

帧数: 36  (SPEAK 15 / LISTEN 21)

[1] LLM 判定延迟 (push -> LISTEN/SPEAK, ms_total)
    P50 126.0ms | P95 153.5ms | max 160.0ms | avg decode 131.2ms
    判据: P95(153.5ms) < 进帧间隔(1000ms)  => PASS

[匹配] SPEAK 轮 <-> 音频轮 (按时间戳，非下标对齐)
    SPEAK 轮: 2 | 音频轮: 2 | 匹配成功: 2

[2] 首响延迟
    e2e  = SPEAK 首帧 push -> 该轮首 wav（硬判据）
    tts  = SPEAK 首帧 t_done(LLM完成) -> 首 wav（仅展示）
    speak#0/audio#0: e2e 521ms | tts 368ms (push@5000 done@5153 wav@5521)
    speak#1/audio#1: e2e 406ms | tts 246ms (push@30000 done@30160 wav@30406)
    e2e P50 463ms | P95 515ms
    tts P50 307ms | P95 362ms
    判据: 首响 e2e P95 < 进帧间隔(1000ms) => PASS

[3] 音频 RTF
    TTS RTF = (末 wav - LLM t_done) / 音频时长  （硬判据，需 < 1.0）
    e2e RTF = (末 wav - 首帧 push) / 音频时长  （仅展示，含 LLM 等待）
    speak#0/audio#0: 音频 12.28s | TTS wall 11.19s RTF 0.91 | e2e wall 11.34s RTF 0.92
    speak#1/audio#1: 音频 2.56s | TTS wall 2.06s RTF 0.80 | e2e wall 2.22s RTF 0.87
    平均 TTS RTF: 0.86 | 平均 e2e RTF: 0.90
    判据: 平均 TTS RTF < 1.0 => PASS

[4] 单个 wav chunk 时长分布 (验证「一帧!=1s音频」)
    chunk 数: 16 | 总音频 14.84s
    时长 min 0.44s | P50 1.00s | max 1.00s
    轮末 (is_final) 时长: ['0.44s', '0.56s']
    说明: 满窗 chunk ≈1.0s，轮末 remainder 在 (0,1.0]s；单帧产出的音频量取决于该帧说了多少字。

================================================================
  [PASS] LLM 判定实时性 (P95<间隔)
  [PASS] 首响 e2e (<间隔)
  [PASS] TTS RTF (<1.0)
----------------------------------------------------------------
  最终判定: 该机器可支撑双工
================================================================
```
