# Beta-readiness checkpoint 20

Status date: 2026-09-08

Status: **bounded automated implementation complete; owner review queued**.

This checkpoint covers session-radar read recovery and truthful compact
presentation. It does not change metric calculations, analysis authority,
calibration, model behavior, beta readiness, v1 status, native integrations,
packaging, or release status.

## Scope

The implemented read policy is canonical Metric V2 receipt first, then typed local
receipt, then the legacy committee receipt. Stored session metrics are metadata
only: they are consulted after a missing latest model-analysis snapshot response
(404) or an undefined latest-snapshot method, and can establish only an empty
or data-gap state. An empty metadata response remains explicit absence;
nonempty metadata establishes a data gap, never chart values. Sources are
never mixed.

The UI scope is four keyboard-accessible radar groups over the canonical 20
metric keys. Valid finite numeric readings remain numeric, including zero.
Missing, pending, not-applicable, abstained, and error states are not drawn as
zero; the shared chart omits them from numeric dots, areas, and gap-crossing
edges. Provenance and state detail remain bounded to the selected group.

## Baseline

Root reproduced **7/7 red tests in 3.15s**. This is a failure baseline only;
it is not evidence that the CP20 implementation or browser presentation is
complete.

## Evidence boundary

Root's backend receipt is:

`uv run --frozen --no-sync python -m pytest -q tests/test_metric_publication_v2.py tests/test_prompt_check.py tests/test_session_metric_pack_provenance.py`

It passed **40/40 in 15.43s**.

Root's focused frontend receipt is:

`$env:DEBUG_PRINT_LIMIT = '400'` followed by

`npm test -- --run src/features/session-radar src/features/prompt-check src/features/project-workspace src/features/model-ensemble/ModelEnsembleRadar.test.ts src/features/model-ensemble/ModelEnsemblePanel.test.tsx src/shared/api/metricPublicationV2Contract.test.ts src/app/AppPrimaryControlAudit.test.tsx src/app/AppScopedRoutes.test.tsx --reporter=dot`

It passed **237/237 across 11 files in 42.00s**. This is a focused suite, not
all frontend tests.

Root's focused browser receipt is:

`npx playwright test e2e/beta-session-radar.spec.ts e2e/beta-session-drilldown-recovery.spec.ts e2e/beta-project-workspace-recovery.spec.ts e2e/sweep-01b-accessibility.spec.ts --workers=2`

It passed **43/43 in 1.4m**: nine CP20 checks, eight CP19 checks, six CP18
checks, and 20 accessibility checks.

Strict E2E TypeScript passed with exit 0:

`npx tsc --noEmit --strict --target ES2022 --module ESNext --moduleResolution Bundler --esModuleInterop --skipLibCheck --jsx react-jsx --types vite/client,node,@playwright/test e2e/beta-session-radar.spec.ts e2e/fixtures/session-radar.tsx e2e/beta-session-drilldown-recovery.spec.ts e2e/loopback-built.spec.ts e2e/loopback-lazy-recovery.spec.ts playwright.loopback.config.ts`

The generated API check (`npm run check:api`) passed. The production build
(`npm run build`) and bundle-budget check (`node scripts/check-agent-bundle-budget.mjs`)
passed. The final bundle sizes are shell **1,153,808 B**, Agent incremental
**550,096 B**, and initial Agent **1,703,904 B**.

The disposable real-loopback runner passed **27/27 in 32.7s**:

`uv run --frozen --no-sync python tests/support/convergence_loopback_runner.py --skip-build`

Cleanup confirmed released listeners, zero remaining model runtimes, runtime
cleanup, temporary-state removal, and no startup failure.

The privacy scan passed:

`uv run --frozen --no-sync python scripts/privacy_scan.py`

The whitespace/diff check passed:

`git -c core.safecrlf=false diff --check`

Final cleanup left both loopback ports 8765 and 4173 with listener count zero.
No actual application restart or reload, and no model use, was required for
this checkpoint. Owner review remains queued. No broader completion, beta, v1,
model, native, or release claim is made.

## Owner checks (maximum four)

1. Switch all four radar groups by keyboard and verify each selected group has
   its own bounded numeric/state presentation without horizontal overflow.
2. Verify canonical V2 wins over conflicting typed and committee values; then
   verify typed and committee are selected only when their higher-priority
   source is absent.
3. Verify a measured zero remains numeric while unknown, pending,
   not-applicable, abstained, execution-error, invalid, and missing rows are
   excluded from numeric geometry and clearly labelled.
4. Cancel, retry, and replace the radar owner while reads are pending; confirm
   late results cannot replace the current session/transport state, while 404
   metadata absence stays distinct from a content-free read failure.

## Next pointer

No next checkpoint is proposed. A later source review may identify a bounded
candidate, but none is an implementation commitment here.
