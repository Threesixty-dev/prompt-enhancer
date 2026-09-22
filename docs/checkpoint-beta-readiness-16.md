# Beta-readiness checkpoint 16

Status date: 2026-09-08

This checkpoint records the bounded Sessions Catalog read-reliability
contract. It is not beta, v1, latency, provider-coverage, model,
calibration, native, packaging, or release certification.

## Scope

The Sessions Catalog must show the first 100 validated records promptly. It
must not autoload ten 100-session pages before the first display. An explicit
fetch obtains the next 100-session page, while rendering is independently
bounded to 50 rows per page. Retrieval size and rendering size are separate
contracts.

Loaded-only counts, search, source filters, and the end-of-current-index state
must describe only validated rows currently loaded. They must not be presented
as atomic provider coverage or as proof that an entire provider was read.

Every response envelope and row must pass the shared validator named
`sessionCatalogContract.ts`. The contract requires exact response and row keys,
stable row identity, provenance and date fields. Each catalog call site then
rejects duplicates after shared-page admission. A malformed envelope,
malformed row, missing provenance/date, or duplicate is refused without
replacing the last validated rows.

Initial and subsequent reads have a 15-second local deadline and explicit
cancellation. A failed or cancelled read keeps validated rows visible and
offers a manual retry at the same offset. Later-page errors therefore do not
erase earlier validated pages. Synchronous request coalescing prevents
duplicate reads; stale fencing prevents late responses from changing the
current view. Reload starts fresh at offset zero, and replacing the transport
identity resets provider/source filters and related loaded state.

## Evidence boundary

Bounded automated implementation is **complete**. Root's current receipts are:
frontend **149/149 across 10 files in
34.86s**, followed by the post-format owning Sessions receipt **26/26 across
2 files in 6.46s** (a subset, not added to 149); browser **33/33 in 2.3m**;
Python harness **6/6 in 9.22s**; production build with 599 modules; explicit
strict E2E TypeScript; API; and bundle-budget checks passed. The bundle report
records shell **1,153,781 B**, Agent incremental **549,826 B**, initial Agent
**1,703,607 B**, and 10 deferred boundaries. Built real loopback passed
**24/24 in 22.9s**: 23 healthy no-interception API journeys plus one
intentional CP14 asset-fault case. Cleanup confirmed listener release, runtime
cleanup, temporary-state removal, zero model runtimes and no server-thread
failure.
The final privacy scan passed (exit 0), exact diff check passed, and ports 8765
and 4173 had no listeners at final review.

This bounded result is not beta, v1, SOTA, native, model, hardware, provider,
calibration, packaging, release, or product-completion certification. No app
restart, model load, native/hardware/provider action, commit or push occurred.

## Reproducible receipts

- Frontend owning/adjacent command: `npm test -- --run src/features/project-catalog src/features/session-catalog src/features/metric-coverage src/shared/ui/BoundedListPager.test.tsx src/app/App.test.tsx src/app/AppRouteTraversal.test.tsx src/app/AppPrimaryControlAudit.test.tsx` — 149/149.
- Browser command: `npx playwright test e2e/beta-session-catalog.spec.ts e2e/beta-project-catalog.spec.ts e2e/sweep-01b-accessibility.spec.ts --workers=1` — 33/33.
- Python harness: `uv run --frozen --no-sync python -m pytest -q tests/test_convergence_loopback_harness.py` — 6/6.
- Final build, API, bundle-budget, and strict E2E TypeScript checks passed; strict E2E used the explicit CP15/CP16/loopback file list rather than the normal config.
- Built loopback: `uv run --frozen --no-sync python tests/support/convergence_loopback_runner.py --skip-build` — 24/24.

## Owner checks (maximum four)

1. With a synthetic catalog larger than 100 rows, confirm the first 100
   validated records display promptly, the render page is 50 rows, and the
   explicit next-page action requests offset 100.
2. Confirm counts, search, source filters, and end-of-current-index wording
   remain limited to loaded validated rows and never imply atomic provider
   coverage.
3. Exercise malformed/duplicate envelope and row refusal, timeout,
   cancellation, same-offset manual retry, and a later-page failure; confirm
   earlier validated rows remain visible.
4. Exercise coalescing, stale late responses, reload, and transport-identity
   replacement; confirm offset-zero reload and filter reset behavior.

## Next pointer

Historical follow-on: the CP17 MetricCoveragePanel read-recovery slice is
recorded in [beta-readiness checkpoint 17](checkpoint-beta-readiness-17.md).
It remains separate from CP16; consult CP17 for its bounded evidence and
pending root receipts.
