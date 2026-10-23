# Evaluator coverage correction

## Task card

- Task: explain unscored Bench readings and repair missed coding-request cues.
- Atlas scope: MA18, W03, W05 and W07; bounded evaluator and result presentation.
- Approved source baseline: develop `4005bf1`, including the reviewed core 0.3.0
  adapters and integrated synthetic definitions.
- Reproduction: the existing detector does not recognize a request for a patch
  and tests, or a prohibition beginning with "Do not add dependencies".
- Allowed changes: an optional deterministic evaluator binding, its core version
  and exported schemas, Bench result presentation, synthetic tests and evidence.
- Preserved contracts: immutable experiment revisions, v1 evaluator behavior,
  workflow diagnostics, session analytics, model settings, and all unscored states.
- Completion criterion: explicit coding artifacts/prohibitions are recognized;
  missing evidence is never converted to a number; UI distinguishes every state;
  old and new evaluator versions cannot produce a numeric cross-version delta.
- Process bound: local synthetic unit/integration tests and owned loopback HTTP
  and browser servers. No model request or production mutation is part of validation.
- Owner decisions: source review, publication, deployment and selection of the new
  core/evaluator in a new experiment revision remain separate actions.

## Versioned correction

Core 0.3.1 is a source candidate with an additional built-in `deterministic.v2`
binding. It reuses the six metric meanings and the shared deterministic engine,
with a coding-request feature extractor. Requested patches, diffs and test
artifacts are recognized as deliverables. Patch/diff and unit-test formats supply
format cues. Explicit prohibitions such as "do not add", "don't change" and
"never mutate" supply constraint cues; vague clauses retain their weak score.

The new adapter records `prompt-evaluation.v2` and metric engine
`prompt-cues-en-pl-1`. Both sides of a comparison must have identical provenance.
The existing `deterministic.v1` binding, pre-Bench workflow diagnostics and
session-analytics rules retain their existing identities and behavior. No stored
result or existing experiment definition is rewritten. Selecting v2 requires a
new evaluator-profile revision and experiment revision pinned to the released
core artifact.

## States with no numeric score

| Recorded state or reason | Interpretation |
| --- | --- |
| `known`, numeric zero | A measured zero; display it as zero. |
| `diagnostic_task_not_detected` | The heuristic did not detect a diagnosis task. It cannot establish task inapplicability. |
| `constraints_unobserved` | No constraint clause was detected. Precision has no observed denominator. |
| `deliverables_unobserved` | No deliverable clause was detected; a detector miss remains possible. |
| `abstained` / `rubric_abstained` | The rubric model explicitly declined to classify. |
| `rubric_reply_invalid` | The reply was malformed or incomplete; distinct from an explicit abstention. |
| `not_applicable` | The evaluator recorded inapplicability. |
| `execution_error` | Evaluation failed; distinct from a valid abstention. |
| Missing reading | No reading was recorded for that side. |
| `categorical_metric` | Show the before/after labels; there is no numeric difference. |

The current acceptance rubric explicitly permits abstention when acceptance
criteria are unavailable. A sparse prompt without criteria can therefore receive
a valid abstention. Changing that decision rule would require a separately
versioned rubric and qualification; this correction does not force a label.

The Bench counts before/after readings by state, explains unscored values, and
shows categorical transitions. Counts describe measurement availability, not
execution success or assertion outcome. Historical reason codes remain visible
in the complete result.

## Evidence

The six checked-in synthetic inputs reproduce four missing deliverable readings
under v1; v2 recognizes deliverables in all six. Their three sparse inputs still
have unknown constraint precision, and diagnosis evidence remains unscored.
Focused tests cover requested artifacts, verification-only mentions, negated
requests, explicit/vague prohibitions, missing constraints, language abstention,
assistant-context isolation, v1 compatibility and cross-version rejection.

Core tests include real owned loopback HTTP for both evaluator bindings. Bench
integration verifies the selected evaluator and recorded provenance through the
worker. The complete 50-case desktop/mobile browser suite passes, including
zero, unknown, abstained, not-applicable, error, missing-side and categorical
presentation. This is bounded synthetic evidence, not a model-calibration or
general workflow acceptance claim. No production readings were rewritten.
