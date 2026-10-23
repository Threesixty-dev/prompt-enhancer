# Test Bench

Standalone private benchmark storage and UI for `enhancement.v1`. Only explicitly
authored synthetic subjects are supported in this MWE. Definitions and responses
are sensitive even when their inputs are fictional; keep the service private.

Start with the [handoff guide](handoff.md) for the UI journey, result-state
dictionary, AI client contract and remaining qualification gates. It distinguishes
tested local changes from deployed capability.

The [client and export guide](client.md) documents the candidate JSON CLI,
durable submission receipts, read-only preflight and private analysis tables.

The [robustness qualification suite](robustness-experiment.md) defines 240 planned
case/variant attempts, an initial smoke selection, expected missing-data states,
offline fault coverage, and explicit runtime acceptance gates for core 0.3.2.

The [NLI input admission candidate](nli-input-admission.md) records the core 0.3.3
paired-token guard, explicit unavailable readings and offline tokenizer packaging.
Source tests and packaging evidence remain separate from live qualification.

New `bench-experiment/v2` definitions follow the
[versioned workflow contract](versioned-workflows.md): one workflow version, exact
core build and harness evaluation per revision. Variants can change supported
step bindings, policies and parameters. The legacy v1 behavior documented below
remains available for existing definitions.

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
| Unit | A comparison variant. In v2 it uses the revision's fixed workflow with supported model, policy and parameter settings. |
| Subject | An input prompt and any explicitly supplied context. |
| Attempt | Execution of one unit for one subject within a run. |
| Result | The enhanced prompt, evaluations, deltas, assertions, timings and provenance from an attempt. |
| Enhancer | The engine that evaluates, generates and reevaluates a prompt. |
| Consumer | The generation role used by consumer-backed strategies. |
| Evaluator profile | The evaluators and settings shared by units for before/after comparisons. |
| Harness | The Bench/core execution wrapper that judges before/after prompts independently of the workflow's internal diagnostics. |

A strategy is a property of a unit. A prompt is part of a subject. Use **Units**,
**Subjects** and **Results** for those entities in navigation, headings and forms;
use **Strategy**, **Original prompt** and **Enhanced prompt** for their properties.

## Local development

The combined source checkout must contain the authoritative
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

## Experiments and delivery

Prepare a new JSON file in `experiments/` through the owner-reviewed contribution
flow. The `Publish Experiments` GitHub Action validates approved files on the
configured publication branch and delivers definitions to Test Bench. A v2
definition pins the exact registered core artifact; its runs and reruns retain
that digest. Legacy v1 definitions resolve `enhancerVersion` from the registered
catalog when creating each new run. `autoRun: true` queues a Run automatically on import;
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
are retained with the core result. In legacy v1 strategies, the consumer receives
baseline measurements before requesting a candidate. Versioned workflows use
their declared internal diagnostics; independent harness judgments remain outside
the generation context.

Publication schema `bench-publication/v2` contains only `definition` alongside
the envelope schema version. The definition references `enhancerVersion`; a v2
experiment additionally pins its exact core artifact.
Verified core-release receipts register version/variant-to-image bindings through
`POST /api/core-images`; their images must use an allowlisted repository and an
immutable SHA-256 digest. Legacy v1 Runs and reruns resolve the current binding;
queued, running and historical Runs retain their original digests. A v2 Run
retains the revision's pinned artifact, including on rerun. Selecting another
artifact requires a new v2 revision; changed build inputs require a new core version.
Repeated Run requests return their original Run without resolving again.
There is no runtime Git SHA lookup. The definition's `revision`
is an immutable string identity, while integer `generation` determines ordering.
Duplicate delivery is a no-op. A conflicting payload for an existing revision or
generation is rejected atomically. A disabled revision is not eligible for auto-run.

An unavailable version fails Run admission with `core_version_unavailable`.
An import that would auto-run rolls back atomically. Legacy v1 definitions with
`autoRun: false` can be imported before their core is registered; v2 definitions
always require prior registration of their pinned artifact. Legacy v1 envelopes remain
accepted and may seed a missing catalog entry; redelivery never replaces a newer
registration. See [resolution and migration](core-version-resolution.md).

