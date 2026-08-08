# Work packages

Work packages turn the architecture in
[ADR 0001](../adr/0001-modular-monolith-hexagonal-metric-graph.md) into small,
verifiable product increments. A package is complete only when its implementation,
contract tests, privacy checks, and documentation are complete.

The primary milestone is a synthetic task-discovery vertical slice:

```text
synthetic sessions -> task candidate -> user decision -> task revision
                   -> metric pack -> analysis run -> typed API -> dashboard
```

WP-07A is a narrow, active exception for the documented Codex App Server. It
authorizes provider access only when the user explicitly grants `local-history`
consent and then invokes an explicit index, label-enrichment, or analysis command.
Installation, server startup, dashboard page load, tests, and the synthetic demo
must never access real Codex or Claude state.

| ID | Work package | Status | Depends on |
|---|---|---|---|
| WP-01 | Task and immutable analysis storage | Complete (synthetic) | ADR 0001 |
| WP-02 | Deterministic task discovery and review decisions | Complete (synthetic) | WP-01 contracts |
| WP-03 | Typed task/discovery API | Complete | WP-01, WP-02 |
| WP-04 | React Discovery Inbox | Complete (synthetic preview) | WP-03 |
| WP-05 | Constrained desktop host and local auth bridge | Partial (integrated loopback bridge; Tauri packaging planned) | WP-04 |
| WP-06 | Privacy Tier 2 and encrypted content vault | Deferred | WP-05 security review |
| WP-07 | Documented Codex and Claude read adapters | Deferred | WP-06 review |
| WP-07A | Bounded Codex local-history reader | Active (dashboard-integrated labels and metrics) | ADR 0002, WP-01 privacy contracts |
| WP-08 | Local model evaluation and calibration | Deferred | reviewable task labels |

## WP-01: Task and immutable analysis storage

Deliverables:

- numbered SQLite migrations;
- focused repository contracts rather than additional arbitrary SQL access;
- task candidates, candidate-session evidence, decisions, and task revisions;
- immutable analysis runs with versioned result provenance;
- current-result queries implemented as projections, not destructive replacement;
- deletion APIs that can remove a synthetic task and all derived records.

Acceptance checks:

- persistent identities and selectors are 64-character pseudonyms; display labels never act as identity;
- no transcript, full-path, account, or provider-credential columns exist;
- the only plaintext provider-derived columns are bounded, consented private project/session display labels;
- an analysis rerun does not overwrite an earlier run;
- migration checksums are immutable and upgrade from schema version 1 is tested;
- repository tests use reserved synthetic values only.

## WP-02: Deterministic task discovery

Deliverables:

- typed `DiscoverySignal`, `TaskCandidate`, `TaskDecision`, and `TaskRevision`
  contracts;
- deterministic metadata-only discovery strategies;
- evidence explaining every proposed grouping;
- accept, reject, merge, and split decision semantics;
- stable candidate generation without assuming that one session equals one task.

Acceptance checks:

- identical safe inputs produce identical candidates and evidence;
- missing data remains unknown and cannot become negative evidence;
- an algorithm revision creates new candidates rather than changing a human
  decision;
- no discovery strategy can read provider state, content, or the network.

## WP-03: Typed task/discovery API

Deliverables:

- strict Pydantic request and response DTOs;
- discovery inbox, task detail, evidence, metric, and analysis-run queries;
- narrow decision commands for accept, reject, merge, and split;
- optimistic revision checks for user decisions;
- build-time OpenAPI export while runtime API documentation remains disabled.

Acceptance checks:

- loopback, authentication, Host, and Origin protections remain mandatory;
- there is no arbitrary CRUD, SQL, provider mutation, filesystem, or transcript
  endpoint;
- command retries are idempotent;
- malformed or stale revisions fail without changing state.

## WP-04: React Discovery Inbox

Deliverables:

- React, TypeScript, and Vite application shell;
- generated API types and a single transport adapter;
- discovery inbox and synthetic task-detail route;
- shared design tokens and semantic metric/evidence components;
- browser platform adapter, with Tauri deferred;
- Vitest, component, accessibility, and Playwright smoke tests.

