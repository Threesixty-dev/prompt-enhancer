# Enhancement protocol v1

Workstream B owns `contracts/enhancement/` and the authoritative Pydantic models
in `src/prompt_enhancer/enhancement/contracts.py`. Protocol `enhancement.v1`, core
`0.1.0`. Definition revision and core version are independent. Git SHA is optional
build provenance; no runtime Git lookup exists. This is a proposed implementation
boundary pending owner review, not acceptance of the broader workflow roadmap.

The subject is the input prompt. Explicit context is optional. The evaluator
profile is frozen for both passes. Evaluation bindings and consumer bindings are
separate server-configured aliases, never endpoint URLs or credentials supplied
by requests. Unknown values are null with a state. Numeric deltas require matching
metric and provider provenance. Classifier labels and rubric labels are not
numeric scores. An assertion outcome is separate from execution status.

## HTTP interface

All responses are JSON. Unknown fields and unsupported versions are rejected.
The standalone service listens on loopback; it does not mount application routes.
Every endpoint requires `Authorization: Bearer <ENHANCEMENT_API_TOKEN>` (at least
32 characters, injected by the operator/bench). Browser Origin is rejected. POST
uses `Content-Type: application/json`, including cancellation with `{}`. Bodies
are bounded to 320,000 bytes and responses use `Cache-Control: no-store`.

| Method and path | Response |
| --- | --- |
| `GET /health/ready` | `Readiness`, 200 ready or 503 unavailable |
| `GET /v1/capabilities` | Code/core/protocol versions, strategy and typed binding capabilities, request parameter schema |
| `POST /v1/executions` | `ExecuteRequest` -> `Progress`, 202 accepted or duplicate |
| `GET /v1/executions/{execution_id}` | `Progress`, 200; 404 absent |
| `GET /v1/executions/{execution_id}/result` | `ExecutionResult`, 200; 409 not terminal; 404 absent |
| `POST /v1/executions/{execution_id}/cancel` | `Progress`, 202; terminal cancellation is idempotent |
| `DELETE /v1/executions/{execution_id}` | 204 after terminal result persistence by bench; 409 while active |

`execution_id` is SHA-256 of canonical JSON of the six identity fields
(`experiment_id`, `revision`, `run_id`, `correlation_id`, `unit_id`, `attempt_id`),
sorted keys, compact separators, ASCII JSON. Identical identity and full request
return the existing execution. Changed payload with the same identity is 409.
No retry is automatic. New attempts use new attempt IDs. Invalid configuration
or unsupported binding/parameters is rejected before calls with 422. Capacity is
bounded: 429 means admission denied, not queued invisibly. Errors use only
`{"error":{"code":"fixed_code"}}`, without request/provider text.

States: queued -> running -> succeeded/failed/cancelled/timed_out/uncertain.
Cancellation may pass through cancelling. `uncertain` means a submitted remote
operation or its cleanup cannot be confirmed stopped; it must not be retried
blindly. Progress sequence increases monotonically within one process. Polling
does not expose subject or generated content. The result endpoint is sensitive.

Only a bounded synthetic benchmark is admitted, with explicit
`data_policy: synthetic_benchmark` and server opt-in. This is a caller attestation,
not a claim that arbitrary text can be automatically proven synthetic. There is
no session import, home-directory access, native approval, or transcript tool.
The interactive application's existing approval flow is separate and unchanged.

The core holds bounded ephemeral results; bench owns durable complete storage.
Bench persists a terminal result before DELETE and container cleanup. Restart
loses core state; a missing execution after restart is unknown, never success or
permission to rerun. Bench owns duplicate/out-of-order definition delivery.

Strategies: `script.clarify.v1` runs packaged placeholder clarification; it accepts
no arbitrary code. `consumer.rewrite.v1` uses an independently configured consumer
and a fresh conversation per attempt. Both evaluate original, generate candidate,
reevaluate using the same profile, and compare. No universal quality score exists.

## Measured generation context

`ExecuteRequest.objective` declares a versioned objective ID/revision, bounded
description and typed targets. Numeric targets identify a metric, desired
direction and optional desired value; categorical targets identify a desired
label. They are generation goals, not pass/fail assertions. Validation prevents
treating classifier/rubric labels as numeric scores and rejects unknown metric
references before any provider call.

`ExecuteRequest.steering` selects `conservative.v1` or `targeted.v1`, style,
explicit focus aspects and optional bounded instructions. These settings are
experimentable independently of consumer sampling and evaluator generation.
After original evaluation, the core creates `GenerationContext`, protocol
`enhancement-generation.v1`, prompt version `enhancement-rewrite.v2`, containing
the matching identities, measured baseline with unknown states/provenance,
frozen evaluation profile, objective and steering. Both consumer adapters receive
this context together with the subject. The model must preserve intent and
language, respect unknowns and abstentions, and use placeholders for missing facts.

Consumers may return only `enhanced_prompt`; supplied measurements, assertions,
or claims of verification are rejected. The core evaluates the candidate itself.
Results record `effective_objective`, `effective_steering`,
`generation_context_version` and `generation_prompt_version` alongside the actual
before/after evaluations. The consumer cannot overwrite these evidence fields.

