# Dedicated consumer history retention

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
