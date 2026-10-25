# Beta progress journal: published handoff

## 2026-10-25 - Compact Bench previews and link runs to experiments

From reviewed develop `2de0075`, Run variations uses three-line prompt previews
with an ellipsis. A **View experiment** action opens the run's saved experiment
revision. All 38 affected desktop/mobile checks pass, including keyboard
navigation when a newer revision exists; a separate long synthetic preview
confirms compact rows at both sizes. Full prompt details remain
available. Source review and API/UI deployment are pending; W05/B10 stays open.

## 2026-10-25 - Name Bench runs by their saved selections

The [run-label candidate](bench/client-navigation.md#run-labels-show-the-selected-scope---2026-10-25)
replaces the full experiment title in run headlines with the workflow and
selected case/variant, or counts for larger selections. Selected attempt counts
and the full experiment matrix are explicitly separate. History receives only
bounded subject IDs from the saved snapshot; prompt/context content remains
excluded and stored definitions/results remain unchanged. All 105 affected
backend tests and 50 desktop/mobile checks pass with synthetic fixtures,
including missing metadata, restart, navigation, refresh and long identifiers.
Source review, promotion and API/UI deployment remain open. No new core artifact,
experiment execution or recovery action is needed; W05/B10 acceptance is unchanged.

## 2026-10-25 - Reproduce and correct consumer subscriber cleanup

After owner-attested recovery and the reviewed worker/consumer/relay rollout,
the first revision-6 smoke completed its before evaluations but failed with
`remote_cleanup_unconfirmed`. A reproduced SDK defect leaves a finished
conversation subscribed: its websocket stop flag is checked only on the next
received event. An isolated synthetic ACP test reproduces HTTP 409 release
failures with and without the error guard. The
[candidate correction](bench/consumer-retention.md#finished-subscriber-release---2026-10-25)
publishes current state within the existing bound, allowing a stopped client
to disconnect while keeping all release checks. All 48 affected tests pass;
both real-SDK fixtures release in under 0.1 seconds while live subscribers
remain protected. The actual failed attempt's later release and workspace
cleanup are confirmed and recovery is recorded without replay. Source review,
consumer rollout and fresh qualification remain open; acceptance is unchanged.

## 2026-10-25 - Record recovery confirmation without a typed reference

From reviewed develop `f8492d1`, the owner-approved
[confirmation change](bench/recovery-ui.md#confirmation-without-manual-bookkeeping---2026-10-25)
removes manual audit-label entry. The server records one opaque confirmation
reference with the run and time; repeated requests preserve that first record.
Existing API clients may still supply a validated reference. Actual remote-stop
verification, explicit acknowledgement, same-origin JSON and confirmed local
cleanup remain required. Historical results and the no-replay policy are retained.

All 442 Bench tests and 22 affected desktop/mobile checks pass using synthetic
fixtures and owned loopback processes. The receipt-persistence regression failed
before the change. Negative checks retain request rejection and cleanup guards;
browser checks verify checkbox gating, no text entry and retained failure details.
Source review, promotion and deployment remain open; no new core release or
worker update is needed for this form change. W02/W05/W07 acceptance is unchanged.

Separately, owner-approved PRs #98/#99 deployed the preceding recovery UI at main
`a0967c8`. Deployment `40179897463` builds successfully; only the failed revision
verifier is retried after its first HTTP 404, and the serving revision is verified.
Live inspection confirms the primary timeout, evaluation stage, global hold and
local cleanup state. Remote completion and worker cleanup-retry rollout remain
unconfirmed. No recovery hold is cleared and no experiment is replayed.

## 2026-10-25 - Make recovery actionable and expose execution causes

The [Bench recovery candidate](bench/recovery-ui.md), from develop `233b49d`,
puts the primary error and stage in history and above run results, and links
global queue blockers across filters. Guided recovery distinguishes local cleanup
from remote stop, retains operator evidence and never replays interrupted work.
Cleanup failures now retry in the worker loop with a durable three-check budget,
cooldowns and ownership validation; exhausted checks require explicit attention.
All 436 Bench tests and 28 desktop/mobile checks pass. The browser suite uses
installed Chrome after the standalone Playwright browser executable is absent.
Only synthetic fixtures and owned loopback processes are used. Source review,
API/UI and worker rollout, hosted recovery and independent onboarding remain open.
The existing remote hold and MA18/W02/W05/W07 acceptance statuses are unchanged.

## 2026-10-25 - Release core 0.3.7 and prepare qualification revision 6

Owner-approved PRs #94/#95 merge the typed ACP failure correction. Publication
`40145584966`, attempt 2, reuses the initially built image, verifies its offline
identity and cleanup, and confirms core 0.3.7 registration. API deployment
`40145554980`, attempt 2, verifies main `9c64198`; only the failed readiness job
is retried after its initial external HTTP 404. No worker/consumer/relay rollout
or model execution follows while the revision-5 recovery hold remains unresolved.

The [revision-6 definitions](bench/robustness-experiment.md#revision-6-task-card---2026-10-25)
change only identity/core pins. All 32 definitions, 240 semantic requests and 58
focused synthetic tests pass; deployed history ends at generation 5. The plan
retains 15 smoke attempts and 240 main pairs, one pair per run, with
`autoRun: false`. Definition reviews/publication, actual remote-stop evidence, coordinated
rollout, fresh live qualification and independent onboarding remain open.
Historical cohorts and MA18/W02/W03/W05/W07 acceptance statuses are unchanged.

## 2026-10-25 - Preserve partial qualification and classify ACP failures

The [revision-5 cohort](bench/robustness-experiment.md#revision-5-partial-live-result---2026-10-25)
completes 15 technical smoke successes and 209 main attempts: 200 technical
successes, eight invalid reviews and one interrupted embedding evaluation.
The maximum-prompt boundary stops before workflow execution with a gateway I/O
timeout and an explicit recovery hold; 31 pairs remain unsubmitted. All 8,944
smoke/main UI cells and 67,999 typed CSV cells match the APIs and verified private
exports. Earlier failures remain intact and are not reclassified from inference.

The [consumer failure candidate](bench/consumer-failure-reporting.md), based on
reviewed develop `b3d42e7`, proposes core 0.3.7 and a versioned ACP failure adapter.
It preserves safe failure categories through the worker, inspection, UI and
export while retaining remote uncertainty. All 612 affected core/Bench tests and
14 desktop/mobile checks pass; packaged startup and isolated pinned-SDK probes
verify readiness, adapter selection, failure classification and output preservation.
Source review, publication,
coordinated deployment, fresh qualification and independent onboarding remain
open. MA18/W02/W03/W05/W07 acceptance statuses are unchanged.

## 2026-10-24 - Release core 0.3.6 and prepare qualification revision 5

Owner-approved PRs #90/#91 repair the three missed compatibility expectations.
The full 412-test Bench gate now passes locally and in the release/deployment
workflows. Core publication `40127596404` builds, verifies offline, cleans up and
registers core 0.3.6 from main `3b424e8`. Deployment `40127562554` passes API health
and protected revision checks after a verifier-only retry for its initial HTTP
404. Worker/relay replacement preserves the API and consumer, joins the correct
namespace and passes authenticated consumer readiness with no active work.

The [revision-5 definitions](bench/robustness-experiment.md#revision-5-task-card---2026-10-24)
change only identity/core pins. All 29 definitions, 240 semantic requests and 58
focused synthetic tests pass. Fifteen smoke attempts precede the same 240 main
pairs, with one pair per run and explicit continuation checks. Definition reviews,
publication, fresh live qualification and independent onboarding remain open.
Historical cohorts and MA18/W02/W03/W05/W07 acceptance statuses are unchanged.

## 2026-10-24 - Repair the full Bench compatibility gate

Owner-approved PRs #88/#89 merge the flow diagrams and review diagnostics.
Deployment `40126241241` and core publication `40126311234` stop before runtime
changes: the full Bench suite finds three stale response-equality expectations
missed by the earlier 229-test selection. The [bounded repair](bench/experiment-flow.md#release-gate-compatibility-repair---2026-10-24)
retains exact stored-result equality, separately asserts computed continuation,
and verifies safe rejection details through HTTP, storage, inspection and
JSON/CSV export. All 412 Bench tests pass locally. Repair review/promotion,
hosted validation, the authorized core 0.3.6 publication, deployment and complete
live qualification remain open. Acceptance statuses are unchanged.

## 2026-10-24 - Explain experiment flows and completed review rejection

Reviewed PRs #86/#87, definition publication and the approved worker/relay rollout
complete revision-4 prerequisites. Its 15 smoke attempts succeed technically;
the main cohort stops with five successes, one invalid review, two skipped and
232 unsubmitted pairs. All 840 smoke/main UI cells and private exports match
their API records. The response schema reached ACP; strict rejection of a nested
enum is correct. The completed operation is cleaned and the queue is clear.
See the [preserved result](bench/robustness-experiment.md#revision-4-live-result---2026-10-24).

The [flow/diagnostics task card](bench/experiment-flow.md) starts from approved
develop `2e76634`. It proposes core 0.3.6 with allowlisted rejection reason/path,
Bench inspection/API continuation guidance, analysis v2 error columns and
definition-driven diagrams for Check, Clarify and Rewrite. One case/variant per
run allows independent coverage after a confirmed invalid response; uncertain
or incomplete evidence still stops and never authorizes replay. All 301 core
and 229 distinct Bench tests plus 38 desktop/mobile checks pass. Source review,
core publication, deployment, fresh complete qualification and independent
onboarding remain open. MA18/W02/W03/W05/W07 acceptance statuses are unchanged.

## 2026-10-24 - Release core 0.3.5 and prepare qualification revision 4

Owner-approved PRs #84/#85 merge the gateway diagnostics and evaluator recovery
correction. Publish Core `40116214512` builds and registers core `0.3.5` default
from reviewed main `62e0d4e`, with verified runtime identity, tokenizer and probe
cleanup. API deployment `40116199747` passes image health and protected revision
checks after repeating only its initially failed HTTP 404 verification job.
Worker/relay rollout remains a separate prerequisite.

The [revision-4 task card](bench/robustness-experiment.md#revision-4-task-card---2026-10-24)
pins that exact receipt in three new definitions. Only immutable identity and
core selection differ from revision 3. All 26 definitions, 240 new semantic
requests and 58 existing synthetic publication/binding/pipeline tests pass.
The operation plan preserves 15 separate smoke attempts, 240 fresh main pairs
and at most four standard attempts per run. No older success is counted toward
the new artifact's coverage. Named definition reviews, publication, worker/relay
rollout, live qualification and independent onboarding remain open.

## 2026-10-24 - Preserve evaluator transport diagnostics and hold uncertain work

Bounded recovery reaches 139 successful unique pairs of the 240-attempt core
0.3.4 matrix. The next diagnostics-only Rewrite pair stops during embedding
evaluation; 100 pairs remain unstarted. The actual transport cause is unknown.
Matching stable model-host completion counters support stopped-state evidence;
the private export and all 5,612 main UI/API cell comparisons are verified.
The earlier 600 smoke cells remain separate. No uncertain work is replayed.

PRs #81/#82 are owner-reviewed and promoted through #83. A separate
[recovery candidate](bench/gateway-failure-recovery.md), based on develop
`9cd3016`, proposes core 0.3.5 with allowlisted diagnostics across the process
boundary and a Bench hold independent of generation bindings. Nine regressions
fail before correction. All 575 affected tests and ten desktop/mobile checks
pass afterward. Private upstream details remain excluded and earlier results
remain immutable. Source review, release, deployment, complete qualification
and independent onboarding remain open; acceptance statuses are unchanged.

## 2026-10-24 - Preserve the whole-run deadline cause

The [deadline reporting candidate](bench/run-budgets.md) starts from reviewed
develop `ca1af3a`. A frozen qualification run reaches its 1,800-second whole-run
limit after 56 successful attempts, but the reported core uncertainty obscures
why cancellation began. Confirmed stop permits deliberate recovery in smaller
batches while preserving that interrupted history.

The worker candidate records its deadline cancellation cause while preserving
the core result, attempt status, cleanup and reconciliation hold. Four cases
fail before the fix; all 64 affected worker/storage/export tests pass afterward,
including 16 deadline/user/core cause and terminal-outcome regressions. Client
and operator guidance now distinguish whole-run, attempt and observation limits.
Source review, worker deployment, complete qualification and independent
onboarding remain open. No acceptance status changes.

## 2026-10-24 - Qualify smoke, preserve a main interruption and clarify stale results

PRs #79/#80 and Publish Experiments `40098767343` deliver revision 3 with exact
core 0.3.4 pins. All 15 smoke attempts pass technical checks; all 600 rendered
metric cells agree with the API, and private exports retain typed values and
explicit missingness. The live ACP system event includes the formal schema.

The [main result](bench/robustness-experiment.md#revision-3-live-result---2026-10-24)
stops after 56 successful attempts when the whole-run deadline cancels NLI.
Eleven siblings are skipped; 172 later attempts never start. Fresh model-host
completion evidence permits reconciliation, and the historical interruption and
verified partial export remain preserved. Offline tokenization accepts the input;
the deployed 1,800-second run limit and 1,801-second run duration establish
the cancellation cause. The 68-attempt batch exceeded that independent budget.
Future standard batches contain at most one case and four variants.

An expired browser session leaves old results visible with a generic fetch
error. A separate source candidate labels them stale, offers reconnection and
recovers without submitting a run. The network-abort regression fails before
the correction; six new desktop/mobile checks and 20 existing browser checks
pass. Source review and deployment remain open. No main attempt is replayed,
and no general acceptance or independent onboarding gate is closed.

## 2026-10-24 - Release core 0.3.4 and prepare qualification revision 3

PRs #77 and #78 complete the reviewed ACP schema correction. Publish Core run
`40096081387` builds the default artifact from main `8fd3da6`, verifies its offline
runtime/tokenizer identity and cleanup, and registers it with Bench. The release
fingerprint matches the local reviewed source.

The [revision-3 task card](bench/robustness-experiment.md#revision-3-task-card---2026-10-24)
starts from develop `e4d6e82`. It retains all cases, policies, bindings, harness,
assertions and limits; only revision/generation and core pins change. All 23
definitions and 240 new semantic requests validate, with the same 15 smoke and
240 main attempts. Read-only API metadata confirms the new identities are unused.
All 51 targeted publication, synthetic pipeline and privacy tests pass.

The failed revision-2 cohort remains preserved. Definition review/publication,
fresh runtime preflight, complete live qualification and independent onboarding
remain open. No revision-3 model call is submitted during preparation, and no
acceptance status changes.

## 2026-10-24 - Stop failed smoke and preserve the ACP response contract

The [revision-2 smoke result](bench/robustness-experiment.md#revision-2-smoke-result-and-acp-schema-candidate---2026-10-24)
follows approved publication and confirmed recovery. Its first attempt fails on
an invalid review enum; two attempts are skipped and subsequent runs stop. All
five before evaluators return, cleanup completes, and the expected diagnostic
unknown remains explicit. UI/API and private JSON/CSV failure evidence agree.

Proposed core `0.3.4` forwards the previously omitted response schema through ACP
system instructions and records adapter `openhands-acp-1.49.1.v5`. The strict
parser still rejects invalid output; guidance does not guarantee model compliance.
The schema-delivery regression fails before correction, then all 152 affected
tests pass. Source/core review, publication, a new pinned cohort, live smoke and
independent onboarding remain open. Acceptance statuses remain unchanged.

## 2026-10-24 - Prepare the released-core qualification revision

Core `0.3.3` is released from reviewed main `52dff00`, with offline tokenizer,
runtime, cleanup and catalog-registration checks complete. The readiness
correction deployed at `e2ddb7e` passes controller health and authenticated
serving-revision verification under the existing gateway policy.

The [revision-2 task card](bench/robustness-experiment.md#revision-2-task-card---2026-10-24)
starts from develop `0b0b36d`. Three new immutable definitions retain the existing
240-attempt matrix and change only revision/generation and core pins. The run
plan includes nine ordinary and six NLI boundary smoke attempts outside the main
cohort, preserving unknown reasons and independent candidate admission.

Local evidence: 20 definitions and 240 new effective requests validate; exact
r1/r2 comparison and the released build fingerprint agree. All 62 targeted
synthetic publication, pipeline and privacy tests pass. Named source/promotion
reviews, definition publication and live qualification remain pending. Remote
stop evidence must precede reconciliation or inference. No live model call is
made by this preparation; acceptance statuses and independent onboarding remain
open.

## 2026-10-24 - Separate deployment health from sensitive log access

The [readiness correction](bench/continuous-deployment.md#readiness-verification-correction---2026-10-24)
starts from reviewed develop `68761fc`. Controller metadata proves selected-image
health, then a dependent job verifies two fresh responses from the protected
Bench readiness endpoint using the existing publication gateway credentials.
Each job receives only its destination's credentials; neither reads log bodies.

Evidence: 123 affected deployment tests pass across the main and focused loopback
runs, including revision mismatch, unavailable/cached/malformed responses, bounded
reads, consecutive health, denied access and redirect isolation. Source review,
promotion and hosted verification remain open. No token permissions, core pins,
experiment results or remote recovery holds change; R26 remains partial.

## 2026-10-24 - Bound NLI input before remote inference

The [NLI input admission candidate](bench/nli-input-admission.md) starts from
reviewed develop `977cc641`. Core `0.3.3` counts complete premise/hypothesis pairs
with pinned, hash-verified tokenizer files before constructing the gateway client.
Oversized pairs produce an explicit unknown reading; other evaluators continue.
Missing or corrupt tokenizer assets fail locally. Unconfirmed remote operations
retain their existing reconciliation requirement. Adapter `litellm-nli.v2`
records the change, and Bench explains the unavailable measurement.

Evidence: 509 affected unit/integration checks pass across regression and final
focused runs, along with two desktop/mobile browser checks. The default core
image builds and an owned offline, read-only container verifies both tokenizer
pins and input admission without credentials or a gateway call. The container
is removed after the probe. Source review, a separate core release, a new pinned
experiment revision and live qualification remain open. Existing cohorts and
MA18/W03/W05/W07 acceptance statuses remain unchanged.

## 2026-10-23 - Add the Bench client and private analysis contract

The owner approved the [client/export implementation](bench/client.md) on the
existing handoff branch, based on reviewed develop `cdcfb5f`. The client provides
discovery, shared API preflight, receipt-backed submission, bounded observation,
inspection, cancellation acknowledgement and explicit-cohort export. Its JSON
envelopes distinguish admission, execution, assertions and observation timeouts.
The preflight validates every request and core registration; worker/provider/model
readiness remains explicitly unverified. No model call is made by preflight.

Versioned JSON and six CSV tables retain zero, missingness, labels, provenance,
workflow order, configuration fingerprints, timings, assertions and exclusion
reasons. A bundled schema/dictionary and final hash manifest accompany each
private export. Text fields and credentials are omitted; the derived records
remain sensitive. Submission receipts are durable before admission, and retrying
a lost acknowledgement reuses the request identity without duplicate generation.

Evidence: the 363-test affected Bench/core suite and 22 desktop/mobile checks
pass. The final 73-test focused run covers export order/configuration provenance,
unresolvable contract references and v2 HTTP/storage/export agreement. The CLI journey uses actual subprocesses and
an owned loopback API from outside the checkout, with synthetic model/container
doubles. The final client wheel builds offline; its schema command and packaged
export dictionary work outside the checkout. Privacy, JavaScript syntax,
generated-atlas and whitespace checks pass.
No deployment, real-model qualification or source publication occurs here.
Independent onboarding and frozen-candidate acceptance remain open.

The follow-up instruction audit adds tracked `operate-bench-experiment` routing
for Codex and Claude, covering the shared client, admission recovery, explicit
cohorts and interpretation. Authoring/release guidance now consistently separates
v2 artifact pins from legacy v1 catalog resolution. Repository instructions take
precedence over older personal skill copies. All four skill validators and ten
documented parser forms pass; no model or service request is made by these checks.
Runtime generation policies and typed evaluator inputs are documented separately
from operating-agent skills. Independent agent/user walkthrough remains open.

## 2026-10-23 - Prepare Bench handoff and propagate review failures

The [bounded handoff task](bench/handoff.md#correction-task-card---2026-10-23)
starts from reviewed develop `cdcfb5f`. Invalid review responses and confirmed
model failures reproduce a false successful execution in all three review flows.
The execution wrapper now retains their receipts and before measurements while
reporting a failure. It does not evaluate an absent candidate or run assertions.
Valid reviews without rewrites and optional model skips retain their semantics.

The Bench result page shows review state, recorded step outcomes and execution
errors without opening raw JSON. It warns about historical success/failure
contradictions without changing stored records. The guide adds the UI journey,
result dictionary, existing AI API contract, operational limits and handoff gates;
the README removes duplicated terminology and separates v2 pins from v1 behavior.

Evidence: six failing-before regressions, 84 passing affected core/worker/API
tests, and 22 passing desktop/mobile checks. The real core HTTP application,
synthetic model and container double exercise durable partial failure, skipped
remaining attempts, retention cleanup, stored API agreement and later admission.
All inputs are independently authored synthetic fixtures. No live model call,
deployment, source publication or merge is performed. New artifact versions,
frozen-candidate verification and independent onboarding remain required.

## 2026-10-23 - Explain unscored Bench readings and correct coding cues

The [evaluator coverage candidate](bench/evaluator-coverage.md) adds an explicit
`deterministic.v2` binding in core 0.3.1 and explains measurement states in Bench.
It recognizes requested patch/test artifacts and explicit prohibitions while
preserving v1, workflow diagnostics, session analytics and historical results.
Known numeric zero, unknown, abstained, not applicable, evaluation error, missing
readings and categorical transitions remain distinct.

Synthetic evidence covers all six reviewed inputs, negative cue cases, language
and context guards, provenance/version rejection, owned HTTP for both bindings,
Bench worker round trips and 50 desktop/mobile browser checks. Source review,
core publication, Bench deployment and a new experiment revision remain pending.
General metric, workflow and real-model acceptance gates are unchanged.

## 2026-10-18 - Make heavy development CI manual

The owner explicitly approved manual-only full Ubuntu/Windows backend,
frontend/browser, Bench container/runtime and hosted-container checks. The
[development CI policy](ci-quality-gate.md) retains automatic privacy,
repository integrity, PR metadata and Experiment definition checks. Existing
deployment validation, runtime readiness and core-release checks remain intact.
An automatic green quality result now means fast integrity evidence only.

Evidence: 63 focused scheduling, quality-evidence and privacy tests pass. All
workflow YAML and job dependencies parse correctly. The full regression suites
were not run for this scheduling change. R26 and release acceptance statuses are
unchanged.

## 2026-10-18 - Repair Windows checks before workflow promotion

Hosted validation of the workflow candidate exposed four existing filesystem
portability failures in the synthetic consumer tests. Receipt writes now follow
the repository's atomic-file convention: sync the file on every platform, replace
it atomically, and additionally sync its parent directory on POSIX. Windows cannot
open that directory through `os.open`. Tests check Windows read/write attributes
separately from POSIX owner/group modes; no retention scenario is skipped.

Evidence: all 15 focused consumer tests pass locally, including Windows-path
file-sync coverage, preservation of the prior receipt after a file-sync failure,
and propagation/descriptor cleanup after a POSIX directory-sync failure. The
deployed Linux consumer retains directory durability and private file modes.
Hosted Windows revalidation and source promotion remain pending. This correction
does not qualify a native Windows consumer or change the frozen atlas/gates.

## 2026-10-18 - Align prompt workflows with pre-Bench logical steps

The owner requested both a logic adjustment and clear presentation of each flow.
Rewrite and clarification version `2.0.0` now score, infer context and optionally
perform model review with an optional rewrite, using the same sequence as Prompt
Check. Default policies focus on rewriting or clarifying missing details. Their
v1 direct-rewrite and deterministic-placeholder versions retain their digests
and behavior. The UI shows explicit names and ordered steps on experiment,
setup and result pages. Session workflows already preserve their old sequences.

Evidence: 372 affected backend tests, 62 focused checks after the final
policy-version receipt correction, 48 desktop/mobile browser tests and six
offline definition validations pass. The six pre-Bench synthetic cases now
cover all three review flows. Privacy/OpenAPI, syntax and generated-file checks
pass. Workflow/version notation initially triggered the email canary; the prose
was corrected without relaxing the scanner. Source remains an unpublished core
`0.2.0` candidate; existing experiment pins and broader acceptance gates remain
unchanged. See [the workflow record](bench/versioned-workflows.md).

## 2026-10-18 - Versioned core components and fixed experiment workflows

Task branch `codex/versioned-workflows` starts from owner-selected develop
`dbd5bf1`. [ADR 0027](adr/0027-versioned-core-components-and-workflows.md) records
the agreed reusable components, versioned workflow compositions and separate
harness evaluation. The local implementation extracts the pre-Bench Prompt
Check/session logic, exposes three prompt workflows to Bench and fixes v2
experiment workflow/core/harness identities. Supported variant settings remain
model/provider bindings, policies and step parameters. Existing definitions,
history and app privacy boundaries have compatibility coverage.

Evidence: 517 affected backend tests pass with two Windows-only skips; 111
overlapping focused checks pass after the final compatibility fixes. All 42
desktop/mobile browser tests pass, with four workflow checks repeated after
schema export. Six synthetic golden cases match the pre-Bench Prompt Check
metrics, context and model-facing policy/input. Four definitions, loopback CLI,
worker-to-core HTTP integration with synthetic runtime, syntax, privacy,
architecture generation and whitespace checks pass. See the
[implementation record](bench/versioned-workflows.md#local-validation---2026-10-18).

Source review is pending. Core `0.2.0` is an unpublished candidate; existing
experiment pins are unchanged. Session workflows are reusable library/app
compositions but need a separate typed Bench transport and harness before that
use. No models, production data, deployment or publication were used. Broader
MA18/W/WP, device, real-model and release acceptance gates remain open.

## 2026-10-14 - Resolve Bench core versions per Run

On `develop` baseline `f7c380e`, the owner-requested
[resolution change](bench/core-version-resolution.md) makes publication v2 carry
only an Experiment definition. New Runs and reruns resolve a separate core
version/variant catalog and retain an immutable image digest. Catalog registration
does not start work. Duplicate requests keep their original binding, and schema
2 migration preserves existing definition and Run evidence. Proposed ADR 0026
records this amendment; API and worker select the same variant.

Evidence: 237 synthetic Bench tests, three definition validations, privacy scan,
default/model CPU/CUDA Compose validation and two skill validators pass. No
production database, registry, model or deployment was used. The owner-authorized
release-registration Action step delivers the verified artifact receipt to Bench
after successful runtime verification, with gateway credentials scoped to that
step. Workflow-order and failure checks cover that delivery. Hosted
checks, owner review and deployment remain open; no general beta gate closes.

## 2026-10-14 - Definition-only Bench validation

The scoped publication candidate separates Experiment JSON from full Bench
verification. Definition changes validate request contracts, revision/generation
identity uniqueness and privacy; Bench code/runtime/workflow changes retain the
full checks. The CLI shares identity validation with the publisher. Evidence:
277 synthetic Bench/CI-policy/privacy tests and 24 real pinned Action scenarios
pass. Hosted CI and owner merge remain pending; no acceptance gate closes. See
the [experiment task record](bench/concise-structured-experiment.md).

## 2026-10-14 - Scope CI to affected components

Task: R26, B00/B11; baseline `fe47f63`, continuing the separate-core-release PR.
The owner requested affected-component checks for PR updates and main pushes.
Added a pinned `dorny/paths-filter` Action with shared YAML filters; no custom
change parser or historical evidence cache. Per-update comparison prevents a
documentation follow-up from repeating product suites for earlier code changes.
CI edits run focused policy tests. Integrity always runs; an aggregate requires
selected jobs to pass and unselected jobs to be skipped. Exact-main deployment
verification consumes that aggregate without restarting tests.

Evidence: 58 synthetic verifier/aggregate tests, workflow lint, actual pinned
Action comparisons with fictional Git inputs, privacy and whitespace checks pass.
Tests cover unexpected skips, failed/cancelled jobs, provenance mismatches and
rerun races. No product suite or release was started locally for these CI edits.
Hosted checks and owner-authorized merge are pending; no acceptance gate closes.

## 2026-10-14 - Separate optional core release from Experiment publication

On `develop` baseline `01a4d21`, added a manual-only Publish Core Action and a
version/source-bound release command. Experiment publication now resolves
existing core artifacts with read-only package access and cannot build or push
them. A missing image requires the separate release first. The authoring skill
asks whether to reuse a core or prepare a new version; deployment has its own
skill. See [the task and operator guide](bench/core-publication.md).

Local evidence: 201 synthetic Bench tests, release CLI check mode, both skill
structure checks, privacy and whitespace checks pass. Tests cover source/version
refusal, missing artifact/no delivery, runtime probe bounds and failure cleanup,
and separate workflow authority. No new image or Experiment was published; actual
registry/container/worker verification remains separate. No general gate closes.

Follow-up: root Codex/Claude instructions require repository-local skills and
Bench guidance. Three skill validations, 19 referenced paths/imports and nine
privacy tests pass. Merge validation reproduced and corrected an outdated
consumer-process match in the relay smoke; its complete isolated-container run
now passes with every security/restart assertion retained. Six HTTP 422 response
descriptions are explicit across Python versions; all nine OpenAPI export tests
pass without changing the committed schema. These bounded checks add no model,
provider-account or production-release qualification.

## 2026-10-14 - Bench stats preview above list filters

Corrected the history layout on `develop` baseline `994ed34`: a compact stats
preview precedes the homepage and experiment run-list filters. View all stats
opens separate global or revision-scoped charts with their own filters. Applied
filters carry between both views; browser Back restores list pagination.
Existing summaries and metric semantics remain unchanged.

Local evidence: 184 Bench backend tests, 38 desktop/mobile browser checks,
JavaScript syntax, privacy and whitespace checks pass. Synthetic visual checks
confirm preview ordering and no horizontal overflow on either screen size.
Owned fixture servers were stopped and temporary dependency links removed.
See the [bounded correction evidence](bench/client-navigation.md#stats-preview-and-dedicated-charts---2026-10-14).
Hosted deployment verification is separate; no general acceptance gate changes.

## 2026-10-14 - Bench history filters and comparison charts

Implemented on owner-selected `develop` at `56ddc38`. Homepage and experiment
run lists filter the entire saved history by status, identity/revision, trigger,
model alias and UTC dates, preserving filters through pagination and navigation.
Activity/status charts and planned-attempt counts share that scope. Before/After
metric means and model/variant comparisons use paired numeric observations,
separate evaluator provenance and expose sample/exclusion counts. Unknowns remain
unknown, and chart summaries omit prompt/result text and operation identities.

Local evidence: 182 Bench backend tests, 36 desktop/mobile browser checks,
JavaScript syntax, privacy scanner and whitespace checks pass. Synthetic visual
inspection confirms responsive filter/chart layouts. One browser test worker and
owned loopback fixture servers were used; no provider call, production data read,
source publication or deployment occurred. See the [bounded task evidence](bench/client-navigation.md#history-filters-and-charts---2026-10-14).
Owner review and general workflow/native/release acceptance remain separate.

## 2026-10-14 - Bench model details and case-by-variant matrix

Implemented on the owner-selected `develop` baseline at `97b128f`. Experiments
and runs expose configured model aliases, while each attempt displays generation
and before/after evaluator provenance with unknown values preserved. The dynamic
matrix separates cases, variants and attempts, explains the paired comparison,
reflects run-form selections and links to attempt results. Run-card summaries
derive from saved settings and exclude prompts, instructions and evaluator targets.

Local evidence: 162 Bench backend tests and 28 desktop/mobile Chrome browser
checks pass, along with JavaScript syntax, repository privacy scanning and whitespace checks. Synthetic visual
inspection covers desktop/mobile layout. No live provider/model call, publication
or deployment occurred. See the [task evidence](bench/client-navigation.md#model-details-and-run-variations---2026-10-14).
General workflow, native and release gates remain unchanged.

## 2026-10-13 - Bench deployment verification through Coolify

The public gateway readiness request returned a login redirect. The owner chose
to keep gateway policy unchanged. Deployment now verifies the existing API
container through the authenticated controller: exact configured image, healthy
container status and two distinct fresh loopback health receipts containing only
the baked source SHA and timestamp. Receipts must postdate deployment, and stale,
wrong-revision, malformed or repeated lines cannot establish success. Runtime
log bodies are neither printed nor saved. Controller authorization failures fail
immediately. No public route, credential or gateway permission was added.

Local evidence: 160 Bench tests, privacy scanner and whitespace checks passed.
The packaged synthetic container smoke passed, including the local health receipt,
empty API and routed client. This establishes packaged local readiness; it does
not test the public gateway path or claim hosted deployment completion. The
broader desktop quality gate remains outside this owner-requested fix.


## 2026-10-13 - Bench builds from pinned source on Coolify

Replaced the deployment Action's GHCR build/push/pull path with the existing
Coolify service's commit-pinned Git build context. The Action updates one
nonsecret source-revision variable and the API's local image tag, then requests
a cached build for that API only. Gateway preflight, exact baked revision checks,
redirect rejection and content-free failure diagnostics remain in place.

Local evidence: 142 Bench tests passed, including 21 deployment tests; the privacy
scanner and diff whitespace check passed. No UI code changed. These tests prove
the request boundaries and failure handling, not a successful hosted deployment.
The one-time hosted build configuration was saved and read back; unrelated
Compose service definitions were unchanged. Hosted completion still requires
the existing gateway identity to reach readiness and the Action to verify main.
The broader desktop quality gate was not run for this bounded deployment change.


## 2026-10-13 - source reconciliation and Bench deployment Action

Reconciled the gateway/consumer-retention and Experiment publication branches
with the accepted Bench routes, forms, labels and paginated run overview. The
integrated publisher keeps gateway-only access and validates its acknowledgement.
Regenerated protocol schemas to match core 0.1.3 and reconciled the moved example
fixture used by browser tests.

Added the [Bench API deployment Action](bench/continuous-deployment.md): relevant
main pushes build a source image, run a packaged smoke, publish a digest and
redeploy only the selected API container through Coolify. Readiness must report
the baked source commit twice. Worker/consumer lifecycles remain separate.

Local evidence: 137 Bench tests, 108 focused core/consumer/gateway tests, 20
desktop/mobile browser checks, privacy scanning, JavaScript syntax, definition
validation and Compose validation pass. The source-derived container passes the
empty-database API/client smoke. No full desktop quality gate or new model run
is claimed. Hosted deployment remains subject to registry pull and gateway
configuration; local tests are not live deployment evidence.

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
