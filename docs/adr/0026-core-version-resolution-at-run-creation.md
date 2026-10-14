# ADR 0026: Resolve core versions when creating Runs

Status: proposed for owner review; implementation requested by the owner.
Date: 2026-10-14. Amends the image-binding proposal in ADR 0025.

## Context

Freezing an image in an Experiment publication prevents a rerun from selecting
a replacement artifact for the same core version. It requires an unrelated
definition revision even when the comparison and requested core version stay
the same. Artifact traceability belongs to each execution snapshot.

## Proposed decision

Experiments reference only `enhancerVersion`. Bench maintains a separate catalog
of verified release receipts keyed by core version and dependency variant.
Each new automatic or UI Run resolves the current catalog binding transactionally
and freezes its immutable image digest. Reruns resolve again; duplicate delivery
of the same request returns the existing Run. Catalog updates never rewrite
queued, running or historical Runs. Core versions remain independent of Git
revisions, which continue to record source provenance.

Publication v2 contains the definition only. A separate registration API/CLI
accepts verified release metadata under the existing gateway, same-origin and
repository-allowlist boundaries. Registration cannot queue Runs. Changed source
build inputs still require a new core version; rebuilding identical inputs may
produce and register a replacement digest for that version.

## Consequences and migration

The API needs no Docker socket or registry credentials. The worker still verifies
and pulls the frozen digest when starting a Run. Registration does not guarantee
future artifact retention, worker access or model readiness. A missing version
fails Run admission without partial automatic import or supersession.

Schema 2 preserves legacy definition rows and all Run evidence, seeds legacy
catalog entries with unknown release provenance, and supports v1 envelope
redelivery. API and worker upgrade together; old binaries reject schema 2.
See the [task and migration record](../bench/core-version-resolution.md) for
rollout ordering and the release-workflow registration step.

Affected nodes: W02, W07, WP08. This fixed Bench flow does not accept the general
workflow engine, model/GPU or release gates. The dated atlas observation remains
historical. Synthetic tests cover replacement, replay, concurrency, migration,
failure atomicity, variant separation and registration boundaries.
