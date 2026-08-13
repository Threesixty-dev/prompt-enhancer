# Real-metrics campaign ledger

This ledger records implementation evidence and release blockers. A completed
engineering check is not a claim that a metric or estimator is calibrated.
Private sessions, paths, prompts, model responses, credentials, caches, and
local runtime artifacts must never be added here.

## Campaign controls

- Branch: `codex/real-metrics-campaign`
- Merge policy: push coherent green commits; do not merge automatically.
- Data policy: synthetic fixtures for tests and review packets only.
- Review-loop limit: at most two critique/fix loops per phase.
- Phase order: baseline, P0, P1, P2, then optional P3 and P4.

## Phase status

| Phase | Status | Current scope | Acceptance gate | Open blockers |
|---|---|---|---|---|
| Baseline | Complete | Preserve and classify the inherited backend, frontend, model, test, and documentation work | Python, frontend, build, Playwright, privacy scan, clean worktree, and pushed commits | None |
| P0 | Complete | Runtime truth, readiness, visualization, previews, evidence contracts, durable jobs, local automation, Job Centre, exact metric scope, and revocation-safe result activation | Backend, frontend, build, real-loopback and browser E2E, privacy, migration-upgrade, cancellation, supersession, restart, and concurrent revocation gates | No P0 blocker; Codex still truthfully exposes only documented request/response/plan coaching text, so 7 of 20 structures remain unsupported |
| P1 | In progress | Sealed v17 calibration evidence, a durable execution-only runtime through objective evidence and BM25, repository-sealed non-comparable calibration reports, repository-sealed non-activating gate decisions, truthful local metric coverage, and reviewed local automation admission controls | Frozen private holdout, calibration, stability, privacy, latency, and abstention gates | No representative human-calibrated holdout, eligibility-capable decision or activation slot, calibrated model-stage runtime, or product-enabled estimator |
| P2 | In progress | Prospective capture and comparison contracts, untrusted comparison-stratum drafts, untrusted and repository-backed supplied-set raw-aggregation drafts, normalized synthetic-only temporal persistence, repository-issued synthetic comparison-stratum preparation and graph sealing, and bounded repository-sealed synthetic aggregation-validation receipts | Prospective comparable recommendation outcomes with missingness and adverse effects visible | Codex lacks authoritative per-item source timestamps and stable provider snapshot/cursor boundaries, so no product source boundary exists; there are no product snapshots, recommendations, or empirical recommendation-outcome/adverse-effect results, and no legacy backfill is permitted |
| P3 | Deferred | Optional cloud identity, pairing, entitlements, payments, and usage ledger | Tenant isolation, revocation, deletion, balanced ledger, webhook replay, spend caps, and offline-local behavior | Owner approval and completed P2 required |
| P4 | Deferred | Teams, governance, aggregate-only sharing, RBAC, and privacy-preserving boards | RBAC, isolation, consent withdrawal, cohort-inference defense, deletion propagation, and accessibility | Requires P3 control plane and a separately reviewed sharing policy |

## Baseline evidence

Checkpoint ending at `2a3969a` contains three coherent commits:

1. local analysis and model-evidence backend;
2. real local quality workspace frontend;
3. metric-validity and privacy documentation.

The checkpoint passed 659 Python tests with 4 skips, 256 frontend tests, the
production frontend build, 4 Playwright tests, and the repository privacy
scanner. The build reports a non-blocking bundle-size warning; it is tracked as
performance work, not hidden as a failure.

## P0 checkpoint evidence

Checkpoint ending at `bd9ffe7` adds four coherent P0 slices:

1. explicit `synthetic_demo` and `local_real` runtime composition with verified
   loopback health and fail-closed transport identity;
2. truthful 3-8-axis radar eligibility with exact-value bars below three axes;
3. versioned, content-free provider/session metric readiness for all 20 Coaching
   v1 metrics, including exact reason, required evidence, and next action;
4. a ten-minute, in-memory, one-shot redaction preview and approval backend that
   binds the exact session window, metric set, destination, model plan, redactor,
   retention class, size, and cost estimate without a second provider read.

The current Codex capability projection makes 13 of 20 metric structures
attemptable and marks 7 unsupported before any session content is read. This is
a documented evidence ceiling, not a failed model run, and unsupported values
are never synthesized or plotted as zero.

The checkpoint passed 682 Python tests with 4 platform skips, 283 frontend
tests, the production frontend build, the repository privacy scanner, and diff
validation. The remaining non-blocking frontend bundle-size warning is still
tracked. No remote model received session content, and no estimator was
activated.

The continuation checkpoint ending at `9149af8` adds four more coherent P0
slices:

1. the exact redacted-window preview and one-shot approval UI, including
   expiry, stale-session, and consumed-token handling;
2. versioned ephemeral `ACTION`, `DECISION`, `FEEDBACK`, and `VERIFICATION`
   evidence contracts, with objective verification receipts required;
3. a durable SQLite analysis queue and renewable local-only automation grants
   with leases, restart recovery, cancellation, retry bounds, supersession,
   progress, revocation, and private public DTOs that omit worker lease tokens;
4. a truthful Job Centre plus a real uvicorn/httpx loopback E2E covering consent,
   indexing, exact compatibility, preview/approval, 20-metric analysis,
   readiness, automation supersession/revocation, crash recovery, and canary
   absence from SQLite, files, and logs.

