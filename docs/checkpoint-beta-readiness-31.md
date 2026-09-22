# CP31 · Capability-aware retained-chat Resume and Export

Status: **AUTOMATED UI IMPLEMENTATION AND TESTS COMPLETE**

Scope: make the retained-chat controls truthful when a local transport supports
only some retained-history operations. This is a frontend capability and
interaction checkpoint only: it introduces no backend endpoint, persistence,
provider, session, or authority semantic change.

`AgentPage` owns the selected local-history receipt, abortable Resume and
Export operations, their busy states, and the current transport. It passes
independent `resumeSupported` and `exportSupported` flags to
`RetainedHistoryView`; those flags reflect the presence of the corresponding
local transport operation, rather than assuming the two capabilities travel
together.

Acceptance matrix:

| Retained-view condition | Resume | Export |
| --- | --- | --- |
| Neither operation is provided | Disabled as **Resume unavailable**, with a local-transport explanation | Disabled as **Export unavailable**, with a local-transport explanation |
| Only one operation is provided | The missing operation stays disabled and explained | The supported operation remains independently available when its ordinary guards pass |
| Ready, supported, unarchived receipt | **Resume chat** is available | **Export JSON** is available |
| Retained history loading or errored | Disabled; no operation is inferred from incomplete history | Disabled; no operation is inferred from incomplete history |
| Archived receipt | Disabled as **Restore chat before resuming** | Export remains governed by its own supported/ready/busy guards |
| Operation in flight | Its own control says **Resuming…** or **Exporting…** and is disabled | The other supported control remains independent; selection or transport replacement aborts/fences stale work |

Parent wiring keeps the existing retained-history identity and transport fences:
Resume validates the returned session/project/retention and history cursor
before adopting a live chat; Export binds the selected catalog/history
revisions and produces a local object-URL download only after the same
selection remains current. Capability absence therefore has a visible,
accessible explanation instead of a silent callback no-op.

Focused automated evidence:

- Capability matrix: 9 passed (`f66443`).
- Parent retained-history/resume coverage: 20 passed (`94b41d`) after the
  reviewed deterministic ready-project wait (`a1eeff`).
- Conversation-navigation coverage: 9 passed (`0baad4`) at its original
  timeout. An earlier parallel timeout (`d3a47a`) was isolated and resolved;
  these are not a combined aggregate claim.
- Production build passed (`115a32`; initial build receipt `8f8203`) and the
  final diff is clean (`a9f74e`).
- Final privacy validation passed (`b82835`).

There is no dedicated new browser suite for this small UI gate. Native
walkthrough, provider-session exercise, beta/v1 acceptance, and release remain
unverified. This checkpoint does not claim the software beta or v1/release is
complete. Constraints remain: synthetic data only; no app restart, model
loading, install, private provider data, commit, or push.
