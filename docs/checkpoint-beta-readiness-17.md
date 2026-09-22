# Beta-readiness checkpoint 17

Status date: 2026-09-08

This checkpoint records a bounded MetricCoveragePanel read-recovery lifecycle.
It is not calculator, metric-definition, calibration, beta, v1, provider-
coverage, native, model, packaging, or release certification.

## Scope

Metric coverage remains a read-only, content-free report of an exact local
SQLite snapshot. The panel now starts initial and manual-refresh reads with a
local 15-second deadline, an explicit cancellation control, and no automatic
retry or polling. Failure, cancellation, timeout, synchronous transport throw,
and malformed report admission remain manual-retry paths.

The existing strict `parseMetricCoverageReport` admission is applied to every
transport result, including provider and one-project scope checks. A rejected
report produces a fixed content-free Unknown state; it never fabricates zero
counts or changes the existing unknown metric/state/provenance axes.

After a validated report, Refresh coverage is explicit. A same-scope refresh
keeps the last verified report visible, labels it as a previous verified/stale
snapshot while the request is in progress or has failed, been cancelled, or
timed out, and shows the report's `generated_at` timestamp. It does not call an
older snapshot current. Initial failure, cancellation, or timeout remains
Unknown because there is no validated snapshot to retain.

Provider, project, or transport replacement hides the preceding counts and
status before the new effect runs. Requests are abortable and fenced by rendered
owner, request generation, and active request identity before dispatch and
after resolution. Same-scope duplicate clicks coalesce synchronously. Existing
accessibility boundaries, metric table, and no-model/no-new-metric claims are
unchanged.

## Evidence boundary

Bounded automated implementation and validation are complete. Root's backend
receipt is:

`uv run --frozen --no-sync python -m pytest -q tests/test_metric_coverage_contracts.py tests/test_metric_coverage_api.py tests/test_metric_coverage_sqlite.py tests/test_convergence_loopback_harness.py`

It passed **29/29 in 26.75s**.

Root's frontend receipts are:

- `npm test -- --run src/features/project-catalog src/features/session-catalog src/features/project-workspace/ProjectWorkspace.test.tsx src/shared/api/httpTransport.test.ts src/app/AppPrimaryControlAudit.test.tsx src/app/AppScopedRoutes.test.tsx` — **331/331 across 9 files in 27.94s**.
- `npm test -- --run src/features/metric-coverage` — final owning **15/15 across 2 files in 26.82s**.

The two runs total **346/346 across 11 files**; they are bounded receipts, not
all repository suites. Strict E2E TypeScript passed after the sentinel and
fixture type corrections with:

`npx tsc --noEmit --strict --target ES2022 --module ESNext --moduleResolution Bundler --esModuleInterop --skipLibCheck --jsx react-jsx --types vite/client,node,@playwright/test e2e/beta-coverage-recovery.spec.ts e2e/fixtures/coverage-recovery.tsx e2e/loopback-built.spec.ts e2e/loopback-lazy-recovery.spec.ts playwright.loopback.config.ts`

Production build emitted **599 modules** with exit 0; API check and
bundle-budget check each exited 0. The bundle report records shell
**1,153,789 B**, Agent incremental **549,831 B**, initial Agent **1,703,620
B**, and **10 deferred boundaries**.

Root's focused browser receipt is:

`npx playwright test e2e/beta-coverage-recovery.spec.ts e2e/beta-session-catalog.spec.ts e2e/beta-project-catalog.spec.ts e2e/sweep-01b-accessibility.spec.ts --workers=2`

It passed **36/36 in 1.3m**.

Final built loopback receipt:

`uv run --frozen --no-sync python tests/support/convergence_loopback_runner.py --skip-build`

It passed **25/25 in 24.5s** with exit 0: 24 healthy journeys and one CP14
intentional optional-chunk failure contained by its recovery path. Cleanup
reported browser exit 0, `listener_released=true`,
`model_runtimes_remaining=0`, `runtime_cleanup_confirmed=true`,
`server_thread_failed=false`, `startup_failure_component=null`,
`startup_ready=true`, and `temporary_state_removed=true`. Root verified the
earlier synthetic trace file was absent and ports 8765 and 4173 were listener
free.

The post-rerun privacy receipt,
`uv run --frozen --no-sync python scripts/privacy_scan.py`, passed with exit 0
in **7.56s**. The earlier loopback locator ambiguity and its generated
synthetic trace were corrected historical test-output conditions; no scanner or
ignore rule was changed.

These bounded receipts do not prove owner, native, model, calibration, beta,
v1, release, or overall-product readiness. No calculator or calibration
behavior is changed or certified here.

## Owner checks (maximum four)

1. Refresh a validated synthetic coverage report and confirm the displayed
   `generated_at` timestamp and Last verified snapshot wording remain truthful.
2. Force refresh failure, cancellation, and timeout; confirm the last validated
   counts remain visibly stale and Retry coverage is manual.
3. Replace provider, project, or transport during a pending read; confirm old
   counts and status disappear and the late result cannot return.
4. Check responsive layout and the metric table's keyboard/screen-reader access
   across the initial, stale, and Unknown states.

## Next pointer

The next verified candidate is CP18: bounded ProjectWorkspace recovery for the
initial project-session list and selected older-session metadata lookup. It is
limited to local deadline, cancellation, manual retry, and owner fencing; it
does not alter project-analysis bounds, calculators, calibration, native/model,
or release behavior. No CP18 implementation is claimed here.