The combined continuation gate passed 703 Python tests with 4 platform skips,
313 frontend tests, 9 Playwright tests across responsive widths, the production
frontend build, and the privacy scanner. The exact test totals belong to this
checkpoint only; they are not estimator-calibration evidence.

The subsequent P0 checkpoints ending at `9afdedb`, `22752c7`, and `d4e129f`
closed the remaining scope, preview, and revocation conditions:

1. immutable analysis runs now persist their exact selected metric set;
2. `{A}` and `{A,B}` runs combine for compatible observations of `A`, while
   omission of `B` remains distinct from missing, failed, and legacy-unknown;
3. migrated scope is marked exact only when it can be proven, and migration 14
   repairs unprovable schema-13 classifications without changing migration-13
   checksums;
4. preview expiry uses both UTC receipt time and an internal monotonic deadline,
   with atomic one-shot redemption and rollback-clock tests;
5. automation result activation validates the exact job, grant, worker lease,
   provider, project, session, and metric scope in the same SQLite write
   transaction. A revocation that wins that transaction publishes no results;
6. project Automation settings, selected-metric execution, Job Centre, packaged
   route refresh, synthetic browser coverage, and local-real browser coverage
   are implemented.

The final P0 backend gate passed 795 tests with 4 platform-only symlink skips.
The last unchanged frontend gate passed 362 unit tests, the production build,
13 synthetic-browser tests, and 3 local-real browser tests. The privacy scanner,
compile checks, and staged-diff validation passed. These are engineering and
privacy gates, not calibration evidence.

Blinded, content-free P0 review packets were evaluated by GPT-5.6 Sol, Claude
Opus 5, and Claude Fable 5. All three returned `pass_with_conditions` with no
P0 blocker. Their bounded conditions are carried into P1/P2: persist a complete
gate manifest, measure performance and usability budgets, and never activate a
model without representative human calibration. Reviewer agreement is advisory
and is not ground truth.

## P1 foundation evidence

The first P1 foundation defines a content-free, versioned serial-cascade
contract and evaluation-math library. It records the complete estimator
configuration, exact execution and stage lineage, requested and served model
identity, local artifact digests, tokenizer and license identity, preprocessing,
question, prompt/rubric digests, reasoning effort, calibration/router/redactor
versions, fallback state, resource measurements, votes, uncertainty,
adjudication, and distinct unavailable, abstained, failed, and not-applicable
states. Candidate screening is capped at five models per family and promotion at
two; local model stages are explicitly serialized.

The evaluation functions cover correctness, retrieval, calibration, selective
risk, false-confident errors, agreement, EN/PL and task/provider/project/time
slices, repeat/order/format/injection stability, latency/resource/cost/failure
telemetry, and incremental cascade value. Their activation-check projection is
diagnostic only. It cannot write an activation slot, and its caller-supplied
facts are not trusted as release evidence. P1 persistence must derive holdout,
human-truth, privacy, and synthetic-origin facts from frozen immutable records
before any estimator can become eligible. Until that vertical slice and the
representative 100-200-judgment program exist, every estimator remains disabled.

The reviewed runner foundation adds only two bounded paths: exploratory Codex
CLI execution and explicit schema-validated manual native import. Subprocesses
use direct argument arrays, an empty temporary Git workspace, read-only sandbox,
strict ignored-user-configuration overrides, bounded stdin/stdout/stderr/workspace,
process-tree cancellation, sanitized errors, and exact structured output. The
installed CLI surface was checked directly before freezing the adapter. Codex
CLI activation-grade requests fail before disclosure because the documented CLI
does not provide a universal no-tool boundary. Claude consumer-subscription
automation is absent; its only supported path is manual export/import. No BYOK
or provider-network runner is implemented in this checkpoint.

The derived gate manifest accepts no caller assertions about eligibility,
holdout integrity, privacy, or synthetic origin. A pre-evaluation manifest
freezes only static case membership and project/time/slice assignments; the
completed cohort separately fingerprints predictions, confidence, run state,
latency, and reference judgments. The gate exact-matches those two projections
and requires split freeze and preregistration before every holdout evaluation.
It then reconstructs eligibility from holdout-access receipts, independent
truth/adjudication receipts, privacy scans, stability runs, performance, and
operational measurements. Missing evidence stays insufficient; synthetic,
consensus/self-reported truth, split leakage, fallback, privacy findings, or
unverified external execution boundaries reject. Codex CLI, manual import,
OpenAI API, and Anthropic API therefore remain activation-blocked until a
separately reviewed execution boundary and immutable provenance exist.

The local retrieval screen also adds `intfloat/multilingual-e5-base` as a
revision-pinned MIT/safetensors challenger with `trust_remote_code` disabled.
On the fixed 12-case fictional EN/PL screen it reached top-1 `0.833333`, MRR
`0.902778`, and Recall@3 `1.0`, with `453.488 ms` measured inference latency
and `1,078.121 MiB` peak CUDA allocation on this machine. This is a useful
screening result, not a promotion: the candidate remains exploratory and
product-disabled until the frozen representative private holdout and all
activation gates pass.

