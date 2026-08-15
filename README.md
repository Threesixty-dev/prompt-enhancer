# Prompt Enhancer

Prompt Enhancer is a local-first analytics and coaching tool for people and teams who use coding agents such as Codex and Claude Code. It turns consented session events into evidence-backed views of task outcomes, delivery flow, prompt clarity, verification habits, token use, rework, and longitudinal improvement.

The repository includes a runnable local vertical slice: a private SQLite store,
deterministic task discovery and review, immutable task and session analysis, an
authenticated loopback API, a React dashboard, and an experimental bounded Codex
App Server reader.
Synthetic data remains the development default. After explicit `local-history` consent
and an explicit index action, the local catalog retains pseudonymous identities and any
available minimized labels. A separate, selected action may read at most 25 task summaries
to fill missing project-folder basenames and explicit Codex task titles. Local manual
overrides never rename Codex. A separate one-session confirmation can read a bounded
text window into memory, apply the local redactor, compute twenty experimental prompt,
collaboration, observable-logic, and outcome-evidence fractions, and persist only
content-free values and versioned provenance. Project profiles combine compatible immutable session results by
ratio-of-sums; they never average percentages in the browser. Full paths, previews,
transcripts, credentials, and tool content are not persisted, and no analytics are sent
online.

An additional opt-in shadow pipeline can divide that approved redacted window into
at most eight contiguous chunks and run ten revision-pinned Hugging Face experts one
at a time. Four retrieval experts select bounded evidence, two rerank it, three NLI
experts and one structured-rubric expert vote, and only compatible known chunk
fractions are combined into a separate radar. Every model runs in an isolated child
process with CUDA-first and CPU fallback, then exits before the next model so its
weights are released. The database stores normalized content-free votes, aggregates,
provenance, and unload receipts; it never stores the chunk text. This ensemble is
deliberately marked uncalibrated and is not a product score or a substitute for a
representative human-labeled holdout.

## Phase 1 local quickstart

