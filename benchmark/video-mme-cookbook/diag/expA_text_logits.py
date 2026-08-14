#!/usr/bin/env python3
"""实验A: 纯文本 prompt(无图)C++ eval-cli 首 token top5 dump。
与 HF(trackb_empty_margin.py 文本版)同 prompt 对比 → LLM kernel 数值是否干净。
"""
import sys, os, json, subprocess, time
REPO = "/workspace/user_data/temp_project/minicpm-ascend-challenge"
os.environ.setdefault("LLAMA_CLI_BIN", f"{REPO}/code/llama.cpp-omni/build-cann/bin/llama-omni-eval-cli")

PROMPT = ("Carefully read the following question and select the letter corresponding to the correct answer."
          "Highlight the applicable choices without giving explanations.\n"
          "How does the girl feel in this video?\nOptions:\n"
          "A. Scared.\nB. Peaceful.\nC. Relaxed.\nD. Anxious.")

env = dict(os.environ)  # 外部已设 OMNI_TEXT_CHAT_SYS=1 OMNI_DEBUG_TOPK=1
log = open("/tmp/expA_cpp.log", "w")
cli = subprocess.Popen(
    [env["LLAMA_CLI_BIN"], "-m", "/workspace/shared_assets/models/OpenBMB/MiniCPM-o-4_5-gguf/MiniCPM-o-4_5-F16.gguf",
     "-c", "40960", "-ngl", "999", "--max-slice-nums", "0", "--n-predict", "100",
     "--temp", "0.0", "--top-p", "0.8", "--top-k", "100", "--repeat-penalty", "1.02", "--seed", "42"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, env=env, text=True, bufsize=1)
for line in cli.stdout:
    if '"ready"' in line: break
print("[cli ready]", flush=True)
cli.stdin.write(json.dumps({"type": "infer", "id": "textA", "frames": [], "prompt": PROMPT,
                            "max_slice_nums": 0, "n_predict": 100}) + "\n")
cli.stdin.flush()
for line in cli.stdout:
    if '"result"' in line:
        r = json.loads(line)
        print(f"response={r.get('response')!r}", flush=True)
        break
try:
    cli.stdin.write('{"type":"quit"}\n'); cli.stdin.flush(); cli.wait(timeout=30)
except Exception: cli.kill()
print("stderr log: /tmp/expA_cpp.log", flush=True)