The official BGE-M3 repository was re-screened after a newer immutable revision
added a standard, safetensors-only XLM-RoBERTa path. The historical pickle-only
pin remains recorded as blocked. At the safe superseding pin, all required
weight, config, and tokenizer artifacts are hash-verified and remote code stays
disabled. Its 12-case full result was top-1 `0.666667`, MRR `0.819444`, and
Recall@3 `1.0`, using `2,179.602 MiB` peak CUDA memory. It tied E5-small, trailed
E5-base and Qwen, and used more accelerator memory, so it remains an unpromoted,
product-disabled challenger.

The first P1 persistence checkpoint adds a normalized, content-free schema for
synthetic estimator executions. Plans, immutable synthetic cases, evidence
packet receipts, serialized stage receipts, model runs, votes, probabilities,
opaque evidence references, and metric estimates are stored in relational
tables with immutable-child and parent-cascade-only deletion guards. No prompt,
excerpt, evidence body, model response, rationale, commentary, generic payload,
JSON, or BLOB field is available in this schema.

Execution integrity is checked independently by application contracts and
SQLite constraints. The stored response schema must match its exact plan stage;
always-run stages cannot be skipped; run and estimate timestamps must be inside
their serialized execution interval; a final model-cascade state requires a
selected vote supporting that state; known values require cited evidence; and
failed, refused, timed-out, out-of-memory, and cancelled attempts remain
distinct. Repeated stability executions are preserved, exact retries are
idempotent, and early cascade stops retain their reached-stage prefix.

Schema changes, checksum recording, and `user_version` advancement now commit
as one SQLite transaction without rewriting historical migration checksums.
Privacy deletion uses SQLite secure deletion and does not report completion
until the case cascade is committed and the WAL is cleanly truncated; a busy
reader produces a typed pending failure and a later retry proves durable purge.
The schema still accepts only synthetic executions and exposes no activation
write. Calibration cases, frozen private holdouts, adjudications, derived gate
decisions, and activation slots remain a later P1 checkpoint, so all estimators
remain product-disabled.

The first specialist foundation pre-screen is frozen before any private
evaluation. Its runnable set is exactly a deterministic objective-evidence
abstainer plus multilingual MiniLMv2 L6 and L12 NLI. The 24 fictional EN/PL
cases are a bounded plumbing and operability screen, not the planned
preregistered 96+ case promotion screen. Authored compatibility labels act as
an oracle gate; no scope router is evaluated and router metrics stay unknown.
The previously rejected multilingual mDeBERTa is historical only. BGE-M3
zero-shot and bounded Qwen configurations remain future, unfrozen candidates.
Retrieval models and similarity scores are not metric estimators and can never
be promoted as quality scores. Promotion remains limited to at most two
non-dominated configurations after the later preregistered screen; it is not
product activation.

The deterministic scope-router foundation is now implemented as a separate,
label-blind metadata decision. It routes only content-free project, session,
revision, requirement-version, applicability, supersession, and evidence-kind
identities into five closed states: compatible, different scope, superseded,
insufficient evidence, or not applicable. Unknown evidence is never converted
to zero. The frozen synthetic corpus contains 30 distinct scenarios repeated
across four reporting strata; the report therefore records 30 effective cases,
not 120 independent cases, and explicitly fails the planned 96-case promotion
threshold. The router is contract evidence only and remains product-disabled.

The provisional activation-gate v2 contracts now bind the complete stored
estimator plan, all expected attempts, requested and observed identities,
authoritative candidate projections, blind human labels, and state-aware
stability trials. The in-memory decision type cannot represent an eligible
outcome: immutable persistence is an unconditional insufficient-evidence gate.
This prevents synthetic or caller-constructed receipts from activating an
estimator while the durable calibration evidence ledger is still absent.

Schema v16 adds the first frozen private-calibration commitment without storing
private observations or results. A preregistered campaign binds one previously
stored non-synthetic plan, one exact provider/schema identity, exactly one
versioned metric question per metric, a complete case-assignment manifest, a
project/time split, gate policy, full model constellation, and both legacy and
v2 preregistration receipts. Every planned question must be represented before
the campaign can seal. Application and raw-SQL boundaries enforce the same
lineage, canonical-time, control-character, finite-number, and safe-identifier
rules. Activation remains fixed false.

Campaign deletion securely removes all campaign-owned identifiers from the
main database and SQLite WAL/SHM before reporting success. A domain-separated
revocation digest prevents the same erased campaign identity from being
recreated during or after checkpoint retry without retaining the original
identifier. Global plans and gate policies remain immutable. That next gate,
the normalized v17 evidence journal, is now implemented; repository-derived
reports, sealed gate decisions, and activation remain later work.

Checkpoint `2068b5a` implements that v17 journal as normalized, content-free
SQLite evidence. It stores the exact expected-attempt manifest, launch and
terminal receipts, served identities, independently verified structured
estimate receipts, holdout-access events and gaps, objective truth, blind human
judgments and adjudication, privacy findings and scans, stability trials, and
bounded resource, token, queue, and cost provenance. Partial append/restart,
exact replay, concurrent conflict handling, final sealing, hydration, and
privacy deletion are covered without adding a generic payload, transcript,
prompt, response, path, URI, or commentary field.

