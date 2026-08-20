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


## Addendum (2026-08-20): download provenance and the licence admission policy

The first-party Hugging Face path used to discover a mutable repository, download
without a revision, accept any size within a percent, and register no digest,
revision or licence. It now works only against an identity the server resolved
for itself.

- **Discovery pins a commit.** `GET /v1/local-models/remote-files` asks
  `HfApi.model_info` twice: once to learn which commit the repository points at,
  then again addressed to that 40-hex commit oid with `files_metadata=True`, so the
  per-file size, the expected `lfs.sha256` and the repository licence all come from
  the exact revision a download would fetch. A repository that will not name a
  commit oid, or that answers the commit lookup with a different commit, returns a
  fixed content-free unavailable state; a branch name such as `main` or `latest` is
  never reported as pinned. Files without an exact size or an expected sha256 are
  listed as ineligible with a closed reason code, never guessed at.
- **Downloads are bound to that identity, not to the caller.** `POST
  /v1/local-models/downloads` carries the revision, digest, licence and byte count
  the person confirmed in the browser. The service re-resolves the repository and
  refuses unless its own answer matches the confirmation exactly, so substituting a
  repository, file, revision, digest, size or licence is refused, and a repository
  that moved between browsing and confirming is refused rather than silently
  fetched. `hf_hub_download` is called with the commit oid and `repo_type="model"`;
  no repository code is fetched, nothing is unpickled and `trust_remote_code` is
  never involved. Afterwards the file must be a regular non-symlink file inside the
  weights folder, start with the GGUF magic, have exactly the published byte count,
  and hash to the published digest under a constant-time comparison. Any failure
  deletes the file, registers nothing, and reports one closed code; Hub exception
  text is never read or returned.
- **The record carries the provenance.** `LocalModelRecord` gains
  `source_revision`, `source_license`, `source_license_policy` and
  `provenance_verified` alongside the existing `sha256`. Manually registered files,
  folder scans and registries written before this change stay readable and report
  provenance as unavailable; nothing is back-filled or inferred. A download's
  identity includes the commit and the digest, so two revisions of the same file
  can never alias to one download.
- **Repository admission policy (`local-model-license-policy.v1`).** A frozen
  allow-list of licence identifiers this repository is willing to fetch
  automatically, a frozen refuse-list of identifiers reviewed and rejected
  (bespoke community terms, non-commercial and no-derivative clauses, and the Hub's
  `other`/`unknown` placeholders), and everything else treated as unreviewed. Only
  `allowed` permits a download. **Limits:** this is an operational gate for this
  app's downloader, not a legal conclusion. It does not interpret licence text, does
  not see a repository's own additional conditions, says nothing about how model
  output may be used, and can be wrong about a repository that mislabels itself.
  Anything it does not admit is fetched by hand or not at all; gated repositories
  still require the person's own accepted terms and their own Hugging Face login,
  which this app never reads.
- **The Models page shows it.** The revision, licence with its admission outcome,
  the policy version, the exact byte count and the sha256 are on screen before the
  confirmation dialog, which repeats all of them. The download button is disabled
  and labelled "Download unavailable" whenever eligibility is false. The
  recommended list only looks a repository up; nothing downloads from it, and there
  is no automatic "latest model" download anywhere.
