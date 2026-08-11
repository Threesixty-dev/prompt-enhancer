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
| P0 | In progress | Truthful runtime health, metric readiness, radar fallback, typed evidence capability checks, transient preview/approval, durable local jobs, and automation grants | Synthetic-provider HTTP E2E plus restart, revocation, cancellation, supersession, change-during-run, and no-private-persistence tests | Codex currently exposes only documented request/response/plan text for coaching; unsupported action, decision, feedback, and verification evidence must stay unavailable |
| P1 | Blocked by P0 gate | Serialized estimator cascade, generic run/vote records, calibration, reviewed runners, and model comparison | Frozen private holdout, calibration, stability, privacy, latency, and abstention gates | No representative human-calibrated holdout; no estimator is product-enabled |
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
