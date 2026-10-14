# Test Bench

Standalone private benchmark storage and UI for `enhancement.v1`. Only explicitly
authored synthetic subjects are supported in this MWE. Definitions and responses
are sensitive even when their inputs are fictional; keep the service private.

For the combined candidate, fixes, test evidence and a working loopback demo,
see the [integration review](integration-review.md).

The [client navigation](client-navigation.md) separates experiment browsing,
experiment details, run setup and results. Open an experiment and choose **New
run**, or choose **Rerun with changes** on a result. Edit parameters, objectives,
steering and model aliases using form controls; saved results remain read-only.

## Domain language

Client labels follow the experiment definition and execution contracts:

| Term | Meaning |
| --- | --- |
| Experiment | Definition with a stable identity, subjects and units. |
| Revision | An immutable version of an experiment definition. |
| Run | Execution of a revision with its effective settings and overrides saved. |
| Unit | A strategy with parameters, objective, steering, assertions and any consumer binding. |
| Subject | An input prompt and any explicitly supplied context. |
| Attempt | Execution of one unit for one subject within a run. |
| Result | The enhanced prompt, evaluations, deltas, assertions, timings and provenance from an attempt. |
| Enhancer | The engine that evaluates, generates and reevaluates a prompt. |
| Consumer | The generation role used by consumer-backed strategies. |
| Evaluator profile | The evaluators and settings shared by units for before/after comparisons. |

A strategy is a property of a unit. A prompt is part of a subject. Use **Units**,
**Subjects** and **Results** for those entities in navigation, headings and forms;
use **Strategy**, **Original prompt** and **Enhanced prompt** for their properties.

## Local development

The combined source checkout must contain B's authoritative
`contracts/enhancement/` and `src/prompt_enhancer/enhancement/`. During parallel
development set `BENCH_CONTRACTS` to the exact shared-contract directory; the bench
does not maintain copied or alternate execution schemas.

```sh
uv sync --project bench --frozen --extra dev
bench/.venv/bin/python -m pytest -q tests/bench
bench/.venv/bin/python -m enhancement_bench.cli validate experiments/*.json bench/examples/*.json
cd bench
npm ci --ignore-scripts
npx playwright install chromium
npm run test:browser
```

Set `BENCH_DATABASE` and `BENCH_IMAGE_REPOSITORIES` through the process environment,
outside Git. The API
defaults to `127.0.0.1:8088` and expects `BENCH_ORIGIN` to match the browser origin.
Cloudflare Access handles deployed authentication; Bench opens without a separate
login. Keep the origin private behind that gateway. Access logs are disabled.

`enhancement-bench serve` starts the API. `enhancement-bench worker` is a separate
process with an exclusive file lock. Production runs the worker in its named
container so ephemeral cores can share its network namespace. Do not start two
workers against the same SQLite database or duplicate the static worker namespace.

## Domain language

- An **Experiment** is a versioned definition with defaults and sibling Experiment Units.
- An **Experiment Unit** is one configuration being compared. Strategy is a setting on it.
- A **Subject** is an input prompt shared by the selected Experiment Units.
- A **Run** executes an Experiment revision with immutable effective settings.
  UI Runs may override the defaults without editing the Experiment.
- **Prompt Enhancer core** evaluates, enhances, reevaluates and compares.
- A **Consumer** supplies enhancement inference; OpenHands or Codex owns its runtime.
- An **Evaluator** measures the before/after prompts independently of the Consumer.
- **Test Bench** imports Experiments, schedules Runs, starts core containers and
  stores/presents results. There is no separate testing harness.

## Experiments and delivery

Author a new JSON file directly in `experiments/` and push it to the configured
publication branch. The `Publish Experiments` GitHub Action validates the files,
resolves each Experiment's `enhancerVersion` to an immutable core image, and
delivers it to Test Bench. `autoRun: true` queues a Run automatically on import;
its status and results appear in the UI. No manual import or UI Run is needed.

