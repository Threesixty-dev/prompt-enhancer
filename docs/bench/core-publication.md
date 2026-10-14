# Separate core and Experiment publication

`Publish Core` releases a versioned immutable core image. `Publish Experiments`
imports definitions that select an already available core. `Deploy Bench to
Coolify` updates the API/UI. These are three separate workflows.

Bench starts an ephemeral core container for each run. A core release does not
replace the worker or consumer, deploy the API/UI, change model bindings or start
an Experiment. Existing definitions keep their saved image digests.

## Choose whether a core release is needed

When preparing an Experiment, establish whether to reuse an existing core or
prepare a new version separately. Ask for that choice if the request does not
already settle it. New cases, variants and supported parameter changes can reuse
the existing version. New core behavior requires the appropriate source change
and reviewed version bump. Do not silently change an Experiment's requested core
to get publication to pass.

The repository provides the [Experiment authoring skill](../../.agents/skills/prepare-bench-experiment/SKILL.md)
and the separate [core release skill](../../.agents/skills/deploy-enhancement-core/SKILL.md).
Root `AGENTS.md` and `CLAUDE.md` require the relevant skills and Bench instructions
for Codex and Claude Code. Both skills use the repository's authoritative
contracts and current workflows. Creating a definition or preparing a release
does not itself authorize image publication or a model run.

## Publish Core

The manual-only `.github/workflows/bench-core-publish.yml` runs on reviewed
`main`. It requires:

| Input | Meaning |
| --- | --- |
| `core_version` | Exact `CORE_VERSION` in the selected main source. |
| `source_revision` | Full reviewed main commit SHA; a moved checkout fails before registry access. |
| `core_variant` | `default` or `models`; defaults to `default`. |
| `image_repository` | Optional reviewed destination without a tag; otherwise `BENCH_IMAGE_REPOSITORY`. |

The job reuses the existing `bench-publication` environment's approved registry
settings (`BENCH_REGISTRY`, `BENCH_IMAGE_REPOSITORY`) and job-scoped package write
permission. It does not reference Bench delivery or gateway secrets. The
environment name does not itself enforce review; existing GitHub environment and
repository protections remain authoritative. No settings or permissions are
automatically configured by adding the workflow.

`bench/core_release.py --check` verifies repository syntax, dependency variant,
the requested version and the full checked-out source SHA before registry access.
After focused synthetic tests and privacy scanning, `--allow-publish` releases
only that code-owned version. An identical existing image can be reused; changed
source under an existing version is rejected. Historical versions cannot be
rebuilt from current source through this command.

The resulting immutable digest is checked in an owned, offline, read-only
container with bounded CPU, memory, process count and execution time. The probe
compares the actual imported core/protocol versions; for `models`, it also
imports the optional runtime dependencies without loading weights. Cleanup must
be confirmed. No host volumes, model bindings or credentials enter the probe.

The Action summary records the version, variant, digest, build-input fingerprint,
validated source revision and whether the image was built or reused. The JSON
receipt lives in runner-temporary storage. On reuse, the validated revision proves
matching build inputs; it does not claim that the image was built at that commit.

A failed or interrupted probe can occur after the image was pushed. Do not
overwrite the version or infer that the registry is unchanged. Inspect the exact
run and immutable artifact, then retry identical source or prepare a new version
when a source correction is needed. Network/authentication errors are never
treated as evidence that a tag is absent.

## Use the released version

Registry resolution needs the configured repository and matching variant, and
the worker must be able to pull the digest from an allowlisted repository. A
retained local artifact instead uses a separately reviewed `BENCH_CORE_IMAGES`
entry. Core publication does not edit this catalog, prove worker-host access or
configure GPU/cache/model readiness.

Set the Experiment's `enhancerVersion` to the selected released version. Changing
an imported definition or its image requires a new revision and generation.
Publish the definition through `Publish Experiments` separately. Its job has
package read access only, and `bench/ci.py` no longer accepts `--allow-publish`.
All selected definitions/images resolve before any envelope delivery; a missing
core fails with an instruction to use `Publish Core` first. An eligible imported
definition with `autoRun: true` can then queue a run independently.

## Bounded task evidence - 2026-10-14

- Task / atlas scope: separate optional core release from Experiment delivery;
  bounded W02/W07/WP08 publication tooling, without changing accepted architecture.
- Baseline: owner-selected `develop` at `01a4d21` on `codex/separate-core-release`.
- Scope: separate workflow/CLI, shared image helpers, resolve-only Experiment
  publication, synthetic tests, operator docs and two personal skills.
- Local evidence: 201 Bench tests pass, including missing-image refusal before
  envelopes, removal of the old publishing flag, immutable-version checks,
  source/version mismatch rejection, offline probe bounds, cleanup on failure,
  content-free failure, and workflow trigger/permission separation. The real CLI
  check mode passes against the selected checkout without registry access. Both
  skills pass structure validation; privacy/whitespace checks pass.
- Completion boundary: no new core was built, pushed or run locally, and no
  Experiment was delivered. Workflow publication/owner merge, registry access,
  actual container probe and worker availability need separate hosted evidence.
  General workflow, model, GPU and release acceptance gates remain unchanged.
