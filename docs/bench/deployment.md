# Bench deployment recipe

Status: reviewable configuration, not a live deployment. Use Coolify's Compose
application type with `deployment/bench/compose.yaml`. The dedicated Docker host
must be approved for benchmark execution; the worker's Docker socket is powerful
host authority. Do not co-locate it with untrusted tenants or expose it to the UI.

## Images and topology

Build the bench with `deployment/bench/Dockerfile`, the core with B's
`containers/enhancement-core/Dockerfile`, and the dedicated static consumer with
`deployment/bench/Dockerfile.consumer`. All use repository-root contexts narrowed
by their adjacent Docker ignore files. Definitions, private databases, provider
homes and model caches are excluded from build contexts. Do not publish until the
owner approves the artifacts and target registry.

The bench/core base Python image and Docker CLI base are digest-pinned. The static
consumer uses a digest-pinned OpenHands distribution with pinned server/SDK/tools
1.49.1 and Codex 0.156.0. The base pins its bundled `codex-acp`; inspect its version
as part of actual worker qualification. Dependencies/models must be reviewed
again when these pinned versions change; a successful package install is not
consumer acceptance.

| Component | Listener | Responsibility |
| --- | --- | --- |
| Bench API | Host loopback 8088 by default | Authenticated UI, definition import, durable queries and commands |
| Bench worker | No HTTP listener | Single durable executor; owns only labelled enhancer containers |
| Ephemeral enhancer | Loopback 8787 in worker namespace | Its own versioned enhancement/evaluation API |
| Static OpenHands/Codex consumer | Its own loopback 8000, bridged to a private Unix socket | Agent Server API and fresh ACP rewrite conversations; no network interface |
| Consumer relay | Worker loopback 8000 and private gateway Unix socket | Agent API transport and bounded HTTPS model requests; optional deployment-only Access credentials |
| Existing LiteLLM | Configured HTTPS gateway | Consumer model access; model-restricted credential |

`consumer-relay` shares `bench-worker`'s network namespace. Each enhancer is launched
with `--network container:enhancement-bench-worker`, so all private interfaces stay
on loopback without published core/consumer ports. `consumer` uses `network_mode:
none`; its model listener at loopback 4000 and Agent Server at loopback 8000 are
connected through two dedicated Unix-socket volumes. The one-slot policy prevents
8787 collisions. Restarting/replacing the namespace owner also requires restarting
the relay so it joins the new namespace; use the Compose project as the
lifecycle unit. Do not remove its durable data volumes during a restart.
Compose enables an authenticated consumer-readiness gate before claiming queued
runs, so initial worker/relay startup does not submit a turn prematurely. Failed
readiness leaves runs queued. Uncertainty after a submitted turn still requires
the explicit reconciliation described in the protocol.

The core consumer binding maps to the authenticated **Agent Server root** at
`http://127.0.0.1:8000`. It is not LiteLLM `/v1`, an ACP HTTP endpoint, the ADE
PR-review dispatcher, or the enhancer URL. B's `RemoteWorkspace`/`ACPAgent` adapter
creates fresh attempts through the server. The static worker's Codex provider is
configured to the fixed local bridge at `http://127.0.0.1:4000/v1` and uses the
Responses wire API. The relay's operator-supplied `BENCH_LITELLM_URL` selects the
actual HTTPS gateway, including `/v1`. The gateway/model must support that API and
the pinned ACP path; this is a live qualification gate. The deployment creates
this dedicated consumer; no pre-existing OpenHands worker is required.

The relay forwards the consumer's restricted Bearer key only to that fixed HTTPS
gateway, verifies TLS, rejects redirects, and allows only the declared models,
Responses/compaction and Chat Completions routes. Bodies, response bytes, stream
duration and concurrent requests are bounded. It never mints a key or exposes a
general proxy. Evaluator bindings keep their separate core-to-evaluator route.
The socket directories use a dedicated shared group (10003); each receiving side
mounts the other side's socket volume read-only. Neither socket volume contains
model caches or provider account files. No socket or relay has a public port.

## Operator configuration

`settings.example.json` lists only fictional non-secret values. Put actual values
in the deployment manager; do not commit them. The example model/revision/license
are placeholders and are not qualified models.

Provide distinct strong `BENCH_OPERATOR_TOKEN` and `BENCH_IMPORT_TOKEN`, plus
`BENCH_CONSUMER_API_TOKEN` and a model-restricted `BENCH_LITELLM_TOKEN`. These are
environment inputs; no local Codex account or credential file is mounted.
The consumer entrypoint strips unrelated injected environment variables before
starting Agent Server and supervises both transport processes. A transport exit
stops the consumer so Docker can restart the complete unit; health checks exercise
the actual private transports. It writes only its dedicated runtime Codex configuration
and uses read-only session mode, disabled web search and no interactive approvals.
The private synthetic worker is not a general-purpose repository agent.

