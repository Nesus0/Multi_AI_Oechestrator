# Lightweight local fallback

`nesus_ai` is intentionally an on-demand CLI. It does not need a resident daemon. The only optional background process is a tiny `llama.cpp` server managed by `launch.py` and `stop.py`.

## Why the local model stays limited

A Google Cloud Free Tier `e2-micro` VM has 1 GB of RAM and only a fractional shared CPU. A small local model can therefore be useful for standby work, but it should not be presented as a replacement for Codex, Claude or Gemini on non-trivial repository changes.

Recommended local responsibilities:

- provider-health interpretation;
- task classification;
- compact handoff generation;
- summarizing short logs or Git status;
- drafting a checklist while remote APIs are cooling down;
- tiny deterministic text transformations.

Responsibilities to leave to remote coding agents:

- architecture changes;
- debugging across many files;
- security review;
- autonomous tool loops;
- broad refactoring;
- claiming that tests passed without running them.

## Recommended runtime

Use `llama.cpp` because it is a single native runtime and exposes OpenAI-compatible endpoints without requiring a Python inference stack.

For an `e2-micro`, start conservatively:

```text
quantization: Q4
model size: below 1B parameters
context: 1024 tokens
threads: 1
parallel slots: 1
swap: 1–2 GB recommended
```

Qwen3 0.6B is a reasonable multilingual standby candidate. Its official model card lists 0.6B parameters and a 32K theoretical context, but the VM must use a much smaller runtime context to avoid memory pressure. The official Q8 GGUF is approximately 639 MB, which is already tight once Linux, llama.cpp and KV cache are included; prefer a compatible Q4 GGUF file on a 1 GB VM.

Gemma 4 E2B is not recommended on this VM: Google's current memory table estimates about 2.9 GB for regular Q4_0, while even the text-only mobile format is approximately 0.84 GB before normal OS and context overhead.

## Configuration

Install the project, then edit:

```bash
nano ~/.config/nesus-ai/local.env
```

Example with a local GGUF:

```bash
NESUS_LOCAL_LLM_ENABLED=1
NESUS_LOCAL_LLM_BIN=/usr/local/bin/llama-server
NESUS_LOCAL_MODEL_FILE=/srv/models/qwen3-0.6b-q4.gguf
NESUS_LOCAL_LLM_HOST=127.0.0.1
NESUS_LOCAL_LLM_PORT=8080
NESUS_LOCAL_LLM_CONTEXT=1024
NESUS_LOCAL_LLM_THREADS=1
```

The launcher never downloads a model automatically. This prevents unexpected disk use, network use or an unsuitable quantization from being pulled onto the VM.

## Start, inspect and stop

From the repository:

```bash
python3 launch.py
python3 launch.py --status
python3 stop.py
```

After installation:

```bash
nesus-ai-launch
nesus-ai-launch --status
nesus-ai-stop
```

Logs and PID state:

```text
~/.local/state/nesus-ai/local-llm.log
~/.local/state/nesus-ai/services.json
```

The server listens on `127.0.0.1` by default and is not exposed publicly.

## Current scope

The launcher provides the local inference foundation only. The micro-model is deliberately not enabled as a full write-capable agent by default. A future lightweight `standby` adapter can call the local OpenAI-compatible endpoint to produce a compact handoff while the remote providers are unavailable, without granting it broad shell or filesystem authority.

## Primary references

- Google Cloud Free Tier: https://cloud.google.com/free/docs/free-cloud-features
- Google Compute Engine E2 machine types: https://cloud.google.com/compute/docs/general-purpose-machines
- llama.cpp server: https://github.com/ggml-org/llama.cpp/tree/master/tools/server
- Qwen3 0.6B: https://huggingface.co/Qwen/Qwen3-0.6B
- Qwen3 0.6B GGUF: https://huggingface.co/Qwen/Qwen3-0.6B-GGUF
- Gemma 4 overview and memory requirements: https://ai.google.dev/gemma/docs/core
