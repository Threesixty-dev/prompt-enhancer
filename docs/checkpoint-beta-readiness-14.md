# Beta-readiness checkpoint 14

This checkpoint records the bounded Agent initial-load dependency-graph audit.
It is not a latency, beta, v1, or release certification.

## Measured boundary

The Vite manifest is traversed by imports, dynamic imports, CSS and emitted
asset edges with deduplication and fail-closed missing-edge checks. The dated
read-only observation was shell **1,153,289 B** plus Agent **867,535 B** =
**2,020,824 B**. The final manifest-backed measurement is shell **1,153,593 B**,
Agent incremental **549,826 B**, and full initial Agent **1,703,419 B**—about
37% lower for Agent and 16% lower for the full union. These are bytes only; no
startup latency or network timing was measured. The former 678 KB main-chunk
warning is gone, but its reduction alone is not a performance certification.

Agent keeps the conversation shell eager. Nine new wrapper surfaces (Workspace,
Artifacts, MCP store, change-set, controller, MCP project-tools,
native-acceptance, readiness and TeamFolders) are demand-loaded; PDF remains
the existing tenth nested-lazy boundary. Render
failures retain a truthful local Retry path, but import failure is contained
honestly: preserve the draft and require explicit reload; there is no
auto-reload or futile Retry. Real Chromium readiness import failure cached the
failure, so Retry did not recover; this is not declared fully recovered.

## Evidence and limits

The dependency check and synthetic graph tests pass **6/6**; they cover shared CSS
deduplication, side-effect edges, malformed/missing data and boundary
separation. Bounded automated implementation is complete: owning frontend
tests are **209/209 across five files in 217.67s**; synthetic responsive and
accessibility browser tests are **97/97 in 2.5 minutes**. Production build,
strict E2E TypeScript and API checks pass; helper/ReviewDrawer checks are
included in the 209 and are not double-counted. The
real loopback receipt is **22/22 in 21.5s**: 21 healthy zero-interception
journeys plus one explicit asset-fault containment case; cleanup is confirmed,
all cleanup flags are true, and zero model runtimes remain. These are not
latency measurements, and PDF import-failure recovery is not claimed.

No backend, model, native, adapter, calibration, packaging or release closure
is claimed. The canonical metric boundary remains **16 shipped conditional
paths, 0 profile gaps, 4 provider-adapter gaps**. No app relaunch, provider
access, model execution or external client action occurred.

## Owner checks (maximum four)

1. Open Agent and confirm the conversation appears before opening secondary panels.
2. Open Workspace, Artifacts, MCP/controls and PDF surfaces and confirm each is
   demand-loaded with honest loading/error state; render failures may be
   retried, while import failure asks for draft-preserving explicit reload.
3. Exercise a failed secondary-panel load and verify chat remains usable.
4. Record Chromium import-failure containment and explicit reload separately;
   full cached-import recovery remains pending.

## Next pointer

After CP14, the queued safe candidate is [CP15 Project Catalog retrieval-cap readiness](checkpoint-beta-readiness-15.md), covering Project catalog “Load more” for the
100-session retrieval cap: cover counts/search and preserve selections across
pages/filters, but clear selection/comparison and fence outstanding work when
transport identity changes. Use a synthetic 100+ fixture with stale,
failure/cancellation, keyboard and narrow coverage. This is distinct from
30-row rendering pagination and is not active during CP14 (maximum four owner
steps).
