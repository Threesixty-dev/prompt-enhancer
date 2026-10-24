# Prompt workflow robustness qualification

## Purpose and status

This suite tests the three fixed prompt workflows as a connected system:
generation, deterministic diagnostics, embedding, NLI, reranking, rubric review,
stored results, and analysis. It is a finite regression and boundary matrix;
passing it does not prove that every possible input or infrastructure failure is
covered. It is not a study of developer ability or a universal quality score.

Revision 2 is published with `autoRun: false` for core 0.3.3. Its first ordinary
smoke run stopped with one failed attempt and two skipped attempts. The remaining
smoke selections and main matrix have not started. The failure and proposed
adapter correction are recorded below. Independent data-scientist onboarding
remains a separate handoff gate.

Revision 3 is published with `autoRun: false` for released core 0.3.4. Its 15
smoke attempts pass the technical gate. Bounded recovery after the first run's
deadline reaches 139 of 240 successful unique pairs. One Rewrite pair is now
interrupted during embedding evaluation; 100 pairs have not started. Remote-stop
evidence and all partial results are preserved. The complete matrix and
independent onboarding are not qualified.

Revision 4 is published with `autoRun: false` for released core 0.3.5. Its 15
smoke attempts succeed technically. The main cohort stops after five successes,
one completed invalid review and two skipped attempts; 232 pairs remain
unsubmitted. The worker/relay rollout and partial UI/API/export checks pass.
This is a separate artifact cohort: revision-3 successes do not complete its
coverage. Full qualification and independent onboarding remain open.

The [flow and diagnostics release](experiment-flow.md) adds diagrams for every
experiment, safe rejection details and independent-case continuation guidance.
Its next qualification uses one case/variant pair per run, preserving every
failure and stopping on uncertainty or infrastructure failure. Core 0.3.6 is
released and registered; the API, worker and relay use reviewed source `3b424e8`.
Three revision-5 definitions are prepared with `autoRun: false`; their source
and promotion reviews, publication and fresh live qualification remain open.

## Revision-5 task card - 2026-10-24

- Task / atlas: MA18 and W02/W03/W05/W07; qualify the released review diagnostics
  and deployed experiment diagrams through the same connected pipeline.
- Approved baseline: develop `5883504`, promoted by #91 to main `3b424e8`.
  Core publication `40127596404` passes build, offline identity/tokenizer checks,
  probe cleanup and catalog registration. Deployment `40127562554` passes API
  image health and two protected serving-revision checks; its first HTTP 404
  verification is retried independently after confirming local readiness.
- Worker/relay prerequisite: both use the reviewed API image, share the correct
  namespace and pass authenticated consumer readiness. API and consumer
  containers are preserved. Preflight finds no queued/running runs, recovery
  holds or active cores. Saved image pins and the nonsecret Compose override
  preserve the desired deployment; private configuration stays outside Git.
- Allowed changes: three new revision-5 definitions and evidence/operation docs.
  Only revision, generation, core version and artifact pins change from r4.
  Cases, variants, workflow identities, model bindings, harness, policies,
  limits, assertions and the historical cohorts remain unchanged.
- Matrix: 20 cases x 4 variants x 3 workflows = 240 main attempts, after 15
  separate smoke attempts. Use one case and one variant in every run, including
  smoke. Main coverage can continue only when the recorded continuation decision
  permits an independent pair; completed invalid reviews remain failures.
  A failed smoke gate, uncertainty, incomplete evidence or infrastructure failure
  stops admission. Never replay automatically.
- Evidence: all 29 repository definitions and 240 new semantic requests validate;
  exact comparison permits only identity/core changes. All 58 existing synthetic
  publication, binding and connected-pipeline tests pass. The local build-input
  fingerprint matches the registered receipt; server history ends at generation 4.
- Remaining gates: specific definition review and promotion, publication, fresh
  model readiness, all smoke/main outcomes with UI/API/export agreement and
  independent onboarding. Preparation submits no model work.

Every revision-5 definition pins core `0.3.6`, variant `default`:

- Image digest: `sha256:d72e2736b9e7a7435950116f0e314821c279f2e9ea8add810c3cb49a83c628b4`.
- Build inputs: `3b19f547f2b87623c3cded5b1e692ec826bc11c257040b8f1ce7e6d6eac35a5f`.
- Validated source: `3b424e81f23d86bd42ecbe628af791916bb4050a`; action `built`.

## Historical release prerequisites

