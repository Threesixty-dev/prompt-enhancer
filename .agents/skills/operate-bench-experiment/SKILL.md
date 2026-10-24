---
name: operate-bench-experiment
description: Run, observe, inspect, cancel, or export existing Prompt Enhancer Bench experiments through the shared client. Use for AI-assisted experiment operation and result interpretation; definition authoring and service deployment have separate guidance.
---

# Operate Bench Experiment

Operate an existing reviewed experiment and return evidence that distinguishes
admission, execution, assertions and measurement coverage. Resolve all paths
from the selected repository root and follow its `AGENTS.md` requirements.

Read `docs/bench/client.md` for exact commands, credentials supplied through the
process environment, receipts and error/exit semantics. Read
`docs/bench/handoff.md#interpret-results` before interpreting results. For export
analysis, read the export's bundled `README.md` and `analysis.schema.json`.

Use `.agents/skills/prepare-bench-experiment/SKILL.md` when a definition or
comparison design needs changing. Use service deployment instructions only when
that is the actual task. This skill supplies no release, credential-change or
model-execution authority beyond the user's existing request.

## Select and check

Use the installed `enhancement-bench --help` to establish command availability.
The candidate client and `/api/client-contracts` must exist on the selected
installation; source files alone do not prove deployment. Report a version
mismatch explicitly rather than inventing commands or validating against an
unrelated checkout's contracts.

Discover identities with `experiments`; use `runs` with pagination when recovering
an existing run. Select the exact experiment revision, cases and variants from
metadata or the user's existing selection. Establish whether the user wants a
new run or continued observation. Preserve an existing run/receipt when resuming.

Use `preflight` with the same selections and overrides intended for `run`.
Report cases times variants as the attempt count. Preflight checks definition,
requests and registered artifact only. Worker, provider authentication and model
readiness remain unverified. A successful API request does not qualify an
embedding, rerank or generation route.

Check the deployed whole-run budget before batching. It is independent of each
attempt's timeout, and preflight does not verify that the batch fits. Split work
into bounded selections with private receipts, leaving headroom for startup and
cleanup. Use `docs/bench/run-budgets.md`; never increase timeouts to conceal an
unexplained interruption or replay an uncertain attempt without confirmed stop.

Keep generation and evaluator bindings separate. Resolve aliases through approved
metadata; never invent an alias, digest, revision or license. A v2 revision fixes
the workflow, core image and harness evaluation. Selecting a different pin needs
a new definition revision through the authoring workflow.

## Submit and recover admission

For an authorized new run, use `run` with a new private `--receipt` path outside
the repository. The client persists the request UUID before admission. Retain
the original selection/overrides; receipt fingerprints cannot reconstruct them.

After a lost acknowledgement or failed receipt update, reuse the exact receipt,
origin and settings. Do not create a fresh request UUID as a transport retry.
An acknowledged receipt returns its saved run ID without another submission;
use `inspect` or `wait` to read current state. Use a new receipt only for an
intentional new run. `--retry-of` requires a reconciled terminal source run.

## Observe and interpret

Use `wait` or `inspect` with the acknowledged receipt or exact run ID. Parse the
`bench-cli/v1` envelope together with its exit code:

- `0`: operation completed; admission still is not execution completion.
- `2`: input/access/transport/contract/file error; follow `nextAction` and retain
  any submission receipt.
- `3`: `wait` observed technical failure, a hold, or an unmet explicit assertion
  gate. A valid failure report can have `ok:true`.
- `4`: observation timed out; the run has not been cancelled or resubmitted.

Assertions are a separate experimental outcome. Add `--require-assertions` only
when that is the requested acceptance rule. Invalid review responses and model
errors are technical failures, including historical rows recorded as succeeded.
A valid review without a rewrite can succeed while after measurements are absent.

Inspect ordered workflow steps, missing evaluators, errors and cleanup holds.
Never clear a hold or replay an uncertain model operation automatically. A
`cancel` acknowledgement is not confirmed remote stop; observe terminal state and
cleanup. Operator reconciliation requires evidence of the actual remote stop.

Evaluator-only runs can also call remote models. Inspect uncertainty independently
of generation bindings; historical versions may leave their reconciliation flag
unset. Use `docs/bench/gateway-failure-recovery.md` for the versioned diagnostic
categories and recovery limits. A safe error code is not proof of remote stop.

## Export and report

Use `export` with explicit unique run IDs/receipts and a new private output
directory. Keep this cohort with the analysis; a filtered stats page may include
additional runs. Require `manifest.json`, verify its hashes before consuming a
transferred export, and use the bundled schema/dictionary for joins and types.

For numeric paired summaries, use `pair_eligible` and report exclusions. Group by
`comparison_scope` and the configuration fields in the dictionary; do not silently
pool versions, model identities or changed parameters. Preserve zero, unknown,
abstained, not applicable, execution error and missing. Count categorical
transitions separately. Keep execution, assertion and measurement denominators
explicit. Unexecuted attempts remain part of coverage reporting.

Exports omit prompt text but retain sensitive derived data and fingerprints.
They are private analysis artifacts, not public diagnostic attachments. Respect
the user's task-specific scope when reading or sharing results.

Report the run IDs/revisions, attempt counts, terminal/cleanup state, technical
failures, assertion outcomes, coverage/exclusions, export version/location and
remaining unverified dependencies. Separate what the evidence establishes from
scientific conclusions; a prompt score does not verify downstream task success.
