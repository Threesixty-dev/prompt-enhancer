# Beta-readiness checkpoint 12

This checkpoint records the bounded saved-message search slice. It is a finite
beta-readiness packet, not beta, v1, or release certification; the overall goal
remains active.

## Saved-message search boundary

Agent search is a separate entry point for saved-message text, distinct from
metadata title search. It searches opted-in `local_history` chats only, across
all projects or the current project, with archived chats included only by
explicit opt-in. Results are server-paged (default 20, maximum 50), one match
per chat, with plaintext excerpts bounded to 240 characters. The first hit can
open the exact retained history event without autoresume, model start, or send;
draft guards and close/abort/retry/stale-response fencing remain in force.

The phrase is Unicode-aware and tokenized, case-insensitive, with diacritics
significant; it is neither substring nor semantic search. Reasoning, tool
activity, and attachments are not indexed. Query text is sent only in the POST
body and is not written to URLs, logs, browser storage, caches, or raw-transcript
MCP surfaces. The index is sensitive derived data in the private Agent DB;
deletion removes queryability but is not a forensic secure-erase guarantee.

SQLite 3.38.4 local runtime support was checked for FTS5, the SQLite full-text
extension ([SQLite FTS5](https://www.sqlite.org/fts5.html)). Database v31
upgrade automatically indexes only already-opted-in `local_history` chats; it
does not introduce new migration consent. Index lifecycle is transactional and
rolls back when FTS5 is unsupported. Search queries have a 2-second progress
deadline and SQLite busy locking has a 5-second budget; deletion is not
forensic secure erase.

## Evidence boundary

| Gate | Result |
| --- | --- |
| Backend combined search/catalog/history/OpenAPI tests | 84/84 in 79.87s |
| Search-specific regressions, including production HTTP | 10/10 in 8.42s (1 production HTTP test + 9 storage tests) |
| Broad frontend validation | 252/252 across 8 files in 270.87s |
| Focused dialog + timeline validation | 8/8 in 6.00s (overlaps broad frontend) |
| Same-chat focus validation | 1/1 in 9.74s after owner fencing (overlaps broad frontend) |
| API transport/contract subset | 7/7 |
| CP12 + CP11 browser checks | 16/16 in 10.0s; final CP12 rerun 7/7 in 6.2s (subset) |
| Built disposable loopback | 20/20 in 22.6s; listener/runtime/temp cleanup true; model runtimes 0 |
| Build, `tsc-b`, Vite, strict E2E TypeScript, `npm check:api` | Passed; Agent bundle warning 678.14 KB remains a performance gate |

These are bounded receipts only and overlapping subsets are not additive. No
actual provider data, model/GPU, native application, restart, or live user
session was used. The distinct browser/loopback count is 36 (16 + 20); no
large-scale benchmark is claimed. Privacy and final diff checks pass.

## What the user can check later (maximum four steps)

1. Open Agent’s rail and choose Search saved messages; verify all/current-project scope and archived opt-in.
2. Open a result and verify exact-event keyboard focus, same-chat repeat, and no resume/model/send mutation.
3. Exercise first-page retry, load-more retry, and stale-result fencing by starting a fresh search.
4. Close or Escape during a deferred search and verify abort plus no draft loss.

## Known limits and next candidate

The setup form has no draft autosave. Hardware crash/native-close/force-kill
acceptance and packaged-install/signing acceptance are not claimed; retained
history migration and restart behavior were verified above. Broader beta,
native/model/GPU, and release gates remain open.

The next packet was [CP13 metric recoverability](checkpoint-beta-readiness-13.md),
now bounded automated complete:
transient operability-panel retry/stale-map recovery plus the R8 owner-bound
notification boundary, with objective validity kept separate from
recoverability. This checkpoint does not claim overall beta or release
completion.