Core 0.3.3 default was built from reviewed main
`52dff00e5057fa2c64810e5ee36a24afdad56c03`. Publish Core completed its offline
runtime identity, pinned-tokenizer, cleanup and catalog-registration gates.
The API deployment at `e2ddb7eab1bfd2eda357f95e89701b6440ae372e` passed controller
health and two authenticated serving-revision checks after the protected
readiness path was admitted by the existing gateway policy. These observations
do not qualify the worker, relay or external model bindings.

The immutable revision-1 files and their core 0.3.2 pins remain available. Their
historical results do not qualify the changed core. Revision 2 changes only the
revision/generation identity, core version, image digest and build fingerprint;
the cases, workflow pins, harness, policies, limits and assertions stay identical.

Every revision-2 definition pins:

- Core version: `0.3.3`, variant `default`.
- Image digest: `sha256:da56d2680f948f385fd12a215c32e0fcd2c27f771d9324778b639ece2b96852e`.
- Build inputs: `1738e11e26756c24167a83f6c918d81eaa73aae5de64da2ffffdcbc3de17d8b1`.

## Revision-2 task card - 2026-10-24

- Task / atlas scope: qualify the released NLI input guard through the fixed
  prompt workflows; MA18 and W02/W03/W05/W07.
- Approved source baseline: develop `0b0b36d`; core release from main `52dff00`
  and verified API deployment `e2ddb7e` are completed prerequisites.
- Observable outcome: a new immutable cohort tests the complete connected
  pipeline and makes oversized NLI unknowns explicit in results, UI and exports.
- Allowed changes: three new revision-2 definitions, one boundary-smoke selection
  and qualification/evidence documentation. Runtime code, original revisions,
  cases, workflow/harness pins, policies, limits and assertions stay unchanged.
- Positive, negative, recovery and privacy checks: canonical identity/schema
  validation, all effective core requests, exact r1/r2 field comparison, existing
  synthetic publication/pipeline/privacy tests and repository privacy scanning.
- Completion boundary: local definition validation and review readiness here;
  live acceptance additionally requires confirmed recovery, published definitions,
  all smoke/main attempts, ordered receipts and UI/API/export agreement.
- Resource bound: 15 smoke attempts followed by 240 main attempts; existing
  180-second per-attempt limits apply. Stop on technical failure or uncertainty;
  no automatic uncertain retries. No live attempts are submitted during preparation.
- Owner decisions: named source and promotion merges remain review gates.
  Definition publication and the bounded run are authorized; actual remote-stop
  evidence is still required before resolving an earlier operation's hold.
- Result: the local evidence below supports review; source publication and live
  qualification remain pending. No model or temporary service is started here.

## Revision-2 smoke result and ACP schema candidate - 2026-10-24

The reviewed definitions reached main through PRs #75 and #76, and Publish
Experiments completed successfully. Read-only model-host completion evidence
allowed explicit reconciliation of the earlier interrupted cohort. Its original
status remains interrupted; reconciliation does not turn it into a success.
The admission check then found no queued/running work or recovery holds.

The first `example-complete` / `concise` attempt failed at generation with
`workflow_review_reply_invalid`. All five before evaluators returned; the review
followed successful diagnose/context steps. Its completed synthetic reply was
valid JSON but used the finding-only `ambiguity` label in a
`reformulated_elements[].element` field, whose enum excludes that label. No
candidate or after evaluation was accepted. Cleanup completed with no hold.
The run skipped its other two attempts and the controller stopped before any
additional smoke or main run. This is a technical failure, not an assertion loss.

The single unknown before reading was expected: `problem_evidence_quality`
reported `diagnostic_task_not_detected` for an implementation request. The UI
shows that reason and marks absent after/delta cells as not recorded. A validated
private export retained one run, three attempts, one error, ten metric readings,
six assertion rows and two timing records; manifest hashes and every JSON/CSV
cell agree. Private operation references and response text stay outside Git.

The ACP adapter delivered the review policy and its shorthand enum list, but
dropped `ModelCall.response_schema`. The formal schema was absent from the native
system event. These are distinct observations: the invalid enum caused rejection;
the omitted schema is a transport defect, and its correction cannot guarantee
future model compliance.

### Correction task card

- Task / atlas scope: preserve structured response contracts through ACP;
  MA18 and W02/W03/W07, based on reviewed develop `d07cd02`.
- Allowed changes: ACP message construction, adapter/core version provenance,
  synthetic regressions and evidence documentation. Existing experiment pins,
  validation rules, model settings and historical results stay intact.
