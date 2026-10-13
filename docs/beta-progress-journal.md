# Beta progress journal: published handoff

## 2026-10-13 - JSON-only Experiment publication

The owner requested the agreed Experiment JSON push workflow and domain language.
On integration baseline `5d2228d`, publication now watches `experiments/`, keeps
each Experiment's selected core version, imports newest revisions first, supplies
Origin, rejects redirects and preserves idempotent automatic Runs. Experiment
Unit remains the compared configuration; strategy is one of its settings.
The acceptance JSON compares two scripted Experiment Units on two fictional
Subjects, using one deterministic Evaluator and fixed nonregression assertions.

Local evidence: 103 Test Bench tests, six desktop/mobile browser cases, syntax,
schema and privacy checks pass. Following explicit owner approval of the
branch-restricted environment and endpoint-only service token, the original
JSON-only push's publication Action passed in 21 seconds and acknowledged the
import. Test Bench then showed its automatic Run succeeded, with all four
Subject/Experiment Unit results successful and assertions passed. The Action
ends after delivery and does not monitor execution. Acceptance-testability stayed
at zero, so no improvement in that metric is claimed. Broader CI failures remain
open, and the UI terminology source changes are not deployed. See the
[task card](bench/experiment-publication.md) for exact evidence and limits.
No general gate is closed.

## 2026-10-13 - Dedicated bench conversation retention

The owner requested inspection history after successful OpenHands cleanup had
deleted the pilot conversation. Core 0.1.3 and a version-gated consumer adapter
now separate runtime release from native history retention. The default is seven
days after confirmed workspace cleanup, configurable 1-90 days. Uncertain and
cleanup-held attempts do not expire automatically. Native REST history survives
restart; retained HTTP and WebSocket mutation/replay are rejected. Complete Bench
results keep their independent retention policy.

The [task card](bench/consumer-retention.md) binds source `2ab65bb`, paths and
W05/W07/WP05/WP07 scope. Forty-six focused synthetic tests and the privacy scanner
pass. A network-isolated pinned 1.49.1 container verified native history, restart,
authentication, replay refusal and expiry with zero model calls. No full suite or
CI wait was run. Source `6530fd0` was then deployed with the existing portal and
volumes preserved. The live policy and isolated entrypoint startup were verified,
and manual pilot generation 8 binds core 0.1.3 without starting inference. A
checksummed core archive is retained. The already-deleted pilot is not recovered
and the historical architecture atlas is unchanged.

This is the shared execution handoff, not a second readiness ledger. Requirement
acceptance remains in [the product-readiness matrix](product-readiness-matrix-2026-09-12.md).
The owner's preserved development checkout contains additional October 6–7
journal history; this documentation branch does not overwrite or blanket-publish
that dirty tree. Reconcile those entries when admitting their source cohorts.

## 2026-10-13 - all runs above experiments

Added the local run overview, ten rows per page, with experiment/revision labels
and links to results. Added bounded cursor pagination so older history remains
reachable beyond 100 runs, while revision pages retain their existing scope.
Preserved the stronger labels and unchanged-snapshot polling behavior.
Local checks pass: 98 backend tests, 20 desktop/mobile browser checks and
JavaScript syntax. The built-in browser displays the synthetic preview. Changes
remain local; there is no publication or deployment in this iteration.

## 2026-10-13 - bench pages and run forms

Implemented [dedicated bench routes](bench/client-navigation.md) on a feature
branch from `origin/develop` at `aeefb03`. Experiment selection navigates to an
experiment page; new runs and reruns open forms with typed per-strategy controls;
results have durable URLs. Reruns preserve the prior subject/strategy selection,
parameters, objectives, steering and consumer bindings before edits. Polling
skips unchanged DOM snapshots and never overwrites an open run form.

Integrated the existing gateway-only authentication cohort to preserve the live
client's direct-entry behavior. There is no Bench login or browser token state.
The API retains exact Host/Origin checks, same-origin JSON writes and private
deployment assumptions. Existing worktrees and the main development edits remain
preserved. No source publication or deployment was performed.