The v17 trust boundary is repository-owned and fail-closed: structured
estimates require an independent decoder, the sealed root is written last,
hydration recomputes aggregate counts and fingerprints and revalidates the
static v16 campaign lineage, and connection-bound authorization plus SQLite
guards reject raw inserts, deletes, authorization hijacks, and post-seal
appends. Secure deletion must also purge the WAL before success is reported.
The schema contains no calibration-report, gate-decision, or activation table.
Its checkpoint passed 1,143 backend tests with 4 platform skips, compile checks,
the privacy scanner, and adversarial review; those gates prove implementation
integrity, not calibration quality.

Checkpoint `c261ed2` adds fixed calibration-report contracts and deterministic
math over caller-supplied hydrated v17 domain objects. The comparison identity
binds metric semantics, the stored plan, gate policy, assignments and split,
preregistration, submission, served runtime identities, resource provenance,
source bundle, and report-definition versions. Classification, coverage,
selected-confidence calibration, selective risk, independent-human agreement,
stability, missingness, and bounded operational measurements preserve explicit
known, insufficient, unsupported, not-applicable, and incompatible states.
Insufficient scopes emit no numeric detail rows, selective coverage uses the
full eligible known-truth population, partial resource observation stays
missing, human pairs must name distinct participants, and numeric truth is
preserved without pretending that numeric performance has been evaluated.

This report checkpoint is deliberately not trusted release evidence. Every
report has `repository_owned=false`,
`persistence_state=untrusted_projection`, `comparison_allowed=false`, and
`activation_allowed=false`; private export and team sharing are also disabled.
Brier score, log loss, calibration slope, retrieval quality, cold/warm latency,
throughput, disk use, cascade stop rate, cascade incremental value, and numeric
stability/tolerance remain unsupported when their required receipts are absent.
A later repository migration must rederive the complete report from sealed
rows using a repository clock and reproduce its fingerprint before comparison
or gate evaluation. No report persistence, gate decision, or activation was
added by `c261ed2`. Its focused 20-test contract suite, compile checks, privacy
scan, diff validation, and adversarial review passed; none converts the output
into trusted calibration evidence.

Checkpoint `0fabec0` adds the first durable estimator execution runtime without
weakening the synthetic-calibration or product-metric boundaries. A one-shot,
local authorization is consumed atomically with an exact job, session, project,
provider, plan, question, metric, redactor, source-window, and packet binding.
The worker persists append-only state, stage-attempt, terminal-outcome,
checkpoint, objective-observation, and BM25 retrieval receipts. Queue scope,
grant scope, packet provenance, stage fingerprints, attempt order, and terminal
state are independently sealed in application and SQLite boundaries.

This runtime deliberately stops after objective/readiness and BM25 with state
`partial` and reason `local_model_runtime_not_enabled`. It does not enter local
embedding, reranking, specialist, second-opinion, or adjudication stages; it
does not create calibrated votes or estimates; and it never writes the product
`metric_results` projection. Crash and lease recovery record interrupted
attempts or repair already-durable outputs into exact outcomes and checkpoints
without duplicate receipts. Generic queue APIs cannot create or mutate an
orphan estimator execution. Secure deletion retains only the registered safe
plan and does not report physical purge until the WAL is truncated. The final
gate passed 1,223 backend tests with 4 platform skips, privacy and compile
checks, and two adversarial review rounds. These results prove the bounded
runtime implementation, not model validity or activation eligibility.

Checkpoint `0b45b47` persists the complete calibration report as normalized
schema-v19 data. Its sole write command accepts only a sealed v17 submission
identifier; within one `BEGIN IMMEDIATE` transaction the repository hydrates
and revalidates the exact v16 campaign and v17 evidence, captures one repository
timestamp, rederives the unchanged untrusted report, writes every definition,
scope, measurement, detail, resource, missingness, and metric root, then seals
the report root last. Replay preserves the timestamp and fingerprint, while
conflicting or partial writes fail atomically.

The structurally constructible sealed receipt is explicitly not a capability.
Repository reads rehydrate and fully rederive the v16/v17/report graph before
returning it; connection-bound authorization guards reject stale, forged, or
cross-report writes. Missing and unsupported measurements remain `NULL` with
their explicit state and never become zero. Campaign privacy deletion cascades
the report and still requires secure WAL truncation before success. The report
remains `comparison_allowed=false`, `activation_allowed=false`, and private
export/team sharing false. No gate-decision or activation table was added. The
checkpoint passed 1,241 backend tests with 4 platform skips, focused/adjacent
report gates, privacy and compile checks, and independent adversarial review.

Checkpoint `7704ed6` adds repository-sealed gate decisions as normalized
schema-v20 data. Its public write command accepts only a sealed v19 report
identifier, then rehydrates and independently rederives the exact v16 campaign,
v17 submission, and v19 report lineage in one repository transaction before
writing the decision root last. The code-owned decision vocabulary covers every
registered metric, required stratum and language, subgroup dimension, high-risk
rule, and identity, access, privacy, and stability gate. In the frozen
single-metric fixture, adversarial hardening expanded the initial 83-check
projection to 85 checks by making cold- and warm-latency sample sufficiency
explicit; real vocabulary size remains derived from the registered campaign.

