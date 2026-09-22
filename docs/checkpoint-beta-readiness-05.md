# Beta-readiness checkpoint 05

Status: bounded automated validation complete; owner/native/model/release
acceptance remains open. This is a bounded checkpoint and does not claim beta,
beta-v1, or release completion.

## Scope

The Agent composer now supports model-independent, in-memory plain-text
drafting for each chat. A user may write while a session has no selected model,
while its model is stopped, or while model status is loading or disconnected.
The draft remains scoped to that chat and survives chat/model changes during
the current app run. Dedicated-window focus follows the same editable draft
path.

Sending remains explicit and runtime-authority-bound. Form submit, Ctrl+Enter,
Command+Enter, and the Send control all retain the existing readiness guard;
none starts, loads, selects, or implicitly activates a model. Prompt review is
unchanged and remains an explicit no-send action. Attachment capability and
mutation gates are unchanged.

Closing sessions, history-write failures, and command-cleanup quarantine still
protect the composer as before. Drafts are not persisted across an application
restart; no backend or new storage path was added.

## Evidence boundary

| Gate | Current result |
| --- | --- |
| Owning AgentPage tests | **183/183 passed** (final owning-file rerun, 221.27s) |
| Production build | **Pass**; existing AgentPage 654.22 KB chunk warning remains |
| Built disposable real-loopback browser | **16/16 passed** (18.9s); listener released, temporary state removed, cleanup confirmed, zero model runtimes |
| Strict frontend TypeScript | **Pass** |
| Privacy checks | **Pass** |
| Final full-browser rerun | **206 passed, 6 intentional screenshot skips, 0 failed** (3.6 min) |

An earlier full-frontend snapshot (2928 passed / 7 failed of 2935) is retained
as historical evidence only: the failures were stale stopped-input
expectations and were corrected in test-only changes; it is not a clean
2935-test run. The final browser result supersedes the historical 200-pass /
6-failure browser snapshot after test-only corrections. The loopback result is synthetic disposable backend/browser
evidence, not installed-app, native, hardware, or real-model validation.

No native click-through, model/GPU load, application reload/restart, real
provider data, commit, or push was used for this checkpoint. Checkpoint 04's
attachment evidence remains historical and unchanged; this checkpoint does not
replace or broaden it.

## Owner click-later checks

1. Open a chat with no model or a stopped model, type a draft, switch chats and
   return, and confirm each chat keeps only its own in-memory draft.
2. With a draft present and the model unavailable, click Send and try
   Ctrl+Enter and Command+Enter; confirm no model starts and no turn is sent.
3. Start the model explicitly, confirm the exact draft remains, then send it
   manually. Open a chat with a draft and use its normal close flow to confirm
   the unsent-work warning; verify attachment controls remain capability-gated
   and no model starts merely because a draft was typed.

## Next candidate checkpoint

Runtime-readiness uncertainty and recovery audit. This is only a candidate
follow-up; it is not implemented by checkpoint 05.