The gateway protects `POST /api/publications`, `POST /api/core-images`,
`GET /api/experiments`, `GET /api/client-contracts`, `GET /api/runs`,
`GET /api/runs/{id}`, `POST /api/runs`, `POST /api/runs/preflight`,
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

The [evaluator coverage correction](evaluator-coverage.md) documents the proposed
`deterministic.v2` coding-request cues and explanations for unscored readings.
Existing experiment pins and recorded results remain immutable.

## Recovery and retention

Restart converts active runs to interrupted; it never resumes agent turns.
Queued runs remain queued. An owned container is removed and its absence checked
before admission resumes. An unconfirmed remote consumer turn requires explicit
operator reconciliation with a short evidence reference and confirmation that
the remote operation stopped. The UI then permits a fresh retry. This records an
operator attestation, not an automatically verified model success.

The bench retains complete results in its private volume until the operator
performs a reviewed retention operation. There is no automatic deletion of Bench
results or public export endpoint. The candidate client writes explicit private
analysis cohorts locally; see [client and export](client.md). Dedicated OpenHands conversation history has
a separate configurable seven-day default; successful runtime cleanup no longer
deletes it immediately. Uncertain conversations remain held for reconciliation.
See the [deployment policy](deployment.md#operator-configuration).
Back up SQLite with its backup API while the worker is
stopped, and verify the backup in a separate private location. Preserve WAL files
when moving a live database; copying just the main file is not a valid backup.
Never include database contents, prompts, response logs or worker homes in issues
or build contexts. There is no provider-session ingestion in this application.

## CI and deployment

For Experiment JSON changes, `bench-check.yml` runs only definition request
contract validation, cross-file revision/generation identity checks and privacy.
Full synthetic tests, browser suites, Compose and local image smoke checks run
only through manual dispatch of **Bench checks** on the selected branch. That
dispatch first validates definitions, then runs the full verification job.
Ordinary code PRs retain the fast repository/privacy checks described in
[CI scheduling](../ci-quality-gate.md); they do not start Bench image builds.
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
| `BENCH_IMAGE_REPOSITORY`, `BENCH_REGISTRY` | Core-release environment variables | Registry used by the separate core release job |
| `BENCH_CORE_VARIANT` | API and worker environment, optional | Catalog/runtime variant: `default` or `models`; defaults to `default` |

The current catalog is stored in Bench's private database, keyed by core version
and variant. Register the verified `core-release/v1` receipt using
`enhancement-bench register-core /tmp/example-core-release.json` with the existing
delivery origin and gateway settings. Registration does not import an Experiment
or start a Run. The old publisher-side `BENCH_CORE_IMAGES` setting is no longer
read. Migrated legacy entries retain unknown build provenance until replaced by
a verified receipt; do not fabricate a fingerprint from stale image labels.

Experiment publication validates and delivers definitions without registry
access. V2 import requires its verified pinned artifact to be registered first;
`autoRun: false` does not waive that requirement. A legacy v1 Run whose version
is absent from the catalog reports `core_version_unavailable`; use the separate manual
[Publish Core workflow](core-publication.md) to verify and register the selected
version before retrying. A legacy v1 definition with `autoRun: false` can be
imported before registration. A definition-only change can reuse a registered
core. Replacing a catalog entry does not change a v2 artifact pin; selecting a
different artifact requires a new revision. Changed build inputs require a new
core version. Delivery sends the
required Origin and optional gateway credentials, refuses redirects, and emits
only a content-free acknowledgement. Bench has no application login or import
token. Registry access belongs to the separate core-release job and worker.

The core-release workflow's operator-selected `models` variant installs B's
locked optional runtimes and uses its own tag, build fingerprint and image label.
Configure the API and worker to select the matching catalog variant. The
worker's optional local-model profile mounts only a reviewed labelled Docker
volume at a fixed read-only cache path and validates CPU/memory/device settings.
These controls stay outside definitions and UI overrides. See the deployment
recipe for exact configuration and the remaining real-model/device acceptance.

See [deployment](deployment.md), [proposal](architecture-proposal.md), and
[evidence](evidence.md). A local image/provider-simulator smoke is distinct from
live model or static consumer qualification.