Set `BENCH_DOCKER_GID` to the socket's group so UID 10002 can use it, and
`BENCH_CORE_CONFIG_SOURCE` to the reviewed core configuration's **Docker-host**
path. Docker bind mounts resolve on the daemon host, not inside the bench worker.
The configuration contains binding aliases and model provenance, not credentials.
The worker passes only named `ENHANCEMENT_*` credential variables plus a generated
per-container API token. API tokens and gateway credentials are absent from run
snapshots, definition envelopes and command arguments.

The checked-in sample evaluator is `deterministic.v1`. The core also supports
an independently configured gateway rubric evaluator. Add an entry to the
reviewed core configuration's `rubric_evaluators` array, for example:

```json
{
  "binding_id": "example-rubric",
  "provider": "inference",
  "endpoint": "https://gateway.example.invalid",
  "credential_env": "ENHANCEMENT_EVALUATOR_TOKEN",
  "model": "example-evaluation-model",
  "model_revision": "example-evaluation-revision",
  "model_license": "example-reviewed-license"
}
```

Provision `BENCH_EVALUATOR_TOKEN` separately from the consumer token. Compose
passes it only to the worker and the core's explicitly named environment. Bind
the experiment's evaluator profile to this alias using `kind: rubric`, a
core-supported `rubric` key and optional evaluator `generation` controls.
Consumer and evaluator generation settings remain separate. This wiring is
implemented; a gateway/model profile, real inference, retention policy and loaded
model identity still require live qualification.

If the gateway uses Cloudflare Access, provide the paired
`BENCH_CF_ACCESS_CLIENT_ID` and `BENCH_CF_ACCESS_CLIENT_SECRET` deployment secrets
for a service token scoped to that gateway. The relay sends these only to its
fixed HTTPS endpoint, alongside the consumer's separate restricted Bearer key.
It rejects redirects and never accepts Access credentials from incoming headers.
No Access credentials reach the isolated OpenHands/Codex consumer.
For the evaluator binding, add these non-secret environment references:

```json
{
  "access_client_id_env": "ENHANCEMENT_CF_ACCESS_CLIENT_ID",
  "access_client_secret_env": "ENHANCEMENT_CF_ACCESS_CLIENT_SECRET"
}
```

Compose passes the named values to the core; the adapter resolves them only from
its injected environment. Missing pairs and invalid header values fail closed.
Keep Access policies, TLS verification and model-key restrictions enabled.
Browser login alone does not authenticate these service requests; verify the
gateway's machine-access policy before submitting an experiment.

When a hosted gateway does not report a model revision or license, leave the
corresponding binding fields `null`. Results preserve those unknown values;
an alias, successful reply or container version does not prove a model revision.
Local model manifests still require their pinned revision and reviewed license.

Classifier and embedding adapters use reviewed local manifests and offline
caches. They cannot use this chat/rubric endpoint. The operator-configured local
path is described next; actual model and device qualification remains separate.

Coolify may add a private reverse proxy when the owner approves the deployment.
Set `BENCH_ORIGIN` to its exact HTTPS origin and preserve the Host header. The
default port publication is host loopback; do not make it a public unauthenticated
dashboard. Health probes must use the configured Host header when that origin is
changed. Environment review and network controls need actual platform verification.

## Local typed model runtime

Keep the default profile for deployments that do not use local models:
`BENCH_CORE_VARIANT=default`, `BENCH_CORE_MEMORY=1g`, `BENCH_CORE_CPUS=1`, no
model-cache volume and no GPU assignment. The model profile is explicitly enabled
with `BENCH_CORE_VARIANT=models`. Merge `settings.models.example.json` into the
deployment settings and the relevant entries from `core-config.models.example.json`
into the reviewed core configuration. That sample config has no consumer; retain
the separate consumer bindings when consumer-backed units are required.

Provision an isolated **plain local Docker volume**, with a name beginning
`enhancement-bench-models-` and label
`enhancement-bench.model-cache=reviewed-v1`. Set `BENCH_MODEL_CACHE_VOLUME` to that
exact existing volume. Populate it only through the reviewed model provisioning
process with B's manifest-pinned snapshot layout, readable by UID 10001. The label
records operator review; the core separately verifies the actual artifacts.
The bench neither creates nor populates production model volumes. Network volume
drivers, bind-backed volume options, unlabelled volumes and raw host paths are
rejected. The checked-in synthetic test creates its own empty volume and sentinel;
it never accesses an operator cache.

Every local evaluator's `cache_root` must be exactly
`/opt/enhancement/runtime/model-eval`. The worker mounts the selected volume there
read-only with copy-up disabled. The same reviewed core JSON is mounted read-only
into the worker for bounded validation and into each core for execution. Requests
and UI overrides cannot supply cache paths, volume names, Docker arguments,
resource limits, credentials or devices.