The decision outcome has only `rejected` and `insufficient_data`; there is no
eligible state. Missing or unsupported evidence never becomes zero or a failed
measurement, and an all-pass release root is structurally invalid. A clean
synthetic lineage remains insufficient because activation-grade evidence is
absent, while repository-proven violations reject. The sealed decision keeps
`activation_allowed=false`, `activation_slot_written=false`,
`comparison_allowed=false`, private export false, and team sharing false.
Schema v20 contains no activation slot or activation API. The checkpoint passed
1,312 backend tests with 4 platform skips, privacy and compile checks, and
independent adversarial review. This proves decision integrity, not estimator
eligibility or product activation.

Pushed checkpoint `ac84a40` (`Expose truthful local metric coverage`) adds an
authenticated, content-free, counts-only coverage report and matching local UI
for the provider catalog or one project. It reports an exact local SQLite
snapshot while explicitly leaving provider-history completeness unknown. Latest
attempt status is kept separate from the latest completed Coaching snapshot;
contract-compatible, contract-incompatible, and absent results remain distinct,
and per-metric provenance cohorts are not merged. The Codex descriptor still
makes 13 of 20 metric definitions structurally attemptable; this is structural
evidence-channel support, not a claim that 13 metrics were measured in any
session.

Automation coverage in this checkpoint means only that a metric is selected by
at least one bounded active local grant. It proves neither completed execution
nor full-catalog automation coverage. The report grants no product/source or
population-completeness authority, and no comparison, snapshot, recommendation,
or outcome authority. It therefore improves P1 measurement/readiness visibility
and local P2 coverage diagnostics without changing either phase's acceptance
gate or blockers.

Frozen engineering evidence for the exact
`ac84a4080ba6f5f40010576970dbc71daaf94587` tree is 1,817 passing backend tests,
4 expected platform-only symlink skips, and one existing warning; 385 passing
frontend tests; a successful production build; and 13 passing Playwright tests.
The privacy scan, compile checks, and diff validation passed, and independent
backend and frontend reviews returned `PASS`. These are implementation and
privacy results, not calibration, product-history, or recommendation evidence.

Pushed checkpoint `a05c1e3` (`Enforce reviewed automation admission policy`)
turns the previously persisted automation resource receipt into a narrow,
truthful admission boundary. New grants and renewals accept only the reviewed
balanced profile: one per-grant CPU admission lane, a GPU ceiling of one with
zero current session-quality GPU use, battery/unknown power admission pause,
and a declared 1,800-second runtime budget. Historical broader profiles remain
readable and revocable, but they cannot be renewed, scheduled, claimed, or used
to launch estimator work.

The scheduler checks the exact profile before provider, session-candidate, or
job access; current consent is checked before a fresh per-grant power sample.
Battery and unknown power pause only new admission and leave queued attempts and
leases unchanged. They do not interrupt already-running work. SQLite claim
admission runs under `BEGIN IMMEDIATE`, revalidates the live grant, project,
provider, ordered metric scope, local boundary, and exact resource profile, and
allows at most one unexpired active job per grant without starving manual work
or work for another grant. Invalid non-estimator automation rows receive only a
closed set of content-free reconciliation codes. Invalid queued estimator rows
are not claimed and remain queued, unleased, zero-attempt, and unread because
their append-only runtime requires a separate reviewed reconciliation path.

This checkpoint does not enforce the declared 1,800-second budget as a hard
runtime deadline, pause work in progress, allocate a GPU worker, enable a model
stage, validate any metric, or activate an estimator. The API, OpenAPI schema,
and UI expose those limitations directly, and no schema migration was needed.
The remaining hard runtime deadline and estimator-specific cleanup are still
P1 work; the representative human-calibration and activation blockers are
unchanged.

Frozen engineering evidence for the exact
`a05c1e3a8718b19aa1ab8e79a46cbd2e95cddff0` tree is 1,867 passing backend
tests, 4 expected platform-only symlink skips, and one existing warning; 390
passing frontend tests; a successful production build; and 13 passing
Playwright tests. The privacy scanner, compile checks, and diff validation were
green, and two independent read-only reviews returned `PASS`. These results
prove admission, concurrency, failure, and interface integrity, not estimator
calibration, product metric correctness, or outcome evidence.

## P2 foundation evidence

Checkpoints `249f6c0` and `4db7052` define a prospective, content-free temporal
history and capture-lineage vocabulary. The contracts cover exact last-N,
rolling, and custom UTC windows; typed raw aggregation inputs and uncertainty;
independent selection, source, and value states; fully versioned comparison
identities; prospective history-root epochs; CAS-linked project metric
selections; direct selected-window input receipts; conservative session
revisions; typed observation batches; and an exact completion graph. The graph
requires one root, project, session, selection, run, input window, revision,
batch, observation scope, provider identity, and preprocessing/redaction/router
provenance to agree rather than inferring compatibility from timestamps or row
counts. The combined contract gate passed 67 focused tests plus the privacy and
compile checks.

Checkpoint `083ce8f` corrects the prospective capture vocabulary before any
schema depends on it. It distinguishes the keyed selected-redacted-message
window from separate selected-window and post-floor observed-source manifests,
binds selection identity to the exact pack, catalog, and source authority, and
binds session revisions to both predecessor ID and fingerprint. The first
repository implementation may classify only first, provenance-boundary, or
changed/reordered revisions; it cannot claim an append prefix from increasing
counts. Zero-of-zero evidence coverage has an explicit versioned state rather
than being silently dropped or coerced. The public batch-seal draft remains
untrusted, unsealed, repository-verification-required, comparison-disabled,
snapshot-disabled, and activation-disabled. Its 82-test combined temporal gate
and adversarial review passed, including a coordinated chronology/fingerprint
forgery; no temporal storage or authority was added.

