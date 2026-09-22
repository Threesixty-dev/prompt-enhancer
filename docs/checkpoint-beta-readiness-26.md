# Beta-readiness checkpoint 26

Status date: 2026-09-08

Status: **bounded implementation and automated validation complete; owner
review remains pending.**

## Scope

This checkpoint records three user-visible fixes in the Agent retained-resume
boundary. The source scope is `frontend/src/features/agent/AgentPage.tsx` only:

1. a delayed resume for saved chat A cannot take over after the owner selects
   saved chat B;
2. reselecting the same saved row abandons the resume UI wait synchronously and
   triggers a bounded retained-history reread instead of leaving the row stuck
   loading; and
3. the actual retained read cursor is preserved when existing polling or SSE
   receives advanced events, so new messages are not missed after resume.

Resume completion and failure are owned by the exact selected transport,
session identity, catalog revision, retained-history revision, and actual
retained head. Same-identity replacement transports and unmount settlement are
fenced, and an explicit history reload remains available. Normal resume remains
model-neutral and opens the composer without selecting or activating a model.
The work does not change server rollback, model activation, session execution,
provider reads, or native authority.

## Synthetic acceptance

The browser fixture mounts the real Agent page with a wrapper around
`createSyntheticTransport`. It uses reserved 32-hex synthetic IDs, fictional
workspace paths, parser-valid catalog/history/artifact DTOs, an idle runtime,
no installed models, no tools, and unavailable native/provider execution. Its
conspicuous banner identifies the data as fictional. Deferred release/failure
buttons only settle the fixture promise; they do not fake Agent state.

The five bounded journeys are:

1. normal retained resume opens a composer with no model and no implicit model
   activation or send;
2. a delayed successful A resume cannot replace a later selected B;
3. a delayed failed A resume does not show A's error on B;
4. keyboard resume remains usable at 360px without horizontal overflow; and
5. clicking the selected saved row twice keeps Resume ready without implicit
   actions.

## Evidence boundary

Root reproduced the historical A-over-B defect as **1/1 red** in receipt
`4a2044`. The same-row loading defect was **red before the fix** in receipt
`957196` (4.81s). An advanced-event receipt `69d61c` was red, but its
status-only fixture was not decisive; the corrected assistant-message and
actual-cursor proof is **19/19 green in 15.90s** (`89bc04`). The final owning
run is **498/498 across 10 files in 245.68s**, including those 19 cases
(`eb0138`).

Browser evidence is explicitly split: the broader run was **44/46 green**
(`c8af8e`, 51.9s), and a separate corrected run was **14/14 green**
(`c0c646`, 11.1s), comprising the five new journeys and nine existing cases;
it is not reported as a single 46-case green run. The intermittent existing
pointer timeout was not reproduced in the rerun, and no speculative cause is
claimed.

Backend coverage is **68/68** (`f70a2e`, 23.08s). The production build passed
(`1ab03e`), and bundle validation passed (`83dc6f`): shell **1,153,973 B**,
Agent incremental **560,711 B**, initial Agent **1,714,684 B**, with caps
unchanged. API validation passed (`6ec195`). Final strict E2E passed (`ec0e1b`)
against the frozen source and fixture, and final source/test strict-TypeScript
passed (`e0206b`). Built loopback passed **27/27 in 28.4s** (`8e9151`), with
startup success, no failure component, listener release, temporary-state
removal, and zero remaining model runtimes. Final privacy passed in 7.95s
(`e1298b`), and the final diff/listener check passed (`d40506`), with ports
8765 and 4173 unbound.

## Remaining gates and non-claims

This packet records bounded Agent source, synthetic browser, backend, build,
API, strict-TypeScript, loopback, privacy, and diff evidence. It does not prove
beta, v1, release, restart, packaging, native, model, GPU, provider, or
external client readiness. No credentials, real sessions, provider data,
transcripts, models, installations, GPU work, native calls, restart, commit, or
push are claimed. The four provider/composition metric gaps and updater C07
native gate remain unresolved and are not promoted by CP26.

## Owner checks (maximum four)

1. Repeat successful and failed selected-A-then-selected-B walkthroughs and
   confirm B's saved view remains selected with no A-specific takeover or
   failure notice.
2. Verify normal model-neutral resume keeps Send disabled until an owner
   explicitly chooses and starts a model.
3. Reselect the same saved row and confirm loading clears through the retained
   history reread; verify a later assistant message is not missed when the
   actual retained cursor advances.
4. At 360px, repeat keyboard selection/resume and confirm the composer stays
   within the viewport without horizontal overflow.

Final beta, v1, native, model, updater, packaging, and owner-release gates
remain open.
