# Bench API deployment from main

`Deploy Bench to Coolify` builds the Bench API and client from the exact merged
`main` commit. Relevant pushes deploy automatically; manual dispatch can repeat a
main deployment. It never layers patches onto a running image. Experiment JSON
publication remains in the separate `Publish Experiments` workflow.

The Action checks gateway access and the selected Coolify container, runs focused
Bench tests and privacy scanning, builds once with a Docker layer cache, exercises
the packaged API with an empty synthetic database, and pushes that tested image
to `ghcr.io/<repository>/bench`. The deployment pins its digest through Coolify
v4.3.23's service-application API and starts only `bench-api` with `--no-deps`.
Two readiness responses must report the baked source commit before success.
It does not wait for the broad desktop quality workflow.

## Configuration

| Setting | GitHub location | Purpose |
| --- | --- | --- |
| `BENCH_COOLIFY_URL` | Repository variable | HTTPS controller origin |
| `BENCH_COOLIFY_SERVICE_UUID` | Repository variable | Existing Bench Compose service |
| `BENCH_COOLIFY_API_UUID` | Repository variable | Its `bench-api` application |
| `COOLIFY_TOKEN` | `production` environment secret | Existing scoped management access |
| `COOLIFY_ACCESS_CLIENT_ID`, `COOLIFY_ACCESS_CLIENT_SECRET` | `production` environment secrets | Controller gateway access |
| `BENCH_DELIVERY_URL` | `bench-publication` environment variable | Bench HTTPS origin |
| `BENCH_CF_ACCESS_CLIENT_ID`, `BENCH_CF_ACCESS_CLIENT_SECRET` | `bench-publication` environment secrets | Bench gateway access, including `/health/ready` |

The job token publishes to GHCR. The deployment host must be able to pull the
package, either using its existing private-registry authentication or an
owner-approved public package. The workflow does not change package visibility,
save a job token on the host, or expose credentials in output. Configure pull
access before the first deployment. Redirects are rejected and controller
credentials are never sent to Bench. Bench has no application token/login.

## Scope and failure recovery

This workflow deploys the API/UI container. The worker, relay, static consumer,
core image versions, model bindings and durable volumes have separate lifecycles.
Backend changes reconciled in this integration are retained in source; a future
worker/consumer release must still use the corresponding deployment recipe.
In particular, replacing the worker also requires replacing its relay.

A queued Coolify operation is not success. If the exact revision is not healthy
within five minutes the Action fails. Inspect the selected container privately;
correct registry or gateway configuration, then rerun the Action. No automatic
rollback or volume deletion occurs. To roll back code, revert the change through
the normal PR flow and deploy the resulting main commit. A manual dispatch from
another branch cannot deploy.

Configuration and focused checks are bounded separately from the cached image
build. GitHub queue time and first-time base pulls can still vary. The Action
does not rebuild model weights, the consumer, or the main desktop application.
