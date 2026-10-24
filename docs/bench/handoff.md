# Bench handoff guide

Use this guide for the fixed prompt workflows in Test Bench. The supported input
is an explicitly authored synthetic prompt plus optional supplied context.
Session ingestion, arbitrary workflow graphs and downstream coding-task success
are outside this handoff.

Handoff status: **not yet qualified for independent operation**. The failure
reporting correction, client and export described below are local source candidates. A reviewed
release, deployed qualification and an unaided user walkthrough are still
required. Passing tests establishes their stated coverage, not absence of bugs.

## First run in the UI

1. Open Bench through the operator-provided private access gateway. Select an
   experiment and its exact revision; check the workflow, core image and evaluator
   profile. Request access from the operator if the session is unavailable.
2. Choose **New run**. Select input cases and variants. The attempt count is
   selected cases multiplied by selected variants. Before/after columns do not
   add attempts. Start with one case and one variant.
3. Review model bindings and effective settings. Model aliases must already be
   configured by the operator. A model binding selects generation; evaluator
   bindings select independent measurements. Null generation controls mean
   provider-managed values, not zero.
4. Choose **Start run** once. Keep the run ID. After a connection loss, reopen
   that run before submitting anything else. A queued run has not completed a
   model call. **Cancel run** requests cancellation; wait for the terminal state
   and confirmed cleanup before considering it stopped.
5. Inspect execution status, recorded workflow steps, review state and evaluator
   coverage separately. Open **Complete result, provider provenance, timings and
   assertions** for the stored evidence. The interpretation table below is the
   acceptance rule, including for historical results.
6. Use **Rerun with changes** for an intentional new run. A rerun keeps the
   selected revision and its image; deploying a new core does not upgrade old
   experiment pins. Use a new reviewed revision to select a new core or evaluator.

Stats pages aggregate all runs matching their filters. They are not implicitly
limited to the last submitted batch. Keep an explicit list of run IDs for each
analysis cohort and retain the effective settings with the private results.

## Interpret results

| Field or state | Meaning | Action |
| --- | --- | --- |
| Execution `succeeded` | The execution wrapper completed. Historical wrappers could report this despite a failed review. | Also inspect review and step states before accepting an attempt. |
| Review `ok` with a candidate | A structured review and rewrite passed the response contract. | Inspect measurements and assertions. Valid structure does not establish quality. |
| Review `ok` without a candidate | Valid advice with no proposed rewrite. | After measurements are absent; deltas and applicable assertions are unknown. Do not invent a candidate or a zero score. |
| Review `no_active_model` or `skipped` | The optional review did not run. | Use the diagnostics as diagnostics; do not count a completed model review. |
| Review `reply_invalid` | The response failed the review contract. | Treat as a technical failure; inspect the model/policy binding before a deliberate rerun. |
| Review `model_error` | The configured model call failed definitively. | Operator checks the provider route, readiness and credentials privately. |
| Execution `uncertain` / Bench `interrupted` | Completion or cleanup could not be confirmed. | No automatic retry. Resolve any cleanup/reconciliation hold first. |
| Assertion `failed` | A measured result missed a declared threshold. | An experimental finding; do not relabel it as infrastructure failure. |
| Assertion `unknown` / `not_evaluated` | Required comparison evidence is unavailable / checks were not run. | Exclude from pass-rate denominators and report the exclusion count and reason. |
| Metric `known` with numeric zero | A measured zero. | Retain zero in eligible numeric calculations. |
| Metric `unknown` / `input_too_long` | The pinned evaluator cannot accept the complete input; it was not invoked for that reading. | Report the exclusion and reason. Select a reviewed compatible evaluator or explicitly revise the experiment input; do not silently truncate or impute a score. |
| Metric `unknown`, `abstained`, `not_applicable`, `execution_error`, or missing | Distinct reasons a numeric value is unavailable. | Report coverage and reasons; never impute zero. |
| Categorical metric | A label, with a before/after transition when both are known. | Count labels/transitions; do not compute a numeric delta. |

