# Beta-readiness checkpoint 22

Status date: 2026-09-08

Status: **bounded automated implementation complete; owner review queued**.

This checkpoint covers bounded current-conversation navigation in the Agent
surface: local find over already-loaded message text, truthful paged activity
navigation, and narrow manual recovery for a failed optional chunk. It does not
add send, file-write, native, model, network, beta, v1, packaging, or release
authority.

## Scope

The implemented feature provides local find over loaded user and assistant text
in the current conversation. Tool output, reasoning, status events, and
incomplete deltas remain outside that local search. Navigation opens the correct
bounded page and focuses its matched row without silently requesting saved
search, creating a chat, sending a message, or resuming a model action. A
metadata-only live chat remains a valid loaded local-search scope when the
saved-search boundary is unavailable. Synthetic long conversations validate
this bounded behavior.

Activity paging retains a visible manual **Jump to latest activity** recovery
action after Earlier, including when the older page fits the viewport. New
activity must not silently move an owner reviewing an older page. The separate
optional-chunk recovery contract is intentionally narrow and manual.

## Evidence boundary

The initial broad frontend baseline (chunk `0e737f`) recorded **3,221 passing
and two failing of 3,223 across 221 files in 492.17s**. Its failures were a
static ErrorState contract mismatch and a dirty-workspace own-window handoff;
they are retained as historical baseline evidence only.

The focused handoff receipt (chunk `a7e12b`) passed **1/1 with 188 filtered in
8.80s**, unchanged. It does not supersede the two broad-suite failures.

Root reproduced the CP22 Jump regression (chunk `44b10f`): **1/1 red in
6.57s**. After Earlier, the latest event was not restored by Jump to latest.
This is a baseline only, not implementation evidence.

The focused optional-recovery group passed **11/11 across three files in
6.41s** (chunk `5ba0b7`). This verifies that narrow recovery group only.

The owning CP22 frontend group passed **26/26 across seven files in 28.52s**
(chunk `289f30`). The CP22 browser specification passed **9/9 in 9.0s**
(chunk `a8fce3`). The API check passed (chunk `4ed663`) and the interim privacy
scan passed (chunk `a468c2`).

Production and E2E strict TypeScript passed (the explicit specification/fixture
receipt is chunk `47daed`); the production build passed (chunk `2abc71`) after
a listener census found ports 8765 and 4173 empty (chunk `878eaf`); and the
bundle budget passed (chunk `3a07d9`) at shell **1,153,973 bytes**, Agent incremental
**557,301 bytes**, and initial Agent **1,711,274 bytes**, within unchanged
limits of 1,180,000, 575,000, and 1,750,000 bytes. The backend loopback
harness passed **6/6 in 14.64s** (chunk `8ba38b`), which is not a full backend
receipt. The diff check was clean (chunk `56149a`).

The standard browser suite passed **308 cases** with **six existing opt-in
README screenshot cases skipped** and **zero failures** in **4.5 minutes**
(chunk `22edcc`). This includes the nine CP22 cases already counted above; they
are not added again. Its widths and defaults cover the CP22 360/1440 keyboard,
900-height, and 1440×720 layout checks.

The disposable built loopback passed **27/27 in 30.9s** (chunk `207389`). Its
synthetic cleanup receipt recorded browser exit 0, released listener, zero
model runtimes remaining, confirmed runtime cleanup, no server-thread failure,
ready startup, and removed temporary state. It did not restart an actual app.

The final frontend suite passed **3,240/3,240 across 225 files in 522.10s**
(chunk `d4f5bb`). It covers the two historical baseline failures: the typed
ErrorState contract is now covered, while the own-window handoff passed
unchanged; this checkpoint does not claim a substantive handoff change. A final
listener census found ports 8765 and 4173 empty and the diff check clean (chunk
`13463b`). The final post-document privacy scan, diff check, and listener census
for ports 8765 and 4173 passed (chunk `f84be8`).

The initial CP22 browser iteration is retained as corrected historical
evidence: its synthetic status-row selector and keyboard traversal were made
exact, and sticky overlap/scroll behavior was corrected through ordinary
pointer interactions, without force-clicking. It is not treated as a passing
receipt.

The initial broad baseline remains historical evidence; its two failures are
now covered by the final frontend receipt above. This bounded automated result
does not establish full-backend coverage, beta, v1, native, hardware, model,
or release readiness.

## Owner checks (maximum four)

1. In a long real current conversation, use Earlier then Jump to latest; verify
   the current page restores without affecting the composer or a saved draft.
2. Search loaded user and assistant text by keyboard, including case matching,
   next/previous, Enter, and Shift+Enter; verify tool, reasoning, status, and
   incomplete-delta text are excluded.
3. Stay on an older page while a new activity arrives; verify it remains the
   owner-selected page until the owner explicitly chooses Latest.
4. Switch between a current conversation and a metadata-only live chat; verify
   local find resets to the new loaded scope and the optional-chunk recovery is
   explicit, manual, and content-free.

No next implementation commitment is made by this checkpoint.
