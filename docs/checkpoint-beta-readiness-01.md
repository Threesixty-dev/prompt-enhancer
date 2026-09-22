# Checkpoint: beta readiness 01

Status: bounded beta-readiness checkpoint validated; this is not a beta-release claim.

## Changes in this pass

1. Artifact viewer body: `min-width: 0` min-content shrink guard,
   `overscroll-behavior: contain`, and `scrollbar-gutter: stable` in
   `frontend/src/features/agent/AgentArtifactsPanel.css:352-360`, with two
   synthetic real-browser checks in `frontend/e2e/beta-artifacts.spec.ts`.
2. Placement Refresh now retries the same selection.
3. MCP Create/Prepare explanations distinguish native, transport,
  project-load, error/empty, and busy states; protected MCP project Retry
  handles stale results without replacing a newer project choice.

No production metric or adapter implementation changed. Fixture typing fixes
were test-only (including typed tuples, retained attachments, owned `Blob`
copies, and synchronous throw handling). No production change was made for
the earlier AgentPage test failure.

## Confirmed receipts

| Gate | Result |
| --- | --- |
| Production build | Pass; existing AgentPage 650.94 KB warning |
| Real loopback | 16/16 in 19.7s; cleanup listener and temp removal confirmed; models loaded 0 |
| Component checks | MCP 31/31; runtime 34/34 |
| Artifact browser checks | 2/2 in 6.3s |
| Standard browser matrix | 188 passed, 6 intentional screenshot skips, 0 failed in 3.5 min |
| Strict TypeScript | Pass for three new specs and workflow fixture (Node/Vite/client configs) |
| API / privacy / diff checks | Pass |
| Full frontend unit suite | 2,869/2,869 in 192 files (292.69s) |

The initial full-unit receipt (2,868 passed / 1 failed of 2,869) was superseded
by the corrected final receipt above. The close/resume failure was repaired by
awaiting UI/catalog settling and making the row click synchronous; the focused
corrected test passed 1/1 in 5.50s.

## Click later

- Manually verify Placement Refresh retries the currently selected placement
  after a recoverable failure.
- After a project-list failure, manually verify Retry projects restores the
  project choice; while retry runs, changing project must retain the newer
  choice.
- Manually verify artifact viewer wheel scrolling stays inside the viewer and
  Escape closes it with focus returned to Preview.

## Remaining gates

- Re-check the four metric adapters and calibration (unchanged).
- Exercise real-model native lifecycle, external MCP, and signed-updater /
  Windows installer gates separately.
- Restart/GPU-load validation remains unperformed; commit and push remain
  outside this checkpoint.