The candidate correction emits `workflow_review_reply_invalid` or
`workflow_review_model_error` at the `generate` stage. It retains diagnostics,
completed before measurements and the failed step receipt. After evaluation and
assertions do not run. The existing worker stops that run and marks its remaining
attempts `skipped`; it persists the result before releasing core retention and
confirms owned-container cleanup. A later deliberate run may proceed once holds
are clear. Historical rows are not rewritten; the candidate UI flags a recorded
success that contains a failed review.

The measurement dictionary is in [evaluator coverage](evaluator-coverage.md).
Workflow diagnostics can guide generation. Independent harness judgments cannot.
Keep evaluator/model/policy versions together when comparing runs. Prompt scores,
model advice and assertion passes do not verify a downstream code change.

## Contract for AI clients

The tracked instruction entry point is root `AGENTS.md`; `CLAUDE.md` imports
it for Claude Code. Both route to the same repository skills, including:

| Work | Skill |
| --- | --- |
| Change tooling, contracts or UI | `prompt-enhancer-development` |
| Design and validate cases/variants | `prepare-bench-experiment` |
| Run, recover, inspect and export existing revisions | `operate-bench-experiment` |
| Prepare and release a new core artifact | `deploy-enhancement-core` |

Read these from `.agents/skills/` in the selected checkout. Personal installed
copies can be stale. Skills guide the operating agent; they are not injected
into experimental model requests. Workflow generation instructions are versioned
in `src/prompt_enhancer/workflows/prompt_policies.py` and recorded step policies.
Rubric/classifier adapters have their own input/output contracts. Embeddings and
rerankers use typed text/query/document inputs, not coding-agent skills. Keep
that runtime configuration distinct from the agent's operating instructions.

Use the same Bench API and stored definitions as the UI. Do not reconstruct a
second execution engine or directly invoke ephemeral core containers. The
operator provides the approved private origin and authenticated transport;
credentials stay outside prompts, definitions and output. API writes require the
exact `Origin` header and JSON content type. Do not follow an authentication
redirect as if it were a successful API response.

| Operation | Interface | Required interpretation |
| --- | --- | --- |
| Read API health | `GET /health/ready` | Confirms the API responds; does not prove worker, model or credential readiness. |
| Discover definitions | `GET /api/experiments` | Select an explicit stable ID and revision. Responses contain sensitive authored content. |
| Discover form contracts | `GET /api/run-form-schema` | Workflow catalog and configurable fields; not a complete OpenAPI specification. |
| Discover execution contracts | `GET /api/client-contracts` | Versioned schemas and workflow manifests for validating returned results. |
| Validate authored files offline | `enhancement-bench validate <definition.json>` | Local definition/request validation only; no model availability check or execution. |
| Check admission plan | `POST /api/runs/preflight` | Validates requests and registered image; worker/model/authentication readiness remains unverified. |
| Submit a run | `POST /api/runs` | Save the returned `runId`; HTTP 202 is admission, not completion. |
| Read a run | `GET /api/runs/{runId}` | Check run, attempt, review, metrics, assertions and cleanup states. |
| List a cohort | `GET /api/runs?experiment=...&revision=...&limit=100` | Follow `nextCursor` using `before`; retain explicit selected run IDs. |
| Request cancellation | `POST /api/runs/{runId}/cancel` with `{}` | Await terminal state and cleanup; acknowledgement does not prove remote stop. |

Submission shape, using reserved fictional identifiers:

```json
{
  "stableId": "example-review",
  "revision": "1",
  "requestId": "12345678-1234-4123-8123-123456789abc",
  "overrides": {}
}
```

Generate and persist a new request UUID for each intentional run. Reuse that UUID
and the exact body only when reconciling a lost admission acknowledgement. Do not
change overrides under the same ID or create a fresh ID as a transport retry.
Read the existing run after recovery before deciding on a new experiment attempt.
Only a verified operator may confirm that an uncertain remote operation stopped.

Authoritative contracts: `bench/src/enhancement_bench/definitions.py` and
`api.py` define the Bench envelope; `contracts/enhancement/` defines core
execution requests/results. The [client guide](client.md) documents the candidate
CLI's `experiments`, `runs`, `preflight`, `run`, `wait`, `inspect`, `cancel`,
`schema` and private `export` commands. Use its persisted submission receipts for
admission recovery and its structured output/exit codes for automation. Deployment
of this candidate remains pending; do not assume these commands are present in
an older installation. Preflight is deliberately not a provider-readiness doctor.

