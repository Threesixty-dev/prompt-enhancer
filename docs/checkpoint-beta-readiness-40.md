# Beta readiness checkpoint 40 — explicit fresh-analysis handoff

Status: SCOPED AUTOMATED IMPLEMENTATION COMPLETE; owner/native/release acceptance pending (2026-09-08)

CP40 adds a bounded owner-facing handoff when current evidence changes after a
saved metric snapshot has been displayed. The workspace keeps the saved
snapshot immutable and presents an owner-scoped notice with an explicit **Run
fresh analysis** action. The action delegates to the existing guarded Panel or
Overlay command; the evidence surface does not post, start work, or silently
restore authority.

The UI action is disabled for blocked, out-of-date, queued, running, watched,
or otherwise unavailable states. Duplicate clicks, stale session/run/transport
callbacks, deferred completions, old failures, cancellation and unmount are
fenced. A same-owner failure may be retried; a changed owner cannot update the
new surface or its busy state.

Targeted frontend evidence is not a full beta or owner acceptance claim:
MetricWorkspace + Overlay **39/39**, ModelEnsemblePanel **53/53**, and the
combined scoped receipt **92/92** (`f9286f`); the v6 catalog/parser/panel
slice is **45/45** (`e5bf80`). The repaired schema artifact is exact **1/1**
(`7587c8`) after re-export (`a54297`) and generated type/check validation
(`87aaf7`); the v6 production build is green (`18d276`). The general
built-loopback regression with the v6 inventory is **29/29** (`fb0489`,
31.6s; terminal `0b2fdf`) with cleanup confirmed and zero model runtimes;
it is not fresh-action browser proof. Scoped backend evidence covers 14
catalog/API tests and 11 verification tests; these receipts are nonadditive
and do not prove native, provider, runtime, or owner acceptance. Privacy,
native owner interaction, packaged/release, and full beta gates remain open;
no real model, provider, native owner action, or external network request was
used.

The current catalog is v6 with **20/18/0/2**: 20 contracts, 18 conditional
`available_when_evidence_exists` paths, zero profile gaps, and two
`provider_adapter_required` gaps. Its reviewed-verification path is
conditional on a complete compatible Codex source, a native-reviewed plan,
an observed check, and a fresh sealed analysis; a provider-reported check is
not a human coverage acknowledgment. CP40's scoped automated implementation is
complete; CP27's statement that guided reviewed-proposal UX was missing is
historical, and CP29–34 delivered the guided forms and review surfaces, while
CP40 adds only the explicit fresh-analysis handoff. Owner/native, provider,
model, privacy, packaged/release, and full-beta acceptance remain pending.
