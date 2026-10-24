# Bench API deployment from main

`Deploy Bench to Coolify` builds the Bench API and client from the exact merged
`main` commit. Relevant pushes deploy automatically; manual dispatch can repeat a
main deployment. Experiment JSON publication remains in the separate
`Publish Experiments` workflow.

The Action checks the selected Coolify container through its existing controller access, then runs
focused Bench tests, privacy scanning and JavaScript syntax validation. Coolify
builds the image once from a commit-pinned Git context using its host Docker layer
cache. There is no image registry, package publication or registry credential.
Coolify v4.3.23's service-application API replaces only `bench-api` with
`compose up --no-deps --build`. The deployment job checks the exact image and
container health. A dependent job then makes two fresh authenticated requests to
Bench and verifies its baked source revision. Both jobs must succeed. The Action
does not wait for the broad desktop quality workflow.

## Configuration

| Setting | GitHub location | Purpose |
| --- | --- | --- |
| `BENCH_COOLIFY_URL` | Repository variable | HTTPS controller origin |
| `BENCH_COOLIFY_SERVICE_UUID` | Repository variable | Existing Bench Compose service |
| `BENCH_COOLIFY_API_UUID` | Repository variable | Its `bench-api` application |
| `COOLIFY_TOKEN` | `production` environment secret | Existing scoped management access |
| `COOLIFY_ACCESS_CLIENT_ID`, `COOLIFY_ACCESS_CLIENT_SECRET` | `production` environment secrets | Controller gateway access |
| `BENCH_DELIVERY_URL` | Existing `bench-publication` variable | Protected Bench HTTPS origin |
| `BENCH_CF_ACCESS_CLIENT_ID`, `BENCH_CF_ACCESS_CLIENT_SECRET` | Existing `bench-publication` environment secrets | Bench gateway access for read-only readiness checks |

One-time setup: add this build configuration to the existing `bench-api` Compose
entry, substituting the public repository and initial full commit SHA. Preserve
its existing runtime configuration, domains, storage and all other services.

```yaml
services:
  bench-api:
    image: local/enhancement-bench:api-<full-commit-sha>
    pull_policy: never
    build:
      context: https://github.com/example/bench.git#${BENCH_SOURCE_REVISION}
      dockerfile: deployment/bench/Dockerfile
      args:
        BENCH_REVISION: ${BENCH_SOURCE_REVISION}
```

Create the nonsecret service variable `BENCH_SOURCE_REVISION` with that SHA.
The Action updates this one existing variable, pins a matching local image tag,
reads the image setting back, and requests `start?force=true`. A missing variable
fails deployment instead of guessing a source configuration. The build context
and revision argument must reference the same variable. The host must be able to
fetch the public repository and the pinned base images and dependencies.

## Readiness through separate credential boundaries

The `production` job uses controller credentials only. It requires two consecutive
observations of the selected API image with `running:healthy` status. It reads
resource metadata without requesting container logs or sensitive-read privileges.

The dependent `bench-publication` job uses the same protected Bench origin and
gateway credentials as the existing publication workflows. Controller credentials
are absent from this job. It performs only `GET /health/ready`, requiring two
consecutive JSON responses with `ready: true`, schema `bench.v1` and the exact
expected source revision. Each request has a unique query value and requests
cache revalidation; responses must declare `no-store` and have no positive cache
age. The response size is bounded to 4096 bytes. Response bodies and credentials
are never printed or saved as artifacts.

Both checks have a five-minute observation limit. An unhealthy observation resets
the consecutive count. Redirects and authorization failures fail immediately;
TLS verification and the existing gateway policy remain required. A verifier-only
retry observes the existing deployment without starting another build.

This proves image health and the serving revision through the authenticated Bench
HTTP path. It does not qualify the worker, a model, or a browser interaction. The
existing local readiness log receipt remains available for bounded operator
diagnostics but is not an Action dependency.

## Scope and failure recovery

This workflow deploys the API/UI container. The worker, relay, static consumer,
core image versions, model bindings and durable volumes have separate lifecycles.
Backend changes reconciled in the integration are retained in source; a future
worker/consumer release must still use the corresponding deployment recipe.
Replacing the worker also requires replacing its relay.

A queued build is not success. If either bounded health check fails, the Action
fails even if the container already started. Inspect the selected container privately; correct source
or container health configuration, then rerun the Action. No automatic rollback or volume
deletion occurs. To roll back code, revert through the normal PR flow and deploy
the resulting main commit. A manual dispatch from another branch cannot deploy.

GitHub queue time, source fetching and first-time base pulls can vary. Dependency
layers stay cached between builds; UI edits do not reinstall unchanged packages.
The Action does not rebuild model weights, the consumer or the desktop application.
For local packaging checks, `scripts/smoke_bench_image.py` still exercises a built
image with an empty synthetic database; it is not a redundant deployment build.

## Readiness verification correction - 2026-10-24

- Task / atlas scope: bounded deployment verification, R26 and W02/W07.
- Baseline: reviewed develop `68761fc`; the core 0.3.3 promotion is a separate PR.
- Reproduction: controller log access can return HTTP 403 after a deployment
  starts successfully. A valid deployment token need not permit sensitive logs.
- Change: retain image-health checks and verify the serving revision through the
  existing protected Bench readiness API with credentials scoped to its job.
- Evidence: 123 affected deployment tests pass across the main and focused
  loopback runs. They cover wrong revisions, malformed/oversized/cached responses,
  consecutive health, access denial, redirect isolation and workflow dependencies.
- Boundaries: no model run, token change or permission expansion. Source review,
  promotion and hosted verification of the revised workflow remain open; general
  release and real-model acceptance statuses are unchanged.
