# All-20 metric operability

This is the release-facing map of how every canonical metric can obtain a
measured value. It is not a claim that every analyzed window contains the
required evidence. A missing opportunity set, link, or receipt remains
`unknown`; an experimental model estimate never becomes measured evidence.

The authenticated, content-free source of truth is:

`GET /v1/metric-contracts/v2/operability-catalog`

The response is bound to the current contract-set fingerprint, projection
identity, readiness catalog, and all twenty individual contract fingerprints.
It reports the exact counts below and is private/non-cacheable.

## Current release gate

| Gate | Count |
|---|---:|
| Shipped measured path when its evidence exists | 12 |
| Task-profile configuration still required | 3 |
| Provider/extractor adapter still required | 5 |
| Experimental model-estimate path | 8 |
| Metrics for which a model may author the measured value | 0 |

## Per-metric map

| Metric | Measured path | Current release state | Experimental model path |
|---|---|---|---:|
| `prompt.task_definition_coverage` | Focus-owned fixed-factor rubric | Available when evidence exists | Yes |
| `prompt.problem_evidence_quality` | Focus-owned fixed-factor rubric | Available when evidence exists | Yes |
| `prompt.context_sufficiency` | Focus-owned fixed-factor rubric | Available when evidence exists | Yes |
| `prompt.constraint_precision` | Declared task-profile slots | Task-profile configuration required | Yes |
| `prompt.acceptance_testability` | Declared task-profile slots | Task-profile configuration required | Yes |
| `prompt.deliverable_contract` | Declared task-profile slots | Task-profile configuration required | Yes |
| `collaboration.ambiguity_resolution` | Confirmed lifecycle evidence | Available when evidence exists | No |
| `collaboration.clarification_yield` | Confirmed lifecycle evidence | Available when evidence exists | No |
| `collaboration.exploration_conversion` | Confirmed lifecycle evidence | Available when evidence exists | No |
| `collaboration.scope_change_discipline` | Confirmed lifecycle evidence | Available when evidence exists | No |
| `collaboration.rework_candidate_rate` | Confirmed lifecycle evidence | Available when evidence exists | No |
| `logic.decomposition_coverage` | Requirement/plan semantic-unit extraction | Provider/extractor adapter required | Yes |
| `logic.hypothesis_test_linkage` | Typed opportunity, link, and outcome receipts | Provider adapter required | No |
| `logic.decision_rationale_coverage` | Documented decision semantic units | Available when evidence exists | Yes |
| `logic.requirement_action_traceability` | Typed opportunity, link, and outcome receipts | Provider adapter required | No |
| `logic.open_loop_closure` | Explicit plan-to-superseding-action link | Available when evidence exists | No |
| `outcome.agent_claim_grounding` | Typed opportunity, link, and outcome receipts | Provider adapter required | No |
| `outcome.verification_strategy_adequacy` | Documented verification-strategy semantic units | Available when evidence exists | No |
| `outcome.first_pass_verification` | Reviewed task plus task-scoped verification receipt | Available when evidence exists | No |
| `outcome.verified_requirement_coverage` | Typed opportunity, link, and outcome receipts | Provider adapter required | No |

“Available when evidence exists” includes honest `unknown`, `pending`, and
`not_applicable` outcomes. For example, a collaboration family needs a
browser-confirmed complete enumeration before it has a denominator, and
first-pass verification needs exactly one reviewed task owning the session.

## Local agent evidence file

The v1 local-agent file workflow covers the five collaboration lifecycle
families. An API-token client may fetch the contract, preview canonical JSON,
and import an inert proposal. It cannot confirm or reject that proposal. A
separate same-origin browser session, CSRF proof, exact confirmation literal,
and second visible action are required before a confirmed receipt can affect a
future sealed snapshot. See
[`local-agent-metric-evidence-api.md`](local-agent-metric-evidence-api.md).

Extending this file format is not a shortcut around evidence authority. The
next safe extension is a separately versioned task-profile proposal followed
by browser confirmation. Objective evidence must bind app-issued opportunity
identities to typed outcome receipts; an agent-authored claim that a test passed
cannot verify itself.

## Model boundary

The current experimental sidecar can attempt eight immediate metrics. Small
encoders estimate factor evidence; the optional deep judge adjudicates selected
disagreements. All model outputs remain uncalibrated and product-ineligible.
The sealed measured publication is computed only from deterministic reviewed
structure or typed receipts, so switching to a larger model cannot fill one of
the eight authority/configuration gaps above.

The live factor router is deliberately smaller than the historical ten-slot
compatibility graph:

| Stage family | Live role |
|---|---|
| mDeBERTa XNLI | Multilingual factor NLI baseline |
| MiniLM-L6 NLI | Small multilingual factor expert |
| MiniLM-L12 NLI | Small multilingual factor expert |
| Qwen3 4B NF4 | Optional, bounded adjudicator for selected disagreements |
| Four retrieval and two reranking slots | Historical diagnostics; not factor classifiers and not executed by the live router |
| DeBERTa-long and ModernBERT challengers | Reviewed but live-disabled after the current synthetic/resource gates |

Thus a typical live run exposes three small stages and, only when eligible, one
deep stage. “Ten models” is an immutable historical receipt shape, not ten
independent metric authorities. Adding more stages is justified only by a
representative per-metric holdout showing incremental calibrated value within
the latency, memory, privacy, and failure budgets.
