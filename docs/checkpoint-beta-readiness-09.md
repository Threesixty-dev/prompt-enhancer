# Beta-readiness checkpoint 09

This checkpoint records the bounded Models-to-Agent handoff slice. Bounded
implementation and automated validation are complete; this is not beta/v1 or
release certification.

## Temporary Models chat and explicit Agent setup

Models chat is explicitly temporary: its conversation, draft, reasoning and
partial reply are not saved and are discarded when the Models page is left,
reloaded or closed. “Open saved Agent chat” is an explicit, consent-gated
handoff. The confirmation opens a NEW Agent setup; it copies no messages,
draft, reasoning or history. The only in-memory routing input is the currently
selected model alias (or `null` when no model is selected), delivered once to
the setup bridge. It does not create a session, start or activate a model,
send a message, migrate a transcript, or write storage. Cancel and Escape
preserve the temporary draft/history and active stream and restore focus.

This source boundary is also discarded on transport/platform replacement or
navigation unmount. The handoff is one-shot and remains safe under React
StrictMode; it does not replay setup intent.

The Agent setup then chooses workspace and retention, with model selection
remaining optional; ordinary sidebar/back navigation and unload protection are
not yet claimed.

## Evidence boundary

| Gate | Result |
| --- | --- |
| Root production build | Passed; existing Agent bundle warning remains (Agent bundle 667.34 KB) |
| Models + App/Agent owning tests | 82/82 across 4 files in 9.46s (77 Models + 5 App/Agent) |
| CP09 + CP08 recovery browser | 7/7 in 5.3s, including 3 CP09 journeys |
| Existing model-chat browser | 4/4 in 4.1s |
| Built disposable real loopback | 18/18 in 19.0s; cleanup/listener/temp-state/runtime receipts all confirmed; model runtimes 0, startup failure null, server failed false |
| Strict E2E TypeScript including loopback | Passed (explicit file set with Vite/Node types) |
| Broader AgentPage unit tests | 186/186 in 1 file, 205.09s |
| Privacy and diff checks | Passed (privacy scan 8.04s; `git diff --check`) |

No app restart, GPU/model load, download, provider data, commit or push was
used for this slice. Beta/v1 gates remain open.

## Deferred next candidate

Candidate only, not implemented: add an accidental-loss guard across ordinary
navigation while preserving the explicit temporary-chat boundary.

Retrospective: this candidate was subsequently bounded in checkpoint 10;
checkpoint 09’s historical implementation and evidence receipts remain
unchanged.

See [checkpoint 08](checkpoint-beta-readiness-08.md) for the preceding
Models-page recovery boundary.

## Owner review (maximum four steps)

1. Open Models with no model and verify the temporary note and explicit handoff
   control.
2. Confirm the dialog states NEW Agent setup and that no content is copied.
3. Cancel or press Escape with a draft/active partial reply and verify both
   remain intact; then confirm and verify the blank setup opens.
4. Close setup and verify no new chat appears and model state remains
   unchanged; ordinary navigation loss protection remains an open candidate.
