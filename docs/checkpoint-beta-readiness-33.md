# Checkpoint beta readiness 33 — transport-owned composer drafts

Status: **AUTOMATED IMPLEMENTATION AND TARGETED VALIDATION COMPLETE**

## Scope

CP33 closes a window-memory ownership leak in Agent composer drafts and
attachment-retry choices. It adds no browser storage, backend persistence,
provider access, model action, native action, restart, or release authority.

## Reproduced source boundary

`AgentPage` kept drafts and attachment-retry metadata under a session ID alone.
A replacement local transport can legitimately present the same ID as a
different chat authority. Before this slice, React state survived that
replacement and could render the prior transport's unsent draft under the
replacement chat. The existing delayed-close guard prevented a late close from
clearing the replacement draft, but its test replaced the text before checking
whether the old draft had initially appeared.

## Implemented recovery boundary

The in-memory draft state now carries a transport generation. Rendering derives
draft text, retry metadata, and unsaved-draft risk only from the current
generation, so a replacement transport is isolated immediately even when its
chat ID is identical. Each draft/checklist mutation captures the generation and
rejects late work from an old owner. A later passive cleanup releases hidden
old state without overwriting an edit already made by the replacement owner.

The remaining notice defect was also isolated: a late source-stream functional
update could overwrite a child-target retry notice. Default notice writes now
cannot replace a notice belonging to a different chat target.

Normal same-transport chat switching still retains independent drafts for the
mounted window. A page reload, close, crash, or a confirmed close still loses
the relevant unsent draft by design; no `localStorage`, `sessionStorage`,
IndexedDB, retained-history event, telemetry, or new server record is used.

## Current automated evidence

The intended synthetic matrix covers an immediate same-ID transport replacement
with text and attachment-retry state, late old-owner callbacks, transport
generation A-to-B-to-A, ordinary same-transport chat switching, and the
existing exact send/confirmed-close cleanup behavior.

- Historical full AgentPage owning run: 212/216 passed (`7cff7f`). Corrected
  focused follow-up: 3/3 passed (`1efb0d`), followed by the exact own-window
  handoff: 1/1 passed (`eb2035`). These receipts are intentionally split and
  are not presented as a new 216-test green aggregate.
- Close-draft ownership: 15/15 (`234148`); draft switching/send: 6/6
  (`e8d050`); exit-risk: 11/11 (`2e1701`); branch-focused: 6/6 (`436ad0`);
  channel: 8/8 (`926b80`).
- Runtime recovery passed 59/59 (`4f6749`). The final build passed (`7806c4`),
  and final current-files TypeScript validation passed (`9a34ce`).
- The production-built synthetic loopback flow passed 27/27 (`4b46b2`), with
  cleanup confirmed and model count 0.
- Privacy validation after cleanup passed (`79ba07`); the final privacy
  recheck also passed (`4d0f13`).
- The handoff test uses only a test-side wait for the actual lazy workspace
  surface and tree readiness; no timeout was increased. No production
  handoff defect was demonstrated. The CP32 duplicate announcement is closed
  as an integrated finding rather than a separate release claim.

Broader owner/native/release acceptance and full-beta release review remain
pending. This checkpoint makes no whole-product completion or release claim.
