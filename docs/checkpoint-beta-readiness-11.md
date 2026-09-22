# Beta-readiness checkpoint 11

This checkpoint records the bounded Agent exit-risk and unsent-draft slice.
Implementation and bounded automated validation are complete for this slice;
this is not beta, v1, or release certification. The overall finish goal remains
active.

## Agent exit-risk boundary

Agent unsent content is tracked per chat in memory: text drafts (including
whitespace), staged attachments, attachment-retry choices, and manual workspace
edits contribute to the aggregate unsaved dimension. Observed work is a
separate active-work dimension. A draft in one chat remains unsaved when the
user selects another blank chat through the live-session UI, and a failed send
retains the draft and its risk.

Global navigation uses explicit Keep/Discard decisions where the transition is
modeled. Same-branch navigation and dedicated transitions have separate
boundaries. Managed-history and foreign-return Agent guards are implemented and
covered by bounded browser checks; owner/native review remains open.

`beforeunload` covers supported browser unload while risk is present. Native
close, force-kill, crash, and persistence guarantees are not claimed. The
refresh notice is interface-only: it never auto-reloads, and it is disabled
based on current mounted Agent observed work or unsaved state, or temporary
Models content. No autosave, persistence, or native-unload claim is implied.
One-shot reload errors are handled explicitly. Risk is scoped to current
mounted work; no cross-window backend watcher is claimed. The setup form has
no draft autosave, and the standalone ensemble overlay adds no refresh UI.

## Evidence boundary

| Gate | Result |
| --- | --- |
| Agent exit-risk focused tests | 11/11 across 1 file in 6.94s |
| Strict frontend typecheck (`tsc-b`) and production build | Passed; existing Agent bundle warning (668.40 KB) remains |
| Shared platform + UI revision notice | 88/88 across 7 files in 7.00s |
| Models owning tests | 81/81 across 2 files in 5.88s |
| Agent + handoff owning tests | 188/188 across 2 files in 215.16s after the event-list fix |
| Static HTTP tests | 22/22 in 4.11s |
| App owning tests | 151/151 across 12 files in 39.04s after duplicate-dialog/foreign-notice fixes |
| Distinct frontend + backend unit/integration checks | 519 + 22 = 541 |
| CP11 + CP10 + CP09 + CP08 recovery browser checks | 24/24 in 11.2s (9 new CP11 checks) |
| Built disposable loopback | 19/19 in 19.2s; startup/listener/runtime/temporary-state cleanup true; model runtimes 0 |
| Strict explicit E2E TypeScript | Passed |
| Privacy scan after cleanup and diff checks | Privacy passed in 7.54s; diff clean |

The accepted fix updates the matching event page/list observation so a stale
session-list `running` flag cannot keep active-work risk locked after the
current chat reports terminal idle. The earlier CP10 adjacent-gap record is
retrospectively updated by this checkpoint; see [checkpoint 10](checkpoint-beta-readiness-10.md#known-adjacent-gap).
The dedicated layout also records the 984px-at-900px overflow correction,
desktop-only flex notice allocation, mobile natural scroll, and stacked warning
validation. No actual model/GPU/provider/native/live-app restart or user data
was used. These receipts represent 43 distinct browser/loopback checks in
total. No beta/v1/release claim is made.

## Owner click-later checks (maximum four steps)

1. Draft text, whitespace, an attachment, and a manual workspace edit in two chats; verify Keep preserves each and Discard is explicit.
2. Trigger a failed send and verify the draft remains available for retry.
3. Exercise same-branch and dedicated global navigation, including a temporary Models draft, and verify the appropriate confirmation boundary.
4. Observe the interface-only refresh notice and supported `beforeunload`; do not infer autosave, persistence, native-close, force-kill, or crash protection.

## Known adjacent gap

Managed-history transitions and foreign-return Agent navigation remain
owner/native review boundaries. The former automatic UI-revision reload path is
now represented by a manual interface-only refresh notice; this checkpoint
does not certify release or the broader owner walkthrough. These are not
certified by the focused exit-risk tests alone.

## Next candidate

Broader beta, native, model/GPU, and packaged-release gates remain open. Keep
the finish goal active until the owner completes the representative walkthrough
and all required release receipts are current.