The packaged script uses measured gaps/unknowns and optional deterministic
numeric-increase targets plus focus aspects to choose clarification placeholders.
It rejects custom instructions, non-preserving styles, natural-language objective
overrides and non-deterministic/decrease targets it cannot implement. The full
consumer strategy supports the declared typed objectives and steering styles.

New authoritative files: `generation-context.schema.json` and
`examples/generation-context.json`. The result fixture is generated from the
fictional scripted request with the actual deterministic evaluator; timings are
omitted because it is a schema example, not an execution receipt.

## Draft integration refinements

Generation `max_tokens` and `temperature` default to null: provider-managed,
effective value unknown. ACP rejects non-null values because it cannot apply
portable per-request controls. The inference consumer supports both explicitly.
`max_output_chars` is always enforced locally. Model provenance distinguishes
configured identity from verified local manifests. `reported_model` is null
unless returned by the provider protocol; configured revision/license are not
independent proof of what a remote gateway actually loaded.

Additive draft fields: rubric evaluators can carry their own optional `generation`
settings, separate from consumer generation. Local fixed-profile rubric backends
reject overrides they cannot apply. Consumer provenance and structured errors
can carry `operation_id`: the UUID of the newly created ACP conversation. Bench
must persist it even when status is `uncertain`; it identifies the exact remote
conversation for an operator to inspect/pause and confirm cleanup. The core
never treats local client termination as remote cancellation confirmation.
Quarantine has no automatic reset endpoint. Before replacing an uncertain core,
the operator must reconcile that worker/conversation and ensure it is no longer
running. Reusing a worker or retrying a missing/uncertain attempt without that
confirmation is outside this protocol. Missing operation IDs remain unknown.

Authoritative exports include request, result, progress, readiness and capabilities
schemas. Regenerate them with `python scripts/export_enhancement_contracts.py`
from an installed checkout. Fixtures contain only fictional content.

## Container integration

Run `python -m prompt_enhancer.enhancement.cli --synthetic-benchmark --port 8787`
(or the `prompt-enhancement-core` entry point), with an injected API token.
Optional `--config` names an explicitly supplied core-only JSON configuration.
No user application, provider credential file, home configuration or Git lookup
is performed. The persistent task goal is tracked separately by the supervisor.

The initial bench integration uses
`--network container:enhancement-bench-worker` when creating the enhancer container.
Both processes then reach the core at `http://127.0.0.1:8787`. Do not publish a
Docker port or change the bind address. Workstream A owns namespace/container
lifecycle and ensures port exclusivity; it may choose another explicit port for
parallel image instances. The standalone container contains the enhancer core,
not a consumer worker or a testing-harness service.

## Operator-owned local model mounts

Workstream A can use `/opt/enhancement/runtime/model-eval` as the stable container
cache destination. Mount an explicitly selected operator-owned directory there
read-only; never discover a provider home, copy a personal cache, download weights
at startup, or pass a request-controlled host path. The directory must already
contain the approved Hugging Face snapshot layout and readable manifest-pinned
files. The runtime UID is 10001. Symlink targets must stay inside the mounted cache.

Core configuration selects each local alias independently, for example:

```json
{
  "max_active": 1,
  "evaluators": [
    {
      "binding_id": "example-classifier",
      "kind": "classifier",
      "manifest_key": "mdeberta_xnli",
      "cache_root": "/opt/enhancement/runtime/model-eval",
      "device": "cpu"
    }
  ]
}
```

The corresponding execution profile uses the alias with `kind: classifier` and
an explicit target/hypothesis. An embedding example is manifest
`multilingual_e5_small` with `kind: embedding` and a target/query. Rubric manifests
use `kind: rubric` with a supported rubric key. Full manifest definitions and
immutable model/tokenizer/artifact pins remain code-owned under
`infrastructure/text_models/manifests.py`; model IDs are not arbitrary Hub inputs.
`pair_reranking` manifests are not supported by this enhancement interface.

Build the model-enabled image using `--build-arg ENHANCEMENT_WITH_MODELS=1` with
the same Dockerfile and frozen lock. The default (`0`) image does not contain
Torch/Transformers; configuring local-model adapters in it is rejected at startup.
CI/bench must distinguish and fingerprint these variants and resolve the selected
variant to its immutable image digest. The flag is package installation only;
it neither downloads model weights nor qualifies a backend.

For Linux containers, select `cpu` or explicitly provisioned `cuda`. Bench owns
CPU/memory/PID limits and GPU device assignment; the core does not schedule GPUs,
auto-switch devices or share app-owned runtimes. `mps` is only meaningful for a
native macOS package and must not be advertised as a Linux container option.
Start with one admitted execution per core/worker allocation. Local models run
in bounded owned subprocesses, offline with `trust_remote_code=False` and
verified safetensors, then release their model/process resources. Missing cache,
integrity failure or unavailable device is an explicit failure, not fallback to
a different model or network download. The chosen cache/model/device still needs
real-model qualification; synthetic adapters do not provide it.
