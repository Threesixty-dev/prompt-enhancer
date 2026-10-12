# ADR 0023: Enhancement core and experiment bench boundary

Status: proposed for owner review. Date: 2026-10-12.

## Context

Experiments must compare prompt enhancement strategies and consumer model
bindings against the same evaluator configuration. The existing interactive
Prompt Check flow has a metrics-only history and consent rules; a benchmark
requires complete before/after evidence, repeatable source/artifact identity and
private run storage. Implementation was authorized in separate core and bench
workstreams, followed by a combined local review.

This proposal consolidates the [core proposal](../enhancement-core/proposal.md)
and [bench proposal](../bench/architecture-proposal.md). It does not accept ADR
0022, reverse ADR 0015's interactive retention policy, or close the beta workflow
gates. Owner acceptance remains separate from implementation authorization.

## Proposed decision

- The enhancer owns one evaluate/generate/reevaluate engine and its versioned
  HTTP contract. Bench invokes it directly; no testing-harness service is added.
- Experiments are GitOps definitions with a stable identity, immutable revision,
  explicit ordering generation, prompt subjects and sibling units. Code owns the
  enhancer version; delivery binds it to an immutable image digest. Git history
  tracks definitions without becoming the runtime artifact lookup mechanism.
- Parameters, objectives, steering and consumer aliases inherit from experiment
  defaults. Unit values and then UI overrides refine them. Effective settings,
  image, identities and results are durable per run. Both evaluation passes and
  all siblings share the selected evaluator profile.
- Generation and evaluation use separate typed ports and operator-configured
  bindings. A static dedicated OpenHands/Codex worker provides consumer inference;
  evaluation may use separately pinned local models or a configured gateway.
  Model aliases are selectable; URLs, credentials, arbitrary code and filesystem
  paths are not experiment inputs. Packaged deterministic strategies are supported.
- Bench stores complete private experiment evidence separately from the app. One
  worker serializes runs and units, owns ephemeral core containers and verifies
  cleanup. Uncertain consumer termination holds admission for reconciliation;
  restarts never replay an agent turn automatically.
- Newest eligible automatic work is chosen by explicit generation, with atomic
  import/deduplication. UI runs get separate identities and immutable overrides.
  Execution success, assertions and unknown metric states remain distinct.

## Alternatives and consequences

An embedded app bench would mix retention and execution authority with private
interactive history. A separate harness would duplicate the core protocol and
flow. A universal chat adapter cannot faithfully represent classifiers and
embedding models. These alternatives are not selected.

The initial serial queue is simple and bounds resource use, but does not provide
multi-GPU scheduling or a general graph engine. Source connectors are deferred.
Immutable digests require artifact retention: registry policy, or retained local
tags for the demo, must keep referenced images available. A digest identifies
bytes; it does not preserve them by itself.

## Migration, affected components and evidence

Existing Prompt Check routes, DTOs and metrics-only persistence remain compatible;
the deterministic evaluation component is reused. The bench has separate SQLite
storage. Existing v1 definitions without unit bindings keep their publication
identity, and old queued snapshots retain the experiment-level fallback.

Affected atlas nodes: MA18, A20, W02, W03, W05, W06, W07, W08, WF03, WF04 and
WP01-WP08. This fixed enhancement flow is not the complete W01/W02 graph editor
and workflow engine. The October 8 source observation remains historical; this
addendum records the later candidate without recoloring accepted readiness.

The [combined review](../bench/integration-review.md) records tests, browser and
container evidence, baseline failures, image-retention repair and the usable
local demo. Live consumer/evaluator, real model/device, deployment and release
acceptance remain explicitly open. Revisit the boundary before adding external
subjects, multi-worker scheduling or changing interactive consent/retention.