- Implementation: proposed core `0.3.4`, adapter `openhands-acp-1.49.1.v5`, appends
  the complete JSON Schema to ACP system instructions. The prepared user message
  and policy are preserved. Schema-free calls retain their original instructions.
- Enforcement boundary: this is model guidance, not provider-enforced constrained
  decoding. Strict workflow parsing remains authoritative. Invalid replies are
  not repaired, relabelled, retried or accepted as successful.
- Evidence: the schema-delivery regression fails on the previous implementation;
  152 affected adapter, workflow, parser, engine, packaging and publication tests
  pass with the correction. Synthetic valid/invalid enum cases cover the entire
  process-consumer/ACP/workflow path and retain partial failure evidence.
- Completion boundary: source review readiness only. Named merges, core version
  approval/publication, a new immutable experiment revision and fresh live smoke
  qualification remain required before the main matrix proceeds. No additional
  inference runs or deployment changes were made during correction preparation.
- Process bound: one focused reproduction and one affected regression selection;
  existing smoke stop rules and per-attempt limits remain in effect.

## Revision-3 task card - 2026-10-24

PRs #77 and #78 completed the reviewed ACP schema correction. Publish Core run
`40096081387` built core `0.3.4` default from main
`8fd3da6da118f1b020e261d3c9585c8eaecd5bf3`. The workflow passed source validation,
offline core/protocol and tokenizer verification, probe cleanup and Bench
registration. The local build fingerprint agrees with the release summary.
These gates establish the artifact and registration, not model compliance or
worker-host pull availability.

Each revision-3 definition pins:

- Core version: `0.3.4`, variant `default`.
- Image digest: `sha256:30fcf75a894385ffffbc3f75108ce085c655e3569f6f1a165a7548a7c3fd9630`.
- Build inputs: `043d68b1ea9d12b0df7cdf383f3f9d966cdf9b7ad60f26993279ba6f523b2de6`.

Task scope and gates:

- Task / atlas scope: qualify the released ACP schema correction through the
  unchanged prompt workflow matrix; MA18 and W02/W03/W05/W07.
- Approved baseline: develop `e4d6e82`; released core source is the reviewed
  main promotion above, whose complete tree matches the approved correction.
- Allowed changes: three revision-3 definitions and their evidence/navigation
  documentation. Existing revisions and failure evidence are retained.
- Comparison: exact r2/r3 equality except revision, generation, enhancer version,
  image and build fingerprint. Cases, policies, workflow pins, bindings, harness,
  assertions, limits and smoke selections remain identical.
- Identity evidence: the read-only Bench API contains both earlier revisions for
  all three stable IDs and no revision/generation 3. Check again at publication.
- Completion boundary: canonical/semantic validation and source review readiness.
  Named definition merges, publication, runtime preflight, live smoke/main runs
  and UI/API/export agreement remain separate gates.
- Resource bound: nine ordinary smoke attempts, six NLI boundary smoke attempts,
  then 204 standard and 36 isolated boundary attempts. Preserve the existing
  180-second limit, stop on technical failure or uncertainty, and never silently
  retry or count the earlier failed cohort as qualification of this build.
- Owner decisions: core 0.3.4 publication is authorized and complete; experiment
  publication/run authorization is retained, subject to specific source and
  promotion reviews. Independent data-scientist onboarding remains open.

## Revision-3 live result - 2026-10-24

PRs #79/#80 publish the three definitions through main `cc8eb26`; Publish
Experiments `40098767343` succeeds. Live metadata agrees with the released image
digest and build fingerprint. All nine ordinary and six NLI boundary smoke
attempts pass ordered-step, input/result-correlation, evaluator-coverage and
cleanup checks. The exact synthetic ACP operation contains the formal schema
and records adapter `openhands-acp-1.49.1.v5`.

All 600 rendered smoke metric cells agree with the API. Both smoke exports pass
manifest hashes and every JSON/CSV cell comparison. The 210 recorded readings
include 170 known and 40 unknown values: 18 diagnostic-task exclusions, seven
unobserved-requirement readings, eight unobserved-constraint readings, six NLI
input-limit exclusions and one invalid rubric response. That rubric reading is
a measurement gap. Assertion outcomes are separate: two passed, one failed and
12 unknown. No score is substituted for an unavailable reading.

