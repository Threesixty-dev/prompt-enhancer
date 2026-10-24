# Private Bench analysis export - analysis v2

Start with `manifest.json`. Its presence marks a completed export. It lists exact
run IDs, table row counts, and SHA-256 fingerprints of the other files. This is
an explicit cohort, not all runs from an experiment or stats page.

`analysis.json` is the lossless typed representation of these tables;
`analysis.schema.json` defines its shape. The CSV files contain the same rows.
JSON null becomes an empty CSV cell. Numeric zero remains zero. Objects and lists
in CSV cells are JSON. Booleans are `true`/`false`. Potential spreadsheet formulas
in text cells have a leading apostrophe; use JSON for the original string.

These files contain sensitive derived measurements and identifiers. They omit
prompt/context text, generated rewrites, review notes/findings, evaluator targets,
raw policy instructions, credentials and provider response bodies. They are not
anonymous. Keep the directory private; do not upload it as diagnostic evidence.

## Tables and joins

| Table | Row identity | Meaning |
| --- | --- | --- |
| `runs.csv` | `run_id` | Exact revision, image, workflow and evaluator-profile identity; recorded run status, assertion outcome and cleanup holds. |
| `attempts.csv` | `run_id`, `attempt_id` | One selected case/variant pair, including unexecuted attempts. Join cases with `subject_id` and variants with `unit_id`. |
| `metrics.csv` | `run_id`, `attempt_id`, `evaluator_id`, `metric_key` | Paired before/after values or labels, their states/reasons, reported delta and numeric eligibility. |
| `assertions.csv` | `run_id`, `attempt_id`, `position` | Each declared assertion, its threshold, recorded observation and outcome. |
| `timings.csv` | `run_id`, `attempt_id`, `stage` | Recorded stage durations in seconds. No missing duration is replaced by zero. |
| `errors.csv` | `run_id`, `attempt_id`, `stage`, `code` | Recorded execution errors; `retryable` is source metadata, not an instruction to rerun. |

The manifest remains `bench-export/v1`; its `analysisVersion` is
`bench-analysis/v2`. Compared with analysis v1, the errors table adds nullable
`validation_reason` and `validation_field`. These carry an allowlisted category
and schema path for an invalid review, never the rejected value or response.
Null means that the detail was not recorded, including historical results.
Use the bundled schema for every export; older exports are not rewritten.

Run `created_seconds`, `started_seconds` and `finished_seconds` are Unix timestamps
in seconds. Missing timestamps stay null. No total duration, token usage or cost
is inferred. Workflow and evaluator versions are independent of the core image.

Attempt `parameters` records effective core parameters when available, otherwise
the planned parameters. `workflow_steps` records actual step receipts: status,
implementation, binding, provenance, generation controls and policy identity.
`workflow_step_order` preserves execution order independently of JSON object key
order. Policy text is
replaced by its fingerprint. Empty steps mean no receipt was recorded.
`generation_provenance` contains the configured/reported model and version fields;
unknown values remain null. Configuration and input/candidate SHA-256 fields
bind exact recorded values without exporting their text. Objective, steering and
supplied context have separate fingerprints. Generation context/prompt versions
remain explicit; unrecorded versions stay null. `effective_settings_sha256` binds
the entire planned snapshot, including selections.

## Missingness and failures

`known`, `unknown`, `abstained`, `not_applicable`, `execution_error` and `missing`
remain distinct. `missing` means the metric side was not recorded. A completely
absent evaluator appears in the attempt's `missing_before_evaluators` or
`missing_after_evaluators`; the exporter does not invent metric keys for it.
An unexecuted attempt remains an attempt row even when it has no metric rows.

`technical_outcome` is separate from recorded execution and assertion statuses.
It detects failed review steps, invalid reviews and evaluator errors, including
historical results whose recorded execution says succeeded. `incomplete` covers
queued/running/skipped attempts without a result. Valid reviews with no rewrite
can succeed while after readings remain missing. `result_recorded` distinguishes
a missing result from a result with no candidate.

An assertion with `recorded=false` has `outcome=not_evaluated` and null `observed`.
Unknown and unexecuted assertions are excluded from an evaluated pass rate, with
their counts reported separately. Assertion failure is an experimental outcome;
it does not imply infrastructure failure.

## Numeric comparisons

Use only `pair_eligible=true` for paired numeric means. Eligibility requires a
settled run without cleanup/reconciliation holds, a technically successful
attempt, known numeric values, equal before/after provenance and a recorded
comparable delta matching after minus before. Known zero is eligible.

`exclusion_reason` explains every rejected pair: unsettled run, unsuccessful
attempt, unavailable reading, provenance mismatch, categorical metric, unavailable
delta or inconsistent delta. Values are preserved even when excluded. Categorical
labels belong in transition counts, not numeric means.

Group by `comparison_scope` before comparing variants. It binds experiment
revision, core image, workflow, evaluator profile, evaluator/metric and before
provenance. Join the attempt table and additionally group by `unit_id`, parameter
and step-setting fingerprints, objective/steering/context fingerprints, workflow
configuration, generation context/prompt versions and generation provenance
when isolating a configuration. Do not pool different scopes automatically.
Report included/excluded pair counts with every summary. Completed attempts in a
failed run remain available; account for skipped attempts and resulting selection
when interpreting an experiment.

This export does not compute a universal score or verify downstream coding-task
success. Repeated model runs may produce different outputs under the same pins.
