# Beta progress journal: published handoff

This is the shared execution handoff, not a second readiness ledger. Requirement
acceptance remains in [the product-readiness matrix](product-readiness-matrix-2026-09-12.md).
The owner's preserved development checkout contains additional October 6–7
journal history; this documentation branch does not overwrite or blanket-publish
that dirty tree. Reconcile those entries when admitting their source cohorts.

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
