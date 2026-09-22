# Beta-readiness checkpoint 13

This checkpoint records the bounded MetricOperabilityPanel recoverability and
R8 verification-notification slice. Bounded automated validation is complete;
this is not beta, v1, or release certification and the overall goal remains
active.

## Bounded behavior

MetricOperabilityPanel is read-only. A transient initial failure exposes Retry;
Refresh explicitly rechecks an already loaded map. When refresh fails transiently, the panel
retains the explicitly stale last-validated map and labels it stale rather than
presenting an unavailable or empty result. Typed-definition mismatches and
malformed definitions hide the incompatible map. When the endpoint is absent,
the panel explicitly reports unavailable and offers no misleading Retry.

The metric map and uncertain-outcome reconciliation are read-only. R8
preparation and native acceptance are explicit user-triggered mutations.
Successful validated mutations, or explicit reconciliation observing compatible
evidence advancement, emit a MetricWorkspace-internal notice scoped to the
current owner. Saved readiness and metrics remain immutable. No automatic
analysis, model start, provider transcript access, or external-network access
is introduced. Loopback metadata/exact-bound snapshot GETs remain read-only;
Refresh/Retry, preparation, acceptance, and uncertain-outcome reconciliation
require explicit controls. Reconciliation may report advanced current evidence
without proving that the requested acceptance succeeded; the same revision does
not notify. Callback failures cannot relabel a successful mutation as failed.

## Evidence boundary

The bounded implementation and automated checks are complete. Final evidence
includes root’s backend **20/20 in 3.70s**, broad frontend **97/97 across 10
suites in 13.88s**, final
R8/Workspace owning tests **34/34 in 4.09s** across two files (overlapping 32
broad tests and adding two), final operability **15/15 in 2.74s**, strict E2E
fixture/spec/loopback TypeScript, browser **11/11 in 4.1s**, production
`tsc-b`/Vite, API check, and built disposable loopback **20/20 in 20.4s**.
The browser total is **31 distinct cases** (11 + 20). The built loopback cleanup
receipt is green: `listener_released=true`, `runtime_cleanup_confirmed=true`,
`temporary_state_removed=true`, `model_runtimes_remaining=0`,
`server_thread_failed=false`, `startup_ready=true`, and
`startup_failure_component=null`; ports 8765/4173 have zero listeners. The
privacy scan and `git -c core.safecrlf=false diff --check` also pass. This is
bounded automated validation, not a clean release or overall beta claim.
Refresh’s real loopback GET was validated without a POST, session creation,
model start, or provider read. No model, real provider data, real credential
access, restart/reload, native/GPU/MCP execution, commit/push, or
external-network access is claimed.

The canonical coaching surface remains **16 shipped conditional paths, 0
profile gaps, and 4 provider-adapter gaps**. This checkpoint does not add a
calculator, close an adapter gap, establish calibration, or promote beta. CP14
now addresses the dated Agent bundle candidate; see
[checkpoint-beta-readiness-14](checkpoint-beta-readiness-14.md).

## What the user can check later (maximum four steps)

1. Route to Research → Methods and confirm a loaded map can be explicitly rechecked with Refresh.
2. Trigger or observe a transient failure, use Retry, and verify the stale last-validated map remains labelled and visible.
3. In the R8 panel, complete the explicit prepare/review and native-accept flow, then verify the owner-bound current-evidence-changed notice.
4. Change the selected run and verify the notice clears while saved scores remain unchanged.

## Known limits and next candidate

Native/GPU/MCP owner evidence, calibration, packaging and release gates remain
open. The superseded Agent bundle warning was addressed by CP14 and is not a
performance-gate closure or an overall beta-readiness or release commitment.