Acceptance checks:

- the frontend contains no secrets, raw paths, transcript fixtures, or remote
  analytics;
- unexpected network origins are blocked in tests;
- unknown values, coverage, evidence, and provenance are visible;
- an ordinary backend metric renders without a feature-specific UI change.

## WP-05: Constrained desktop host and local auth bridge (partial)

Deliverables:

- an integrated loopback host serving only the built dashboard and local API;
- a same-origin, HttpOnly, SameSite authentication bridge that never exposes the
  API token to browser JavaScript, URLs, logs, or browser storage;
- production Content Security Policy and capability allowlists;
- synthetic integration tests against the same-origin bridge and persistent
  SQLite profile; and
- a future narrow Tauri packaging host without shell, arbitrary filesystem, or
  raw provider-state capabilities.

Acceptance checks:

- the production dashboard can review and analyze synthetic tasks after restart;
- the local bearer token is absent from JavaScript, DOM, URL, storage, and logs;
- non-loopback hosts and unexpected origins remain blocked;
- neither the integrated host nor future desktop wrapper exposes an unrestricted command, file, network, or SQL bridge;
- package signing and updater behavior are explicitly deferred or threat-modeled
  before distribution.

## WP-07A: Bounded Codex local-history reader

This package is intentionally narrower than WP-07. It covers only the documented
local Codex App Server and persists no transcript text. Claude ingestion, raw
cache parsing, model-based content analysis, and unattended provider access stay
deferred.

Deliverables:

- one revocable `local-history` consent scope, recorded as content-bearing source
  access because `thread/list` can contain preview plaintext;
- content-minimizing list and summary DTOs that discard preview, turns, account,
  Git, and all other non-label fields;
- three capability-gated adapter modes: state-only index, at-most-25 selected
  summary reads with `includeTurns: false`, and selected operational reads with
  `includeTurns: true`;
- a separate label-enrichment application service and repository port that bind
  observations to already-indexed safe identities and persist extractor, adapter,
  provider, and source-schema provenance;
- a local manual-label layer with optimistic revisions and precedence over
  provider observations, without any provider rename call;
- fixed read-only RPC allowlists, resource limits, deterministic structural
  metrics, and sanitized cleanup; and
- dashboard and architecture documentation that do not describe list access as
  metadata-only authorization.

Acceptance checks:

- denied consent and construction cause no client or subprocess access;
- index mode forces `useStateDbOnly: true` and never emits `thread/read`;
- label and operational modes require safe persisted selectors before access;
- label mode reads only current-snapshot IDs, rejects non-empty turns, and is
  capped at 25 unique reads;
- tests use only fictional wire responses and leakage canaries;
- preview text, full paths, raw provider IDs, and content canaries never enter
  SQLite, logs, errors, or fixtures;
- label enrichment cannot mutate identity, overwrite a visible manual override,
  or trigger metric recomputation;
- duplicate or renamed display labels never change grouping or selection identity; and
- live compatibility is claimed only after an explicit local user exercise whose
  response is never copied into the repository.

## Completed milestone boundary

WP-01 through WP-04 are complete for fictional metadata. The backend integration
tests exercise persistence across ingestion, discovery, review, analysis, and
query boundaries. The dashboard exercises the same typed contract with an
in-memory synthetic transport, including accept, reject, merge, split, and
explicit analysis creation.

The production HTTP transport bootstraps an ephemeral same-origin browser session
without exposing the persistent API token to JavaScript or storage. The
integrated dashboard can query the persistent local API. This bridge authorizes
no provider access by itself: WP-07A remains consent-gated and requires a separate
explicit index, label-enrichment, or analysis action. Tauri packaging remains a future distribution
step rather than a prerequisite for the loopback browser workflow.

## Exit condition for the active milestone

The synthetic milestone is complete when the UI flow and persistent backend flow
satisfy the same generated contract through the integrated loopback bridge, with
all privacy, unit, integration, build, and browser suites passing. A later desktop
package must preserve the same authentication and capability boundaries.
