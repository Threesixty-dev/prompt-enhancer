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

An additional opt-in local pipeline projects all twenty metric contracts into a
second, explicitly experimental layer. It first builds owned task, collaboration,
reasoning, and outcome-evidence observations so physical chunks never create extra
denominators. Three pinned multilingual NLI encoders form the EN/PL live baseline.
The pinned English long-context challengers remain research-only until their
three-state factor and resource gates pass. A 4-bit Qwen 4B judge is loaded only
for bounded disagreement or manual deep analysis.
Models run one at a time in isolated child processes under a 6,144 MiB VRAM and
8,192 MiB RSS ceiling. A failed optional model cannot erase deterministic metrics.
Only content-free factor summaries, distribution quantiles, provenance, and resource
receipts are stored. Raw softmax values are never presented as confidence: until a
metric passes its own held-out calibration gate the UI calls its band an
**Experimental model range**.

One selected Codex session can also be placed under an explicit continuous local
watch. The watch checks the selected redacted snapshot on a bounded cadence, reuses
an exact unchanged sealed run before inference, and recomputes canonical focus-request
and dependency-bearing whole-window conversation observations when the input changes, then
publishes a new immutable content-free receipt. The radar's solid values come
from the reviewed deterministic coaching contracts with their exact typed
numerators, denominators, message coverage, and missing-value states. Informative
indigo median markers plus per-axis central 50% and 90% whiskers show the separate
experimental model projection; weak ranges are withheld. Models cannot veto or replace measured evidence, and objective
receipts alone can create a solid verified-outcome value. Codex activity time
is reduced to a keyed revision rather than persisted as a provider timestamp. A
fixed-axis radar keeps Unknown and Abstained visible instead of plotting them as
zero. A displayed `0%` therefore means an eligible typed denominator really had
zero positive observations; `—` means the value was not measurable. The live
model path is a gated external mixture of specialists, not a native MoE, not an
average of arbitrary scores, and not yet a calibrated estimate of truth.
NLI neutrality is treated as uncertainty, never as temporal pending evidence;
non-immediate collaboration ranges are withheld until a typed lifecycle proves
that their observation horizon is closed.

The dashboard and floating window consume one canonical durable watch head, so
Analyze, Cancel, stage status, advice, history, and snapshot identity no longer
come from competing UI paths. Content-free attempt/stage receipts survive retry
and partial optional-model failure, and an immutable semantic-unit sidecar prevents
stable provider message IDs from hiding changed content. The current source scope
is still the newest 100 messages / 100,000 redacted characters rather than proven
full-session history; immediate subprocess-tree cancellation and calibrated metric
truth remain future gates.

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

To capture your own Claude Code sessions, grant the separate hook-capture consent, then paste the printed hooks fragment into your Claude Code `settings.json` yourself - the application never writes to that file:

```powershell
python -m prompt_enhancer claude-consent-grant local-history
python -m prompt_enhancer claude-hooks-config
```

From then on each Claude Code lifecycle event invokes `python -m prompt_enhancer claude-hook`, which records only content-free metadata (pseudonymous session and project identity, event kind, tool category, timing) and is silent and harmless when consent is off or the store is absent. Sessions that started before the hook was installed are not read. Index captured sessions from the dashboard's Data source page or the `/v1/local-sources/claude-code/index` route.

For tokens, cost, and model per request, also point Claude Code's documented telemetry at the app's loopback receiver. Print the environment variables and set them where you launch Claude Code (the local server must be running to receive exports):

```powershell
python -m prompt_enhancer claude-otel-config
```

Only `api_request` usage and the documented session counters are recorded; account, organization, user, prompt, tool-parameter, and error fields are never read, and a missing export batch is a gap, never a zero.

Analysis is automatic once a source is consented: every indexed project receives a standing local automation grant, and the single serial analysis lane scores new and changed sessions from Codex and Claude Code alike - the Claude rubric metrics read your own transcript files through the same redacting text source ([ADR 0011](docs/adr/0011-owner-authorized-session-reader.md)). Revoking a source's consent revokes its grants.

To read your own sessions inside the dashboard - for example while rating them for calibration - start the server with `PROMPT_ENHANCER_SESSION_READER=enabled` ([ADR 0011](docs/adr/0011-owner-authorized-session-reader.md)). Codex sessions are read through the documented app-server; Claude Code sessions are read from your own transcript files, on demand, bounded, and never persisted. The `raw_transcripts` capability reports `true` only while this is on.

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

