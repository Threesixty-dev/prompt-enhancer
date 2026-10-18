# ADR 0027: Versioned core components and workflows

Status: owner-approved design; locally validated implementation, source review pending.

## Decision

Core supplies reusable components for prompt enhancement, session analysis and
session-link analysis. Workflows compose those components with explicit order,
branching, contracts and defaults. Shared execution tooling supplies model
connections, process ownership, cancellation and provenance. Bench and the app
are callers of the same workflow layer; Bench integration is the first target.

Each experiment revision binds one immutable workflow version, one exact core
build and one harness evaluation configuration. All units use the same workflow
and step implementations. Units may vary supported model/provider bindings,
policies/instructions and step parameters. They cannot replace implementations,
change step order or override harness evaluation.

Workflow-internal diagnostics may guide later steps. Harness evaluation measures
the workflow without feeding its judgments into generation. Both may reuse core
evaluators, but their configuration and results have separate identities.

Core and workflow versions are independent. A workflow declares compatible core
versions; an experiment pins one exact build. New pins require a new experiment
revision. Existing definitions, run snapshots and retained images keep their
historical meaning. This supersedes the single-flow boundary proposed in ADR
0025 and Run-time image rebinding proposed in ADR 0026 for new definitions.

## Compatibility and scope

The pre-Bench Prompt Check workflow preserves rich metric cues, inferred context,
context selection, model-facing review instructions and response validation.
The newer redactor remains an explicit intentional difference. Existing app
consent, egress and metrics-only persistence boundaries are preserved. No real
sessions, model downloads, source publication or deployment are part of local
validation.

The fixed reviewed workflows are not a general graph editor. Their components
and versioned definitions are reusable without requiring another network service.

The owner's subsequent logic adjustment aligns `prompt-rewrite` and
`prompt-clarify` version `2.0.0` with `prompt-check` version `1.0.0`: score, infer context, optionally
review with a model and return findings with an optional rewrite. Default review
policies distinguish rewriting from clarification. The v1 direct-rewrite and
deterministic-placeholder flows retain their original pins and are identified as
legacy in the UI. This changes the logical sequence, not just its presentation.
Session-analysis and session-links already retain their pre-Bench sequences.

## Evidence

The owner's logic-alignment follow-up passes 372 affected backend checks, 62
focused checks after the final policy receipt correction, 48 desktop/mobile
browser checks and six offline definition validations. All three review flows
match the six pre-Bench synthetic input/context/scoring cases; policies express
their separate review goals. Prior workflow digests and behavior are retained.

Local evidence on 2026-10-18: 517 affected backend tests pass, with two
Windows-specific owned-process checks skipped. A focused follow-up after the
final compatibility corrections passes 111 tests. The full Bench browser suite
passes 42 desktop/mobile checks; four workflow checks also pass after the final
schema export. Six authored synthetic cases match the pre-Bench Prompt Check
metrics, inferred context, model-facing input and policy. Immutable experiment
bindings, historical migrations, shared contracts and privacy checks pass.

The [implementation record](../bench/versioned-workflows.md#local-validation---2026-10-18)
details evidence and limits. Core `0.2.0` is a source candidate. Bench exposes
three prompt workflows; the two session workflows retain their library/app input
contracts. Generic session-input Bench transport, live models, devices,
deployment and general workflow-product gates remain separate.

Affected atlas nodes: MA18, W01, W02, W03, W05, W06, W07, W08, WP01-WP08.
