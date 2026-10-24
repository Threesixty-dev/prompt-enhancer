# Run budgets and deadline reporting

Bench has separate limits for an entire run and an individual core attempt.
The worker's default whole-run limit is 1,800 seconds, including readiness and
all attempts in that run. A 180-second per-attempt limit does not give every
attempt another 1,800 seconds. Cleanup follows cancellation and must still be
confirmed before another run can use held capacity.

Preflight validates the definition, requests and registered core artifact. It
does not inspect the deployed worker's run budget or guarantee that every
selected attempt will fit. Confirm that budget with the operator before a large
batch. Keep the sum of attempt limits comfortably below it, allowing additional
time for startup, polling and cancellation. The robustness plan uses one case
and its four variants per standard run: four 180-second limits total 720 seconds.
Boundary selections use one attempt per run.

Each deliberate run needs its own private admission receipt. Observation timeout
is also independent: a client `wait` timeout does not cancel the worker. Reuse
the original receipt to recover admission after a connection failure. Keep
interrupted history, confirm remote stop before reconciliation, and use explicit
retry lineage for an intentional replacement selection. Do not count skipped
attempts as completed or pool duplicate successes into coverage.

## Reporting correction - 2026-10-24

Task / atlas / gates: preserve an observed whole-run cancellation cause;
MA18 and W02/W07, bounded failure reporting and recovery evidence.

Baseline: reviewed development source `ca1af3a`. During the frozen core 0.3.4
qualification, a 68-attempt batch reached the deployed 1,800-second run deadline
after 56 successes. Its active attempt returned an uncertain remote state. The
worker stored `core_uncertain`, losing the known reason it had sent cancellation.

The candidate stores `run_deadline_exceeded` when the worker issued cancellation
because that deadline expired and then received a non-success terminal result.
It preserves the core result, attempt status, remaining-attempt disposition,
cleanup and reconciliation requirements. User cancellation remains distinct,
including when waiting for its acknowledgement crosses the run deadline. Core
failures received without deadline cancellation retain their existing code.
Unconfirmed transport, retention and cleanup failures retain their specific
error handling. No historical records are rewritten.

Four deterministic regressions fail before the correction. All 64 affected
worker, storage and export tests pass afterward, including 16 combinations of
deadline/user/core causes and terminal outcomes. The synthetic clock avoids
timing-dependent tests; no model call is made by these tests.

Source review and a separately authorized worker deployment remain open. The
running qualification keeps its frozen deployment and uses bounded selections.
This correction does not establish complete qualification, automatic capacity
planning, independent onboarding or general product acceptance.