The optional predictive layer needs the model extras and the reviewed public
snapshots prepared before the browser run. Preparation is an explicit networked
step over synthetic test cases; selected-session inference is then forced offline:

```powershell
python -m pip install -e ".[models]"
python scripts/evaluate_local_text_models.py --candidate all --device auto --smoke --download
python scripts/evaluate_specialist_screen.py --device auto --smoke --download
```

After those commands pass, open a Prompt Quality or Reasoning Quality session
page in the integrated app and choose **Analyze metric ranges**. The first cold pass
can take about a minute on the reference machine because model processes load
serially; the p95 latency targets in the design document remain promotion gates,
not achieved claims. CUDA is used when available, small-model OOM retries once on
CPU, and the deep judge is optional. The historical ten-stage committee receipts
remain readable but that committee is no longer executed for live updates.

To keep the selected session updating, choose **Watch this session** on that
page. Only one session can hold the continuous serial model lane. An optional
frameless, minimizable, always-on-top Windows window uses custom React chrome to
display the latest fixed-axis radar and model progress without putting a session
identifier or API token in its URL or exposing a general-purpose native bridge.
Its compact scope bar switches among the newest indexed projects and
sessions and persists an exact newest-message window of 10, 25, 50, or 100
messages. The date control filters the indexed session catalog; it is not an
inside-session date cutoff because Codex does not yet expose complete normalized
timestamps for every admitted message. Changed sealed publications form a
bounded radar trajectory; unchanged polls do not create fake points, and
incomparable scope changes are never overlaid as if they were movement:

```powershell
python -m pip install -e ".[desktop]"
prompt-enhancer-desktop
```

The mini-window also has an explicit **Analyze now** action. While work is live,
that action becomes **Restart analysis**, which atomically revokes a dead or
unwanted lease, retains the last sealed radar, and queues a fresh run. Normal
crash recovery uses a five-minute renewable lease; active child inference
heartbeats keep that lease alive.

`prompt-enhancer-desktop` is a Windows GUI entry point: it opens only the React
window and does not create or retain a PowerShell/CMD console. It attaches only
to the authenticated loopback service on the configured port, or starts and
owns that service when the port is free. Before it renders anything it proves
the listener's identity with a fresh random challenge (`/auth/desktop-identity`):
only a service that already holds the same local token can return the
exact-socket-origin-bound keyed answer. The launcher resolves `localhost` to
separate numeric IPv4/IPv6 candidates before probing, so a port squatter never
receives the persistent token and cannot replay or relay a captured answer to
a genuine instance on another loopback address or port. Closing the window
stops only a server instance that the window started itself. `python -m
prompt_enhancer desktop` remains available as a terminal-oriented diagnostic
command.

See [the live metric radar pipeline](docs/live-metric-radar-pipeline.md) for all
twenty contracts, zero-versus-missing semantics, model routing, distribution and
trajectory contracts, resource ceilings, and the remaining calibration gates.

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
- Claude Code: two channels under one `claude_code` consent grant. The **transcript adapter** ([ADR 0011](docs/adr/0011-owner-authorized-session-reader.md)) is the primary source: it indexes your whole Claude Code history from your own transcript files - provider timestamps, per-response tokens, tool calls and errors, project, title - read-only and bounded. **Hooks** ([ADR 0010](docs/adr/0010-claude-code-hook-capture-boundary.md)) are the live signal and the only source for a session that has no transcript; `prompt-enhancer claude-hook` minimizes each payload in-process and keeps no tool input or output. Where a transcript exists it is the single source of record, so nothing is counted twice. Opt-in OpenTelemetry supplies per-request tokens, cost, model, and provider version through a loopback OTLP receiver that reads eleven allowlisted attributes and drops account, organization, user, prompt, and error fields. Direct JSONL parsing remains a rejected fallback.
  Claude display labels arrive with the hook as a bounded basename; persisting them through the migration-5 label tables still requires a provider-neutral migration.
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

1. Whether to add opt-in OpenTelemetry token counters beside the hook capture, and which consent UX presents both.
2. Which two or three task types form the initial evaluation dataset.
3. Which operating systems form the first supported adapter matrix.
4. Which public license to use.

## Repository status

- Default branch: `main`
- Stage: synthetic vertical slice plus experimental Codex index/selected-history adapter, hook-captured Claude Code sessions, and explicitly confirmed local Prompt Quality / observable-logic profiles; calibrated model scoring remains deferred
- License: not yet selected. Until a `LICENSE` file is added, no reuse license is granted by this repository.