Keep `stableId` for later revisions and change both `revision` and `generation`.
An existing revision is immutable. The publisher imports newest generations
first, and repeated delivery does not create another Run. Older revisions may
remain in the folder, with their own core versions. Disabling `autoRun` leaves
an Experiment available for UI Runs. Deleting a file does not delete its stored
Runs or imported revision.

`bench/examples/example-widget.json` is a reserved fictional example with a
packaged script and a consumer-backed rewrite. Its evaluator profile is identical
for both sibling Experiment Units. This development fixture is outside the
publication folder. Parameter overrides are shallow property replacement; provide
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
and per-unit steering; the API also accepts `unitObjectives`. Targets guide
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

The gateway protects `POST /api/publications`,
`GET /api/experiments`, `GET /api/runs`, `GET /api/runs/{id}`, `POST /api/runs`,
`POST /api/runs/{id}/cancel`, and `POST /api/runs/{id}/reconcile`. UI run creation
includes `stableId`, `revision`, a UUID `requestId`, explicit `overrides`, and an
optional `retryOf`. Reusing a request ID with changed settings fails with 409.
All mutations require the configured `Origin` and an `application/json` body.

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

`bench-check.yml` validates tests, privacy, the UI, Compose and local image smoke.
`bench-publish.yml` runs on JSON changes in `experiments/` on
`BENCH_PUBLICATION_BRANCH` (the repository default branch when unset). Explicit
manual dispatch remains available for recovery. All publication jobs share one
serial concurrency group and bind to the `bench-publication` environment.
Configure that environment's allowed branches and any required review in GitHub;
its name alone enforces neither.

The one-time operator configuration is:

| Setting | Location | Purpose |
| --- | --- | --- |
| `BENCH_PUBLICATION_BRANCH` | Repository variable | Branch permitted to publish automatically |
| `BENCH_DELIVERY_URL` | Environment variable | HTTPS Test Bench origin, without an API path |
| `BENCH_CF_ACCESS_CLIENT_ID`, `BENCH_CF_ACCESS_CLIENT_SECRET` | Environment secrets, when needed | Existing machine access through the access gateway |
| `BENCH_CORE_IMAGES` | Environment variable | Optional reviewed catalog of retained immutable core artifacts |
| `BENCH_IMAGE_REPOSITORY`, `BENCH_REGISTRY` | Environment variables, when needed | Registry for versions outside the retained catalog |
| `BENCH_CORE_VARIANT` | Environment variable, optional | `default` or `models`; defaults to `default` |

The retained artifact catalog is JSON keyed by core version, for example:

```json
{
  "0.1.4": {
    "image": "registry.example.com/example/enhancer@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "variant": "default"
  }
}
```

Register an artifact only after verifying its runtime core version, build variant
and availability to the Test Bench worker. The digest identifies the exact bytes.
`buildInputSha256` may be recorded when the complete build-input fingerprint is
known; do not invent it from a stale image label. Reusing the checkout's current
core version requires that fingerprint to match the current source. Other
retained versions do not claim source equivalence to this checkout.

For versions outside the catalog, the Experiment publisher resolves an existing
verified registry image. It has read-only package access and cannot build or
publish a core image. A missing version reports `core_release_required`; use the
separate manual [Publish Core workflow](core-publication.md) to release the
selected source version first. A definition-only change can reuse an existing
core. Changed source under an existing version fails instead of replacing the
tag. All Experiments validate and all images
resolve before delivery begins. Delivery sends the required Origin and optional gateway
credentials, refuses redirects, and emits only a content-free acknowledgement.
Bench has no application login or import token. Registry access uses the job
token; no personal credential is committed.

The core-release workflow's operator-selected `models` variant installs B's
locked optional runtimes and uses its own tag, build fingerprint and image label.
Select the matching variant when publishing Experiments. The
worker's optional local-model profile mounts only a reviewed labelled Docker
volume at a fixed read-only cache path and validates CPU/memory/device settings.
These controls stay outside definitions and UI overrides. See the deployment
recipe for exact configuration and the remaining real-model/device acceptance.

See [deployment](deployment.md), [proposal](architecture-proposal.md), and
[evidence](evidence.md). A local image/provider-simulator smoke is distinct from
live model or static consumer qualification.
