# Prompt Enhancer

Prompt Enhancer is a local-first analytics and coaching tool for people and teams who use coding agents such as Codex and Claude Code. It turns consented session events into evidence-backed views of task outcomes, delivery flow, prompt clarity, verification habits, token use, rework, and longitudinal improvement.

The repository includes a runnable local vertical slice: a private SQLite store,
deterministic task discovery and review, immutable task analysis, an authenticated
loopback API, a React dashboard, and an experimental bounded Codex App Server reader.
Synthetic data remains the development default. After explicit `local-history` consent
and an explicit index action, the local catalog retains pseudonymous identities and any
available minimized labels. A separate, selected action may read at most 25 task summaries
to fill missing project-folder basenames and explicit Codex task titles. Local manual
overrides never rename Codex. Full paths, previews, transcripts, credentials, and tool
content are discarded, and no analytics are sent online.

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
- Analysis: deterministic metrics first, then small local Hugging Face models that pass an in-domain benchmark. Remote LLM analysis is optional, redacted, previewed, and explicitly approved.
- Agent access: a read-only, allowlisted local MCP server can let an already-authenticated Codex or Claude session query aggregate metrics. Data returned through MCP enters that model's context and may leave the device.

The detailed proposal is in [docs/architecture.md](docs/architecture.md), the metric definitions are in [docs/metrics-catalog.md](docs/metrics-catalog.md), and the 131-publication research journal begins at [docs/research/research-journal.md](docs/research/research-journal.md).

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
- Stage: synthetic vertical slice plus experimental Codex content-discarding index/selected-history adapter; Claude and content analytics deferred
- License: not yet selected. Until a `LICENSE` file is added, no reuse license is granted by this repository.