## Required handoff gates

These gates apply to this Bench handoff, not the wider app beta. Record the
source revision, core digest, experiment revision, test scope and cleanup in a
private content-free qualification receipt. Never include prompts, responses or
credentials in the receipt. No general product gate is closed by this checklist.

| Priority | Gate | Completion evidence |
| --- | --- | --- |
| 1 | Truthful failure reporting | Invalid reply, confirmed provider failure, valid no-rewrite, optional model, timeout and uncertain cleanup tests; UI agrees with stored state. Candidate local evidence below. |
| 2 | Repeatable operations | A reviewed core release and Bench deployment pass identity verification; synthetic end-to-end checks exercise configured generation and every evaluator. Resolve deployment verification errors before calling delivery successful. |
| 3 | Recovery | Frozen-candidate tests cover duplicate admission, lost acknowledgement, timeout, cancel, worker restart, unavailable evaluator and failed cleanup. No duplicate generation; durable partial results; held capacity until cleanup is confirmed. |
| 4 | Usable human and AI entry points | The candidate client provides one documented validate/preflight/submit/wait/inspect/export path, structured errors and a persisted receipt. Synthetic CLI/API and recovery checks pass locally. Source review, deployed qualification and user validation remain open. |
| 5 | Analysis contract | The candidate versioned export preserves run/case/variant IDs, values/states, reasons, provenance, timings and numeric inclusion rules. Hand-computable fixtures cover row counts, zero, missingness, labels and exclusions. It exports tables without silently pooling configurations; source review and deployed-data qualification remain open. |
| 6 | Independent onboarding | A new user completes one small run, interprets a deliberate failure, compares variants and obtains the analysis table using only the guide. Capture ambiguities as defects; repeat after fixes. |

Use the existing tests as evidence, not a substitute for the deployed candidate:

- `tests/test_versioned_workflows.py` and `tests/test_enhancement_core.py`:
  workflow outcomes, no-rewrite behavior, deadlines and execution lifecycle.
- `tests/bench/test_versioned_experiments.py`: real core HTTP application,
  synthetic provider, durable storage/API agreement, fail-fast behavior, cleanup
  and admission of a later run. Containers are a test double.
- `tests/bench/test_client_worker.py`: uncertain transport, cleanup holds and
  separation of assertion failure from execution failure.
- `tests/bench/test_operator_client.py`: authoritative contracts, preflight,
  lost admission acknowledgement, durable receipts, timeout/cancellation and a
  real CLI journey against an owned synthetic loopback API.
- `tests/bench/test_analysis_export.py`: typed tables, missingness and provenance,
  comparison exclusions, file permissions/failures and private-text canaries.
- `bench/browser/workflows.spec.mjs` and `metrics.spec.mjs`: desktop/mobile
  failure explanation, historical warning and measurement-state presentation.

Run affected tests using the environments in [Bench development](README.md#local-development)
and [CI quality gates](../ci-quality-gate.md). Full platform/container suites are
manual; automatic green CI establishes fast integrity checks only.

## Correction task card - 2026-10-23

- Task / atlas / gates: Bench handoff failure reporting; MA18, W02/W05/W07.
- Baseline: reviewed develop `cdcfb5f`; isolated task branch.
- Outcome: failed workflow steps cannot produce a successful new execution;
  valid reviews without rewrites and optional model skips retain their meaning.
- Scope: execution wrapper, Bench result display, synthetic regression tests,
  this guide and entry-point documentation. Workflow manifests, evaluator
  definitions, schemas and historical rows retain their identities.
- Evidence: six failing-before regression cases cover the three review flows
  and both failure states. Local core, worker/API and desktop/mobile checks
  cover corrected behavior. Exact totals are recorded in the readiness ledger.
- Remaining: owner review, a separately versioned core release, Bench deployment
  and qualification against that frozen candidate. This task publishes no image,
  runs no production experiment and does not claim handoff completion.
