# Beta-readiness checkpoint 07

Status: bounded implementation and automated validation complete. This is a
bounded checkpoint and does not claim beta, beta-v1, or release completion.

## Scope

The Agent composer gains an explicit idle-chat generation-settings editor under
Model & context for temperature, top-p, maximum output tokens, and thinking.
Settings are persisted through a revision-fenced API for sessions using local
history retention. Metadata-only chats remain current-run state and do not gain
new profile retention.

A chat can be created, opened, and edited without a model, including a
model-neutral chat. When output budget reaches or exceeds known context, the
chat is recovered with a clear capacity warning rather than abandoned. No
reserve or success guarantee is invented; exact tokenizer preflight remains at
send time.

The update is explicit and idle-session-only. It cannot change permissions,
model, workspace, instructions, retention, or ownership; it does not
auto-send or auto-start a model. Existing draft, history, chat-switch,
active/pending, closing, cleanup, transport, stale-response, and failure
guards remain in force.

The implementation also keeps generation editing model-independent for chat
creation/opening, retains typed drafts through model selection and settings
reload, uses a revision/content/project-fenced save, and preserves the
last-request/context receipt when parameters change. A known-context budget
that cannot fit is refused with configured capacity evidence; no reserve or
guarantee is invented. Conflict recovery reloads the remote settings before a
second explicit save. Metadata-only settings remain current-run state.

## Deferred issue

The confirmed ModelsPage issue is outside checkpoint 07: a `Promise.all`
runtime read failure currently unmounts a direct chat, losing its draft/history
and aborting a reply while hiding acquisition despite a valid catalogue. It is
deferred to a separate future checkpoint and is not fixed here.

Checkpoint 08 records the bounded Models-page recovery slice; see
[checkpoint-beta-readiness-08](checkpoint-beta-readiness-08.md).

## Evidence boundary

The following root receipts are recorded.

| Gate | Final result |
| --- | --- |
| Backend catalog/history/parameter suite | 90 passed in 22.00s |
| HTTP transport focused suite | 6 passed in 2.00s |
| OpenAPI contract/schema checks | 6 tests in the combined 29-test export/schema run; the 23 duplicated parameter-contract checks are not counted again |
| API check and explicit strict TypeScript checks | Passed |
| Full frontend regression | 2,979/2,979 across 200 files in 527.75s |
| Owning generation-settings/runtime-control tests | 69/69 in 12.61s after the final retention-note fix |
| Production build | Passed; existing AgentPage chunk warning at 666.76 KB (>500 KB) |
| Focused accessibility/regression follow-up | 13/13 in 13.6s after correcting two production descriptions and keyboard order |
| Final post-build disposable loopback | 17/17 in 19.4s; browser exit 0, startup ready, listener released, temporary state removed, runtime cleanup confirmed, zero model runtimes, no server-thread or startup failure |
| Final privacy scan and diff check | Privacy scan passed in 7.58s; diff check passed |

The first full-browser pass recorded 213 passed, 2 failed, and 6 intentional
product-tour screenshot skips in 4.1 minutes. Both failures were corrected in
production and covered by the focused 13/13 follow-up; this is not represented
as a clean 215-test rerun. The first built-loopback pass had one selector
failure; after its test-only correction, 17/17 passed in 25.5s, and the final
post-build run above confirmed the cleanup invariants. The early privacy scan
ran concurrently with live disposable loopback traces and is not evidence;
the final post-cleanup scan is the recorded privacy result. No scanner rule or
exclusion changed. The app build was not used to restart or reload the user's
installed app. No native app restart, model/GPU load, installation, real
provider data, commit, or push was performed. Owner/native/GPU/model/install/
restart/release gates remain open.

## Owner click-later checks

1. Open an idle chat, edit each generation setting, save it, switch chats and
   return, and confirm the values are revision-consistent and drafts/history
   remain intact.
2. Open or create a model-neutral chat and edit settings without starting a
   model; confirm no model starts and no message sends.
3. Enter an output budget at or above the shown known capacity and confirm the
   clear refusal/recovery warning leaves the chat and draft available.
4. While a chat is active, pending, closing, or cleanup-quarantined, confirm
   settings editing is unavailable or safely refused.

## Next candidate checkpoint

The deferred ModelsPage runtime-read/unmount recovery issue was delivered
separately in [checkpoint 08](checkpoint-beta-readiness-08.md); checkpoint-07
does not absorb its evidence or close owner/native/model/release gates.