Checkpoint `a1626a9` adds a public source boundary only for bounded synthetic
tests. A draft request revalidates and binds the exact prospective history root,
selection revision, project scope, metric keys, pack, catalog, and source
authority. Canonical chronology and local resource bounds are enforced before
a concrete local HMAC creates content-free commitments; the HMAC is a local
integrity mechanism, not source or repository authority. The resulting draft is
fixed untrusted, synthetic-only, unsealed, and repository-issuance-required.

The Codex capability descriptor remains unavailable because the documented
provider boundary supplies neither an authoritative UTC timestamp for every
source item nor stable provider snapshot and cursor boundaries. Capture, list,
read, session, turn, and repository-clock values cannot substitute for those
missing facts. The draft has no `AnalysisInputReceiptV2` mapping and cannot
enter product capture. Repository verification and issuance, a batch seal,
comparison, snapshot materialization, and activation all remain false. The
checkpoint passed 62 focused tests, a 173-test adjacent temporal/privacy/config
gate, and independent adversarial review. These are synthetic contract and
privacy results, not proof that product history capture is available.

Checkpoint `71246b2` defines the comparison-stratum request and draft boundary
without granting comparison authority. Its privacy projection contains only
the target session and omits unrelated session membership. Task ambiguity
remains explicit, while language, complexity, agent permission, and agent model
dimensions remain `unknown_not_recorded`; unknown categories are visible and
are neither pooled, dropped, imputed, nor treated as equal.
`PreparedComparisonStratumDraftV1` and `SealedComparisonStratumDraftV1` remain
structurally constructible drafts, not capabilities: every repository, source,
run, and batch authority flag remains false, as do product capture/history,
pair matching, comparison, aggregate and snapshot materialization,
recommendation and outcome evaluation, causal claims, activation, private
export, and team sharing. This checkpoint adds contracts and synthetic tests,
not a comparison repository or product capability.

Checkpoint `cdc8f56` adds schema-v21 normalized, content-free, synthetic-only
temporal persistence with zero legacy backfill. It creates one prospective root
epoch per project, append-only CAS-linked metric selections, and an immutable
prepared automation-grant snapshot. Exact Coaching fraction results and the
typed temporal graph are committed atomically with the repository-owned graph
seal written last; v21 permits at most one temporal revision per session within
that project epoch.
Hydration rederives the stored run, session, results, identities, counts,
selection chain, snapshot, observations, and seal before returning them.
Privacy deletion uses SQLite secure deletion, parent-cascade removal, and WAL
truncation, with a pending result when a pinned reader prevents physical purge.

The live job lease and current automation-grant row are seal-time-only
authorization. They are checked under a transient, full-lineage local
authorization during the atomic append but are not persisted as public seal
lineage; later reads rely on the immutable prepared grant snapshot and durable
run/session/results graph. The repository seal therefore proves only exact
repository graph ownership and reconstruction. Source authority, product
history eligibility, comparison, snapshot materialization, activation, private
export, and team sharing remain false, and no product capture source,
recommendation, or product snapshot is exposed.

The schema-v21 checkpoint passed 37 focused temporal-persistence tests, 292
primary adjacent history/capture/session/grant/job tests, 26 SQL-adjacent tests,
and the full 1,584-test backend suite with 4 platform skips. The privacy scanner
and diff validation passed, and two independent read-only reviews returned
`PASS`. These are implementation-integrity results, not empirical comparison,
recommendation-outcome, adverse-effect, or calibration evidence.

Pushed checkpoint `339878d` (`Add synthetic temporal aggregation drafts`) adds
a pure, deterministic, supplied-set-only synthetic raw descriptive aggregation
draft. It implements all four typed raw semantics without averaging incompatible
values: fraction ratio-of-sums, count and exposure sums with preserved units,
pooled distribution samples with code-owned Type-7 quartiles, and summed
sampled-proportion successes and trials with a recomputed code-owned two-sided
95% Wilson interval. Code-owned policy identity also fixes half-open temporal
windows, prospective-floor clipping, last-N revision ordering, finite numeric
handling, compatibility segmentation, and non-pooling task-mix behavior.

Selection, source, value, evidence-coverage eligibility, and evidence-coverage
state remain separate and fully counted. Known zero-of-zero evidence coverage
stays known with an absent ratio; unknown, not-applicable, missing, failed,
abstained, incompatible, not-selected, and selection-unknown states are never
coerced to zero. Reviewed task buckets remain visible and unpooled. Full
comparison-identity changes create contiguous run-length segments, so
`A -> B -> A` remains three runs, while an identity-unavailable gap visibly
breaks a run without inventing a compatibility change.

The draft describes only the bounded set supplied by its caller; collection and
population completeness remain unknown. It is not repository-owned or sealed,
has no source or product-history authority, and grants no comparison, pair
matching, aggregate or snapshot materialization, recommendation, outcome
evaluation, causal claim, activation, private export, or team-sharing authority.
The checkpoint passed 33 focused/adversarial aggregation tests, 415 temporal
tests, and the full backend suite with 1,617 passed, 4 platform skips, and one
existing Starlette deprecation warning. Independent adversarial review returned
`PASS`; privacy, compile, and diff checks were green.

