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
`compose up --no-deps --build`. Two fresh local readiness receipts must report
the source commit baked into the image while Coolify reports the API healthy. The Action does not wait for the
broad desktop quality workflow.

## Configuration

| Setting | GitHub location | Purpose |
| --- | --- | --- |
| `BENCH_COOLIFY_URL` | Repository variable | HTTPS controller origin |
| `BENCH_COOLIFY_SERVICE_UUID` | Repository variable | Existing Bench Compose service |
| `BENCH_COOLIFY_API_UUID` | Repository variable | Its `bench-api` application |
| `COOLIFY_TOKEN` | `production` environment secret | Existing scoped management access |
| `COOLIFY_ACCESS_CLIENT_ID`, `COOLIFY_ACCESS_CLIENT_SECRET` | `production` environment secrets | Controller gateway access |

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

## Readiness through the controller

The public gateway policy is unchanged. Deployment makes no request to the public
Bench origin and does not use the Experiment publication gateway credentials.
The existing container healthcheck requests `/health/ready` over loopback. After
a successful local request, the API emits only `BENCH_READY_V1`, its baked source
commit and a millisecond timestamp. Remote requests, rejected requests and builds
without a full commit SHA cannot produce a receipt. No request data is logged.

The Action checks the exact API application's image setting and `running:healthy`
status, then requests at most 20 log lines through Coolify's existing authenticated
service-application API. It accepts only complete, strictly formatted receipts
for the expected source revision, created after deployment began and within 90
seconds of the current time (with five seconds of forward clock tolerance).
Two distinct receipts across healthy observations are required; replaying one
line cannot pass. An unhealthy observation resets the consecutive-check count.
Controller and host clocks must be synchronized. Raw log bodies are never printed
or saved as artifacts. Controller redirects and authorization failures fail early.

This proves the local API responds from the expected image. It does not claim to
test the public gateway/browser path. No authentication policy, public exposure,
credential, application token or host terminal access is added.

## Scope and failure recovery

This workflow deploys the API/UI container. The worker, relay, static consumer,
core image versions, model bindings and durable volumes have separate lifecycles.
Backend changes reconciled in the integration are retained in source; a future
worker/consumer release must still use the corresponding deployment recipe.
Replacing the worker also requires replacing its relay.

A queued build is not success. If the exact revision is not healthy within five
minutes the Action fails. Inspect the selected container privately; correct source
or container health configuration, then rerun the Action. No automatic rollback or volume
deletion occurs. To roll back code, revert through the normal PR flow and deploy
the resulting main commit. A manual dispatch from another branch cannot deploy.

GitHub queue time, source fetching and first-time base pulls can vary. Dependency
layers stay cached between builds; UI edits do not reinstall unchanged packages.
The Action does not rebuild model weights, the consumer or the desktop application.
For local packaging checks, `scripts/smoke_bench_image.py` still exercises a built
image with an empty synthetic database; it is not a redundant deployment build.
