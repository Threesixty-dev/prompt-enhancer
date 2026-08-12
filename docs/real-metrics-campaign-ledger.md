# Real-metrics campaign ledger

This ledger records implementation evidence and release blockers. A completed
engineering check is not a claim that a metric or estimator is calibrated.
Private sessions, paths, prompts, model responses, credentials, caches, and
local runtime artifacts must never be added here.

## Campaign controls

- Branch: `codex/real-metrics-campaign`
- Merge policy: push coherent green commits; do not merge automatically.
- Data policy: synthetic fixtures for tests and review packets only.
- Review-loop limit: at most two critique/fix loops per phase.
- Phase order: baseline, P0, P1, P2, then optional P3 and P4.

## Phase status

| Phase | Status | Current scope | Acceptance gate | Open blockers |
|---|---|---|---|---|
| Baseline | Complete | Preserve and classify the inherited backend, frontend, model, test, and documentation work | Python, frontend, build, Playwright, privacy scan, clean worktree, and pushed commits | None |
| P0 | Complete | Runtime truth, readiness, visualization, previews, evidence contracts, durable jobs, local automation, Job Centre, exact metric scope, and revocation-safe result activation | Backend, frontend, build, real-loopback and browser E2E, privacy, migration-upgrade, cancellation, supersession, restart, and concurrent revocation gates | No P0 blocker; Codex still truthfully exposes only documented request/response/plan coaching text, so 7 of 20 structures remain unsupported |
| P1 | In progress | Serialized estimator cascade, generic run/vote records, calibration, reviewed runners, and model comparison | Frozen private holdout, calibration, stability, privacy, latency, and abstention gates | No representative human-calibrated holdout; no estimator is product-enabled |
| P2 | Blocked by P1 gate | Immutable temporal snapshots, compatible aggregation, recommendations, and model/job/history views | Prospective comparable recommendation outcomes with missingness and adverse effects visible | Requires calibrated P1 estimates and completed P0 provenance boundaries |
| P3 | Deferred | Optional cloud identity, pairing, entitlements, payments, and usage ledger | Tenant isolation, revocation, deletion, balanced ledger, webhook replay, spend caps, and offline-local behavior | Owner approval and completed P2 required |
| P4 | Deferred | Teams, governance, aggregate-only sharing, RBAC, and privacy-preserving boards | RBAC, isolation, consent withdrawal, cohort-inference defense, deletion propagation, and accessibility | Requires P3 control plane and a separately reviewed sharing policy |

## Baseline evidence

Checkpoint ending at `2a3969a` contains three coherent commits:

1. local analysis and model-evidence backend;
2. real local quality workspace frontend;
3. metric-validity and privacy documentation.

The checkpoint passed 659 Python tests with 4 skips, 256 frontend tests, the
production frontend build, 4 Playwright tests, and the repository privacy
scanner. The build reports a non-blocking bundle-size warning; it is tracked as
performance work, not hidden as a failure.

## P0 checkpoint evidence

Checkpoint ending at `bd9ffe7` adds four coherent P0 slices:

1. explicit `synthetic_demo` and `local_real` runtime composition with verified
   loopback health and fail-closed transport identity;
2. truthful 3-8-axis radar eligibility with exact-value bars below three axes;
3. versioned, content-free provider/session metric readiness for all 20 Coaching
   v1 metrics, including exact reason, required evidence, and next action;
4. a ten-minute, in-memory, one-shot redaction preview and approval backend that
   binds the exact session window, metric set, destination, model plan, redactor,
   retention class, size, and cost estimate without a second provider read.

The current Codex capability projection makes 13 of 20 metric structures
attemptable and marks 7 unsupported before any session content is read. This is
a documented evidence ceiling, not a failed model run, and unsupported values
are never synthesized or plotted as zero.

The checkpoint passed 682 Python tests with 4 platform skips, 283 frontend
tests, the production frontend build, the repository privacy scanner, and diff
validation. The remaining non-blocking frontend bundle-size warning is still
tracked. No remote model received session content, and no estimator was
activated.

The continuation checkpoint ending at `9149af8` adds four more coherent P0
slices:

1. the exact redacted-window preview and one-shot approval UI, including
   expiry, stale-session, and consumed-token handling;
2. versioned ephemeral `ACTION`, `DECISION`, `FEEDBACK`, and `VERIFICATION`
   evidence contracts, with objective verification receipts required;
3. a durable SQLite analysis queue and renewable local-only automation grants
   with leases, restart recovery, cancellation, retry bounds, supersession,
   progress, revocation, and private public DTOs that omit worker lease tokens;
4. a truthful Job Centre plus a real uvicorn/httpx loopback E2E covering consent,
   indexing, exact compatibility, preview/approval, 20-metric analysis,
   readiness, automation supersession/revocation, crash recovery, and canary
   absence from SQLite, files, and logs.

