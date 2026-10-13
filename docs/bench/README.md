# Experiment bench

Standalone private benchmark storage and UI for `enhancement.v1`. Only explicitly
authored synthetic subjects are supported in this MWE. Definitions and responses
are sensitive even when their inputs are fictional; keep the service private.

For the combined candidate, fixes, test evidence and a working loopback demo,
see the [integration review](integration-review.md).

## Local development

The combined source checkout must contain B's authoritative
`contracts/enhancement/` and `src/prompt_enhancer/enhancement/`. During parallel
development set `BENCH_CONTRACTS` to the exact shared-contract directory; the bench
does not maintain copied or alternate execution schemas.

```sh
uv sync --project bench --frozen --extra dev
bench/.venv/bin/python -m pytest -q tests/bench
bench/.venv/bin/python -m enhancement_bench.cli validate bench/definitions/*.json
cd bench
npm ci --ignore-scripts
npx playwright install chromium
npm run test:browser
```

Set `BENCH_DATABASE`, distinct `BENCH_OPERATOR_TOKEN`/`BENCH_IMPORT_TOKEN`, and
`BENCH_IMAGE_REPOSITORIES` through the process environment, outside Git. The API
defaults to `127.0.0.1:8088` and expects `BENCH_ORIGIN` to match the browser origin.
The token entered in the UI stays in tab memory. Access logs are disabled.

`enhancement-bench serve` starts the API. `enhancement-bench worker` is a separate
process with an exclusive file lock. Production runs the worker in its named
container so ephemeral cores can share its network namespace. Do not start two
workers against the same SQLite database or duplicate the static worker namespace.

## Definitions and delivery

`bench/definitions/example-widget.json` is a reserved fictional example with a
packaged script and a consumer-backed rewrite. Its evaluator profile is identical
for both siblings. Parameter overrides are shallow property replacement; provide
the whole `generation` object when changing its settings. Null temperature and
token limits mean provider-managed/unknown; they are not replaced with numbers.
The ACP adapter rejects settings that its pinned worker cannot enforce.

Each consumer unit may set `consumerBinding` to select a different configured
model alias. Fields are inherited from the experiment's `consumerBinding`, so
`{"binding_id":"example-comparison-model"}` keeps the experiment's provider.
Aliases resolve to operator-configured models with recorded revision/license
provenance; definitions cannot supply endpoints or credentials. The shared
evaluator profile remains fixed across siblings and across each before/after pass.
UI/API `unitConsumerBindings` overrides take precedence and are frozen per unit
with the effective settings. Rerun retains those bindings. Script units reject
consumer-binding overrides. Older v1 definitions and queued snapshots remain
readable, and omitted unit bindings preserve existing publication identities.

The definition's versioned `objective` and `baseSteering` are inherited by each
unit; a unit can replace individual fields with `objective` and `steering`.
UI/API overrides apply after these defaults. The UI exposes an objective editor
and per-strategy steering; the API also accepts `unitObjectives`. Targets guide
generation and remain separate from assertions. Every run freezes the merged
objective and steering for each unit. Rerun copies those effective settings.
The measured baseline, evaluator profile and generation context/prompt versions
are retained with the core result; the core sends these measurements to the
consumer before requesting a candidate.

Publication schema `bench-publication/v1` contains `definition`, `image`, and
`coreVersion`. `image` must be an allowlisted repository followed by an immutable
SHA-256 digest. There is no runtime Git SHA lookup. The definition's `revision`
is an immutable string identity, while integer `generation` determines ordering.
Duplicate delivery is a no-op. A conflicting payload for an existing revision or
generation is rejected atomically. A disabled revision is not eligible for auto-run.

`POST /api/publications` accepts only the CI import token. The operator token owns
`GET /api/experiments`, `GET /api/runs`, `GET /api/runs/{id}`, `POST /api/runs`,
`POST /api/runs/{id}/cancel`, and `POST /api/runs/{id}/reconcile`. UI run creation
includes `stableId`, `revision`, a UUID `requestId`, explicit `overrides`, and an
optional `retryOf`. Reusing a request ID with changed settings fails with 409.

Effective parameters, objectives, steering, selected subjects/units, provider bindings, evaluator
profile, definition revision, image digest and identity fields are durable before
execution. The result UI shows original/enhanced prompts, before/after metrics,
comparable deltas, assertions, errors, stage progress and complete provenance.
It distinguishes unknown metric values from zero and assertion failure from
execution failure. Manual reruns do not require a Git commit.

## Recovery and retention

Restart converts active runs to interrupted; it never resumes agent turns.
Queued runs remain queued. An owned container is removed and its absence checked
before admission resumes. An unconfirmed remote consumer turn requires explicit
operator reconciliation with a short evidence reference and confirmation that
the remote operation stopped. The UI then permits a fresh retry. This records an
operator attestation, not an automatically verified model success.

The bench retains complete results in its private volume until the operator
performs a reviewed retention operation. There is no automatic deletion of Bench
results or public export endpoint. Dedicated OpenHands conversation history has
a separate configurable seven-day default; successful runtime cleanup no longer
deletes it immediately. Uncertain conversations remain held for reconciliation.
See the [deployment policy](deployment.md#operator-configuration).
Back up SQLite with its backup API while the worker is
stopped, and verify the backup in a separate private location. Preserve WAL files
when moving a live database; copying just the main file is not a valid backup.
Never include database contents, prompts, response logs or worker homes in issues
or build contexts. There is no provider-session ingestion in this application.

## CI and deployment

`bench-check.yml` validates tests, privacy, the UI, Compose and local image smoke
without publishing. `bench-publish.yml` is manually dispatched and binds to an
owner-configured `bench-publication` environment. Environment review requirements
must actually be configured; naming the environment does not enforce them.

The publication job reads B's code-owned `CORE_VERSION`, verifies definitions,
reuses a matching version image when its build-input hash matches, or builds with
B's Docker recipe and publishes it. Changed code under an existing core version
fails instead of replacing the tag. Definitions are delivered only after the
immutable digest is known. Rerunning delivery is safe. The workflow uses the job's
registry token and a separate bench import secret; no personal token is committed.

The publication workflow's operator-selected `models` variant installs B's locked
optional runtimes and uses its own tag, build fingerprint and image label. The
worker's optional local-model profile mounts only a reviewed labelled Docker
volume at a fixed read-only cache path and validates CPU/memory/device settings.
These controls stay outside definitions and UI overrides. See the deployment
recipe for exact configuration and the remaining real-model/device acceptance.

See [deployment](deployment.md), [proposal](architecture-proposal.md), and
[evidence](evidence.md). A local image/provider-simulator smoke is distinct from
live model or static consumer qualification.
