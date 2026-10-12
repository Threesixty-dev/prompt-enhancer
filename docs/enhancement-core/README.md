# Independently runnable enhancement core

Core `0.1.0`, protocol `enhancement.v1`. This feature-branch implementation is
proposed for owner review; it does not accept ADR 0022 or close the general
workflow/real-model roadmap gates. See [protocol](protocol.md),
[proposal](proposal.md), and [task card](task-card.md).

## Scope and separation

`prompt_enhancer.enhancement` composes the reusable evaluator and one sequential
engine. `application.prompt_evaluation` is shared with Prompt Check; its six
deterministic readings keep their existing definitions. The interactive app
still owns consent, redaction, inference preview, native approval, and its
metrics-only history. The headless entry point imports neither app bootstrap
nor application repositories. Bench stores complete results and manages image
selection, definition delivery, attempts and cleanup.

The core is not a separate testing-harness service. It runs in the chosen enhancer
image. One code-owned version/build is shared by sibling units in an experiment
revision; definitions can reuse an image. CI/bench pin the image digest outside
the core. A Git checkout is unnecessary at runtime.

## Local and container execution

Install locked dependencies with `uv sync --frozen --extra enhancement-acp` on
Python 3.12+. Base application and deterministic core retain Python 3.11 support.
Start `prompt-enhancement-core --synthetic-benchmark --port 8787`, or use
`python -m prompt_enhancer.enhancement.cli` with the same flags. Inject a random
`ENHANCEMENT_API_TOKEN` of at least 32 characters. Every endpoint requires it.
No secrets are embedded in example requests or image layers.

Build from the repository root:

```sh
docker build -f containers/enhancement-core/Dockerfile -t enhancement-core:local .
```

The recipe pins the Python base digest, uv revision and Python dependency lock.
It includes the pinned OpenHands client, runs as an unprivileged user, and binds
to loopback only. A recipe-specific ignore file sends only package source and
build metadata to Docker; no Git metadata, configuration, sessions or model
weights enter the build context. Bench runs it in its worker network namespace
as described in [the protocol](protocol.md). Read-only root, a bounded `/tmp`,
capability dropping, PID/memory/CPU limits and port exclusivity belong to the
bench's launch configuration.

Use `--config /run/secrets/enhancer-config.json` for an explicitly mounted,
read-only configuration. [config.example.json](config.example.json) contains
only reserved fictional endpoints and model identities, not deployable values.
Credentials come exclusively from the named `ENHANCEMENT_*` variables supplied
by the operator. No provider credential files or user app settings are loaded.
Configured aliases and provenance are visible in capabilities; endpoints and
credentials are not. Capabilities report configuration, not live qualification.

## Supported role adapters

| Role | Adapter | Effective configuration and behavior |
| --- | --- | --- |
| Consumer | OpenHands SDK 1.49.1 ACP / RemoteWorkspace | Dedicated static worker, configured model/revision/license and command, explicit read-only mode, fresh conversation per attempt; no local provider account access |
| Consumer | Existing LiteLLM transport | Independent configured alias; complete assistant JSON required; optional explicit temperature/token bound |
| Evaluation | Deterministic prompt evaluator | Existing six readings; explicit prior context, same redaction/language/rubric as app |
| Evaluation | Local typed Transformers | Reviewed offline manifest/safetensors snapshot; classifier NLI labels, embedding similarity, or structured rubric labels |
| Evaluation | Existing LiteLLM rubric transport | Separate binding and rubric profile; never used for classifier or embedding calls |

Generation settings are separate from each evaluator's settings. A rubric
evaluator may carry `generation` overrides for gateway token/temperature controls.
Omission delegates those controls to the provider and keeps their effective value
unknown. Local rubric generation remains the versioned reviewed backend's fixed
16-token deterministic profile; per-request generation overrides are rejected.
Classifier and embedding inputs have their own required `target`; a rubric
requires a supported `rubric` key. Typed models evaluate subject text only; the
deterministic evaluator also consumes explicit context. No context is fetched
from previous benchmark conversations. All parameters are validated before the
first provider call. Unsupported binding/kind/metric/parameter combinations fail.

Generation receives the actual original measurements through the versioned
`GenerationContext`, together with typed optimization targets and bounded
profile/style/focus instructions. Both consumer adapters use it; the packaged
script chooses clarification placeholders from measured gaps and supported
targets. Effective objective/steering and prompt/context versions accompany each
result. Consumer output cannot supply or override evaluator evidence. See the
[measured generation contract](protocol.md#measured-generation-context).

Local text-model composition additionally requires an image built with
`--build-arg ENHANCEMENT_WITH_MODELS=1` (or the locked `models` extra), an explicitly
mounted isolated cache ending in `runtime/model-eval`, a reviewed `manifest_key`,
and an explicit device. Model downloads are disabled, `trust_remote_code` stays
false, and every artifact must match its manifest. No model weights are vendored.
This optional heavy model image is separate from the default packaged check.

## Cancellation, privacy and qualification

Blocking SDK/model calls run in owned bounded subprocesses with an isolated
environment and temporary home. They inherit no account/proxy/telemetry settings.
SDK output and errors never enter logs or responses. Local process exit is
confirmed before capacity is released. Cancelling a remote client cannot prove
the remote agent stopped: the result becomes `uncertain`, carries the consumer
operation ID, and quarantines admission. Bench/operator reconciliation is
required; do not restart blindly to clear uncertainty or share that worker with
another core. Confirmed finished synthetic conversations are explicitly deleted
and absence is verified; unsuccessful cleanup remains uncertain.
The adapter also creates an exclusive private temporary directory for each
conversation and removes it only after confirmed completion/deletion. Directory
creation/removal commands contain only a core-generated UUID, never request text;
nonempty or unsuccessful cleanup is retained as uncertainty for reconciliation.

Full results are sensitive even for pseudonymized input. Only explicitly
attested synthetic benchmarks enter this service. The flag is authorization,
not automatic proof that text is synthetic. Browser origins are rejected and
results are not cached. State is ephemeral and bounded; bench persists before
deletion. A restart produces missing state, not proof of success or permission
to retry. There is no automatic egress from existing sessions.

Synthetic tests prove protocol/adapter behavior. Actual worker authentication,
ACP read-only mode/model selection, remote cleanup, gateway retention and loaded
model revision, and real local-model inference need separate bounded operator
qualification. No such live evidence is claimed by the test doubles.
