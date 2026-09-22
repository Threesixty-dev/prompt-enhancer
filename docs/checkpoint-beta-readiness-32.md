# CP32 · Bounded context preflight and recovery

Status: **AUTOMATED IMPLEMENTATION AND TESTS COMPLETE**

Scope: bound context-preflight polling and refresh recovery in the local agent
runtime. The implementation gives each preflight attempt a 10-second
deadline, including a hung read and a permanently pending response. Recovery
must remain tied to the exact transport/session/model/turn identity; stale
results must not replace a newer context. A visible **Refresh** action must
restart recovery for the current context.

The implementation must preserve unknown values as unknown. A timeout or
permanent pending state is not converted into a fake zero, successful context,
or task failure, and no backend, model, provider-session, persistence, or
restart behavior is introduced by this checkpoint.

Baseline evidence:

- Existing `AgentRuntimeControl` coverage: 52 tests passed (`373f76`), before
  the bounded-preflight implementation.
- The implementation supplies the per-attempt deadline, hung-read and
  permanent-pending handling, exact identity fences, and explicit Refresh
  recovery.

- The first focused CP32 run passed 57 of 58 tests; its remaining regression
  showed polling stopping after the first lower-revision
  `turn_pending_preflight` receipt (two reads total). A separate poll
  scheduling key was then preserved across that response while retaining the
  same 10-second attempt deadline; the final run passed 58 of 58.

Focused automated evidence:

- `AgentRuntimeControl`: 58/58 passed (`64b589`), including six regressions
  covering timeout, polling, explicit retry, stale identity/transport, and
  GET rejection.
- Build and TypeScript validation passed (`3254a9`), bundle check passed
  (`5e8dbb`), and the existing synthetic runtime-recovery browser flow passed
  4/4 at 320px and 1440px (`ae11d6`).
- The production-built synthetic real-loopback flow passed 27/27 in 31.9s
  (`18b9f3`); its listener was released, temporary state removed, runtime
  cleanup confirmed, and model count remained zero.
- Code privacy validation passed (`f3b11d`).

This checkpoint does not claim beta, full-beta acceptance, release, task
success, or metric authority. The dedicated browser proof for the 10-second
timeout was added and is recorded in [CP37](checkpoint-beta-readiness-37.md):
the pending/hung recovery matrix passes 8/8 at 320px and 1440px. Constraints
remain: synthetic fixtures only; no real provider sessions, models, app
restart, installation, or remote data.
