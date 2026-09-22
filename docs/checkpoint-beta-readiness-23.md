# Beta-readiness checkpoint 23

Status date: 2026-09-08

Status: **bounded automated implementation validated; owner review queued**.

## Scope

This checkpoint covers one narrow Agent close invariant: a successful close,
including an authoritative already-absent response, discards only that live
chat's in-window composer draft. A cancelled or failed close preserves the
target draft and every other chat's draft. It adds no send, model, native,
provider, persistence, network, beta, v1, packaging, or release authority.

After an explicit close confirmation starts, the exact target chat accepts no
fresh composer, attachment, or workspace edit; its existing composer remains
read-only and selectable for copying until the close settles. Other chats stay
editable. This boundary does not roll back an already-dispatched file
transaction.

The pending-close ownership is also transport-scoped: a completion from a
replaced transport cannot settle, unlock, discard, or remove the current
transport's chat. The final automated gates below cover this same-ID transport
replacement fix.

The browser fixture mounts the real application with two fictional mutable live
chats and content-free counters. Its one-shot failure mode proves row-local
close recovery before a second explicit confirmation. It uses the existing synthetic runtime only;
no provider, model, native action, or external request is involved.
The close coverage deliberately selects the real fallback live-session rail:
the durable catalog rail requires catalog-attested rows and remains covered by
its owning unit tests rather than receiving unattested synthetic live ids.

## Evidence boundary

Root reproduced the original close regression as **1/1 red in 5.22s** (chunk
`619b79`): an authoritative close outcome left a hidden composer draft that
continued to block navigation. That is a baseline failure, not passing evidence.

The interim frontend receipt passed **217/217 across six files in 231.26s**
(chunk `d20e0e`). It covered the first draft-discard correction before the
row-local unconfirmed-close and retry extension; it is retained as intermediate
evidence only and is not the final CP23 receipt.

The pre-fix close-draft browser receipt passed **26/26 in 20.1s** (chunk
`5abd7b`); strict E2E/fixture TypeScript passed (chunk `349b94`), the build
passed (chunk `31f617`), API validation passed (chunk `a16c7e`), the owning
frontend group passed **84/84** (chunk `a567c3`), and the legacy close/draft
group passed **37 with 152 filtered** (chunk `734ef1`). All predate the final
same-id transport-replacement correction to the close-request ownership set and
are intermediate receipts only, superseded by the final CP23 evidence below.

The browser coverage exercises:

1. pointer close at 1440px, with a synthetic authoritative 404 treated as a
   successful close, then Overview navigation without a false exit dialog;
2. keyboard cancellation at 320px, retaining the noncurrent chat's draft and
   the ordinary exit guard; and
3. a synthetic unconfirmed close, retaining its target draft without claiming
   whether the backend stayed live or a misleading current-chat error, then a
   successful explicit retry that clears only the closed chat while another
   draft still guards navigation.
4. a deferred synthetic close: its target composer is read-only but selectable,
   another chat remains editable, and a failed completion unlocks the target
   with its original draft intact.

## Final automated addendum

The final transport-owned close-request implementation passed the owning
frontend group **85/85 across nine files in 27.75s** (chunk `cc7402`) and the
legacy AgentPage close/draft group **37 passing with 152 filtered in 46.34s**
(chunk `3d5b41`). The affected browser suite passed **26/26 in 20.0s** (chunk
`0407de`). Production build passed (chunk `6e890b`), strict E2E plus fixture
TypeScript passed (chunk `9f6229`), and the unchanged API validation receipt is
chunk `a16c7e`.

The bundle gate passed (chunk `57c678`): shell **1,153,973 B**, Agent
incremental **559,666 B**, and initial Agent **1,713,639 B**, all within the
unchanged caps. The disposable built real-loopback harness passed **27/27 in
28.0s** (chunk `ab91e8`), with cleanup true, zero remaining runtimes, and
temporary state removed. These are bounded automated receipts; the current
whole-app full suite was not rerun and CP22's historical whole-suite receipt is
not reclassified as CP23 evidence.

The first final privacy attempt (chunk `5a66f0`) raced Playwright artifact
deletion and exited with `FileNotFound`; it is not a passing privacy receipt.
The post-loopback privacy scan passed (chunk `a07df3`). The final post-document
privacy, listener, and diff receipt (chunk `4df60a`) passed with ports 8765 and
4173 unbound and the diff clean. No beta, v1, packaging, or release-readiness
claim follows from this checkpoint.

## Owner checks (maximum four)

1. Draft two idle chats, close one, and verify only its draft disappears after
   a confirmed close; keep the other draft through the exit guard, then clear
   it manually before expecting Agent to leave without a discard dialog.
2. Cancel a close; if a later close is not confirmed, verify the row says so
   without claiming the backend state and the draft remains copyable.
3. While one close is pending, switch to another chat and edit it; return to
   the pending chat and verify its draft is readable but not editable until the
   close settles.
4. At a narrow width, use keyboard close and cancel controls; verify the draft
   remains selectable/copyable and the controls remain reachable.

## Deferred CP24 pointer

The safe next measurement/analytics candidate is provider-capability truthfulness,
not a metric-value expansion. In
`frontend/src/features/provider-compatibility/ProviderCompatibilityCard.tsx`,
`isPromptTextCompatible` currently accepts an exact or compatible
`operational_events` status as prompt-text-compatible because it omits the
`session_text_analysis` capability check. The same card labels any result
“Session text analysis.” The DTO permits both capabilities in
`frontend/src/shared/api/contracts.ts`, while
`frontend/src/features/quality-profile/QualityProfileView.tsx` later correctly
requires `session_text_analysis` to bind readiness. A synthetic operational-event
status should fail closed for text-analysis launch and be disclosed only as its
own surface; it needs no provider data, model, calibration, or metric value.
The present no-transcript Claude fixture is `operational_events` **and
degraded**, so it does not prove that an existing no-transcript path unlocks
text analysis. The candidate proof must instead use a synthetic exact or
compatible `operational_events` status to exercise the capability predicate and
the label truthfully.

No CP24 implementation is authorized by this note.
