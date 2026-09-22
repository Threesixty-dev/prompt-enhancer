# Beta-readiness checkpoint 10

This checkpoint records the bounded temporary-chat discard-protection slice.
Implementation and automated validation are complete; this is not beta, v1,
or release certification.

## Temporary Models chat protection boundary

The temporary Models chat remains unsaved. Sidebar/direct navigation and
app-owned browser History API Back/Forward transitions are guarded while draft,
history, a partial reply, or an in-flight reply is at risk. New conversation
requires explicit confirmation; Keep/Cancel/Escape preserve the draft,
history, partial output and active stream, while explicit Discard aborts once
and ignores late callbacks. `beforeunload` is installed only while content is
dirty; no IndexedDB or chat-storage persistence is implied. The CP09 Agent handoff remains a single-consent action with no copied
messages, draft, reasoning or history.

Browser history entries that are foreign or unindexed cannot be safely
auto-addressed: the chat stays mounted and offers an explicit Return to Models
action after Keep/Escape with an explanatory notice. This does not claim
protection against force-kill, native close, crash, or persistence.

## Evidence boundary

| Gate | Result |
| --- | --- |
| LocalModelChatPanel focused tests | 34/34 passed |
| Strict production typecheck (`tsc-b`) | Passed |
| Models owning tests | 81/81 across 2 files in 6.31s |
| App + shared-platform tests | 217/217 across 16 files in 38.64s (13 focused overlaps) |
| New App Models-navigation ownership tests | 6/6 in 1 file in 6.11s |
| Production build | Passed; existing Agent bundle warning (667.34 KB) remains; Models bundle 53.58 KB |
| CP10 + CP09 + CP08 recovery browser | 15/15 in 7.7s (8 CP10 + 3 CP09 + 4 recovery) |
| Existing model-chat browser | 4/4 in 4.9s |
| Built disposable loopback | 19/19 in 22.0s; startup/listener cleanup, temp removal, and runtime cleanup true; model runtimes 0, server failed false, startup failure null |
| Strict explicit E2E TypeScript | Passed |
| Privacy and diff checks | Passed (privacy 7.84s; `git diff --check`) |

No app restart, model/GPU work, provider data, installation, commit, or push
was used. Broader beta, native, GPU/runtime, and release gates remain open.

Two initial beforeunload harness failures were fixed by awaiting the actual
native-prompt dismissal; no production failure was waived. The pre-existing
reset test was updated to confirm the new explicit confirmation behavior.

## Owner click-later checks (maximum four steps)

1. With a whitespace draft or partial reply, use sidebar/direct navigation and
   verify Keep/Cancel preserves content and focus.
2. Use Discard or confirmed New conversation and verify one abort, blank state,
   and no late reply.
3. Use browser Back/Forward with an app-owned entry; for a foreign entry,
   verify the chat stays mounted and Return to Models is explicit.
4. Confirm beforeunload protection appears only while dirty; do not infer
   protection against native close, force-kill, crash, or persistence.

## Known adjacent gap

At checkpoint 10, Agent draft navigation and automatic UI revision reload
protection were open. This historical gap is addressed by [checkpoint 11](checkpoint-beta-readiness-11.md),
whose bounded implementation and automated checks are complete. Broader
native/model/GPU/release gates remain open.

## Next candidate

Continue the broader beta-readiness, owner/native, model/GPU, and packaged
release gates tracked by checkpoint 11; no beta or release certification is
implied by this historical update.
