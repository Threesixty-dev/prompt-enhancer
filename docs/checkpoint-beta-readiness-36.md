# Beta readiness checkpoint 36 — own-window handoff ownership

Status: IN PROGRESS. This is a synthetic window-message lifecycle repair, not
native acceptance, provider execution, model, release, or beta completion.

## Scope

An own-window handoff could be lost when a same-owner catalog refresh replaced
the session-list array while its exact target lookup was pending. The active
chat safely remained in place, but the requested dirty-workspace confirmation
could never be reached. The listener now owns each selection by revision while
still cancelling on a changed transport or active chat. It reads the current
session list and workspace-dirty state at commit time: a newer selection wins,
and an edit made during lookup still requires the normal discard confirmation.

The settings/files regression uses only user-triggered lazy-import settlement
in its test; it neither preloads panels nor changes the existing timeout.

## Evidence so far

The prior full AgentPage run was 188/190 with two failures (`9c7acf`). A
deterministic same-owner catalog-refresh handoff test reproduced the dropped
confirmation (`b033be`); its stale-before-target case, a newer-target-before-
older-resolution case, and a clean-then-dirty lookup case now pass in the
focused 3-test run (`b9b037`). Channel and exit-risk coverage is 19/19 green
(`0a6124`), and the production build is green (`a745db`) after confirming port
8765 was absent.

The current full owning AgentPage suite is 191/191 green (`f73966`); this is
the current suite, not a historical 216-test aggregate. The fresh
built-loopback gate is 28/28 green (`51691f`) with cleanup confirmed and zero
models. The initial complete frontend suite later reached its terminal result:
**3,426 passed and 2 failed across 240 files** (`36ab9b`); see the [CP37
checkpoint](checkpoint-beta-readiness-37.md). This is not a green full-suite
result and no broader completion claim is made here. Privacy also remains OPEN/RED: scan `b755ae` found two residual
synthetic `.tmp-cp34-privacy` databases. Owner walkthrough, native acceptance,
provider/model execution, release, beta, and v1 acceptance remain unverified.