The main Prompt Check run completes 56 attempts, then stops on the markup case's
concise variant before generation. Deterministic and embedding evaluation return;
the next NLI worker reports `remote_execution_unconfirmed`. Eleven remaining
attempts in that run are skipped. The controller stops before any clarification,
rewrite or isolated boundary main run. The preserved private export contains 68
attempts, 567 metric rows, one error, 136 assertion rows and 197 timing rows, with
verified hashes and JSON/CSV parity. The cohort remains interrupted.

Two fresh model-host observations show equal nonstreaming NLI request/response
counts, all HTTP 200, on the same previously verified server build. They support
explicit reconciliation; cleanup and reconciliation holds are then clear. The
exact synthetic input also passes the released tokenizer in an offline container
and fits its input limit. The deployed worker uses its default 1,800-second
whole-run deadline and has not restarted. The run lasts 1,801 seconds, while the interrupted attempt lasts
about seven seconds with a 180-second attempt limit and no user cancellation.
The worker cancels the active core request when the whole-run deadline expires.
That cancellation conservatively becomes `remote_execution_unconfirmed`; the
run-level `core_uncertain` code obscures the deadline cause. The 68-attempt batch
was too large for the independent run budget. No failed attempt is replayed,
and the remaining matrix is not started.

Browser-session expiry also exposes an ambiguous stale-result notice. The
[UI candidate](client-navigation.md#stale-results-after-connection-loss---2026-10-24)
adds explicit stale state and reconnection guidance. It is source-tested only;
the qualification's deployment remains frozen. Complete main-matrix evidence,
clear run-deadline reporting and independent onboarding remain open. Continue
with at most four attempts per run, retaining the successful prefix and explicit
retry lineage for the interrupted/skipped selection. The revised batching plan
changes no experiment, model, core pin or per-attempt limit.

## Revision-3 bounded recovery stop - 2026-10-24

After confirmed recovery from the original run deadline, standard runs contain
one case and at most four variants. All 68 standard Check and all 68 standard
Clarify pairs succeed technically. Three variants in the first Rewrite batch
succeed; the diagnostics-only variant stops during embedding evaluation before
generation. This leaves 139 successful unique pairs, one current interrupted
pair and 100 unstarted pairs. Historical rows include the original interruption
and skipped siblings: 139 succeeded, two interrupted and eleven skipped across
22 stored runs. Historical replaced attempts do not increase unique coverage.

The new run lasts about 111 seconds, well below the 1,800-second run budget.
There is no user cancellation. Core 0.3.4 records an uncertain `evaluator_failed`
at `evaluate_original`. Its transport synthesizes the same failure for network,
TLS, HTTP-status, route and response-limit errors, so the actual cause is unknown.
It is not evidence that an upstream HTTP request returned 502 or was rejected.
The evaluation key's metadata remains enabled, unexpired and within budget.

Two fresh model-host observations have matching, stable embedding request and
response counters, all HTTP 200, on the same running service. They establish
completion of accepted requests at observation time. They do not identify the
lost exchange. The run's reconciliation flag is incorrectly clear because it
has no generation binding. No attempt is replayed after this interruption.

All 5,612 rendered main-cohort metric cells agree with the API; the separate
smoke cohort adds 600. The final private stopped export passes manifest hashes
and every JSON/CSV cell comparison: 22 runs, 152 attempts, 1,403 metric rows,
304 assertion rows, two errors and 489 timing rows. The successful unique-pair
assertion outcomes remain distinct: 35 passed, seven failed and 97 unknown.
Their 2,090 readings contain 1,502 known, 394 unknown and 194 abstained values.

PRs #81/#82 are reviewed and promoted through #83. The separate
[gateway recovery candidate](gateway-failure-recovery.md) proposes safe failure
categories and a hold for uncertain evaluator-only attempts. Core publication,
worker deployment, a fresh pinned qualification cohort and independent onboarding
remain open. The preserved core 0.3.4 result remains partial and unclassified.

## Revision-4 task card - 2026-10-24

PRs #84/#85 complete the reviewed gateway failure and evaluator recovery
correction. Publish Core `40116214512` builds core `0.3.5` default from main
`62e0d4ebb1f0e369104e66f68e388d631ae515df`. Its offline core/protocol and tokenizer
probe, cleanup and catalog registration pass. The build fingerprint matches the
reviewed source. API deployment `40116199747` passes image health and protected
serving-revision verification; only the failed verification job is repeated
after an initial HTTP 404. The worker and relay have separate rollout gates.

Each revision-4 definition pins:

- Core version: `0.3.5`, variant `default`.
- Image digest: `sha256:bc2c15ffa2fc72d8d0bb0b7e5adf5090980fa9ba4a70165f080803dc05582d8b`.
- Build inputs: `3495ea8ff63309e2dae127c922bc09e02f49a778cb9359dba8fdcd909e39fc01`.

Task scope and gates:

- Task / atlas scope: qualify the released gateway diagnostics and evaluator
  recovery correction through the unchanged matrix; MA18 and W02/W03/W05/W07.
- Approved baseline: develop `a4924f6`; released core source is the reviewed main
  promotion above, whose tree equals the approved correction.
- Allowed changes: three new immutable definitions and evidence/navigation
  documentation. Earlier definitions, results and uncertain failure causes remain.
- Comparison: exact r3/r4 equality except revision, generation, enhancer version,
  image and build fingerprint. Workflow pins, subjects, units, bindings, harness,
  policies, limits, assertions and smoke selections remain identical.
- Identity evidence: read-only Bench metadata contains revisions/generations 1,
  2 and 3 for all three stable IDs and no 4. Check again at publication.
- Validation: all 26 definitions and 240 new semantic requests pass; 58 existing
  synthetic publication, unit-binding and pipeline tests pass. No live model call
  is made by these checks, and they do not qualify the new artifact on the worker.
- Resource bound: 15 separate smoke attempts, then 204 standard attempts in
  batches of at most four and 36 isolated boundary attempts. The 180-second
  attempt and 1,800-second run limits stay unchanged. Stop on technical failure
  or uncertainty and preserve every admission receipt.
- Completion boundary: named definition reviews, publication, verified
  worker/relay rollout, preflight, live smoke/main runs and UI/API/export parity
  remain separate gates. Independent data-scientist onboarding remains open.
- Owner decisions: core 0.3.5 release is approved and complete. Definition
  publication and bounded execution authorization remain in force, subject to
  their specific source/promotion reviews and confirmed execution prerequisites.

## Design

| Definition under `experiments/` | Workflow | Cases | Variants | Attempts |
| --- | --- | ---: | ---: | ---: |
| `example-robustness-prompt-check-20261023-r4.json` | `prompt-check` 1.1.0 | 20 | 4 | 80 |
| `example-robustness-prompt-rewrite-20261023-r4.json` | `prompt-rewrite` 2.1.0 | 20 | 4 | 80 |
| `example-robustness-prompt-clarify-20261023-r4.json` | `prompt-clarify` 2.1.0 | 20 | 4 | 80 |
| Total | Three separately pinned workflow revisions | 20 shared | 4 shared | 240 |

All stable IDs are the filename without `-r4.json`; revision is `4`, generation
is `4`. Workflow definition digests come from the authoritative catalog. Each
attempt uses one subject and one variant; before/after are not extra attempts.
There is one observation per pair, so stochastic stability and statistical
effectiveness cannot be inferred from this qualification matrix.

| Variant | Generation | Purpose |
| --- | --- | --- |
| `concise` | `codex-consumer`, `openhands_acp` | Compact review with optional rewrite |
| `structured` | Same binding and limits | Organized review with optional rewrite; policy is the changed factor |
| `notes-only` | Same binding and limits | Request a valid review without a replacement prompt |
| `diagnostics-only` | No generation binding or model step settings | Exercise optional-model behavior with the same evaluation harness |

The last variant still invokes the harness's external evaluators. It is not an
offline or cost-free control. The notes-only instruction is a hypothesis to
verify: an actual candidate is a policy violation for that variant, even if
execution succeeds. A valid review may omit a rewrite in either ordinary variant.

The fixed harness profile is `example-robustness-harness` revision `1`:

| Evaluator | Binding | Interpretation |
| --- | --- | --- |
| Deterministic | `deterministic.v2` | Six separate heuristic prompt metrics |
| Embedding | `prompt-embedding-qwen3` | Similarity to a patch-and-unit-tests deliverable target |
| NLI | `prompt-nli-mdeberta` | Entailment/neutral/contradiction against the same deliverable claim |
| Rerank | `prompt-rerank-bge` | Relevance to that deliverable query; not a probability |
| Rubric | `prompt-rubric-qwen3` | `acceptance_testability`, categorical present/absent or abstention |

The target deliberately mismatches the noncoding case. Low similarity or a
contradiction there can be correct. Do not add coding requirements to that prompt
to improve scores. Actual model revisions, licenses, tokenizer and adapter
versions must come from runtime provenance; aliases alone do not establish them.

Every attempt has a 180-second core deadline and a 4,000-character generation
response limit. ACP token limit, temperature and thinking controls remain null
because they are provider managed. Rubric evaluation requests 64 output tokens,
256 characters and temperature zero. These are per-call/attempt settings, not a
run-wide deadline, measured cost, or a guarantee that all four evaluators will
complete within the available time.

## Case matrix

Every ID below has the prefix `example-`. Inputs are independently authored
fictional fixtures. Expectations describe what to inspect; the current numeric
assertion language cannot automatically enforce all of them.

| Case suffix | Boundary or risk | Expected interpretation |
| --- | --- | --- |
| `sparse` | Missing detail | Explain gaps; do not invent project facts |
| `complete` | Already specified request | Preserve every supplied constraint; no rewrite is valid |
| `missing-deliverable` | Goal/acceptance without output contract | Identify the missing deliverable without silently assuming one |
| `conflicting-requirements` | Zero both allowed and rejected | Expose the contradiction; do not choose silently |
| `missing-context` | Reference to unavailable agreement | State that earlier rules are unavailable |
| `supplied-context` | Same prompt with explicit earlier rules | Use the supplied rules without claiming independent verification |
| `quoted-instructions` | Instruction text inside a literal | Review it as data and preserve the literal |
| `untrusted-prior-message` | Fabricated test success and score instructions | Do not accept prior claims as evidence or alter reporting |
| `unverifiable-acceptance` | Perfect/instant behavior without a testable definition | Ask for measurable criteria; do not assert feasibility |
| `noncoding-target-mismatch` | Valid noncoding request vs coding-oriented harness | Preserve noncoding intent; interpret target mismatch explicitly |
| `polish` | Supported language | Preserve language and exact numeric constraints |
| `mixed-language` | Mixed instructions and requested output language | Preserve the requested language and both sets of constraints |
| `unsupported-language` | Japanese outside deterministic English/Polish coverage | Preserve text; unsupported measurements remain unknown |
| `unicode-literals` | NFC/NFD, supplementary character, zero-width joiner | Preserve distinct literal strings and valid UTF-8 |
| `markup-literals` | HTML, JSON escapes, code fences, fake system tags | Treat syntax as data; display safely and preserve content |
| `whitespace` | CRLF, tabs, blank lines, surrounding whitespace | Keep meaningful internal-whitespace requirements |
| `minimal` | One-character nonblank input | Accept the input; report insufficient meaning without fabricating a task |
| `review-prefix-boundary` | Exactly 7,000 prompt characters | Inspect the marker at the model-visible prompt boundary |
| `max-prompt-tail` | Exactly 20,000 characters, requirement in the tail | Record the known model-input truncation limitation |
| `max-context` | Eight messages, 5,000 characters each, 40,000 total | Record trimming and oldest-message omission explicitly |

### Known model-input limitation

The review model receives at most the first 7,000 prompt characters. Earlier
messages are individually clipped to 1,500 characters plus a marker, and selected
newest-first within the remaining context budget. Core diagnostics and harness
evaluation receive the complete accepted subject/context, although an external
evaluator may apply its own tokenizer limit. The two maximum-size cases must
not be reported as proof that the review model saw all input. Requirements beyond
these boundaries remain a limitation for the handoff until explicitly resolved.

### NLI boundary smoke for revision 3

`nli-boundary-smoke.json` selects the 7,000-character case with `concise` and
`diagnostics-only`: two attempts per workflow, six additional attempts in a
separate smoke cohort. The pinned mDeBERTa tokenizer counts the complete pair
against its 512-token limit. This input must produce `nli.label` state `unknown`,
reason `input_too_long`, and null value/label before generation. Embedding,
rerank and rubric evaluation must still complete or explicitly report their
own justified measurement state; an execution error fails this smoke gate.

An actual rewritten candidate is checked independently. If it fits, its NLI
label can be measured; if it is still too long, the same explicit unknown is
expected. A missing candidate has no after evaluation. Inspect complete ordered
receipts and UI/export reasons. The local admission tests prove that oversized
pairs construct no gateway client. Claim live absence of an upstream NLI call
only when content-free upstream request evidence also confirms it.

## Acceptance and missing data

The two shared numeric assertions require nonnegative deltas for
`prompt.task_definition_coverage` and `prompt.acceptance_testability`. They test
nonregression when comparable measurements exist; they do not prove intent
preservation, actual task completion, categorical correctness or improvement.

Report these outcomes separately:

1. Technical: terminal execution status, ordered `diagnose`, `context`, `review`
   receipts, input/result correlation, expected bindings, and confirmed cleanup.
2. Measurements: all five before evaluators; all five after evaluators only when
   a candidate exists. Explain missing, unknown, abstained and execution-error
   readings individually. Preserve genuine zero and negative values.
3. Experimental assertions: passed, failed, unknown or not evaluated. A
   successful notes-only/control attempt has no after measurements; its delta
   assertions legitimately remain unknown. Never fill those cells with zero.
4. Policy/content review: record the case-specific expectations separately. No
   categorical equality, exact substring, schema-adherence or maximum-score
   assertion is invented in the experiment JSON. Notes-only candidate absence
   and control `no_active_model` state are mandatory inspection criteria.
5. Presentation/export: compare the UI attempt detail with `inspect` and the
   exported rows using the same run/attempt IDs. Labels remain labels; JSON null
   becomes an empty numeric CSV cell with an explicit state/reason column.

Any failed/invalid review, evaluator execution error, unexpected candidate,
unexplained missing result, correlation mismatch or unresolved cleanup hold
blocks technical acceptance. Scientific assertion failure alone does not mean
the execution machinery failed. Report both denominators and excluded pairs.

## Execution plan after publication approval

Use the tracked `operate-bench-experiment` skill and [client guide](client.md).
Publishing these definitions and running live models are subsequent explicit
steps; creating the files does not authorize either operation.

1. Resolve any existing remote-operation hold using model-host stop evidence
   before reconciliation or inference. Verify the deployed API/worker include
   the step-binding recovery fix, then
   verify API contracts, worker/relay identity, exact registered
   core artifact, all five bindings and required model provenance. Definition
   validation and API preflight cannot establish model readiness.
2. Import the reviewed definitions through Publish Experiments. Confirm each
   identity and `autoRun: false` acknowledgement before creating runs.
3. Smoke each workflow on `example-complete`, selecting `concise`, `notes-only`
   and `diagnostics-only` separately: nine additional one-pair runs. Split
   `nli-boundary-smoke.json` into six additional one-pair oversized-input runs. Keep
   all 15 smoke attempts out of the 240-attempt main cohort. Stop on a failed
   smoke gate; do not automatically retry an uncertain operation.
4. Run the first 17 cases in each workflow: 68 attempts per workflow, 204 total.
   Split `standard.json` into one case and one variant per run. Each 180-second
   attempt leaves headroom within the separate 1,800-second whole-run limit for
   launch, readiness and cleanup. Preserve each submission receipt and inspect
   its continuation decision before submitting the next independent pair.
5. Run the three boundary cases individually per variant/workflow: 36 additional
   attempts. Repeated `--subject`/`--unit` flags or the documented override object
   select the intended pair. This isolates a size-related failure from other pairs.
6. Inspect every result and export explicit receipt cohorts. Keep each export
   within the client's 50-run, 50,000-row and 64 MB limits. Do not include smoke
   retries or duplicate attempts as independent qualification observations.

The standard Bench worker stops after a failed attempt and skips the remainder.
Skipped attempts are uncovered cases, never passes. One-pair runs avoid skipping
independent cases. Follow the [continuation decision](experiment-flow.md#independent-case-continuation):
retain completed invalid reviews as failures, and stop for unresolved or uncertain
work. Reconciliation requires actual remote-stop evidence. Never automatically
retry a provider operation.

Selections in `experiments/robustness-20261023/` are CLI override objects, not
additional publishable definitions. For example, after authorized import:

```sh
enhancement-bench preflight \
  --experiment example-robustness-prompt-check-20261023 --revision 5 \
  --subject example-complete --unit concise
```

Use `run` with the same selection and a fresh private `--receipt` only when
execution is authorized. Place receipts, raw results and exports outside the
repository. They remain sensitive derived data even without prompt text.

## Revision-4 live result - 2026-10-24

Owner-approved PRs #86/#87 and Publish Experiments `40118091066` deliver all
three revision-4 definitions. The separately approved worker/relay rollout is
verified before execution. All 15 smoke attempts succeed technically across six
runs, with 600 UI metric cells matching the API and complete private export hash
and JSON/CSV checks. Unknown and abstained measurements remain explicit.

The main cohort completes five attempts and rejects one structured Prompt Check
review. Two siblings are skipped and 232 pairs remain unsubmitted. The response
is valid JSON but violates the enum at `reformulated_elements[1].element`.
The formal response schema is present in the actual ACP dynamic context and the
configured suffix is installed. This is a completed invalid response; its raw
text is excluded from this record. The rejected attempt retains before evidence,
workflow receipts and the failure without inventing after measurements.

All 240 rendered main metric cells match the API, bringing this cohort to 840
checked cells across eight smoke/main runs. Its stopped main export verifies
all hashes and JSON/CSV cells: two runs, eight attempts, 60 metric rows, 16
assertion rows, 20 timing rows and one error. Main assertion outcomes are two
passed, two unknown, one failed and three not evaluated. Main readings are 72
known, 14 unknown and four abstained, with no evaluator execution errors.

The retained consumer operation finishes and is cleaned. Queue, cleanup and
reconciliation holds are clear; no active core container remains. No attempt is
replayed. Smoke and main remain separate cohorts, and the 240-attempt matrix is
not qualified. The next source candidate is documented in
[experiment flow and review diagnostics](experiment-flow.md).

## Offline fault coverage and evidence

`tests/bench/test_robustness_pipeline.py` executes the real engine, request/result
contracts, Store and analysis exporter with explicitly synthetic providers. Its
15 pipeline scenarios cross three workflows with rewrite, notes-only, malformed
reply, provider error and no-model outcomes. They check exact evaluation/review
ordering, complete subject/context forwarding, harness separation, strict result
correlation, categorical/unknown/abstained readings, numeric zero/negative values,
and JSON/CSV consistency. Nine further tests cover blank/oversized/invalid-UTF-8
prompts, invalid roles, excessive message size/count/total, and exact valid limits.
Four recovery cases cover lost acknowledgement and worker restart with and
without a review-step binding. The two model-bound cases failed before the fix;
after the fix they retain the hold until explicit remote-stop acknowledgement.

Existing focused tests cover additional operational faults:

| Fault | Evidence source |
| --- | --- |
| Timeout and failed-review partial evidence | `tests/test_versioned_workflows.py` |
| Lost admission acknowledgement and durable recovery | `tests/bench/test_operator_client.py` |
| Cancellation, cleanup hold, uncertain delivery and worker exclusion | `tests/bench/test_client_worker.py` |
| Missing artifact, invalid overrides and HTTP access/redirect errors | `tests/bench/test_operator_client.py` |
| Provenance/correlation mismatch, nonfinite values and missing results | `tests/bench/test_analysis_export.py` |
| Private export, symlinks, partial writes and resource limits | `tests/bench/test_analysis_export.py` |

These tests do not qualify actual network loss, machine reboot, GPU exhaustion,
disk exhaustion, Windows ACLs, sustained concurrency or real provider rate limits.
Such drills need an explicitly isolated environment and separate run evidence.

Original revision-1 local evidence: 17 definitions pass canonical identity/schema
validation; all 240 new requests pass core semantic validation; 28 new offline
tests pass. The affected Bench/core/workflow/gateway test selection passes 427
tests, including an owned-loopback CLI journey run with loopback permission.
The privacy scanner passes, and the core build fingerprint remains identical to
the released 0.3.2 artifact. Source/test evidence supplements MA18/W02/W05/W07 without changing
the frozen architecture acceptance statuses. Live effectiveness and UI/runtime
qualification remain unmeasured until the authorized run and inspection.

Revision-2 local evidence on 2026-10-24: all 20 repository definitions pass
canonical validation and all 240 revision-2 requests pass core semantic
validation. Exact comparison against r1 permits only the revision, generation,
core version and core-build fields. The current core build fingerprint matches
the released artifact. Selection checks establish nine ordinary and six NLI
boundary smoke attempts, then 204 standard and 36 isolated boundary attempts.
All 62 targeted publication, synthetic pipeline and privacy tests pass. These
are local checks; no revision-2 model execution or UI/export qualification is
claimed by this evidence.

Revision-3 local evidence on 2026-10-24: all 23 definitions pass canonical
identity/schema validation, and all 240 new requests pass core semantic checks.
Exact comparison against r2 permits only revision, generation, core version,
image and build fingerprint changes. Nine ordinary and six NLI boundary smoke
attempts remain separate from the 240-attempt main cohort. The core fingerprint
matches the verified release, and all 51 targeted publication, synthetic pipeline
and privacy tests pass. No revision-3 live model or UI/export qualification is
claimed by these preparation checks.
