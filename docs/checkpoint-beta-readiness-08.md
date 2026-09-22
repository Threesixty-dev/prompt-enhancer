# Beta-readiness checkpoint 08

Bounded implementation and automated validation are complete; this is not a
beta or release certification.

## Local model chat and runtime-readiness recovery

Checkpoint 08 records bounded synthetic validation for the Models page.
Catalog, compatibility, and coordinated-runtime reads are independent; failed
or timed-out reads retain the last confirmed catalog and current-tab chat
history/draft. Each bounded status read has a 10-second deadline, and Refresh
is explicit recovery without implicit model loading or message send.

The page warns when catalog data is unavailable and fails closed for fresh
Send, Retry, launch, switching, and download actions. Exact guarded unload
remains available only where retained runtime identity and revision permit it.
Stale GET results, replaced transports, lower revisions, and superseded
commands cannot restore readiness. Active streams remain stoppable, with
partial output and the next draft preserved.

## Evidence boundary

| Gate | Result |
| --- | --- |
| Agent recovery browser journey | 4/4 in 4.1s, including explicit e2e strict TypeScript |
| Root Models chat browser journey | 4/4 in 4.9s |
| Root intercepted Models HTTP journey | 4/4 in 7.1s |
| LocalModelsPage + LocalModelChatPanel owning tests | 72/72 in 5.42s |
| Production build | Passed; existing AgentPage 666.76 KB warning unchanged; ModelsPage 50.45 KB |
| Final disposable built loopback | 17/17 in 17.1s; startup/listener/cleanup/temporary-state receipts passed; zero model runtimes remained |
| Privacy and diff checks | Passed (`privacy_scan.py`; `git diff --check`) |

No original-source red regression run is claimed. No real model, GPU,
provider data, app restart/reload, installation, commit, or push was used.
Owner, native, model/GPU, and release acceptance remain open; broader beta
acceptance remains unproven.

## Owner click-later checks

1. Lose runtime status in a model chat and confirm warning, retained
   history/draft, blocked fresh actions, and explicit Refresh recovery.
2. Stop an active partial stream after status failure and confirm no late
   result or duplicate retry.
3. Confirm retained exact unload identity/revision is the only cleanup action
   offered while status is unavailable.

## Deferred next candidate

Candidate only, not implemented: make Models chat's current-tab-only history
boundary explicit in the UI, then assess an explicit Agent durable-chat
handoff if an existing API supports it. This requires separate scope review.

Retrospective: the bounded slice was subsequently delivered and recorded in
[beta-readiness checkpoint 09](checkpoint-beta-readiness-09.md). It adds an
explicit new-Agent setup handoff without transcript migration; the historical
candidate and evidence above remain unchanged.
