# Beta-readiness checkpoint 24

Status date: 2026-09-08

Status: **bounded automated implementation validated; owner review pending**.

## Scope

This checkpoint corrects one capability-truthfulness boundary. An exact or
compatible `operational_events` compatibility receipt is not evidence that this
app can analyze session text. Prompt-text launch remains disabled unless the
receipt is explicitly `session_text_analysis`, `supported`, and exact or
compatible.

The production slice is limited to three files:

1. `ProviderCompatibilityCard.tsx` makes the predicate capability-specific,
   labels the visible card by its actual capability, and includes that capability
   in the accessible status announcement.
2. `ModelEnsemblePanel.tsx` retains the precise capability blocker at its
   analysis action.
3. `ModelLinkExperimentPanel.tsx` retains the same precise blocker at its
   experiment action.

Consent, readiness ownership, metric calculators, stored metric values, and
provider adapters are unchanged. The product still has 20 canonical coaching
contracts, 16 shipped measurement paths when their required evidence exists,
and four provider-adapter gaps; this checkpoint neither fills a gap nor makes a
calibration, accuracy, model, or provider-data claim.

The existing no-transcript Claude state is `operational_events` and degraded.
It is not represented as a successful text-analysis path. Browser evidence uses
only parser-valid fictional compatibility DTOs and `createSyntheticTransport`.
The one positive fixture action dispatches an explicit synthetic preview which
truthfully returns the pre-existing safe 501; it does not complete analysis or
run a model.

## Evidence boundary

Root reproduced the original predicate/consumer defect as a genuine red result
(chunk `f0f782`). That run also exposed one fixture assertion with a missing
`AbortSignal` argument; it did not establish a fourth production defect.

The final owning frontend group passed **364/364 across eight files in 20.96s**
(chunk `2ecacf`). Backend coverage passed **47/47 in 66.46s** (chunk
`2dd398`). The first mixed browser invocation passed all 97 pre-existing cases
but had one new fixture-selector failure (**101/102**, chunk `543973`); the
corrected new capability suite then passed **5/5 in 3.7s** (chunk `b6eddc`).
Those are separate receipts, not a claim that one 102-case invocation passed.

Strict E2E fixture TypeScript passed (chunk `f26bab`). Final production build
passed (chunk `b740be`), with the same production asset hashes as the earlier
loopback-tested build; only tests changed between them. API and bundle-budget
validation passed (chunk `2d50c1`): shell **1,153,973 B**, Agent incremental
**559,666 B**, and initial Agent **1,713,639 B**, all under unchanged caps.
The built real-loopback harness passed **27/27 in 27.9s** (chunk `7b7f2e`),
with cleanup true, zero retained runtimes, and temporary state removed.
Listener inspection passed (chunk `a6a58d`) with ports 8765 and 4173 unbound,
and `git diff --check` passed. Final privacy scanning passed (chunk `be04c7`)
after this documentation freeze. These are bounded automated receipts, not beta, v1,
release, real-provider, native, restart, or model-execution evidence.

## Browser coverage

The synthetic fixture mounts the real QualityProfileView and compatibility card
with content-free numeric counters only. It covers:

1. exact and compatible operational-event receipts, both refused for text
   analysis with their own visible and accessible capability labels;
2. an explicit exact text receipt, where opening review performs no read and
   only explicit preparation dispatches one synthetic request;
3. a deferred degraded operational check, during which both check controls and
   the analysis action stay locked until an explicit text-capable result arrives;
   and
4. narrow-width keyboard traversal, including skipping the disabled analysis
   action without overflow.

## Owner checks (maximum four)

1. Inspect an operational-event receipt and confirm its card says Operational
   events, while all prompt-text analysis actions remain disabled.
2. Inspect an exact or compatible session-text receipt and confirm that it is
   the distinct, necessary capability condition alongside the existing local
   access checks for a local review action.
3. At a narrow width, tab through the provider check and methods disclosure;
   confirm disabled analysis is skipped rather than activated.
4. Confirm an existing metric/readiness view remains unchanged: this checkpoint
   changes UI eligibility, not values, readiness, or provider evidence.

## Deferred CP25 pointer

`AnalysisJobCentre.tsx` currently maps a cancel 404 with
`analysis_job_not_found` to action error text while leaving its confirmation
control available. Root verified this as a separate candidate; no CP25
implementation or acceptance claim is made here.