The combined continuation gate passed 703 Python tests with 4 platform skips,
313 frontend tests, 9 Playwright tests across responsive widths, the production
frontend build, and the privacy scanner. The exact test totals belong to this
checkpoint only; they are not estimator-calibration evidence.

The subsequent P0 checkpoints ending at `9afdedb`, `22752c7`, and `d4e129f`
closed the remaining scope, preview, and revocation conditions:

1. immutable analysis runs now persist their exact selected metric set;
2. `{A}` and `{A,B}` runs combine for compatible observations of `A`, while
   omission of `B` remains distinct from missing, failed, and legacy-unknown;
3. migrated scope is marked exact only when it can be proven, and migration 14
   repairs unprovable schema-13 classifications without changing migration-13
   checksums;
4. preview expiry uses both UTC receipt time and an internal monotonic deadline,
   with atomic one-shot redemption and rollback-clock tests;
5. automation result activation validates the exact job, grant, worker lease,
   provider, project, session, and metric scope in the same SQLite write
   transaction. A revocation that wins that transaction publishes no results;
6. project Automation settings, selected-metric execution, Job Centre, packaged
   route refresh, synthetic browser coverage, and local-real browser coverage
   are implemented.

The final P0 backend gate passed 795 tests with 4 platform-only symlink skips.
The last unchanged frontend gate passed 362 unit tests, the production build,
13 synthetic-browser tests, and 3 local-real browser tests. The privacy scanner,
compile checks, and staged-diff validation passed. These are engineering and
privacy gates, not calibration evidence.

Blinded, content-free P0 review packets were evaluated by GPT-5.6 Sol, Claude
Opus 5, and Claude Fable 5. All three returned `pass_with_conditions` with no
P0 blocker. Their bounded conditions are carried into P1/P2: persist a complete
gate manifest, measure performance and usability budgets, and never activate a
model without representative human calibration. Reviewer agreement is advisory
and is not ground truth.

## P1 foundation evidence

The first P1 foundation defines a content-free, versioned serial-cascade
contract and evaluation-math library. It records the complete estimator
configuration, exact execution and stage lineage, requested and served model
identity, local artifact digests, tokenizer and license identity, preprocessing,
question, prompt/rubric digests, reasoning effort, calibration/router/redactor
versions, fallback state, resource measurements, votes, uncertainty,
adjudication, and distinct unavailable, abstained, failed, and not-applicable
states. Candidate screening is capped at five models per family and promotion at
two; local model stages are explicitly serialized.

The evaluation functions cover correctness, retrieval, calibration, selective
risk, false-confident errors, agreement, EN/PL and task/provider/project/time
slices, repeat/order/format/injection stability, latency/resource/cost/failure
telemetry, and incremental cascade value. Their activation-check projection is
diagnostic only. It cannot write an activation slot, and its caller-supplied
facts are not trusted as release evidence. P1 persistence must derive holdout,
human-truth, privacy, and synthetic-origin facts from frozen immutable records
before any estimator can become eligible. Until that vertical slice and the
representative 100-200-judgment program exist, every estimator remains disabled.

## Version inventory

| Component | Pinned identity | Product status |
|---|---|---|
| Deterministic coaching pack | `core.redacted-text.prompt-logic` v1; engine `text-rules-en-pl-1`; rubric `prompt-logic-rubric-1` | Local deterministic observations only; missing objective evidence abstains |
| Redactor | `deterministic-local-redactor-v1` | Local risk reduction; not sufficient by itself for remote disclosure |
| Qwen embedding challenger | `Qwen/Qwen3-Embedding-0.6B` at `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | Synthetic exploratory challenger; not product-enabled |
| BGE reranker challenger | `BAAI/bge-reranker-v2-m3` at `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` | Synthetic exploratory challenger; not product-enabled |
| Claude Opus review target | Exact requested and served model must be recorded by a reviewed BYOK/API runner | Not implemented; no private-session review is authorized |
| Claude Fable review target | Exact requested and served model plus retention acknowledgement must be recorded | Not implemented; synthetic architecture review only until the remote approval boundary exists |

Full local model revisions, weight digests, tokenizer pins, licenses, bounds,
and gate results live in [the model manifest](model-manifests/wp-11-local-candidates.md).

## Decision log

- Unknown, unsupported, abstained, incompatible, not-applicable, and failed are
  distinct states. None may be converted to zero.
- Objective tests, artifacts, and explicit acceptance outrank model-written
  completion claims.
- Review-load metrics stay on an exact-value board unless a bounded,
  documented normalization exists.
- Remote work is per-run only: a local automation grant can enqueue it, but it
  cannot approve disclosure.
- P1, billing, and teams remain disabled until their preceding phase gates pass.
