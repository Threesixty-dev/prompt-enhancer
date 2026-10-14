---
name: prepare-bench-experiment
description: Author, revise, and validate Prompt Enhancer Test Bench experiment JSON, including shared cases, comparison variants, generation and evaluation bindings, assertions, and publication readiness. Use when preparing an experiment or reviewing its design before Publish Experiments; ordinary Bench UI changes use the development workflow.
---

# Prepare Bench Experiment

Prepare a reviewable experiment definition and explain exactly what its run will
compare. Resolve repository paths below from the selected Prompt Enhancer checkout,
not from this skill's installation directory.

## Establish the task and sources

Read repository `AGENTS.md` and follow its privacy and contribution rules. Reuse
the approved checkout and preserve unrelated work; repository edits belong on a
task branch from the selected `develop` baseline. Inspect existing definitions
before choosing identities or revision numbers.

Use these sources instead of inventing an experiment schema:

- `docs/bench/README.md`: domain language, inheritance and publication behavior.
- `bench/src/enhancement_bench/definitions.py`: definition fields and effective
  settings; `protocol.py` and `cli.py`: validation of every case/variant pair.
- `contracts/enhancement/execute-request.schema.json` and
  `src/prompt_enhancer/enhancement/contracts.py`: shared execution contract and
  semantic model validation.
- `src/prompt_enhancer/enhancement/engine.py`: strategy restrictions, supported
  metrics, assertions and comparison semantics.
- `experiments/example-clarification-focus.json`: scripted comparison example.
  `bench/examples/example-widget.json`: consumer-binding example. Treat their
  versions and aliases as examples, not evidence of current runtime availability.

Read [authoring details](references/authoring.md) for field rules and pitfalls.
Read [validation](references/validation.md) when checking a candidate.

## Choose the core independently

Establish whether the experiment should use an existing released core or needs
a new core version. If the request and prior answers do not establish this,
ask: "Should this experiment use an existing core version, or should we prepare
and deploy a new core version separately first?" Then resolve the exact version
and dependency variant. Do not repeat a decision already supplied by the user.
Continue drafting cases and variants while this choice is pending.

An experiment change does not require a new core when the existing version
already supports it. For a new core, read
`.agents/skills/deploy-enhancement-core/SKILL.md` and use the separate
`Publish Core` Action. Verify the selected version's immutable image and relevant
runtime prerequisites before publishing an experiment that needs it. Follow
`docs/bench/core-publication.md`; if the required skill is missing, resolve that
checkout prerequisite before proceeding with core work.

`Publish Experiments` must only resolve existing images. It cannot build or
publish a missing core. A missing image is a separate release prerequisite,
not permission to bump versions, retag an artifact or invoke core publication.
Honor explicit core deployment authorization already provided in this task.
Before publication, verify the approved workflow has this separation. If it
still passes `--allow-publish` to `bench/ci.py`, the workflow update must be
reviewed and promoted first; do not claim the old Action is resolve-only.

## Design the comparison

Extract the user's hypothesis, cases, variants, intended models/evaluators and
execution limits. Ask only for missing decisions that affect the intended
comparison or require real configured bindings. Prepare independent parts while
waiting. Never invent an operational alias, model revision or image digest.

Use `subjects` for input cases and `units` for variants. Each selected subject is
paired with every selected unit: N cases x M variants = N*M attempts per run.
Before/After evaluates the original and enhanced prompt inside each attempt;
neither column creates another case. Model choice is a property of each unit,
not an extra automatic dimension. Explicitly enumerate combinations when crossing
multiple factors. Explain which factor each variant changes and keep the other
settings fixed when the aim is to isolate its effect.

Hold one `evaluatorProfile` fixed across sibling units and before/after passes.
Keep generation models separate from evaluator models. Record a compact matrix
of cases and units, effective generation binding, evaluator binding(s), core
version and total attempts before declaring the design ready.

Use authored synthetic cases only, never transformed provider sessions or private
source. Follow the user's actual comparison goal; a deterministic script smoke
is useful for wiring checks but does not substitute for a requested model study.
Keep objective targets, assertion thresholds and interpretations separate. Choose
assertions that can detect the stated regression; a zero delta threshold proves
only nonregression, and no assertions means `not_evaluated`.

## Author the definition

Write a regular JSON file directly under `experiments/` for intended publication.
The publisher reads `experiments/*.json`, not nested folders. Keep disposable
validation fixtures outside the publication directory.

For a new experiment, choose a unique `stableId`, revision string and positive
generation. For an existing experiment, preserve `stableId`, create a new
`revision`, and increase `generation`; never rewrite an imported revision in
place. Check both identity pairs `(stableId, revision)` and
`(stableId, generation)` against all definitions. An incomplete local history
does not prove that an identity is unused on the server.

Set `autoRun` deliberately. For preparation-only drafts with no execution intent,
set it to false and report that choice. If the user requests automatic execution
on publication, set it to true. This field does not itself authorize publication.
Changing it after import requires a new revision too.

Pin `enhancerVersion` to an available reviewed core artifact. Existing retained
versions may differ from the checkout's `CORE_VERSION`; do not silently rewrite
the requested version or change core code to make publication succeed. Resolve
runtime/model readiness separately from local definition validation.

Use closed `parameterSchema` definitions and explicit effective parameters.
Overrides merge shallowly: replace the whole nested `generation` object when
changing it. Preserve null token limits and temperature as provider-managed or
unknown values. Keep selected generation limits, per-attempt timeout and total
attempt count visible; do not infer a measured cost or run-wide timeout from them.

## Validate and hand off

Follow the validation reference: canonical CLI validation, cross-field semantic
checks, strategy/metric review, identity collision check, privacy scan and diff
review. Local validation must not invoke a provider, publish an image, enqueue a
run or inspect a production database. Use existing synthetic tests when the
change touches behavior; a definition-only edit does not need the full UI suite.

Return the file path, hypothesis, case/variant matrix, total attempts, generation
and evaluator bindings, core version, limits, assertions and `autoRun` choice.
State which checks passed and which runtime prerequisites remain unverified.
Do not claim success from schema validity, a publication acknowledgement or a
run's execution status alone.

If publication is requested, inspect `.github/workflows/bench-publish.yml` and the
current nonsecret publication-branch setting. Follow the repository's PR and
owner-authorized merge flow. Use an explicitly verified repository with `gh -R`;
do not rely on an implicit CLI repository. Existing authorization for this task
still applies; preparation alone does not grant publishing or model execution.

`Publish Experiments` validates all top-level definitions and resolves their
images before delivering them, newest generation first. It is not a single-file
dispatch, core release or Bench API/UI deployment. Delivery is idempotent; eligible
`autoRun: true` revisions can queue a run. The Action stops at import
acknowledgement. Track publication, execution status and assertion outcomes as
separate evidence. Do not retry an uncertain model operation automatically.