Checkpoint `2330afd` adds schema-v22 normalized, content-free, zero-backfill
persistence for repository-issued synthetic comparison-stratum preparations and
graph seals. The committed V1 drafts and v21 temporal rows remain unchanged.
Because the temporal grant snapshot and comparison grant authority deliberately
use separate fingerprint domains, an explicit repository-verified bridge
rederives both identities from the same full active grant instead of equating or
rewriting them. The selected-session analysis-run contract remains pinned to
schema 21 while the additive database schema advances to 22, and the analysis
command and comparison repository share one keyed, installation-local expected
run-ID issuance boundary.

Preparation requires the exact live synthetic session-quality job lease and
active local grant, prepared temporal scope, project, session, metric selection,
pack, catalog, completed-session authority, and code-owned comparison policies.
The repository derives the target-only reviewed-task manifest from the latest
revision at or before its captured cutoff. Its MAX+1 query rejects an overflow
rather than silently truncating the reviewed 100-task bound. Normalized children
are written before the prepared root; exact retries and concurrent attempts
rehydrate the same repository timestamp, identities, and fingerprint.

Run completion, result persistence, temporal batch sealing, live job/grant
revalidation, the terminal run transition, and the comparison graph seal occur
in one SQLite transaction, with the comparison root written last. The public
seal method is replay-only and cannot attach a comparison graph after completion.
Hydration independently rederives the prepared, run, temporal-batch, and
revalidation graph. Transient local HMAC authorization and raw-SQL guards reject
late attachment, altered-lineage reuse, replacement, mutation, and unauthorized
child deletion even with recursive triggers disabled; injected faults before or
after the terminal update roll the entire transaction back.

Run privacy deletion removes prepared-only or sealed comparison graphs through
SQLite secure deletion and WAL truncation. Task and candidate privacy deletion
expands the complete review-decision component, removes every affected comparison
graph under transient authorization, and preserves an already completed run and
its temporal history; an absent retry still checkpoints the WAL. Prepared and
sealed receipts remain content-free and omit worker lease secrets.

Repository ownership and graph verification do not make the comparison stratum
complete. Source authority, product capture and history eligibility, pair
matching, comparison, aggregate and snapshot materialization, recommendation and
outcome evaluation, causal claims, activation, legacy inference, backfill,
remote processing, private export, and team sharing all remain false. No HTTP,
CLI, UI, product snapshot, recommendation, or activation surface was added.

The checkpoint passed 109 focused v22 tests: 95 direct-contract tests and 14
SQLite persistence tests. An independent frozen integration gate passed 178
tests with one existing deprecation warning, and the full backend gate passed
1,732 tests with 4 platform-only symlink skips and one existing Starlette
deprecation warning. The privacy scanner, compileall, and diff validation passed;
three independent contract, SQL, and integration reviews returned `PASS`. These
results prove synthetic repository-graph integrity, not source truth, comparison
validity, recommendation effectiveness, adverse-effect safety, or calibration.

Pushed checkpoint `bdff8a5` (`Add repository-backed synthetic aggregation
drafts`) adds an application-only V2 raw aggregation draft over schema-v22
repository-sealed synthetic comparison-stratum receipts. The repository backing
belongs to the revalidated input graph, not to the aggregation output. The draft
still describes only the bounded set supplied by its caller: it is unsealed,
nonrepository, noncomplete, and does not claim repository-return provenance or
population completeness. Its exact content-free authority manifest commits the
anchor preparation plus every supplied prepared and sealed stratum, analysis run
and authority fingerprint, sealed batch, temporal revision, session coordinate,
effective and sealed times, and window disposition. Authority-only changes move
the draft identity and fingerprint even when the descriptive numbers do not.

The V2 path reuses the exact aggregation semantics rather than introducing a
second estimator: fraction ratio-of-sums, count and exposure sums and rates,
pooled Type-7 distribution quartiles, and pooled sampled-proportion successes,
trials, and Wilson intervals. Selection, source, value, missingness, evidence
coverage, reviewed task buckets, compatibility runs, `A -> B -> A` transitions,
and identity-unavailable gaps remain separately visible and conservatively
counted. Synthetic contract tests cover one- and two-receipt paths; a separate
SQLite integration uses one actual v22 repository-prepared and repository-sealed
receipt. Neither establishes that the caller supplied a complete repository
collection.

Every product capture, source, comparison, pair-matching, aggregate and snapshot
materialization, recommendation and outcome-evaluation, causal, activation,
private-export, and team-sharing authority remains false. The checkpoint adds no
schema migration, repository write, HTTP or CLI API, or UI surface. Its frozen
evidence is 30 focused V2 tests, an exact 172-test adjacent gate, 554 passing
temporal tests, and the full backend gate with 1,762 passed, 4 platform-only
symlink skips, and one existing Starlette deprecation warning. The privacy scan,
compileall, and diff validation passed, and an independent review of the exact
`bdff8a5b35bdb1a93893c93c38b8b4a57b46442b` tree returned `PASS`. These are
synthetic implementation-integrity results, not product/source truth,
comparison validity, snapshot authority, recommendation effectiveness, or
adverse-effect evidence.

