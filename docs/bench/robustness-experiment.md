# Prompt workflow robustness qualification

## Purpose and status

This suite tests the three fixed prompt workflows as a connected system:
generation, deterministic diagnostics, embedding, NLI, reranking, rubric review,
stored results, and analysis. It is a finite regression and boundary matrix;
passing it does not prove that every possible input or infrastructure failure is
covered. It is not a study of developer ability or a universal quality score.

The definitions are prepared with `autoRun: false`. No live attempt from this
suite has run. Local validation proves structure and orchestration with synthetic
providers, not current authentication, model availability, latency or model
quality. Independent data-scientist onboarding remains a separate handoff gate.

Core 0.3.2 default was built from main
`3327aaa94e142176544be5a7f8e34fef04747ed7`. Its release passed offline runtime
identity and cleanup checks. The verified receipt was subsequently registered
through the existing Bench API with HTTP 202 after the Action's delivery step
failed. The running Bench API passed two loopback health checks at that source
revision. The Actions deployment verification encountered HTTP 403; automated
deployment verification and release delivery still need operational follow-up.
These observations do not qualify the worker, relay or external model bindings.

The suite's recovery tests exposed a Bench Store bug: an uncertain operation
with only a review-step binding did not retain the reconciliation hold. This
candidate fixes both lost-acknowledgement and worker-restart paths. Review and
deploy this Store change to both API and worker before running the suite; the
API revision observed above predates it. API deployment alone does not replace
the worker. This Bench fix does not change the core 0.3.2 image.

All definitions pin:

- Core version: `0.3.2`, variant `default`.
- Image digest: `sha256:ab11919803f58daf32ba5a0c77cbddfa6545d8c2ce801c08a57de8931bca8c89`.
- Build inputs: `47d6c7dd0ac6228063f05508be67128c171431bc99b475b5e438228562bd8021`.

## Design

| Definition under `experiments/` | Workflow | Cases | Variants | Attempts |
| --- | --- | ---: | ---: | ---: |
| `example-robustness-prompt-check-20261023-r1.json` | `prompt-check` 1.1.0 | 20 | 4 | 80 |
| `example-robustness-prompt-rewrite-20261023-r1.json` | `prompt-rewrite` 2.1.0 | 20 | 4 | 80 |
| `example-robustness-prompt-clarify-20261023-r1.json` | `prompt-clarify` 2.1.0 | 20 | 4 | 80 |
| Total | Three separately pinned workflow revisions | 20 shared | 4 shared | 240 |

All stable IDs are the filename without `-r1.json`; revision is `1`, generation
is `1`. Workflow definition digests come from the authoritative catalog. Each
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

1. Verify the deployed API/worker include the step-binding recovery fix, then
   verify API contracts, worker/relay identity, exact registered
   core artifact, all five bindings and required model provenance. Definition
   validation and API preflight cannot establish model readiness.
2. Import the reviewed definitions through Publish Experiments. Confirm each
   identity and `autoRun: false` acknowledgement before creating runs.
3. Smoke each workflow on `example-complete`, selecting `concise`, `notes-only`
   and `diagnostics-only`: nine additional attempts, kept out of the main cohort.
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
  --experiment example-robustness-prompt-check-20261023 --revision 1 \
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

Local evidence for this candidate: 17 definitions pass canonical identity/schema
validation; all 240 new requests pass core semantic validation; 28 new offline
tests pass. The affected Bench/core/workflow/gateway test selection passes 427
tests, including an owned-loopback CLI journey run with loopback permission.
The privacy scanner passes, and the core build fingerprint remains identical to
the released 0.3.2 artifact. Source/test evidence supplements MA18/W02/W05/W07 without changing
the frozen architecture acceptance statuses. Live effectiveness and UI/runtime
qualification remain unmeasured until the authorized run and inspection.
