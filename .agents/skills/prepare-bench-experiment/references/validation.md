# Local validation and publication readiness

Run from the selected repository root with an already installed compatible Bench
Python environment. If absent, the repository's locked setup is
`uv sync --project bench --frozen --extra dev`. Honor existing dependency/network
permissions; never inspect credential files to make a validation command work.

## Canonical validation

```sh
bench/.venv/bin/python -m enhancement_bench.cli validate experiments/*.json
bench/.venv/bin/python scripts/privacy_scan.py
git diff --check
```

Use the equivalent installed interpreter and `PYTHONPATH=bench/src` when working
in a clean worktree without its own virtual environment. For an explicit draft
outside the publication folder, pass that file to the CLI separately and include
its parent directory in a privacy scan. Do not add disposable examples to
`experiments/`: publication processes every top-level JSON there.

The CLI validates every subject/unit request against the shared JSON schema. It
does not prove that runtime aliases exist, that a retained image is available, or
that every core model/adapter semantic constraint is satisfied.

## Semantic and identity checks

For local cross-field validation, use `validate_definition`, `effective_settings`
and `Contracts.request` to construct every pair, then pass each request to the
core's `ExecuteRequest.model_validate`. The core model checks consumer/strategy
consistency, evaluator requirements and referenced evaluator IDs in addition to
the JSON schema. Import contracts only; do not construct a runtime or load models.

For the publication directory, check uniqueness of both `(stableId, revision)`
and `(stableId, generation)` across files. The CLI validates files independently;
`bench/ci.py` adds those cross-file checks before image resolution. Do not run
the publisher as an offline validator: it can contact registries and pull images.
It cannot build or publish them. Use the separate `Publish Core` Action and
`deploy-enhancement-core` skill for an explicitly requested new core release.

Inspect `EnhancementEngine.validate` for script restrictions, supported metric
keys, objective kinds and provider-specific validation. Model validation alone
does not call this method. If all units are scripts and all evaluators are
deterministic, the real `DeterministicEvaluation` provider can be used with
`EnhancementEngine.validate` locally without running inference. Register only
the known deterministic binding. A synthetic local execution is optional and
must be explicitly described as local deterministic evidence.

For consumer/model experiments, validate structure and review the selected
adapter's restrictions; report runtime binding/image compatibility as unverified
until there is appropriate evidence. Do not use permissive fake providers to
declare a real configuration supported. Validation against the checkout also
does not prove compatibility with a different retained core version.

Check immutable history through the available approved metadata or tracked
definitions. If prior revisions are missing locally, mark identity availability
unconfirmed instead of opening the production database or assuming a fresh ID.
Use a new revision for intentional changes; do not edit an imported identity to
clear a publication conflict.

## Review evidence

For a definition-only change, validated pairs, a reviewed comparison matrix,
semantic/identity checks and the privacy scan are the primary local evidence.
Use existing tests when modifying underlying behavior, particularly
`tests/bench/test_experiment_publication.py`, `test_unit_bindings.py` and
`test_store.py`. Preserve unknowns and do not weaken tests or assertions merely
to pass. Before a commit, follow the repository's staged-diff and public/noreply
identity checks.

Report validation in separate terms:

- Definition validity: JSON schema, semantic constraints and identity checks.
- Experimental design: cases, variables, controls, meaningful assertions and
  limitations such as small samples or categorical observations.
- Runtime readiness: selected core artifact, configured aliases and adapter
  capabilities; unknown unless independently verified.
- Publication: confirmed import acknowledgement, only after authorized delivery.
- Execution and assertions: independent terminal outcomes from Bench, only after
  an authorized run. The publication Action does not wait for these outcomes.

No credentials, production prompts, result payloads or screenshots belong in
validation reports or repository evidence.
