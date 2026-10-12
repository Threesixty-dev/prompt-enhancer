# Proposal: versioned enhancement execution boundary

Status: proposed, owner acceptance required. Date: 2026-10-12.
This is Workstream B's architecture proposal for central ADR/atlas integration.
It does not silently supersede ADR 0015 or accept proposed ADR 0024.

## Problem and resulting behavior

Prompt Check currently has an app-composed deterministic pass and optional
commentary/rewrite. Its metrics-only history and approval policy are appropriate
for interactive private use, but a benchmark needs a complete before/after
comparison from a selected immutable enhancer image without importing the UI,
session ingestion, database, or user's configuration.

Extract the deterministic evaluator into a shared application component and add
one enhancement engine with separate consumer and evaluation ports. Both
packaged script and consumer generation feed the same reevaluation/comparison
sequence. Sibling units share a core build; experiment definitions and provider
bindings remain external. Bench owns complete run storage and container cleanup.

## Decisions proposed

- Versioned closed JSON schemas and an authenticated loopback headless API live
  with the core; no separate testing-harness product/service is introduced.
- Experiment/run/correlation/unit/attempt identity is preserved in progress and
  results. Idempotence is bounded to the instance's retained request identity;
  bench remains responsible for durable definition/run deduplication.
- A dedicated static consumer worker is reached through the pinned OpenHands
  SDK's ACP/RemoteWorkspace API. It hosts no enhancer or harness. Each trial has
  a new conversation; unsupported controls are rejected and completion/cleanup
  is verified through provider state. Unknown cleanup quarantines admission.
- Evaluation uses explicit typed adapters. Deterministic metrics, classifier
  labels, embedding similarity and rubric interpretation remain distinct.
  Numeric deltas require matching evaluator/provenance; categorical or unknown
  values do not become zero. No universal prompt/developer score is added.
- Generation receives a versioned context containing measured baseline evidence,
  typed optimization objectives and bounded profile/style/focus instructions.
  Both consumer adapters receive those effective values. Consumers return only
  candidate text; reevaluation and assertions remain core-owned evidence.
- Headless synthetic admission is an explicit deployment/caller policy. It
  never bypasses the interactive app's existing consent, egress preview, native
  approval or metrics-only persistence. No real sessions enter this validation.
- Server configuration declares separate consumer/evaluation aliases and pinned
  model provenance. Runtime requests cannot choose arbitrary endpoints, shell
  scripts, weights or provider credential files. Owned model workers stay offline.
- The default container runs unprivileged on loopback in bench's network
  namespace. No public listener, automatic publication or live deployment is
  introduced. Immutable image digest resolution/delivery belongs to Workstream A.

## Alternatives and tradeoffs

Embedding bench scheduling/storage in the app would mix a full-result retention
policy with metrics-only history. A new testing-harness service would duplicate
the enhancer's execution authority. A universal chat adapter would misrepresent
classifier and embedding models. These alternatives are not implemented.

Ephemeral core state is deliberately small. A core restart loses progress; bench
must record unknown state and reconcile an uncertain remote consumer before a
new attempt. Model-process isolation adds startup cost, which timings retain.
Resource leases across independent core instances are an operator/bench concern;
the MWE uses dedicated workers and bounded admission. Advanced scheduling, graph
editing and data-source connectors remain outside this work.

## Migration and evidence scope

Affected atlas nodes: MA18, A20, W03, W06, W08, WF03, WF04, WP01-WP08.
The reusable fixed flow is not the full W01/W02 graph engine. Existing Prompt
Check routes, DTOs, commentary behavior and history remain compatible; tests
exercise those existing contracts. Shared protocol/schema tests, synthetic
role/failure/cancel/unknown tests, subprocess cleanup, loopback HTTP and local
container checks accompany the implementation. Native/real-model qualification,
remote retention/TLS policy and clean-machine/release acceptance remain separate
owner-run gates. Central ledger/atlas updates must preserve these distinctions.