Evidence: 92 backend tests, 14 desktop/mobile browser checks and JavaScript syntax
pass. Chrome visually verifies the token-free synthetic form. Tests cover expired
access without a token fallback, typed overrides and retained null/zero values,
route isolation, stale responses, reruns and stable DOM identity across polling.
This does not establish hosted, consumer/model or release qualification.

## 2026-10-13 - complete one live synthetic bench pilot

Task: repair Qwen rubric completion and OpenHands/Codex generation, preserving
the separately deployed portal. Core `42de206` and consumer `a653b2d` qualify one
manual end-to-end run: eight valid rubric replies (seven known labels and one
original abstention), a strictly parsed rewrite, and ten saved comparison records
in approximately 41 seconds. Assertions were not evaluated. The deployment
receipt verifies conversation, workspace, process and ephemeral-core cleanup,
no queue/reconciliation holds, and the retained core archive checksum.

The fixes keep strict parsing, operator-bound reasoning control and explicit
provenance. Codex's custom alias must be selectable for ACP initialization;
an offline metadata check verifies this without inference. Automatic runs stay
off, the PR stays draft for owner review, and no full suite or CI wait was added.
This does not establish quality improvement or close any beta gate. See the
[integration evidence](bench/integration-review.md#october-13-live-synthetic-completion).

## 2026-10-12 - reconcile enhancement candidate for PR promotion

Task: owner-requested source integration, PR and promotion to main, followed by
live provider qualification and closure of the inherited failure set. The source
candidate combines the core, bench and inherited provider boundary, then merges
current main `4b4efba`. The original dirty checkout and both workstream checkouts
remain preserved. Repository routing is feature PR to develop, then a separate
develop-to-main promotion; merge authority is limited to this direct request.

Main contains repairs for 30 of the 40 inherited failing/error cases. The remaining
ten share seven stale HTTP factory fixtures, corrected by accepting the explicit
inference argument with all assertions unchanged. All 40 now pass within the
affected-module run: 621 passed, six unrelated platform/tooling skips. The combined
core/provider/bench selection passes 265 tests. Dependency locks, privacy and
generated architecture consistency pass. All 2,920 frontend tests, generated API
consistency and production build pass; the existing chunk-size advisory remains.
Full hosted checks remain to be recorded.

Conflicting evidence entries and dependencies retain both branches' changes.
The new inference and experiment ADRs are renumbered 0024 and 0025 to avoid
collisions with main's accepted identifiers. Live consumer/evaluator checks still
require a task-specific authenticated route; credentials remain outside source
and chat. No real model inference is claimed by the local synthetic receipts.

## 2026-10-11 — cancellation-test startup synchronization

Task ID / atlas nodes / gates: cancellation-startup-fixtures; MA13, A15, R26;
B02/B05/B07 and native acceptance retain their existing status.

Approved source baseline: develop `3528f517`, whose tree also reached main
`bc38d6e` through the reviewed promotion. The main Windows shard first failed a
watch caller-join assertion; its one targeted retry passed that case but failed
an approved command's three-second child-readiness assertion. The latter failure
occurred before the cleanup clock started. No third unchanged retry was started.

Allowed files: the two cancellation test modules, this journal, the readiness
addendum and affected atlas evidence/catalog. Application behavior, native
approval, process ownership, CI job/time limits and deployment gates are unchanged.

Reproduction: six new delayed-start cases add bounded synthetic worker or child
startup delay. All six fail against the original startup assumptions. The watch
test previously counted setup before reaching its selected boundary inside a
two-second cancellation join. The command test allowed only three seconds for a
cold shell/interpreter to create its readiness marker.

Implementation: each watch boundary signals readiness, then the caller requests
Stop before the original two-second join. The disposable command has a separate
ten-second readiness window and twenty-second watchdog; it stays alive until
cancellation rather than racing natural completion. Its original two-second
shutdown/reaping assertions and three-second elapsed-cleanup assertion remain.
Failure finalization stays bounded by the fixture watchdog plus two seconds.
No production timeout, failure/quarantine assertion or required test is relaxed.

Evidence: all twelve ordinary and delayed-start cases pass after the correction.
The six new cases failed before it. The six-module command/watch ownership and
cancellation selection passes 74 tests, including those twelve cases, with nine
platform-specific skips on the local host. Full hosted Linux/Windows candidate
validation and owner review remain pending. These are source-test fixtures,
not model, native-window or packaged acceptance.

Process/resource bound: one bounded correction cohort after diagnosing both
content-free CI failures. Fixtures use fictional data, isolated storage and owned
processes; no personal sessions, models or unrelated processes are inspected.
Owner decisions still needed: review and authorize this repair's develop merge
and corresponding main promotion. The earlier one-time promotion authorization
is not authority for this new cohort. No production deployment ran.

## 2026-10-11 — final build-manifest inventory check (R19)

Task: repair the manifest safety failure exposed by the deployment candidate's
Windows quality shard. Baseline: develop `d68f281`; separate task branch
`codex/fix-manifest-tree-check`. The already-approved deployment PR is unchanged.
Scope: build-manifest inventory verification and synthetic regressions; no
accepted architecture decision or release authority changes.

The existing generator enumerated the staging tree once, hashed known files,
and checked file/directory metadata afterward. Directory metadata alone did not
reliably prove that no new entry had appeared. Three deterministic synthetic
regressions hold directory metadata stable while adding a root file, nested file
or empty directory after hashing. All three fail before the correction.

The proposal performs a second bounded inventory walk using the same link,
reparse-point, hard-link, portable-path and collection-limit checks. Both file
paths and directory paths must match the initial inventory. Existing final file
and directory metadata checks remain, and source bytes are still hashed once.
This detects the observed late entries; it does not claim an atomic filesystem
snapshot under arbitrary concurrent mutation.

All 93 manifest and distribution checks pass, including the new regressions,
unchanged-source determinism and single-read checks. Full Windows CI and owner
review remain pending. R19, R26 and all native/build/release acceptance gates
retain their prior status; no deployment has been authorized by this evidence.

## 2026-10-09 — develop integration and dev_pm routing

The owner requested integrating the follow-up documentation into develop and
creating exact dev_pm afterward. At inspection, origin/main already included
the atlas PR; origin/develop included main plus a collaborator's calibration
preview fix. The 747-file original development checkout remains separate.
The follow-up branch starts from that existing develop head and preserves its
fix. ADR 0023, contributor/agent guidance and metadata-policy regressions record
the requested task → develop → main flow. Merge/branch execution outcomes are
reported separately; no release or application acceptance is inferred.

The focused metadata-policy regression suite passed 173 tests in 1.72 seconds;
trusted-base execution and hostile-input/no-echo protections remain intact.
Hosted Actions on develop was inspected: jobs had zero executed steps and an
account billing/spending-limit annotation. This is not passing hosted evidence.
No billing, branch-protection or release settings were changed.

The first ordinary merge attempt was refused because repository merge commits
are disabled. Metadata confirmed squash is allowed. The documentation branch is
short-lived and can use squash; future long-lived promotions need an explicit
owner decision on merge-method settings. No setting was changed to force it.

## 2026-10-08 — architecture and collaborator documentation

### Follow-up: explicit shared-prompt review and storage clarification

At the owner's request, added the [TR01–TR08 product requirement](work-packages/team-prompt-review.md)
and proposed ADR 0022. Documented [actual session-data lanes](architecture/session-data-lifecycle.md)
from read-only source inspection: imported metadata versus ephemeral transcript
reads, sensitive title exception, separate authored-chat retention, and bounded
tool-event/payload coverage. No personal data or actual installation settings were
read. No implementation, collection, sharing or beta-scope expansion is claimed.
The existing gates and owner-review rules remain unchanged.

Documentation-only validation: all TR01–TR08 rows present, ADR proposed status
checked, generated catalog synchronized, 599 changed-document local links
resolved, scoped privacy scan zero findings and diff whitespace check passed.
No application tests or runtime acceptance were rerun for this documentation edit.

### Initial atlas delivery

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

[ADR 0024](adr/0024-inference-provider-boundary.md) proposes a shared inference
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
demo controls. Proposed [ADR 0025](adr/0025-enhancement-experiment-boundary.md)
consolidates the workstreams without accepting or silently superseding earlier
decisions. The live consumer/evaluator, model/GPU, hosted delivery and deployment
gates remain open. The broad suite's 36 baseline failures and four errors are
unchanged; no general workflow/native/release acceptance is claimed.

## 2026-10-10 — Coolify Actions source deployment (R26)

Task: owner-requested GitHub deployment action. Baseline: imported `develop`
`cadba09`; task branch `codex/coolify-deployment-action`. Scope: deployment
workflow, controller client, hosted authentication/readiness, synthetic tests and
operator documentation. Existing inference feature changes remain outside this
cohort. No provider sessions, model requests or live production deployment ran.

The existing image-publishing workflow did not match the configured Git-source
application. The proposal validates configuration, retains the full quality gate,
builds and smoke-tests the exact source, pins the existing Dockerfile application,
and verifies both deployment completion and two matching health responses.
Cloudflare origin verification and the Python health command preserve the hosted
login/runtime profile. The client checks source/build-argument read-back, refuses
incompatible application profiles and never retries an uncertain deployment POST.
The secret-free PR image check is separate from production approval.

Fresh synthetic selection: 85 deployment and Cloudflare tests passed; 258 tests passed including the
collaboration-policy checks. It includes
real owned loopback redirect/JWT-handler checks and mocked controller contracts;
no external controller or provider was contacted. Image CI and live acceptance
must be recorded separately. No beta gate or full-suite acceptance is claimed.
Owner review, promotion to main, deployment secrets and the documented Coolify
build-time/runtime settings remain required before a production run.

The public Coolify API contract omits environment-variable values for ordinary
read/write tokens. A follow-up accepts that redacted update receipt while still
checking the build-time flag, source pin, deployment commit and running revision.
An explicitly returned wrong value still prevents deployment. This avoids granting
sensitive-data read permission to validate a non-secret build revision.

## 2026-10-10 — repair inherited quality-gate fixtures (R26)

Task ID / atlas nodes / beta gates: quality-fixture-repair; R26, MA01, MA04,
A04, A05, A08, A09, A25; B00/B11 remain open.

Approved source baseline: develop `e47b709`, after the deployment-action merge.
The owner requested resolving the full quality gate failures blocking deployment.
The initial frontend run reported 28 failures; Linux backend tests exposed stale
fixtures before a Windows-platform mock changed process-wide `os.name` and
crashed pytest's path handling. These are synthetic source-test findings.

Allowed files and preserved contracts: failing frontend/backend tests, shared
historical-schema and runtime fixtures, bounded MCP cleanup, explicit provider
compatibility retry, CI execution and this evidence record. Model readiness,
private route boundaries, native approval and exact checksum validation remain
required. Every backend test and platform security preflight remains required.

Implementation: isolate the platform mock; reconstruct historical schemas with
the correct FTS and checksum state; provide explicit synthetic power and regular
interpreter fixtures; require recoverable-trash refusal on unsupported platforms.
Frontend assertions cover local drafting with every send path blocked, exact
localized counts, advertised resume capability and no automatic attachment replay.
Controller discovery explicitly excludes owner-facing saved-message search.

The complete diagnostic run exposed additional MCP migrations and platform
assumptions. A virtualenv symlink is resolved to the real interpreter with only
the explicit installed test dependencies; native absolute temporary paths replace
Windows-only fixture paths. The scope-router corpus keeps its exact digest with
LF checkout bytes. The manifest CLI uses its base interpreter plus the locked
test dependencies, preserving the one-process budget on Windows.

Two runtime defects have synthetic regressions: an owned process status error
now remains unknown and is retried within the existing cleanup deadline, with
persistent errors still refusing cleanup verification. An explicit compatibility
check retries an unavailable primary text surface after onboarding supplies a
valid folder; cached GETs do not probe, and an unavailable text surface retains
the event-surface fallback. The onboarding test also isolates its default home
before clearing the environment override.

Positive, negative, recovery and privacy checks: 149 focused backend tests passed;
one existing reviewed-tool packaging integration is opt-in and was skipped.
All 2,912 frontend tests across 201 files passed. Generated API drift and the
production frontend build passed. These are integration results with fictional
fixtures. Privacy scanning of the exact staged source export and the architecture
check passed. The full diagnostic backend census was 6,174 passed, 32 failed and
56 platform/opt-in skips; its collection predates these follow-up corrections.
The complete affected selection passes under the CI Python 3.11 runtime:
558 passed and four existing platform/opt-in skips. Python 3.13
changes HTTP reason phrases in generated OpenAPI descriptions; the committed
artifact and CI retain their Python 3.11 binding. Git worktree pointer metadata
is excluded by scanning the staged source export, without changing the scanner.

The browser census was 183 passed, six failed and six existing skips. All six
failed readiness scenarios pass after the correction, including keyboard-send
refusal with a retained draft. The initial repair commit passed hosted frontend
unit/API/build, repository integrity, policy and container smoke checks; complete
checks on the final candidate remain pending.

Required evidence / completion: unchanged full quality jobs must pass on the
candidate; a successful source deployment needs its separate controller and
running-revision receipts. No native, model, packaged or beta acceptance follows
from these test repairs.

Process/resource bound: inspect incremental failures, run focused corrections,
then each full gate; do not raise test timeouts or weaken assertions. The Windows
baseline reached about 97% before its 60-minute limit. Two required backend
shards per platform partition the full collection, with an independent synthetic
CLI proof of exactly-once coverage and failed-test propagation. A local
browser run that reused an occupied port was stopped after identifying unrelated
404 responses; its replacement owns a separate loopback port. It is not passing
browser evidence.

Owner decisions still needed: review this repair cohort and authorize its merge
and promotion. Result / source commit / artifact digest / cleanup: pending full
candidate checks; no release artifact or production change in this cohort yet.


## 2026-10-11 — deployment HTTP client identity (R26)

Task: resolve the remaining failure in the owner-authorized deployment.
Baseline: develop `d68f281`; task branch `codex/fix-deployment-client-headers`.
Scope: deployment HTTP headers, their synthetic regression, operator guide and
bounded evidence records. No architecture or acceptance policy is changed.

The reviewed main candidate passed its full quality and container checks. An
edge Browser Integrity Check then rejected the generic Python HTTP client before
controller authentication; no new deployment was started. An unauthenticated
probe with an explicit application identity reached the Access login boundary.
No credentials, response content or private records were used in that probe.

The proposed client sends `Prompt-Enhancer-Deployment/1.0` and requests JSON for
source pinning, the single deployment trigger, status polling and health checks.
The existing destination-specific authentication, redirect refusal, exact commit
checks and two consecutive health responses remain required. The regression
failed before the fix; all 85 synthetic deployment/authentication tests pass after
it. The worktree privacy check detected Git pointer metadata; staged-source
privacy and canary checks exclude that worktree-only pointer without changing
the scanner. This is integration evidence with fictional fixtures, not live
source-deployment acceptance. Owner review, promotion and authenticated live
verification remain pending; B00/B11 and native/model gates remain open.

## 2026-10-11 — reuse validated main quality evidence (R26)

Task: remove redundant full test runs at the owner's request.
Baseline: develop `d68f281`; continuation of the deployment-client task branch.
Scope: quality scheduling, read-only release evidence verification, synthetic
regressions and operator documentation. The full Linux/Windows/backend/frontend
suite, container boundary and live revision checks retain their coverage.

PR updates run the full quality workflow once; feature/develop pushes no longer
start a duplicate. Superseded PR runs are cancelled. Each distinct main commit
retains its own validation. Manual deployment checks the newest matching main
push run and all six required jobs instead of invoking the full suite again.
The verifier waits for an existing pending run, rejects missing or unsuccessful
evidence and validates repository, workflow, branch, revision and job attempts.
It uses read-only Actions permission, receives no deployment secrets and can
only make GET requests. A failed-job-only rerun can reuse earlier passing jobs
from that same commit; newer failed or skipped evidence cannot be hidden.

All 50 new synthetic verifier/scheduling tests pass. A read-only check against
an existing successful main run also passed without triggering CI or deployment.
This is bounded workflow integration evidence. The accompanying HTTP identity
fix still awaits owner review, promotion and live deployment verification;
R26 and all beta/native/model acceptance statuses remain unchanged.
