# Beta-readiness checkpoint 03

Status: bounded feature implementation and focused validation complete; final
beta and release gates remain pending.

## What exists

The Metrics workspace now exposes an explicit, ephemeral exact-clause review
flow. A native user can read the current requirement, acknowledge that exact
text, choose a disposition, and submit one native-confirmed disposition.
Review receipts are short-lived and bound to the current session,
source run, source window, reviewed plan, opportunity set, revision, and
authority head. Expired, mismatched, or stale receipts fail closed. Requirement
text is held only ephemerally for the review; it is not durably stored, and
acceptance is not an objective verification result.

The MCP Store’s unavailable setup-plan action now names its native-window gate
and keeps browser state read-only; it does not imply that a browser can perform
the protected action.

## Current evidence

- Focused MCP/Agent evidence: 37/37; focused 34/34 receipt in three files
  (predating the final reconciliation test).
- New feature-focused validation: 38/38 across four files in 5.76 seconds.
- Backend verification coverage: 72/72 across five suites in 109.53 seconds;
  the dedicated review/production-HTTP flow is 14/14 in 50.34 seconds (86
  non-overlapping checks).
- OpenAPI coverage: 5/5; byte-exact validation is 1/1 in 14.44 seconds after
  UV regeneration. The earlier byte-exact failure was system/runtime mismatch
  evidence, not a waived check.
- Final panel-focused validation: 20/20 in 5.97 seconds.
- Strict fixture TypeScript validation passed.
- API TypeScript validation and production build passed.
- Full browser coverage: 200 passed with 6 intentional screenshot skips in
  approximately 4.2 minutes.
- Full frontend suite: 2915 passed, 2 failed, 2917 total across 197 files in
  555.50 seconds. Failures were an AgentPage artifact-flow timeout and a
  following missing-feedback assertion;
  the isolated rerun passed 2/2 in 12.34 seconds (8.35 seconds of tests), and
  the owning AgentPage suite passed 172/172 in 206.16 seconds with one worker.
  This does not make the one-shot full suite green; timing reconciliation
  remains pending.
- Built real-loopback coverage: 16/16 in 25.1 seconds; cleanup flags were all
  true and zero model runtimes remained.
- Synthetic browser acceptance suite: 12/12 in 7.7 seconds, covering explicit
  accepted native disposition, cancellation, unavailable native capability,
  stale/mismatched review refusal, keyboard use, and 320px layout. The 320px
  case selects unknown but does not submit it; rejected/unknown submission is
  not claimed by this receipt.
- Agent production build passed; the existing 650.94 KB Agent chunk warning
  remains informational.
- Privacy scan passed after removal of an agent-created untracked lockfile;
  scanner behavior was unchanged. Diff check passed.

Historical metrics remain immutable. A current human decision is shown as a
separate receipt and does not rewrite the selected analysis snapshot. Exact
historical GET remains revision-bound; current reconciliation uses an explicit
current-head read (undefined revision) with independent scope validation.

## Still pending

Final broad gates remain pending. The four canonical provider/composition gaps
remain 16 shipped conditional paths, 0 profile gaps, and 4 provider/composition
gaps. Objective issuer controls, calibration, native model/GPU execution,
trusted MCP and external-client runs, updater/package release, and owner UX
review remain open. Full unit/frontend timing reconciliation remains pending.
No full beta-v1 claim is made.

## Click-later checklist

1. In the Metrics workspace, prepare the current reviewed requirements.
2. Open one exact requirement and verify the text is readable and ephemeral.
3. Acknowledge it, choose a disposition, and confirm the native receipt is
   separate from objective results.
4. Verify stale or expired review attempts refuse without mutation.
5. In a browser-only composition, verify the MCP setup action explains the
   native-window recovery path and remains unavailable.

No app or PC restart, model/GPU load, real provider transcript, external
account, commit, or push was used for this checkpoint.