Python 3.11 or newer is required. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m prompt_enhancer init
python -m prompt_enhancer demo
python -m prompt_enhancer status
cd frontend
npm install
npm run build
cd ..
python -m pytest
python scripts\privacy_scan.py
python -m prompt_enhancer serve
```

The application state is created outside the repository by default. The repeatable `demo` command imports only fictional, deterministic metadata and makes no provider or model calls. `serve` binds to loopback and exposes authenticated, allowlisted queries plus narrow idempotent review and analysis commands. The health response, static dashboard files, and same-origin browser-session bootstrap are unauthenticated but contain no private metrics. Every `/v1/*` route requires either the private API token or an ephemeral HttpOnly browser cookie; browser mutations also require strict same-origin and CSRF checks.

The dashboard's development profile is synthetic and does not require the local API token:

```powershell
cd frontend
npm install
npm run test
npm run build
npx playwright install chromium
npm run test:e2e
npm run dev
```

The Vite development profile remains synthetic. After `npm run build`, `serve` hosts the production dashboard and API on one loopback origin. The browser code receives only an in-memory CSRF token and never reads or stores the persistent API token.

For explicit real-backend development with hot reload, start the backend on its
dedicated loopback development port, then run the opt-in Vite mode in another
terminal:

```powershell
$env:PROMPT_ENHANCER_PORT = "8766"
$env:PYTHONPATH = "src"
python -m prompt_enhancer serve

cd frontend
npm run dev:local -- --port 4174
```

This mode proxies only `/auth`, `/health`, and `/v1` to the fixed loopback
backend. Ordinary `npm run dev` stays synthetic. Granting source access,
indexing sessions, and starting a selected-session analysis remain separate
explicit actions in the UI.

The optional ten-model shadow ensemble needs the model extras and all ten
reviewed public snapshots prepared before the browser run. Preparation is an
explicit networked step over fictional test cases; the later selected-session
run is forced offline:

```powershell
python -m pip install -e ".[models]"
python scripts/evaluate_local_text_models.py --candidate all --device auto --smoke --download
python scripts/evaluate_specialist_screen.py --device auto --smoke --download
```

After those commands pass, open a Prompt Quality or Reasoning Quality session
page in the integrated app and choose **Run 10 models locally**. The operation
can take several minutes. It uses CUDA when available, otherwise CPU, and
executes one model process at a time rather than loading all weights together.

See [docs/phase-1.md](docs/phase-1.md) for the safety boundary, explicit Codex workflow, API behavior, and deferred features.

## Product direction

The core design is deliberately not a single “prompt score.” The dashboard will keep separate dimensions for:

- verified task outcome;
- time, token, and tool efficiency;
- prompt clarity, constraints, and testability;
- requirement-to-action-to-evidence traceability;
- rework, retries, compaction, and workflow bottlenecks;
- private coaching signals such as frustration or cognitive load;
- safety, privacy, and provenance.

Objective evidence such as tests, builds, CI, artifacts, and explicit user acceptance must outrank linguistic or LLM-generated judgments.

## Proposed integration model

- Codex: the implemented App Server adapter separates a state-only content-discarding index, selector-gated summary label enrichment, and selector-gated operational history. Summary mode uses `thread/read` with turns omitted, is capped at 25 current-snapshot IDs, and persists only missing minimized labels with provenance. All modes require `local-history` consent. Opt-in OpenTelemetry remains a future live source.
- Claude Code: use the Agent SDK's local session readers and opt-in OpenTelemetry or hooks. Direct JSONL parsing is a versioned fallback only.
  Do not register Claude display-label persistence until a schema-v6 migration
  provides provider-neutral, versioned provenance.
- Storage: SQLite as the initial source of truth, with a separate optional encrypted content vault. DuckDB/Parquet can be added later for larger analytical workloads.
- Analysis: deterministic metrics first, then small local Hugging Face models that pass an in-domain benchmark. The local Model Lab screens seven revision-pinned candidates in isolated one-at-a-time subprocesses with CUDA, Apple MPS, or CPU fallback. Current neural candidates remain evaluation-only; none is activated in product metrics. Remote LLM analysis is optional, redacted, previewed, and explicitly approved.
- Agent access: a read-only, allowlisted local MCP server can let an already-authenticated Codex or Claude session query aggregate metrics. Data returned through MCP enters that model's context and may leave the device.

The detailed proposal is in [docs/architecture.md](docs/architecture.md), the metric definitions are in [docs/metrics-catalog.md](docs/metrics-catalog.md), and the 131-publication research journal begins at [docs/research/research-journal.md](docs/research/research-journal.md). The dashboard-facing method stack and activation gates are summarized in [docs/research/prompt-agent-analytics-methods.md](docs/research/prompt-agent-analytics-methods.md).

## Synthetic cross-model challenge

The real offline session-link models have an explicit optional runtime and a
targeted preparation screen. It downloads only immutable reviewed public
artifacts, then closes the network before inference:

```powershell
python -m pip install -e ".[models]"
python scripts/evaluate_local_text_models.py --candidate session-link --device auto --smoke --download
```

This evaluates Qwen3 Embedding 0.6B and BGE reranker v2 M3 on fictional EN/PL
cases. It does not activate either model as a product metric; real-session
annotations and an adjudicated holdout remain required.

The fixed fictional EN/PL frontier packet can be exported without a provider
call:

```powershell
python scripts/cross_model_challenge.py export --variant all
```

It writes blinded prompts and strict response schemas below
`runtime/model-eval/cross-model-v1`. After a model produces a JSON response in
that same runtime directory, score one variant and its order stability locally:

```powershell
python scripts/cross_model_challenge.py score --model-id example-model-1 --variant order-a --response example-model-1.order-a.response.json
python scripts/cross_model_challenge.py stability --model-id example-model-1 --response-a example-model-1.order-a.response.json --response-b example-model-1.order-b.response.json
```

The scorer accepts only the checked-in fictional challenge and bounded runtime
response files. It reports retrieval, NLI, rubric, and order-stability measures
separately; it never creates an overall model score. See
[WP-18](docs/work-packages/wp-18-metric-validity-and-roi-constellation.md) for
the live synthetic results and the proposed cheap-first model constellation.

The dashboard also exposes a versioned nine-family metric opportunity map for
user value, quality-adjusted delivery, oversight, durability, artifact quality,
measurement trust, safety, recommendation effectiveness, and private ease.
Roadmap entries are explicitly partial, unmeasured, or opt-in and never create
placeholder values or an overall score. The evidence, post-processing, visual,
and activation contracts are defined in
[WP-19](docs/work-packages/wp-19-expressive-metric-system.md).

## Privacy promise

This repository must contain only synthetic examples. Never commit real prompts, transcripts, source snippets from private repositories, tool output, usernames, email addresses, hostnames, absolute home paths, account identifiers, access tokens, databases, model caches, or telemetry exports.

See [PRIVACY.md](PRIVACY.md), [SECURITY.md](SECURITY.md), and [CONTRIBUTING.md](CONTRIBUTING.md) before contributing.

## Architecture decision and remaining questions

The implementation architecture is recorded in
[ADR 0001](docs/adr/0001-modular-monolith-hexagonal-metric-graph.md): one local
modular monolith, ports and adapters at privileged or replaceable boundaries, and
an explicitly registered metric dependency graph. The dashboard target is a
React/TypeScript/Vite SPA followed by a constrained Tauri desktop shell.
The Codex read boundary and metric assumptions are recorded in
[ADR 0002](docs/adr/0002-codex-app-server-read-boundary.md).


Before expanding provider and content support, the maintainers still need to decide:

1. Which documented Claude Code interface and consent UX to implement.
2. Which two or three task types form the initial evaluation dataset.
3. Which operating systems form the first supported adapter matrix.
4. Which public license to use.

## Repository status

- Default branch: `main`
- Stage: synthetic vertical slice plus experimental Codex index/selected-history adapter and explicitly confirmed local Prompt Quality / observable-logic profiles; Claude ingestion and calibrated model scoring remain deferred
- License: not yet selected. Until a `LICENSE` file is added, no reuse license is granted by this repository.
