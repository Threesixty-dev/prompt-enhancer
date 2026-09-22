# Beta-readiness checkpoint 04

Status: bounded automated implementation validated. This is not a whole-beta,
beta-v1, or release-complete claim.

## Current implementation

- Attachment-only turns now revise correctly.
- Attachment-aware prepare retry/regeneration creates a child before the
  selected turn, preserving source/effects without auto-send.
- The ephemeral metadata checklist requests an exact child-owned staged-file
  match (hash, type, and size), or an explicit per-item omission.
- Backend remaps copied-prefix IDs; AgentPage reads the branch's actual
  retained history without remapping it. The metadata checklist matches fresh
  staged child files.
- Recovery on child-read failure, the 320px long-name CSS case, and the
  checklist-only draft-close warning are included in the current validation
  scope. Child-history hydration is an AgentPage concern.
- The prepared branch draft uses fresh IDs, preserves the close warning, and
  exposes the stable keyboard-omit control.
- The prior combined artifact test was split into two independent tests for
  test isolation; budgets were unchanged.

## Confirmed evidence

| Gate | Result |
| --- | --- |
| Backend attachment tests | 28/28 in `test_agent_attachments.py` (9.01s) |
| Split artifact tests | 2/2 (16.30s) |
| Agent-focused browser checks | 4/4 in 6.9s (final; supersedes 5.3s receipt) |
| Production build | Pass; existing AgentPage 654.03 KB chunk warning |
| Full browser matrix | 204 passed, 6 intentional screenshot skips, 0 failed in 3.7 min |
| Strict fixture TypeScript | Pass |
| Privacy and diff checks | Pass |

Latest full-frontend snapshot: 2,929 passed / 2 failed of 2,931 tests across
198 files in 469.39s. The failures were the new checklist-focus regression
and a new close test targeting the wrong legacy button; both were fixed after
the snapshot. Existing artifact tests passed. The corrected owning-file rerun
passed 197/197 (AgentPage 179, Checklist 7, TurnDetails 11) in 287.18s. The
final focused browser rerun passed 4/4 in 6.9s. The 2,929/2,931 snapshot above remains historical evidence: both
failures were repaired, but this does not claim a single clean 2,931-test run.
Checkpoint 03's historical evidence remains unchanged in its own report and
is not treated as a current whole-beta or beta-v1 completion claim.

## Still pending

Broader beta/v1 validation remains open, including recovery, provider/model/
native execution, trusted or external MCP, updater/package release, and owner
UX review. All work in this checkpoint was offline: no model/GPU load, restart,
application reload, installer check, real provider data, commit, or push was
used.

## Automated checks

Failure injection for child-read recovery belongs in automated tests, not the
owner click-through checklist.

## Owner click-later checks

1. Open a saved text-and-file turn, choose Prepare, and confirm it remains a
   draft and does not run.
2. Re-select the same file with Attach and verify the exact-file state and
   Send control.
3. Remove the file, choose explicit Omit or Require, and verify Send behavior.
4. Retry an attachment-only turn, navigate away and back, then close it and
   verify the unsent warning.
5. At a narrow window, verify long names and controls remain readable.

## Next checkpoint

Checkpoint 05 is model-independent text drafting: allow typing while the model
is stopped while Send remains blocked; preserve closing, history, and cleanup
guards, with no attachment or model-authority changes.
