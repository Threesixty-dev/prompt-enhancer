# Bench recovery and explicit failures

## Task card - 2026-10-25

- Scope: MA18 and W02/W05/W07, from reviewed develop `233b49d`.
- Reproduction: a remote embedding timeout leaves an interrupted run and a global
  admission hold. History shows only run status; the useful cause is inside an
  attempt. Separately, failed container cleanup is retried only at worker startup,
  and another cleanup failure can terminate that startup.
- Change: expose cause/stage in history and above run details, show global blockers
  across filters/revisions, guide recovery and retry owned-container cleanup.
- Contracts: retain results, execution status, metrics, assertions, model bindings,
  remote-stop requirements and no-replay behavior. Core code and experiment
  definitions do not change. No new core artifact is required.
- Evidence: synthetic worker/API/storage and owned-loopback client tests, plus
  desktop/mobile checks: all 436 Bench tests and 28 recovery, evaluator-failure
  and reconnection browser checks pass. Browser checks use installed Chrome;
  the separate Playwright executable is absent in this development environment.
- Bounds: three cleanup checks per cycle, five then thirty seconds between
  failures; one check per worker tick. Docker operations retain their deadlines
  and ownership checks. An ownership mismatch stops automatic retries.
- Remaining gates: owner review, API/UI and worker rollout, hosted recovery
  verification and independent onboarding. The historical embedding request
  is not cleared, retried or relabelled by this change.

## UI journey

The **Queue paused: recovery required** banner links to blocking runs, including
older runs outside the current history page or experiment filter. New runs can
be queued but cannot execute. The banner returns the oldest 100 blockers and
explicitly reports truncation. An active run's normal container ownership is not
reported as a recovery fault.

Run cards show **Execution issue**, its code and stage. Run details put this
explanation above prompts, diagrams and measurements, identifying the case and
variant where recorded. The underlying error, such as `gateway_io_timeout`,
takes priority over a wrapper such as `core_uncertain`. Historical successful
statuses with invalid reviews retain their status and expose the contradiction
through the existing review warning and the new summary.

**Recovery required** separates local container cleanup from remote completion.
It shows check count, last/next check, cleanup error, operation reference when
recorded, run start/interruption times and next action.

**Retry container cleanup** requests another bounded cycle after automatic checks
are exhausted or ownership needs operator attention. It does not restart a run
or model, remove unowned containers, or clear a remote-operation hold.

Remote reconciliation requires explicit operator confirmation after checking
actual completion/cancellation on the affected model host. Local cleanup must
already be confirmed. There is no text field: Bench creates an opaque confirmation
record and saves its run ID and timestamp. The button stays disabled until the
operator checks the acknowledgement. The record identifies that attestation; it
does not independently verify the remote service. Releasing all holds allows
queued runs to start; the interrupted attempt is never replayed.

## Automatic recovery limits

The historical embedding timeout did not record an upstream request identifier.
This candidate cannot recover that missing identity or automatically establish
whether the request stopped. A healthy service, later successful request, elapsed
time or cancelled HTTP client is not request-specific completion evidence.
The remote hold remains explicit and requires the existing operator attestation.
Automatic provider completion/cancellation remains an open capability.

Local cleanup is independently verifiable. The worker checks the exact owned
container and confirms absence before releasing its local hold. Failure is
persisted, so normal worker iterations retry without a process restart. Crashes
reserve a check for 120 seconds and retain its count; restarting cannot reset the
budget. An expired third reservation requires manual attention instead of staying
in an endless checking state. Unexpected exceptions become fixed safe diagnostics.

## API and AI operators

- `GET /api/recovery` returns `bench-recovery-queue/v1`: global blocker count,
  bounded run identities, cause/stage and truncation. It contains no prompt,
  provider response or model configuration and performs no recovery action.
- `GET /api/runs/{id}` and the existing `enhancement-bench inspect` command share
  `failure` and `recovery` projections. `nextAction` describes inspection, waiting,
  cleanup retry or remote confirmation. `automaticReplay` is always false.
- `POST /api/runs/{id}/cleanup-check` with `{}` returns 202 after scheduling an
  eligible cycle. Duplicate requests while pending are a no-op. Active runs or
  runs without a cleanup hold return 409. Same-origin JSON remains required.
  A 202 is scheduling acknowledgement, not cleanup or worker-liveness proof.
  Inspect the same run afterward.
- `POST /api/runs/{id}/reconcile` requires `{"remoteStopped": true}` after
  actual stop verification. Omitting `evidenceReference` creates one durable
  `operator-confirmation-<id>` record in the same transaction that releases the
  hold. Duplicate requests preserve the original record and time. Existing
  clients can still supply a validated reference. This remains an operator
  attestation; the generated identifier does not prove remote completion.

Existing settings and attempt results are unchanged. `cleanup_checks` is additive,
optional operational metadata in database schema 3. Older databases gain the table
without rewriting historical runs; older binaries ignore it. API/UI and worker
must both roll out to activate the behavior. API deployment alone does not install
the worker fix. Existing analysis exports and their schema/version are unchanged.

## Verification

`tests/bench/test_recovery.py` covers live-loop recovery, cooldowns, bounded
restarts, interrupted reservations, ownership mismatch, unknown exceptions,
old-database initialization, global blockers, content-free projections, explicit
reconciliation and preserved failures. Existing worker/API/export/client and
real-core synthetic tests verify compatibility.

`bench/browser/recovery.spec.mjs` covers cause/stage, cross-filter visibility,
explicit stop attestation, retained confirmation, disabled retry and bounded
cleanup scheduling at desktop/mobile widths. Existing evaluator-failure and
reconnection checks remain required. Tests use synthetic data and owned loopback
services; they do not invoke live models or change deployed runs.

## Confirmation without manual bookkeeping - 2026-10-25

- Scope: W02/W05/W07, from reviewed develop `f8492d1` after PRs #98/#99.
- Reproduction: a required text reference asks the operator to invent an audit
  label; entering it performs no remote check. The owner explicitly approved
  removing the typed field while retaining actual stop verification and consent.
- Change: create the confirmation record transactionally on the server and show
  it after confirmation. Preserve supplied references for existing API clients.
- Boundaries: the local-cleanup guard, explicit `remoteStopped: true`, same-origin
  JSON checks, remote hold, original results and no-replay policy are retained.
  No schema migration, core release or worker update is needed for this change.
- Verification: API/store checks cover receipt persistence, duplicate requests,
  rejected confirmation, cleanup holds and historical reference compatibility.
  Browser checks cover no text entry, acknowledgement gating and preserved errors
  on desktop/mobile. All 442 Bench tests and 22 affected desktop/mobile checks
  pass. Source review, promotion and deployment remain separate.

## Reviewed deployment - 2026-10-25

Owner-approved PRs #98/#99 deployed the preceding error and recovery UI at main
`a0967c8`. Workflow `40179897463` built successfully; its first revision verifier
received HTTP 404. Rerunning only that failed job verified the serving revision.
The live UI showed the primary timeout cause, evaluation stage, global blocker
and confirmed local cleanup. Remote completion remains unconfirmed. The worker
cleanup-retry rollout and the confirmation-form change above are still pending;
no hold was cleared or experiment replayed by this deployment.