Pushed schema-v23 checkpoint `57d623a` (`Persist bounded synthetic aggregation
validations`) adds normalized, content-free, zero-backfill SQLite persistence
for bounded `RepositorySealedSyntheticAggregationValidationV1` receipts. Under
`BEGIN IMMEDIATE`, the repository rejects conflicting live idempotency-key reuse
before clock capture or enumeration, captures one repository UTC `as_of`, and
enumerates at most 10,000 schema-v22 repository-sealed synthetic comparison
strata in the anchor's exact history-root, installation, project, and provider
scope. Normalized members and ordered graph commitments are written before a
root-last transient-HMAC-authorized seal, and hydration rederives the persisted
issuance graph.

The `bounded_sealed_stratum_collection_complete=true` claim covers only that
exact repository transaction snapshot as of its server clock. It proves neither
population nor source or product-history completeness, and later writes do not
alter an existing receipt. The embedded V2 raw aggregation draft remains
nonrepository and unsealed; only the outer validation receipt is
repository-owned and sealed.

Run, task, and candidate privacy deletion discovers every validation containing
an affected v22 member, authorizes each whole-root cascade under the exact live
upstream operation and actual member lineage, and removes v23 before v22.
Restrictive member-to-v22 foreign keys and guarded root-to-child cascades prevent
partial graphs; multi-root causes are deduplicated and processed serially, and
faults roll back the joint transaction. SQLite secure deletion and WAL
truncation remain required, including on an absent retry. Deletion erases the
root, members, graph commitments, and idempotency binding without retaining a
tombstone: replay is guaranteed only while the receipt exists, and later reuse
of the same key is a fresh issuance.

This checkpoint adds only bounded synthetic collection, enumeration, graph
verification, and receipt-persistence authority. Comparison-stratum and
population completeness, source authority, product capture and history,
pair matching, comparison, aggregate and snapshot materialization,
recommendation and outcome evaluation, causal claims, activation, legacy
inference, backfill, remote processing, private export, and team sharing all
remain false. No HTTP, CLI, UI, product snapshot, recommendation, or activation
surface was added.

Frozen evidence for the exact `57d623ac40ef7eb545351872fd911a4c8553bedb`
tree is 14 focused SQLite tests, a 148-test reviewer-adjacent gate, 586 temporal
tests, a 175-test schema/version-adjacent gate, and the full backend suite with
1,794 passed, 4 expected platform-only symlink skips, and one existing Starlette
deprecation warning. The privacy scanner, compileall, and diff validation were
green, and two independent decisive read-only reviews returned `PASS`. These
results prove bounded synthetic repository-transaction and deletion integrity,
not product/source truth, comparison validity, snapshot authority,
recommendation effectiveness, or adverse-effect evidence.

P2 remains in progress: the product-source boundary is still blocked by missing
authoritative per-item timestamps and stable provider snapshot/cursor
boundaries. The repository graph is not a complete or product comparison
stratum, and there are still no product comparisons, aggregates, snapshots,
recommendations, or empirical recommendation-outcome/adverse-effect results.
P3 and P4 remain deferred in phase order.

## Version inventory

| Component | Pinned identity | Product status |
|---|---|---|
| Deterministic coaching pack | `core.redacted-text.prompt-logic` v1; engine `text-rules-en-pl-1`; rubric `prompt-logic-rubric-1` | Local deterministic observations only; missing objective evidence abstains |
| Redactor | `deterministic-local-redactor-v1` | Local risk reduction; not sufficient by itself for remote disclosure |
| E5-base retrieval challenger | `intfloat/multilingual-e5-base` at `d128750597153bb5987e10b1c3493a34e5a4502a` | Synthetic exploratory challenger; not promoted or product-enabled |
| BGE-M3 dense challenger | `BAAI/bge-m3` at `142964af7e05de16511657561de8e8750fc153a0` | Safe superseding pin evaluated; trails the current retrieval Pareto set and remains disabled |
| Qwen embedding challenger | `Qwen/Qwen3-Embedding-0.6B` at `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | Synthetic exploratory challenger; not product-enabled |
| BGE reranker challenger | `BAAI/bge-reranker-v2-m3` at `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` | Synthetic exploratory challenger; not product-enabled |
| Claude Opus review target | Exact requested and served model must be recorded by a reviewed BYOK/API runner | Not implemented; no private-session review is authorized |
| Claude Fable review target | Exact requested and served model plus retention acknowledgement must be recorded | Not implemented; synthetic architecture review only until the remote approval boundary exists |

Full local model revisions, weight digests, tokenizer pins, licenses, bounds,
and gate results live in [the model manifest](model-manifests/wp-11-local-candidates.md).

## Decision log

- Unknown, unsupported, abstained, incompatible, not-applicable, and failed are
  distinct states. None may be converted to zero.
- Objective tests, artifacts, and explicit acceptance outrank model-written
  completion claims.
- Review-load metrics stay on an exact-value board unless a bounded,
  documented normalization exists.
- Remote work is per-run only: a local automation grant can enqueue it, but it
  cannot approve disclosure.
- P1, billing, and teams remain disabled until their preceding phase gates pass.
