# Beta-readiness checkpoint 21

Status date: 2026-09-08

Status: **bounded automated implementation complete; owner review queued**.

This checkpoint covers a bounded Agent workspace-navigation outcome: synthetic
file discovery/search, locating distant lines in an open editor, and preserving
or discarding an unsaved draft through the existing confirmation boundary. It
does not add file-write, native, provider, model, network, beta, v1, packaging,
or release authority.

## Scope

The implemented navigation remains read-only. A same-file recorded-line jump
uses the current draft without another file read; a different file keeps the
existing discard guard. Local literal find supports case matching, next and
previous controls, Enter and Shift+Enter, with Ctrl/Cmd+F and Ctrl/Cmd+G scoped
to the editor. Cursor output uses native textarea UTF-16 positions; an
out-of-range recorded line is explicit. Read ownership fences requests and
post-load focus. Exact reviewed-write boundaries are unchanged.

The browser fixture mounts the real AgentWorkspacePane with only fictional
in-memory data: two editable files, a long line, and a distant search result.
It exercises focus, selection, scroll position, local find next and previous,
go-to-line, keyboard escape, and the existing keep-draft/discard confirmation
choices. The fixture makes no HTTP requests, native calls, writes, or model
requests.

## Evidence boundary

Root reproduced **1/1 red regression in 3.73s** in the focused workspace
navigation unit test: the expected selection started at character offset 20 in
a three-line fixture while the actual selection started at offset 69. This is a
baseline only, not implementation evidence.

Root's backend receipt is:

`uv run --frozen --no-sync python -m pytest -q tests/test_workspace_read_boundaries.py tests/test_workspace_write_boundaries.py tests/test_workspace_discovery.py`

It passed **93/93 in 9.51s**.

Root's corrected focused workspace/editor receipt passed **84/84 across six
files in 18.69s** (chunk `2c8e8b`). From the frontend working directory, its
exact PowerShell command was:

`$env:DEBUG_PRINT_LIMIT = '400'`

`npm test -- --run src/features/agent/AgentWorkspacePane.navigation.test.tsx src/features/agent/AgentWorkspaceEditor.test.tsx src/features/agent/agentEditorNavigation.test.ts src/features/agent/AgentWorkspacePane.test.tsx src/features/agent/AgentWorkspaceDiscoveryPanel.test.tsx src/features/agent/AgentRouteBoundary.test.ts --reporter=dot`

Final strict E2E TypeScript passed with exit 0, including the new browser
fixture and loopback coverage. The CP21 browser receipt is:

`npx playwright test e2e/beta-workspace-navigation.spec.ts --workers=2`

It passed **9/9 in 5.1s**.

Root's adjacent workspace workflow browser receipt is:

`npx playwright test e2e/workflow-panels.spec.ts --grep 'workspace|Files|file|artifact' --workers=2`

It passed **20/20 in 23.3s**.

The disposable real-loopback runner passed **27/27 in 31.0s**:

`uv run --frozen --no-sync python tests/support/convergence_loopback_runner.py --skip-build`

Its cleanup confirmed released listeners, zero remaining runtimes, runtime
cleanup, and temporary-state removal. The production build and bundle budget,
API check, and strict TypeScript check are green. Final bundle sizes are shell
**1,153,808 B**, Agent incremental **550,096 B**, initial Agent **1,703,904 B**,
and Workspace deferred **110,651 B**.

The full Agent run (chunk `11da50`) recorded **715 passing and two failing of
717 across 44 files in 284.56s**, exiting 1. Both failures are known
pre-correction test-harness failures in `AgentWorkspaceEditor.test.tsx`: a
wrapper remount lost owner-reset focus, and the same remount invoked a duplicate
token twice. The corrected focused **84/84** receipt above supersedes those two
cases; the other 715 passed. No third full-Agent run is claimed.

Final privacy scanning passed:

`uv run --frozen --no-sync python scripts/privacy_scan.py`

The whitespace/diff check passed with exit 0:

`git -c core.safecrlf=false diff --check`

The final production TypeScript build passed with exit 0:

`npx tsc -b`

The final listener census found no listeners on loopback ports 8765 or 4173.

No actual application restart or reload, and no model use, was required for
the CP21 evidence. This bounded evidence does not establish beta, v1, native,
model, packaging, or release readiness.

## Owner checks (maximum four)

1. In a real workspace-file navigation surface, open a distant recorded
   discovery/search position and confirm the editor has focus, selects that
   whole line, and scrolls it into view without changing content; the bounded
   search preview is not rechecked against the file.
2. Use local find next, previous, and go-to-line against the open synthetic file;
   confirm direction, selection, and line range are explicit.
3. Make a dirty draft, attempt to leave it, and verify local Escape and Keep
   draft preserve the text while explicit **Discard and open file** opens the
   requested other file.
4. Repeat keyboard navigation and disclosure/confirmation flows at 360px and
   1440px; confirm no page overflow, no console/page errors, and no transport
   write calls.

## Next pointer

No next implementation checkpoint is proposed.
