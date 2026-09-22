# Beta-readiness checkpoint 18

Status date: 2026-09-08

This checkpoint records a bounded ProjectWorkspace project-session read-recovery
slice. It is not project analysis, calculator, calibration, beta, v1, native,
model, packaging, or release certification.

## Scope

The initial project-session page remains bounded to 100 rows. The explicitly
selected older-session metadata lookup retains its existing 9-page initial and
10-page continuation bounds, with the existing explicit Search next 1,000
sessions action. Neither path starts analysis or expands the 100-session
project-analysis boundary.

Both reads now have a local 15-second deadline, explicit cancellation, manual
retry, synchronous request coalescing, and abort/fencing before dispatch and
after resolution. Initial catalog ownership is project plus transport; the
older-session lookup additionally binds session and the validated base-catalog
identity. The shared `safeSessionCatalogRow` validator now admits rows, with
an exact project-page envelope check. Replaced project, transport, session, or
base catalog state cannot render previous counts, status, continuation offsets,
or resolved metadata.

Transient failure, cancellation, and timeout retain the validated base catalog
for same-offset older-session retry. An inconsistent page, total, or duplicate
is refused and requires explicit Refresh project sessions at offset zero to
establish a fresh base. Unknown catalog counts remain unknown; failures do not
become zero. Existing exact row/page admission, duplicate refusal, and project
scope checks remain in force.

## Red regressions addressed

Root independently reproduced two source/UI regressions: initial catalog
loading had no cancellation path, and a same-project transport replacement
could leave the prior ready project label and one indexed-session count visible
to a parent layout observer. This slice adds the owner-bound recovery behavior
described above; it does not certify every route or downstream consumer.

## Evidence boundary

Root's backend receipt is:

`uv run --frozen --no-sync python -m pytest -q tests/test_api_and_cli.py::test_project_session_catalog_is_scoped_counted_and_bounded tests/test_project_quality_aggregation_api.py tests/test_convergence_loopback_harness.py`

It passed **12/12 in 21.23s**.

Root's final focused frontend receipt passed **360/360 across 12 files in
38.61s**. It used:

`npm test -- --run src/features/project-workspace src/features/metric-coverage src/features/project-catalog src/features/session-catalog src/shared/api/httpTransport.test.ts src/app/AppPrimaryControlAudit.test.tsx src/app/AppScopedRoutes.test.tsx`

This is a bounded focused suite, not all repository tests.

Root's focused browser receipt is:

`npx playwright test e2e/beta-project-workspace-recovery.spec.ts e2e/beta-coverage-recovery.spec.ts e2e/sweep-01b-accessibility.spec.ts --workers=2`

It passed **29/29 in 1.3m**: six CP18 checks, three CP17 checks, and 20 Sweep
accessibility checks. Strict E2E TypeScript also passed after the fixture
contract fix.

Strict E2E TypeScript and the API check exited 0. A fresh production build
exited 0 with **599 modules**. The bundle-budget check exited 0 and recorded
shell **1,153,792 B**, Agent incremental **549,831 B**, and initial Agent
**1,703,623 B**.

The final disposable real-loopback run passed **26/26 in 27.2s** with exit 0.
Cleanup confirmed listener release, runtime cleanup, temporary-state removal,
zero remaining model runtimes, and no server-thread or startup failure. The
initial static-asset collector false positive (`jsx-runtime` JavaScript) was
corrected by excluding static assets; this did not change production API
behavior. The real-loopback journey covers one session per synthetic project;
the same-project lookup beyond 100 rows is covered by unit and fixture-browser
tests.

The privacy scan passed with exit 0 in **8.86s** (`privacy scan passed`), and
the final diff check exited 0. No broader green status is claimed.

## Owner checks (maximum four)

1. Cancel and retry the initial project-session read; confirm the masthead says
   the indexed count is unknown rather than loading or zero.
2. Start an older-session lookup, cancel or time it out, and retry the same
   bounded start offset without starting analysis.
3. After reaching the explicit 1,000-row continuation, replace transport and
   confirm a fresh page-zero then offset-100 path; change only the selected
   session and confirm the catalog is preserved while older lookup restarts at
   offset 100 without late prior metadata.
4. Verify responsive and keyboard/screen-reader access for loading, Unknown,
   retry, refresh-base, and older-lookup continuation controls.

## Next pointer

CP19 is a source-reviewed candidate only, not an implementation commitment. It
would address bounded recovery for the three ProjectWorkspace session drilldown
reads: stored metrics, latest immutable quality run, and metric readiness. The
source review found cleanup aborts but no local deadline or explicit cancel for
those reads. It changes neither calculators nor analysis semantics.
