---
name: deploy-enhancement-core
description: Prepare, publish, and verify a versioned Prompt Enhancer core image through the separate Publish Core GitHub Action. Use when a new core artifact is needed for experiments or the user requests a core release; experiment authoring and Bench API/UI deployment have separate workflows.
---

# Deploy Enhancement Core

Core deployment means releasing an immutable image that Bench can select for a
run. Bench starts ephemeral core containers per run; publishing an image does not
restart Bench, replace its worker or consumer, or start an experiment.

Resolve repository paths from the approved Prompt Enhancer checkout. Read
`AGENTS.md`, `docs/bench/core-publication.md`,
`.github/workflows/bench-core-publish.yml`, `bench/core_release.py`, and
`bench/src/enhancement_bench/core_images.py`. Follow the repository's development
skill and contribution flow when changing source.

## Establish the release

Resolve the intended core version, reviewed source commit, image repository and
dependency variant (`default` or `models`). Ask only for missing decisions; use
answers and task-specific authorization already given. If the request is only to
prepare a release, complete its source changes and validation before requesting
publication approval. Do not treat an experiment request as core-release authority.

Read `CORE_VERSION` in `src/prompt_enhancer/enhancement/__init__.py`. The requested
release must match the selected source's version. A new implementation requires
a reviewed version bump when its build inputs change. A rebuild with identical
verified build inputs may register a replacement digest for the same version.
Resolve a new version with the user rather than
silently changing an experiment's selected version. Historical artifacts remain
available through Bench's registered catalog; releasing one requires its reviewed
source and verified receipt.

The `models` variant includes optional runtime dependencies, not model weights.
It has a separate tag and build fingerprint. Worker variant, device, cache and
configured model bindings remain separate operator settings; this skill does
not change them or qualify actual model/GPU execution.

## Prepare and validate

Use a task branch from the selected `develop` baseline for source edits, preserving
unrelated changes. Run affected core tests, Bench publication tests, and the
privacy scanner. Review the staged diff and public/noreply identity before a
commit. Publish source and perform merges only within the user's authorization
and repository contribution rules.

`bench/core_release.py --check` verifies local release inputs without registry
access. Supply `--repository`, `--version`, `--source-revision` and `--variant`
using reviewed values and a compatible installed Bench Python environment.
The source revision must equal the checkout's full HEAD SHA. Never include
credentials in command arguments or read provider/configuration files to fill
missing values. The checked destination is an image repository without a tag.

The workflow releases reviewed `main` only. If the workflow or source changes
are not yet on that approved branch, prepare the PR/promotion first. Do not use
the old experiment publisher as a fallback core builder.

## Execute the separate Action when authorized

Verify the repository explicitly and pass it with `gh -R` on every call. Check
the available `Publish Core` workflow and selected main SHA before dispatch.
Use `bench-core-publish.yml`, `--ref main`, and the exact `core_version`,
reviewed full `source_revision`, `core_variant` and, when needed,
`image_repository` inputs. Pin publication intent
to the reviewed main source; if main moved, inspect the difference before proceeding.

The job uses the existing `bench-publication` environment for reviewed registry
settings and job-scoped package write access. Its final registration step uses
the configured Bench HTTPS origin and gateway secrets only for receipt delivery.
Upgrade Bench to support `/api/core-images` before running this workflow.
If registry or Bench access is unavailable, report the
specific missing prerequisite without enumerating secrets, granting new access,
or changing repository/environment policy.

Monitor the exact dispatched workflow run. The release reuses an identical
existing image or builds/publishes the code-owned version, then verifies the
immutable digest's runtime core/protocol identity in an isolated offline container.
The models variant also checks runtime dependency imports without loading weights.
Completion requires a successful workflow, immutable digest, verified probe
cleanup and confirmed catalog registration. Prefer metadata and the bounded summary; do not dump raw runner,
registry or production logs.

On an uncertain or failed run, inspect that run's state before retrying. The
image may already have been pushed before a runtime probe or registration failed. Never overwrite
its tag or assume failure means nothing was published. Correct source under a
new version when necessary; an identical successful artifact can be reused.

## Hand off the artifact

For `bench-experiment/v2`, a release receipt supplies the experiment's exact
`coreBuild` pin. Registering a replacement image preserves earlier artifact
receipts and does not rebind those experiments. Selecting that replacement
requires a new experiment revision. The version-catalog resolution described
below applies to legacy v1 definitions; see `docs/bench/versioned-workflows.md`.

Report core version, variant, immutable digest, validated source SHA, action
(built or reused) and exact verification scope. The summary's source SHA shows
which checkout's build inputs were validated; a reused image may have originally
been built at another commit with identical inputs. Do not claim it was rebuilt.

For legacy v1 definitions, Bench resolves the current registered image when
creating each Run, including reruns. V2 uses its exact artifact pin. Use the
verified release receipt with `enhancement-bench register-core`
when registration is authorized. It uses the configured Bench HTTPS origin and
gateway access, recording the artifact and current version/variant binding. Registration does
not start an Experiment or prove worker-host availability/model readiness.
The Action registers the verified receipt after successful runtime verification.
Confirm the registration acknowledgement separately from publication; if delivery
failed, retry registration of the same verified receipt rather than rebuilding
the image. Do not invent missing legacy provenance.

Return to `.agents/skills/prepare-bench-experiment/SKILL.md` when an experiment
needs the new version.
Changing `enhancerVersion` requires a new experiment revision/generation.
Selecting a replacement registered image also requires a new v2 revision; legacy
v1 new runs can resolve a changed catalog binding. Old runs retain their image
digests. Publish changed definitions through `Publish Experiments` only
when requested. Keep core release, experiment import, run execution and assertion
outcomes separate in the final report.
