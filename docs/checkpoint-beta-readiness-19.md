# Beta-readiness checkpoint 19

Status date: 2026-09-08

Status: **bounded automated implementation complete**.

This checkpoint covers bounded read recovery in ProjectWorkspace for three
session drilldown reads: stored metrics, the latest legacy quality run, and
metric readiness. It is not metric-calculation, analysis, calibration, beta,
v1, native, model, packaging, or release certification.

## Scope

The implemented lifecycle gives each read a local 15-second deadline, explicit
manual cancellation, manual retry, and owner fencing before dispatch and after
resolution. Owners bind the admitted project/session/provider/category,
transport, current catalog identity, and legacy-disclosure state as applicable.
Late results must not replace a new drilldown owner or an explicitly adopted
completed quality result.

The legacy disclosure remains optional: no latest-quality or readiness read is
started until it is opened. A 404 latest-quality result remains an explicit
absence rather than an error. Readiness failure must remain separate from saved
quality results. This slice adds no mutation authority and does not change
metric calculations or analysis semantics.

## Baseline

Root reproduced **2/2 failures in 4.83s**: missing cancellation controls for
stored-metrics loading and legacy-quality loading. This is a red baseline, not
evidence that implementation or broader recovery behavior is complete.

## Evidence boundary

Root's current backend receipt is:

`uv run --frozen --no-sync python -m pytest -q tests/test_metric_readiness.py tests/test_session_metric_pack_provenance.py tests/test_session_quality_aggregation_api.py tests/test_convergence_loopback_harness.py`

It passed **20/20 in 19.16s**.

Root's focused frontend receipt is:

`npm test -- --run src/features/project-workspace src/features/quality-profile src/features/coaching-loop src/entities/analysis src/shared/api/httpTransport.test.ts src/app/AppPrimaryControlAudit.test.tsx src/app/AppScopedRoutes.test.tsx --reporter=dot`

It passed **493/493 across 22 files in 49.62s**. The focused browser receipt
is:

`npx playwright test e2e/beta-session-drilldown-recovery.spec.ts e2e/beta-project-workspace-recovery.spec.ts e2e/sweep-01b-accessibility.spec.ts --workers=2`

It passed **33/33 in 1.2m**: seven CP19 checks, six CP18 checks, and 20 Sweep
accessibility checks. Strict E2E TypeScript and the API check are green.

The real fixture makes two metrics GETs because the session radar and drilldown
are separate consumers. This does not claim radar reliability, provenance,
unknown-state, error behavior, or calibration is fixed.

The final production build and bundle-budget check are green. The final bundle
report records shell **1,153,800 B**, Agent incremental **550,096 B**, and
initial Agent **1,703,896 B**. Final CP19 browser coverage passed **8/8 in 6.7s**;
the earlier broad 33/33 receipt includes seven overlapping CP19 checks.

The final real-loopback run passed **27/27 in 27.6s**. Cleanup confirmed
browser exit 0, listener release, zero remaining model runtimes, runtime
cleanup, temporary-state removal, and no startup failure. Final strict E2E,
privacy, and diff checks are green.

The discovered Agent draft-loss race was resolved with a functional latest
per-session draft merge. Root's focused Agent-suite command was:

`npm test -- --run src/features/agent/AgentPage.test.tsx src/features/agent/AgentPage.exitRisk.test.tsx src/features/agent/AgentPage.handoff.test.tsx src/features/agent/AgentComposerAttachments.test.tsx src/app/App.agentNavigation.test.tsx src/app/App.modelsHandoff.test.tsx --reporter=dot`

It produced **230 passed and one failed of 231 in 214.87s**; both new draft
tests passed. The sole failure was an exit-risk workspace fixture that did not
await a lazy import. An isolated reproduction had **10 passed and one failed in
8.20s**. The test-only correction waits for `vi.dynamicImportSettled` inside
`act` and asserts the exact workspace-tree call, without sleeps, skips, global
timeout changes, or product changes. The resolving targeted receipt was:

`npm test -- --run src/features/agent/AgentPage.exitRisk.test.tsx src/features/agent/AgentWorkspacePane.test.tsx src/shared/ui/RetryableLazyFeature.test.tsx --reporter=dot`

It passed **73/73 across three files in 17.78s**. This resolves the one failure
without claiming that all 231 tests were rerun as one green suite. Final
`npx tsc -b`, post-test privacy, and diff checks are green.

These bounded receipts do not prove beta/v1 readiness or overall product
completion.

No broader green status is claimed.

## Owner checks (maximum four)

1. Cancel and retry each of the three reads; confirm the controls remain
independent when another drilldown read is loading or has failed.
2. Change project, session, category, transport, or legacy disclosure while a
read is pending; confirm old analytics data, status, and late results cannot
displace the current drilldown owner.
3. Confirm a missing latest legacy-quality run is shown as absence while a
failure remains content-free and retryable; then complete analysis while an
older GET is pending and confirm the adopted result and readiness refresh win.
4. In Agent, type while an attachment list loads, edit again, switch chats, and
confirm the latest draft stays in its own chat and late loading cannot erase it.

## Next pointer

CP20 is a source-reviewed candidate only, not an implementation commitment. It
would separately examine session-radar source/provenance, finite/range/unknown
presentation, and loading/error recovery. It is not implemented here.
