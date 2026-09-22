# Beta readiness checkpoint 02 — evidence workspace and verification boundary

Status: bounded implementation and automated validation COMPLETE. This does not
declare the entire beta, C07, or release complete.

## Current bounded evidence

The metrics workspace now keeps observed values, coverage, and confidence
separate. Inconsistent observation counts or coverage ratios fail closed as
`Coverage unknown`; complete coverage with an unreported confidence remains
an observed value with neutral `Confidence unknown` copy. This is a presentation
truthfulness repair, not a calibration claim.

The R8 requirement-verification surface now has a synthetic browser checkpoint:
the person explicitly prepares the current reviewed requirements, or inspects
an exact persisted historical revision. The panel makes the source identity,
objective authority, and native acceptance authority distinct; diagnostics are
collapsed by default and stale/error reads have retry guards. Preparation is an
explicit POST only after the person clicks the preparation control; mounting the
panel performs no mutation. Preparation does not run a model, set a metric,
issue an objective pass/fail result, or record native acceptance.

Current integrated receipts are **36/36 frontend workspace/parser/HTTP tests in 4 files
(5.99s)**. The earlier **36/36 in 5 files (4.60s)** and **23/23 focused
subset** remain historical context. Existing backend requirement-verification
coverage is **46/46 across 5 suites (90.35s)**. Six new browser checks pass in
**4.2s**; they exercise an in-memory browser fixture only and are not
claimed as a new full zero-interception R8 workspace journey. Production build,
API contract check, strict fixture/spec TypeScript, and built real-loopback
**16/16 in 23.4s** also pass. The backend receipt includes synthetic
persistence/restart coverage staged in-process; it is not a PC-restart claim.
The production build includes the existing AgentPage **650.94KB** warning.
Full frontend validation is **2906/2906 in 196 files (439.72s)**. Standard
browser coverage is **194 passed, 6 intentional screenshot skips, 0 failed**
in about 3.8 minutes. The final post-test privacy scan also passed after
temporary loopback/browser cleanup; the initial overlapping scan is superseded,
no scanner was weakened, and no user data was removed.

The real-loopback receipt included `listener_released=true`,
`runtime_cleanup_confirmed=true`, `temporary_state_removed=true`, and
`model_runtimes_remaining=0`. No actual app or PC restart occurred, no models
were loaded, and no commit or push is claimed.

The prior checkpoint-01 receipts remain historical and are not silently
recounted as current evidence.

## Click-later owner checklist

1. Open the Metrics workspace and follow Outcome evidence to “Verified
   requirement coverage” on a supported reviewed run; use “Prepare current
   reviewed requirements” and verify that it prepares evidence and does not
   score the metric.
2. Inspect the persisted snapshot, exact source identity, revision, and
   collapsed evidence details.
3. Confirm objective result and native acceptance are separate authorities.
4. Trigger a read failure and use the exact-read retry; verify stale guards.

## Remaining release gates

The readable exact-clause/native-acceptance path and trusted objective issuer
remain open, as do the 4 canonical provider/composition gaps (16 shipped
conditional paths, 0 profile gaps, 4 provider/composition gaps), empirical
calibration, native
actual-model GPU/MCP execution, signed updater/package release evidence, and owner UX review.
There is no 4-gap closure, calibration claim, C07 promotion, or overall beta
claim in this checkpoint. No private content, home paths, screenshots, real
provider sessions, models, or external services are part of this record.
