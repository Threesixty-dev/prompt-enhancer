# Beta progress journal: published handoff

This is the shared execution handoff, not a second readiness ledger. Requirement
acceptance remains in [the product-readiness matrix](product-readiness-matrix-2026-09-12.md).
The owner's preserved development checkout contains additional October 6–7
journal history; this documentation branch does not overwrite or blanket-publish
that dirty tree. Reconcile those entries when admitting their source cohorts.

## 2026-10-08 — architecture and collaborator documentation

Selected scope: source architecture/feature audit, colored graph, ADRs, README,
repository skill and a reviewed documentation branch/PR. Application behavior,
model loading, native installation and release execution were outside this task.

- Observed main baseline: `bfb67b6`; development source: `acdf0e5` plus 747
  preserved pending files. Source repository metadata confirmed private.
- Created a 122-component atlas, including all twenty metric contracts, eight
  workflow model-family requirements and all eight composer-hook gates.
- Scanned 1,161 source files, 23 route families, 32 frontend feature directories
  and 53 HTTP route modules. Static Python parsing reported no syntax errors.
- Added seven local PNG/SVG diagrams, source/test bindings, source census,
  change recipes and remaining-work sequence. Recorded existing owner decisions
  and a proposed atlas maintenance convention without claiming beta acceptance.
- Fresh bounded synthetic selection: 122 metric graph/aggregation/Agent contract
  tests passed; owned cleanup confirmed. See [validation](architecture/validation.md)
  for the final documentation/privacy checks and their scope.

The October 7 full frontend run timed out at its 600-second bound; its final-only
reporter did not retain a complete case census. The clean-main bundle gate failed
with `E_BOUNDARY`. Those development findings remain open and are not erased by
this documentation pass. The POSIX inventory race, compiled worker qualification,
real native journeys and signed clean-machine release gates remain open too.

Next finite task: make full-suite evidence incremental and localize unfinished
frontend cases, then review the separate deferred-loading cohort. Parallel work
can prepare owner-approved release/model/hardware inputs. New feature work must
name its baseline and dependencies. The owner controls PR acceptance and merge.

## 2026-10-09 — proposed inference-provider separation

Baseline: clean `main` at `6fa1100`; local feature branch
`feature/inference-providers`. No source publication, deployment, merge or
real provider/session access occurred during this change.

[ADR 0022](adr/0022-inference-provider-boundary.md) proposes a shared inference
port with local-runtime and LiteLLM adapters. Chat, Prompt Check (including its
Agent shortcut), explicit indexed/supplied-text analysis and Agent model steps
can use reviewed remote requests. Local lifecycle and native workspace approval
remain separate. Automatic session analysis stays local. Operational variables
and the useful local-application/shared-model topology are in the gateway guide.

Fresh bounded evidence, using only fictional data:

- Backend compatibility selection: **373 passed, 3 Windows-only skips** across
  local models, Agent, model judging, Prompt Check, bootstrap, API, cancellation
  units and redaction. The sandbox initially prevented loopback fixture binding;
  the successful run allowed owned loopback test servers.
- Final inference-provider selection: **22 passed**. TLS adapter selection:
  **14 passed**, including real generated-certificate loopback cancellation
  before headers and during close-delimited streamed/ordinary bodies.
- Shared HTTP cancellation plus inference selection: **40 passed**. Stop joins
  owned workers; Agent tool-result egress needs a new review.
- Privacy/configuration/text-metric/distribution selection: **59 passed**.
  One independent manifest CLI test remains environment-blocked: its child uses
  the base interpreter, which lacks `pydantic`. That test was not weakened and
  no full-suite pass is claimed.
- Core affected UI selection: **89 passed**. Agent gateway/inline-check selection:
  **5 passed**. These include local-catalog failure, stale preview invalidation,
  stream abort and separate inference-versus-tool approval.
- Broader UI regression checkpoint: **392 passed, 19 failed**. Clean `main`
  independently reproduced the identical 19 Agent test failure names
  (**149 passed, 19 failed** in that file). Most concern existing composer
  disabled-state expectations; archive reconciliation and projected-document
  metadata also fail. These remain open baseline issues.
- TypeScript, Vite production build, generated API consistency and Python
  compilation passed. Vite retains its large-chunk advisory. Privacy scan,
  architecture rendering check and whitespace check passed.

Synthetic and owned-loopback evidence does not qualify a real gateway model,
tool-call capability, model revision, retention policy, hosted multi-user
isolation or a native/release journey. No B/W/WP gate closes. Next: owner review
of the proposed egress exception, followed by fictional-input gateway validation
before any deployment. Existing source-observation bindings remain frozen.

## 2026-10-12 - combined enhancement core and bench review

The owner commissioned a third temporary integration worktree and a usable local
demo after the two implementation workstreams. The candidate uses `6fa1100` plus
the 55 inherited source changes and both scoped implementations. All imported
files were privacy-scanned and byte-verified. The original checkout and both
workstream checkouts remain unchanged; nothing was committed, pushed or deployed.

Integration corrected missing sibling consumer-model selection, build fingerprints
affected by generated package metadata, and retention of local demo images.
Fresh validation: 186 focused core tests, 79 bench tests, six desktop/mobile
browser tests, final core-container smoke and the interactive GitOps/UI/rerun
demonstration. Restart preserves all six historical run records and creates no
duplicate automatic run. One earlier missing-image failure remains visible.

The [integration review](bench/integration-review.md) records exact evidence and
demo controls. Proposed [ADR 0023](adr/0023-enhancement-experiment-boundary.md)
consolidates the workstreams without accepting or silently superseding earlier
decisions. The live consumer/evaluator, model/GPU, hosted delivery and deployment
gates remain open. The broad suite's 36 baseline failures and four errors are
unchanged; no general workflow/native/release acceptance is claimed.
