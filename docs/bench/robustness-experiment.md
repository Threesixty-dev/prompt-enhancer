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

## Design

| Definition under `experiments/` | Workflow | Cases | Variants | Attempts |
| --- | --- | ---: | ---: | ---: |
| `example-robustness-prompt-check-20261023-r2.json` | `prompt-check` 1.1.0 | 20 | 4 | 80 |
| `example-robustness-prompt-rewrite-20261023-r2.json` | `prompt-rewrite` 2.1.0 | 20 | 4 | 80 |
| `example-robustness-prompt-clarify-20261023-r2.json` | `prompt-clarify` 2.1.0 | 20 | 4 | 80 |
| Total | Three separately pinned workflow revisions | 20 shared | 4 shared | 240 |

All stable IDs are the filename without `-r2.json`; revision is `2`, generation
is `2`. Workflow definition digests come from the authoritative catalog. Each
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

### NLI boundary smoke for revision 2

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
   and `diagnostics-only`: nine additional attempts. Then use
   `nli-boundary-smoke.json` for six additional oversized-input attempts. Keep
   all 15 smoke attempts out of the 240-attempt main cohort. Stop on a failed
   smoke gate; do not automatically retry an uncertain operation.
4. Run the first 17 cases in each workflow: 68 attempts per workflow, 204 total.
   Use the supplied `standard.json` selection. Preserve the submission receipt.
5. Run the three boundary cases individually per variant/workflow: 36 additional
   attempts. Repeated `--subject`/`--unit` flags or the documented override object
   select the intended pair. This isolates a size-related failure from other pairs.
6. Inspect every result and export explicit receipt cohorts. Keep each export
   within the client's 50-run, 50,000-row and 64 MB limits. Do not include smoke
   retries or duplicate attempts as independent qualification observations.

The standard Bench worker stops after a failed attempt and skips the remainder.
Skipped attempts are uncovered cases, never passes. Diagnose the failure and
obtain a reconciled state before an intentional, separately recorded retry or
smaller selection. Never automatically retry an uncertain provider operation.

Selections in `experiments/robustness-20261023/` are CLI override objects, not
additional publishable definitions. For example, after authorized import:

```sh
enhancement-bench preflight \
  --experiment example-robustness-prompt-check-20261023 --revision 2 \
  --overrides experiments/robustness-20261023/smoke.json
```

Use `run` with the same selection and a fresh private `--receipt` only when
execution is authorized. Place receipts, raw results and exports outside the
repository. They remain sensitive derived data even without prompt text.

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