Set `BENCH_MODEL_DEVICE=cpu`, or `cuda` on a provisioned Linux NVIDIA host. CUDA
requires `BENCH_GPU_DEVICE` to identify one numeric device index or full GPU UUID;
the launcher uses Docker's explicit device request. `all`, device lists, arbitrary
device paths and `mps` are rejected. All local evaluator `device` fields must match
the worker setting; no silent fallback or cross-device scheduling occurs.
The host's GPU runtime/driver and image compatibility must be qualified separately.

`BENCH_CORE_MEMORY` accepts whole MiB/GiB values using `m`/`g`, bounded from 64 MiB
to 128 GiB. `BENCH_CORE_CPUS` accepts 0.1 through 64 CPUs with at most two decimal
places. These are explicit operator limits, not automatic sizing recommendations.
The model example uses 4 GiB and 2 CPUs; actual models may need different limits.
The read-only root, PID limit, dropped capabilities, bounded temporary filesystem
and one-run admission policy remain enforced. Stop/drain the worker before changing
its runtime profile; the models profile rejects queued default-variant images.

Select `models` in the manual publication workflow or pass `--variant models` to
`bench/ci.py`. It builds B's recipe with `ENHANCEMENT_WITH_MODELS=1` and resolves
`core-<version>-models`; the default uses `core-<version>` with build argument `0`.
Both the build fingerprint and `example.enhancement.build-variant` image label
include the variant. Reuse requires the matching label and source/build hash.
The model-enabled launcher refuses an image without the `models` label. Switching
an experiment to another digest requires a new definition revision/generation;
an existing immutable revision cannot be republished with a different image.

## Validation and acceptance

```sh
bench/.venv/bin/python tests/bench/check_deployment.py
docker build -f containers/enhancement-core/Dockerfile -t local/enhancement-core:bench-validation .
docker build -f deployment/bench/Dockerfile -t local/enhancement-bench:validation .
bench/.venv/bin/python tests/bench/docker_smoke.py
docker build -f deployment/bench/Dockerfile.consumer -t local/enhancement-consumer:validation .
bench/.venv/bin/python tests/bench/consumer_smoke.py
bench/.venv/bin/python tests/bench/relay_smoke.py
docker build -f containers/enhancement-core/Dockerfile --build-arg ENHANCEMENT_WITH_MODELS=1 --label example.enhancement.build-variant=models -t local/enhancement-core:bench-models-validation .
bench/.venv/bin/python tests/bench/docker_smoke.py --core-image local/enhancement-core:bench-models-validation --model-runtime
```

The smoke owns isolated temporary containers and a synthetic loopback inference
simulator. It runs the real core image, persists a script and consumer-adapter
result, checks duplicate suppression, reopens the database, reruns with overrides,
and confirms cleanup. The simulated provider validates the actual generation
context against the authoritative schema, then the test compares its measured
baseline, objective, steering, identities and profile to the persisted result.
The second run changes objective/steering while keeping the same profile.
No source/image is pushed. This proves packaged HTTP and
lifecycle integration; it does not prove an actual gateway, Codex turn, static
worker or genuine evaluator model completed work.

The model-runtime smoke additionally builds the real optional dependency variant,
constructs B's local embedding alias without loading weights, imports Torch and
Transformers, and checks actual Docker CPU/memory settings plus a read-only cache
write failure using a synthetic sentinel. B's actual cache-boundary validation
accepts the mount and its offline snapshot loader rejects the absent model without
downloading. The test deletes only its own labelled volume.
CUDA command selection is covered by synthetic launch tests; no GPU execution or
model performance/accuracy claim follows from these checks.

The relay smoke uses real isolated worker/relay containers and a verified-TLS
synthetic upstream. It tests both transport directions, restricted key forwarding,
stream completion, socket ownership and read-only mounts, filtered agent
environment, bridge failure, restart and removal of its own containers/volumes.
These are transport probes; the test does not ask Codex to generate a response.

Live acceptance additionally requires an owner-provisioned gateway/model binding,
the static worker built from this recipe, safe credentials supplied through the
deployment manager, a script and actual consumer-backed unit against one qualified
evaluation profile, cancellation/cleanup evidence, and a restart/restore check of
the persistent bench volume. Preserve only content-free receipts outside Git.

The missing deployment inputs are the target application's approved
management/access binding, the actual gateway HTTPS endpoint and restricted
consumer model identity, and the chosen evaluator alias/profile (or approved
local model volume/device). Supply secret values through Coolify's secret store.
Do not discover saved service objects, account files or live environment values.
No existing bench/worker deployment, source publication or automatic deployment
is assumed or required to review this recipe.
