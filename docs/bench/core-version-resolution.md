# Core version resolution at Run creation

Date: 2026-10-14. Implementation, including automatic release registration,
authorized by the owner; merge and deployment remain pending.

## Task card

- Task / atlas nodes: move core-image binding from Experiment publication to
  Run admission; bounded W02/W07/WP08 Bench behavior.
- Baseline: `develop` at `f7c380e`, branch `codex/bench-core-version-resolution`.
- Outcome: an Experiment requests `enhancerVersion`, and each new Run records
  the image currently registered for that version. Rebuilding the same version
  does not require a new Experiment revision. Historical evidence stays fixed.
- Scope: Bench publication/API/CLI/store/schema, API variant configuration,
  synthetic regression tests, architecture amendment and operational guidance.
- Checks: replacement images, reruns, duplicate and concurrent requests, unknown
  versions, atomic import rollback, immutable Run settings, legacy publication
  delivery, v1 database migration, variant separation and private error responses.
- Resource bound: offline synthetic tests and temporary databases; no deployment,
  registry publication, real model execution or production database access.
- Evidence: 237 Bench tests, three synthetic definition validations, privacy scan,
  default/model CPU/CUDA Compose validation and both skill validators pass.
  Hosted checks, owner merge and deployment remain open.

## Binding and compatibility

`bench-publication/v2` carries a definition whose `enhancerVersion` selects the
core. A verified `core-release/v1` receipt registers the current immutable image
for `(coreVersion, variant)` through `POST /api/core-images`. The registration
requires the existing Host/Origin/JSON protections and image repository allowlist.
It records version, variant, digest, source revision, build-input fingerprint and
runtime-verification receipt; it never queues an Experiment.

New automatic and UI Runs, including reruns, resolve that catalog inside their
admission transaction. Resolution uses `BENCH_CORE_VARIANT`, supplied equally to
the API and worker. A duplicate request is checked against its original image
before resolution, so a catalog change or missing entry does not invalidate its
acknowledgement. Changed settings with the same request ID still fail with 409.

Catalog replacements cannot mutate queued, active or historical Run snapshots.
Rebuilds with the same verified build-input fingerprint may register a new image
digest. Changed build inputs still require a new reviewed core version. The
Git revision is provenance and never forms the core version or image tag.

Missing catalog entries return `core_version_unavailable` at Run admission.
An automatic import rolls back without superseding existing queued work; a
definition with `autoRun: false` can be imported without an available version.
Registry and worker pull access remain operational prerequisites. A registration
receipt is not proof that an image will remain available indefinitely.

Schema 2 adds a separate core catalog. Upgrade seeds each version from its most
recent legacy definition, for the configured variant, without changing any
definition body/hash or Run image/hash/result/event. Legacy provenance remains
unknown. The old definition image column stays solely for compatibility; v2
stores an empty value there and new Run admission never reads it. Existing v1
publication envelopes can seed a missing binding but cannot replace a registered
release. Same-definition v1/v2 redelivery remains idempotent regardless of image.

## Rollout

Stop both API and worker, take the normal private database backup, and upgrade
them together: schema 1 binaries reject schema 2, and an old already-running
binary must not keep accepting image-bound publications during transition.
Confirm both services select the same variant. Upgrade the API before delivering
v2 publications or release registrations. Register a verified pullable image
before starting or retrying work that previously referenced a missing artifact.

The registration CLI is available for explicitly authorized operator use:

```sh
enhancement-bench register-core /tmp/example-core-release.json
```

It uses the same configured HTTPS Bench origin and gateway access as Experiment
delivery. Do not put credentials in command arguments. The receipt contains only
release metadata, not Experiment inputs, outputs or provider sessions. Manual
registration has been tested with a synthetic in-process API; no live delivery
has been performed for this change.

## Automatic registration step

The registration step in `bench-core-publish.yml` follows successful
runtime verification. It sends the verified release
receipt to the already configured `BENCH_DELIVERY_URL` at `/api/core-images`.
It does not import definitions or start Runs. Gateway credentials are scoped to
this delivery step and do not enter the image build or offline runtime probe.

```yaml
- name: Register the verified core for future Runs
  env:
    BENCH_DELIVERY_URL: ${{ vars.BENCH_DELIVERY_URL }}
    BENCH_CF_ACCESS_CLIENT_ID: ${{ secrets.BENCH_CF_ACCESS_CLIENT_ID }}
    BENCH_CF_ACCESS_CLIENT_SECRET: ${{ secrets.BENCH_CF_ACCESS_CLIENT_SECRET }}
  run: bench/.venv/bin/python -m enhancement_bench.cli register-core "$RUNNER_TEMP/core-release.json"
```

The workflow-order regression test checks that registration runs only after
successful verification and cannot ignore failure. Registration
failure fails the job without undoing or overwriting the published artifact;
an operator can retry registration of the same verified receipt. Keep separate
publication, registration, worker availability and Run outcome evidence.
