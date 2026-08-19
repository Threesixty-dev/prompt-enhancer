# ADR 0013: Local model runtimes and the model-judge lane

- Status: accepted (2026-08-19); runtime slice first, judge lane second
- Owner direction: run a strong local LLM on this machine (GPU where it fits,
  CPU or GPU/CPU split otherwise), use it to help produce and analyse metrics,
  and expose every installed model on the app's local API so a person can use
  it as a regular LLM for small tasks.

## Context

The repository already runs small local text models (transformers backends,
isolated snapshot loader) and keeps every byte of session content on the
machine. The model the owner named, `orcarouter/Qwen3.8-27B-Uncensored`, is
published in several formats; the MLX variant is Apple-Silicon-only, while the
author's GGUF variant runs through llama.cpp on Windows/NVIDIA. On the owner's
machine (RTX 3080 Ti Laptop, 16 GB VRAM, 32 GB RAM) a 27B model at 4-bit does
not fit in VRAM alone, so partial offload (GPU/CPU split) is the realistic
mode; that is exactly the device option the owner asked for.

## Decision

1. **Runtime = llama.cpp `llama-server`.** One subprocess per activated model,
   bound to loopback on a free port, started with the chosen device:
   `cpu` (no offload), `gpu` (all layers), `split` (an estimated number of
   layers that fits the free VRAM; the person can override). The binary is
   detected on PATH or configured (`PROMPT_ENHANCER_LLAMA_SERVER`); the app
   never downloads or executes a binary without an explicit, size-stated
   confirmation in the dashboard.
2. **Registry.** Installed models (alias, source repo/file or local path,
   format, size, sha256 when known, default device, context size) live in
   `local-models/registry.json` under the app home (registered in the private
   path inventory). Weights live under `local-models/weights/`. Downloads go
   through `huggingface_hub`, which uses the person's own Hugging Face login;
   the app never reads or stores the token, and every download is confirmed
   with its size first.
3. **Endpoints.** Under the authenticated local API: list, add, activate
   (device, gpu layers, context), deactivate, status, and an OpenAI-compatible
   `POST /v1/local-models/{alias}/chat/completions` that proxies to the model's
   loopback runtime. Nothing leaves the machine; the runtime port is never
   exposed beyond loopback; the app's token guards the proxy.
4. **Metrics use (model-judge lane, second slice).** The local model rates the
   redacted analysis window on the same three calibration questions and scale
   as the Calibration page (low / medium / high / cannot judge). Those are
   **model judgments**: stored separately (model id, prompt version, label),
   never merged into product metrics, compared with human ratings via the
   existing agreement math, and only ever promoted through the preregistered
   estimator activation gate. Objective evidence (ADR 0012) always outranks
   them.
5. **Scheduling.** Judge work runs in the single serial analysis lane after the
   P1 run, one model process at a time, so models never double-spawn; batching
   within one runtime is used where llama.cpp allows parallel slots.

## Consequences

- A person can keep several models installed and switch which one is active
  and on which device; only active models consume GPU/CPU memory.
- Chat responses from an uncensored model are the person's own local use; the
  app does not filter them, and they are never persisted by the app.
- The judge lane makes no metric "calibrated" by itself; the Calibration page
  ratings and the activation gate decide that.

## Addendum (2026-08-19): streaming and OpenAI-style base URLs

- The chat proxy honours `stream: true` by relaying the runtime's server-sent
  events unchanged, bounded to 16 MB per reply; a failure the runtime reports
  before streaming (for example a context overflow, HTTP 400) is returned as
  the same JSON error a non-streamed call would get.
- Every model is reachable under an OpenAI-style base URL:
  `/v1/local-models/{alias}/v1` (`GET /models`, `POST /chat/completions`), and
  one shared base URL `/v1/local-models/openai/v1` routes by the request's
  `model` field among running aliases. The app token may be sent as
  `Authorization: Bearer <token>` so unchanged OpenAI clients can use the local
  models; the aliases `openai`, `downloads` and `remote-files` are reserved.
- The Models page offers a chat box for running models (thinking disabled by
  default, conversation kept in the browser tab only, never persisted).

