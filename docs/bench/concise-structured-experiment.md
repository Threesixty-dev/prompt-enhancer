# Concise versus structured rewriting

Status: prepared for owner-authorized publication; automatic execution disabled.

Definition: [example-concise-structured-20261014.json](../../experiments/example-concise-structured-20261014.json).
Identity: `example-concise-structured-20261014`, revision `1`, generation `1`.

## Hypothesis and comparison

On sparse prompts, structured rewriting produces a larger improvement in
`prompt.acceptance_testability` than concise rewriting. Neither style should
discard supplied requirements or invent missing facts. Already specified prompts
serve as regression controls, where extra detail is not automatically useful.

| Fictional task | Sparse input | Specified control | Styles | Attempts |
| --- | --- | --- | --- | --- |
| Widget record parser | Missing format and validation details | Exact fields, bounds, errors and tests | concise, structured | 4 |
| Item list filter | Missing matching and state rules | Exact matching, ordering and immutability rules | concise, structured | 4 |
| Inventory CSV export | Missing output and quoting rules | Exact header, escaping, ordering and empty behavior | concise, structured | 4 |

Six subjects cross two units for **12 attempts per run**. Before/after passes
are evaluations within an attempt. All cases are authored synthetic inputs with
empty context; the specified controls are separate subjects, not context that
the sparse subjects are allowed to assume.

Both units use `consumer.rewrite.v1`. Only `steering.style` differs; effective
consumer binding, instructions, focus, objectives, parameters, assertions and
evaluator profile are identical. There is one candidate per case/style in this
pilot, so stochastic variation remains unmeasured.

## Bindings and limits

- Core: retained version `0.1.4`, dependency variant `default`. The publication
  environment's retained-artifact catalog was checked on 2026-10-14 and maps
  this version/variant to an immutable digest. A completed synthetic qualification
  run also records this core version. Compatibility with this exact definition
  and readiness for a new run still need verification.
- Generation: `codex-consumer` / `openhands_acp`, observed in the deployed
  `example-qwen-codex-pilot` definition, revision `pilot-service-v9`. Its completed
  synthetic run on 2026-10-13 records configured and reported model `gpt-6-sol`,
  adapter `openhands-acp-1.49.1.v5`, and core `0.1.4`. This is execution evidence
  for the binding, not an assertion pass or a result for the new experiment.
  Model revision, license and tokenizer revision are null in that evidence;
  keep them unknown. Both units inherit this same binding. Capture and compare
  actual provenance in the new results rather than assuming the alias pins an
  immutable model revision.
- Evaluation: one shared `example-rewrite-style-deterministic` profile, revision
  `1`, with evaluator `prompt` bound to `deterministic.v1`. There is no model
  evaluator. Keep the profile fixed across units and before/after passes.
- Limits: 180 seconds per attempt, at most 4,000 output characters. Token limit
  and temperature are null (provider-managed/unknown). This is not a measured
  cost estimate or a run-wide deadline.
- `autoRun` is false. The definition is not published, queued or executed by
  local validation.

## Interpretation fixed before a run

Each unit asserts a minimum before/after delta of zero for task definition
coverage and acceptance testability. Local deterministic evaluation confirms both
have known baselines for all six subjects. These checks detect metric regressions;
passing them does not demonstrate positive improvement, requirement preservation
or completion of a coding task.

Constraint precision is unknown for the three sparse inputs, and deliverable
contract is unknown for the parser and filter inputs under the current metric
rules. Delta assertions cannot be evaluated for those subjects, even with a valid
rewrite. These metrics remain evaluator observations and review dimensions,
but are not universal pass/fail assertions. Preserve unknown values and compare
these metrics only when both observations are known and provenance matches.

For the three sparse subjects, compare the paired acceptance-testability deltas:
`(structured after - before) - (concise after - before)`. A positive arithmetic
mean supports the directional hypothesis in this pilot; zero is inconclusive
and a negative mean favors concise rewriting. Report each case as well as the
mean. Do not pool the sparse subjects with specified controls. Require known,
comparable observations for all three pairs; otherwise report the comparison as
incomplete without filling missing values or silently changing the denominator.

Report control-subject regressions separately. Review every rewritten prompt
against its input for omitted/changed requirements, invented facts or requirements,
and whether missing details remain explicit placeholders. A numeric gain cannot
override a failed preservation review. Record output length as descriptive data;
longer text is not inherently better. The current definition language cannot
assert cross-unit superiority or semantic preservation, so these conclusions
require separate result analysis and review.

## Task card and evidence

- Task/scope: prepare one Bench experiment and its study plan; no runtime,
  architecture or beta-gate change.
- Baseline: fetched `develop` at `714d958`; branch
  `codex/concise-structured-experiment` in an isolated worktree.
- Outcome: reviewable cases, isolated style comparison and bounded settings.
  Owned files are the linked definition and this study plan.
- Local checks: canonical CLI validation of both publication definitions;
  semantic validation of all 16 subject/unit requests (12 new, four existing);
  unique local revision/generation identities; effective settings differ only
  by style; known baselines for every asserted metric on all six new subjects;
  repository privacy scan and 11 privacy/canary tests passed.
- Validation uses the checkout's contracts, whose core version is `0.1.3`.
  It does not establish runtime equivalence with retained `0.1.4`.
- Completion boundary: definition prepared and generation binding resolved from
  the deployed definition and completed synthetic execution metadata. Server
  identity availability, exact retained-core compatibility and current worker
  readiness remain unverified. Only the authored inputs were evaluated locally
  with deterministic rules. No new model call, image build, publication or Bench
  run occurred.

## Scoped publication candidate

The release candidate starts from `main` at `33f81e6` and includes the existing
core-publication separation (`2deb323`), affected-component CI rules (`45ca55b`),
and this experiment (`14e6348`). It also carries the Bench relay smoke correction
from `fe47f63`, matching the existing consumer's actual process entry point while
preserving its environment-isolation assertion. Application source, application
tests and dependencies are unchanged from main.

Local validation of this combined candidate passes all 201 Bench tests, 142
focused publication/CI/privacy checks, canonical validation of both definitions,
semantic validation of 16 requests, identity checks, the privacy scan and
architecture-output consistency. Hosted validation, owner merge and import
acknowledgement remain separate. Publication reuses core `0.1.4`; `autoRun`
remains false.
