# Separate core and Experiment publication

`Publish Core` releases a versioned immutable core image. `Publish Experiments`
imports definitions that select an already available core. `Deploy Bench to
Coolify` updates the API/UI. These are three separate workflows.

Bench starts an ephemeral core container for each run. A core release does not
replace the worker or consumer, deploy the API/UI, change model bindings or start
an Experiment. Definitions select a core version; each Run keeps its saved image
digest. See [Run-time version resolution](core-version-resolution.md).

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
permission. The final registration step uses the existing `BENCH_DELIVERY_URL`
and gateway secrets; those credentials are not supplied to build or probe steps. The
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

## One-time public GHCR setup

For a public source repository whose owner approves public images, configure
`BENCH_REGISTRY=ghcr.io` and an exact lowercase `BENCH_IMAGE_REPOSITORY`, such as
`ghcr.io/example/enhancement-core`, in the existing `bench-publication`
environment. The Action uses its existing job-scoped `GITHUB_TOKEN` for the push;
no personal registry token is needed. Keep the package associated with the source
repository and verify its public visibility during initial package setup.
Publication success alone does not prove anonymous pull access.

Add that exact repository to both the API and worker's
`BENCH_IMAGE_REPOSITORIES` allowlists. Preserve any previous repositories needed
by recorded Runs. Apply this configuration once through the deployment manager,
then verify an anonymous pull of the registered digest on the worker host.
Do not mount host Docker credentials or provider account files into the worker.

After setup, each release uses the existing `Publish Core` workflow dispatch
with the selected version, main revision and variant. The Action builds or reuses
the image, verifies its runtime identity and registers the digest. There is no
per-version Coolify image edit or worker/relay restart. Experiment publication
and Run execution remain separate; the workflow does not start a Run. Generated
core-version defaults alone no longer trigger a Bench API deployment.

A private registry requires separately provisioned, scoped worker pull access;
the public setup does not configure or infer such credentials.

## Use the released version

Register the verified release receipt through `enhancement-bench register-core`
using the existing configured Bench HTTPS origin and gateway access. This updates
Bench's version/variant catalog for future Runs, without importing definitions or
starting execution. The [automatic registration Action step](core-version-resolution.md#automatic-registration-step)
performs this delivery after successful release verification. Upgrade Bench to
support `/api/core-images` before running that workflow. A failed registration
fails the job even if the image has already been published; retrying registration
of the same verified receipt is idempotent.

The worker must be able to pull the digest from an allowlisted repository with
the matching variant. Registration does not prove worker-host access or configure
GPU/cache/model readiness. Legacy database/catalog entries retain unknown build
provenance rather than inventing a release receipt.

Set the Experiment's `enhancerVersion` to the selected version. Changing that
version or other definition settings requires a new revision and generation;
replacing the registered image for the same version does not. Publish definitions
through `Publish Experiments` separately. That job no longer accesses a registry
or requires package permissions. New Runs, including reruns, resolve the current
catalog entry and record its digest. An unavailable version fails Run admission;
`autoRun: false` definitions may be imported before registration.

## Release automation follow-up - 2026-10-14

- Baseline: reviewed `develop` at `dbd5bf1`; recovery branch
  `codex/core-release-recovery` preserves the staged automation follow-up.
- Proposed behavior: compatible core releases use the versioned registry publication and
  registration workflow without a Bench API deployment for version-only schema
  defaults or per-version worker/relay maintenance.
- Scope: deployment selection, synthetic Git-history regressions, content-free
  HTTP status diagnostics for delivery failures, operator guidance, and
  owner-selected registry/allowlist configuration outside Git.
- Evidence: 256 Bench tests, privacy scanning and architecture consistency pass,
  including synthetic Git histories and delivery privacy boundaries. The
  owner-authorized public package setup and anonymous worker pull of the verified
  artifact are confirmed separately. Automated registration and a rerun remain
  operational verification steps until their receipts are confirmed. Source
  review, hosted CI and promotion remain separate from that operational evidence.
- Boundary: no new core implementation, Experiment revision, model binding,
  database migration or broader workflow acceptance is implied by this follow-up.

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

## Agent instructions and merge validation - 2026-10-14

Root `AGENTS.md` and `CLAUDE.md` now require the development skill, the Bench
guide for relevant work, and the applicable experiment/core skill. All three
skills are tracked in `.agents/skills/`; personal installation is unnecessary.
Three skill validators, 19 instruction references/imports and nine focused
privacy tests pass. Existing privacy and contribution requirements are preserved.

Pre-merge CI exposed two existing compatibility defects. The relay smoke still
identified the old Agent Server process after startup moved to the retention
wrapper. It now checks the exact current process arguments and retains the
unrelated-environment canary assertion. The failure reproduced locally; the
complete relay smoke then passed with newly built isolated Bench/consumer images,
including authentication, TLS streaming, network isolation and restart checks.
No model or provider account was used and no image was published.

Six explicit HTTP 422 responses also inherited Python-version-dependent status
descriptions. Their descriptions now match the committed OpenAPI artifact on
both Python status tables. All nine OpenAPI export tests pass, including exact
artifact checks under both descriptions. Response schemas, status codes and
runtime behavior are unchanged. These checks do not substitute for the final
hosted CI result or broader release acceptance.
