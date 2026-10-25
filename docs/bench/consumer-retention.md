# Dedicated consumer history retention

## Finished subscriber release - 2026-10-25

- Baseline: reviewed develop `f8492d1`; affected W02/W05/W07.
- Reproduction: the first revision-6 smoke attempt finishes its before
  evaluations, then reports `remote_cleanup_unconfirmed` during generation.
  The consumer reports a finished conversation but has no release receipt.
- Root cause reproduced with SDK/server 1.49.1 and a synthetic ACP server:
  `RemoteConversation.close()` sets the websocket stop flag and joins for five
  seconds, but the receive loop observes that flag only after another event.
  An otherwise idle connection can remain subscribed. The retention guard then
  correctly refuses release with `conversation_still_active`. Both guarded and
  unguarded ACP fixtures reproduce the issue without model calls.
  The original core failure retained only the generic cleanup code, so its
  underlying HTTP response cannot be reconstructed from the stored result.
- Correction: after verifying a finished Bench-owned conversation, send its
  existing state to attached subscribers within the existing two-second budget.
  A stopped SDK client can disconnect. A live or slow subscriber still blocks
  release; the original idle and process-termination checks remain mandatory.
  No subscriber is forcibly detached, model work retried, or history deleted.
- Evidence: 48 affected unit tests pass, including two failing-before
  regressions and bounded slow-subscriber refusal. An isolated consumer with the
  exact candidate source releases both real-SDK fixtures in under 0.1 seconds,
  while preserving the refusal for a subscriber that has not requested stop.
  The new `retention_lifecycle_smoke.py` repeats the actual HTTP/websocket
  lifecycle, checks thread termination, retained history and workspace cleanup,
  and is included in the manual Bench container check.
- Remaining gates: owner review, source promotion, consumer image rollout and
  fresh live qualification. This changes only the consumer compatibility
  boundary; core 0.3.7 and experiment definitions remain compatible. No broader
  acceptance status changes.

The preceding revision-5 interruption was reconciled using the owner's restart
attestation, without claiming independently observed upstream termination.
The reviewed worker, consumer and relay were then deployed with unchanged
environment values and mounts; consumer readiness and relay namespace checks
passed. Revision 6 stopped after one of 15 smoke attempts; its 240 main attempts
remain unsubmitted. The failed smoke's consumer later confirmed runtime release
and workspace cleanup, and its recovery was recorded without replay. Its failed
result and completed before measurements remain preserved.
All 40 observed metric-table cells match the API: nine known before readings,
one unknown and ten absent after readings shown as not recorded. The private
analysis-v2 export retains the failure and passes every manifest hash check.

Date: 2026-10-13. Owner requested retention of bench OpenHands conversations.

## Task card

- Baseline: `2ab65bb`, branch `codex/bench-gateway-access`.
- Affected atlas/gates: W05/W07 and WP05/WP07, within proposed ADR 0025's
  separate private synthetic bench. No general workflow gate closes.
- Outcome: release finished consumer runtimes immediately while preserving
  native OpenHands conversation/event history across restart for inspection.
- Owned paths: core OpenHands adapter/version, dedicated consumer startup and
  retention adapter, deployment recipe, focused tests and evidence documents.
- Bounds: seven days by default, configurable 1-90 days; minute expiry sweep;
  unresolved and cleanup-held operations never expire automatically. No new
  network listener, credential, provider ingestion or inference service.
- Evidence: synthetic adapter failure cases, pinned server/container native
  history, restart, read-only behavior and expiry; no additional model call.

Successful cleanup used to delete the entire OpenHands conversation to stop ACP.
That combined two independent lifetimes. The new capability-gated release closes
the runtime under OpenHands' conversation lifecycle lock, checks the captured
ACP process termination, and preserves its native catalog and files. Core then
confirms workspace cleanup before activating expiry. A durable held receipt
survives interruption between those steps. Repeated acknowledgement never extends
expiry. Retained native history rejects mutation/replay through its HTTP routes.

The adapter isolates the pinned server's internal unload operation because its
public API only supports permanent deletion. SDK/server upgrades must revisit
this boundary. Native history remains separate from the indefinitely retained
Bench result, and the deployment remains a private Agent Server without a
publicly exposed OpenHands UI. The October 8 atlas remains historical.

Validation and live rollout evidence are recorded in the integration review.
