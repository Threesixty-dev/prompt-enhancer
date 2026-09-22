# Beta-readiness checkpoint 25

Status date: 2026-09-08

Status: **bounded implementation and automated validation complete; owner
review pending.**

## Scope

This checkpoint narrows one Analysis Job Centre recovery boundary in
`AnalysisJobCentre.tsx`. A strict `404` with reason
`analysis_job_not_found` is authoritative absence only for the exact selected
job. Whether received while cancelling or verifying detail, it retires that
cached row, detail, and confirmation control immediately and announces:

> This job record is no longer available. Refresh the queue to view its current
> receipts.

Other records stay intact. A generic 404, or a 503 including one with the
mismatched `analysis_job_not_found` reason, retains the last verified receipt
and shows the existing content-free unconfirmed-cancellation recovery. An
identity conflict blocks cancellation. Stale list and detail generations are
fenced, and no cancel command is retried automatically: every retry requires an
explicit user confirmation.

Cancellation captures focus origin before its confirmation control is disabled.
After a committed retirement, a post-commit owner fence moves focus to the
existing Refresh queue control only when a retired card/detail control had
previously owned it, including focus lost to the document when that control was
disabled. It never treats arbitrary body focus as owned or steals focus from
another connected control. A current same-id, same-identity record may reappear
only through a fresh queue read started after the observed absence. Refresh
begun while a still-owned cancellation is pending does not void that
cancellation's strict 404 result; changed state and timestamp alone do not
change immutable identity.

The work is limited to this one production recovery file, new synthetic
acceptance coverage, and tracking documentation. It changes no job execution,
queue storage, provider read, model, native operation, session text, metric
calculation, adapter, consent, retry policy, or backend authority.

## Synthetic acceptance boundary

The browser fixture mounts the real local-real Analysis Job Centre with
`createSyntheticTransport` wrapped by parser-valid fictional job records. It
uses one cancellable receipt, one retained receipt, and content-free list,
detail, and cancel counters. No job is submitted, provider contacted, model
loaded, native API called, or durable queue modified.

The journeys are:

1. exact cancellation 404 retires only the selected job and preserves the
   other receipt;
2. generic 503 retains the selected receipt and retries only after a second
   explicit confirmation;
3. detail 404 retires immediately, while a later explicit Refresh may show a
   current same-identity record; and
4. at 360px, keyboard cancellation returns focus to Refresh queue after the
   focused control is removed, without horizontal overflow; and
5. a deferred strict cancellation 404 leaves focus on Queue state when that
   still-connected control, rather than the retired card/detail, owns focus.

## Evidence boundary

Root reproduced the stale-404 defect as **1/1 failing in 3.52s** (chunk
`768653`). The final owning frontend group passed **234/234 across three files
in 5.78s** (chunk `76b11f`); backend queue and publication-context coverage
passed **20/20 in 24.61s** (chunk `af84b5`).

The initial browser run passed **7/9** and exposed a genuine focus defect plus
a fixture-count expectation (chunk `545045`). A second run passed **9/10**;
its only failure was the new fixture's label-selector mismatch (chunk
`4b3bb7`). The final run passed **10/10 in 5.8s**, comprising five existing and
five new journeys (chunk `d97da9`). Strict E2E passed (chunk `1e1723`); build
and bundle validation passed with unchanged caps—shell **1,153,973 B**, Agent
incremental **559,666 B**, initial Agent **1,713,639 B** (chunk `962237`)—and
API validation passed (chunk `6ee585`).

The built real-loopback harness passed **27/27 in 27.4s** (chunk `a24333`),
with cleanup, listener release, and temporary-state removal confirmed; runtime
count was zero and no startup failure occurred. Post-documentation privacy
scanning passed (chunk `a9ff2e`); listener inspection and `git diff --check`
passed (chunk `62724b`), with ports 8765 and 4173 unbound. These are bounded
automated receipts, not beta, v1, release, real-provider, native, restart, or
model-execution evidence.

## Owner checks (maximum four)

1. Cancel a selected local queue record that is already absent and verify only
   that receipt disappears with the stated recovery notice; the other receipt
   remains.
2. Cause an ordinary unavailable cancellation and verify the receipt remains
   until another explicit confirmation is chosen.
3. Verify an absent detail cannot leave a stale Cancel or confirmation control,
   and a generic/mismatched 404 cannot remove the receipt.
4. At a narrow width, complete keyboard cancellation and verify Refresh queue
   receives focus only when the retired control had focus; Queue state remains
   focused when it owns focus instead.
