# Authoring details

Repository paths resolve from the approved checkout. Recheck current contracts
when they differ from this guide; these notes are not an alternate schema.

For new versioned-workflow definitions, use `bench-experiment/v2` and follow
`docs/bench/versioned-workflows.md`. Pin one workflow reference and exact core
release receipt; fix harness evaluation/assertions at the experiment level.
Only declared step settings may vary. The table and strategy guidance below
describe retained v1 definitions; do not apply their run-time image rebinding
or mixed-strategy examples to v2.

For the pre-Bench prompt logic, select `prompt-check` version `1.0.0`,
`prompt-rewrite` or `prompt-clarify` version `2.0.0`. Each scores, infers context and
optionally performs model review/rewrite using strategy `prompt.check.v1` and
step ID `review`. Configure policy/model/parameters there, not in legacy
objective/steering fields. Rewrite/clarify `1.0.0` remain the distinct legacy
two-step flows; never change an existing pin to the new version in place.

## Fields and inheritance

| Field | Authoring rule |
| --- | --- |
| `schemaVersion` | Use `bench-experiment/v1` while that is the supported definition contract. |
| `stableId` | Stable logical experiment identity; unique for a new experiment. |
| `revision` | Immutable string identity. A changed definition gets a new value. |
| `generation` | Positive integer controlling revision ordering, independently of the revision string. |
| `enhancerVersion` | Exact core version resolved to an immutable image when each Run is created. |
| `subjects` | Shared synthetic input cases, each with unique `id`, `text`, and explicit context. |
| `units` | Comparison configurations, each with a unique `id`, title and packaged strategy. |
| `consumerBinding` | Default generation binding for consumer units; null for a script-only experiment. |
| `evaluatorProfile` | One versioned evaluator profile used by every sibling unit and both passes. |
| `baseParameters` | Explicit timeout and full generation settings. |
| `parameterSchema` | Closed JSON object schema validating every effective unit parameter set; no remote refs. |
| `objective` | Versioned generation goal and typed targets, separate from assertions. |
| `baseSteering` | Default profile, style, focus and optional generation instructions. |
| `autoRun` | Whether an eligible imported revision should automatically queue a run. |

Read actual limits from `definitions.py` and the shared request contract. Bench
and core restrictions both apply; accepting a field at one layer does not mean
it is executable at the other.

Definition parameters merge in this order: `baseParameters`, unit `parameters`.
UI run-wide overrides and per-unit overrides apply after that. Objectives and
steering follow the same shallow replacement pattern. Replacing `targets`,
`focus` or `generation` replaces the complete field, not individual items.

An omitted unit consumer binding inherits the experiment's binding. A unit such
as `{"binding_id":"example-model-b"}` retains the inherited provider. Script
units reject consumer-binding overrides. Bindings contain approved aliases and
provider identifiers only; never endpoints, credentials or arbitrary model paths.
Actual model/revision/license provenance belongs to the configured binding and
the recorded result; do not invent definition fields for it.

## Strategy constraints

Check `EnhancementEngine.validate` and the selected adapter before assuming a
strategy supports a setting.

`script.clarify.v1` currently supports conservative/targeted clarification with
style `preserve`, no custom instructions, null `max_tokens` and temperature, and
the core's default objective description. Its objective targets must be numeric,
refer to deterministic evaluation, and request an increase. Focus and targets
control which missing aspects get clarification placeholders. The added text is
not verified task context or evidence that quality improved.

`consumer.rewrite.v1` requires a configured consumer alias and provider. Different
generation models belong in different units with explicit bindings. Check the
selected adapter's supported settings; an adapter may reject generation controls
it cannot enforce. A consumer-backed experiment with unresolved aliases can be a
draft, but must not be reported as runtime-ready.

## Evaluation and assertions

| Evaluator kind | Required configuration | Output and comparison |
| --- | --- | --- |
| `deterministic` | Approved deterministic binding; target, rubric and generation are null. | Numeric `prompt.*` metrics listed in `engine.py`; unknown values stay unknown. |
| `embedding` | Configured binding and nonempty synthetic `target`; no rubric or generation. | Numeric `embedding.similarity`; similarity alone is not task-success evidence. |
| `classifier` | Configured binding and nonempty synthetic `target`; no rubric or generation. | Categorical `nli.label`; labels are not numeric deltas. |
| `rerank` | Configured gateway binding and nonempty synthetic query `target`; no rubric or generation. | Numeric `rerank.relevance`; a descriptive pair score, not a calibrated probability. |
| `rubric` | Configured binding and supported rubric; target is null; generation settings are optional if the adapter supports them. | Categorical `rubric.label`; absent, present and abstention remain distinct. |

Use unique evaluator IDs. Every assertion and objective target must refer to an
evaluator in the shared profile and a metric it actually produces. Use numeric
targets for deterministic/embedding metrics and categorical targets for
classifier/rubric labels. Read allowed labels and rubric IDs from the contracts
and engine instead of deriving labels from model prose.

The current assertion operators are `minimum_value` (after value) and
`minimum_delta` (after minus before), both numeric lower bounds. There is no
categorical equality or maximum-value assertion. Do not invent one or translate
labels into arbitrary numbers. State when the desired acceptance criterion
requires a separate engine change rather than pretending the definition tests it.

For example, a `minimum_delta` threshold of zero on
`prompt.acceptance_testability` checks nonregression. It does not require positive
improvement, and four attempts do not establish broad effectiveness. Numeric
deltas require known values and matching evaluator provenance. Unknown,
abstained and non-comparable observations cannot become zero or a pass.

Execution `succeeded` and assertion `passed` are distinct. With no assertions,
the assertion outcome is `not_evaluated`. A chart or an assistant completion
claim does not prove the underlying task was completed.
