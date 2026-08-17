# All-20-metric local probabilistic radar

This document is the product and implementation contract for the always-on
radar. It contains no source text, model output, local paths, or account data.

## What the radar means

The radar intentionally shows two different kinds of information:

- The **solid line and points** are evidence-backed typed measurements.
- The **dotted line** is the local model median.
- The **dark translucent band** is the model's central 50% range.
- The **light translucent band** is its central 90% range.
- The outer coverage ring reports observed eligible evidence, not confidence.

All twenty axes always remain visible. `Not applicable`, `Pending`, `Unknown`,
and `Execution error` are axis states and gaps; none is drawn at zero. A solid
zero exists only when the deterministic contract proved an eligible denominator
and observed no positive factor. Until a metric passes its own calibration gate,
the model layer is labelled **Experimental model range** rather than probability,
confidence, or predictive interval.

Four fixed lenses keep unlike constructs separate:

| Lens | Metrics |
|---|---|
| Task framing | task definition, problem evidence, context, constraints, acceptance testability, deliverable contract |
| Collaboration | ambiguity resolution, clarification yield, exploration conversion, scope-change discipline, rework candidate rate |
| Reasoning trace | decomposition, hypothesis-test linkage, decision rationale, requirement-action traceability, open-loop closure |
| Outcome evidence | claim grounding, verification strategy, first-pass verification, verified requirements |

There is no combined developer score and no universal trust percentage.

## Twenty versioned contracts

Each metric has one observation owner. Context may overlap for inference, but a
physical fragment or chunk boundary never creates an additional denominator.

| Metric | Observation unit | Live evidence route |
|---|---|---|
| Task definition coverage | canonical request revision | deterministic extraction + small factor model |
| Problem evidence quality | diagnostic request | deterministic extraction + small model; deep adjudication on ambiguity |
| Context sufficiency | stateful request | deterministic extraction + small factor model |
| Constraint precision | one explicit constraint | deterministic extraction + small factor model |
| Acceptance testability | one requirement | deterministic extraction + small model; deep adjudication on ambiguity |
| Deliverable contract | one requested artifact | deterministic extraction + small factor model |
| Ambiguity resolution | one ambiguity and its resolution horizon | deterministic linkage + small model; deep adjudication on weak links |
| Clarification yield | one agent question and linked user response | deterministic linkage + small factor model |
| Exploration conversion | one hypothesis, evidence action, and plan update | deterministic linkage + small model + objective receipt when available |
| Scope-change discipline | one scope-change episode | deterministic linkage + small factor model |
| Rework candidate rate | one feedback episode | deterministic routing + small model; deep adjudication on disagreement |
| Decomposition coverage | one requirement linked to a plan item | deterministic extraction + retrieval + small model |
| Hypothesis-test linkage | one hypothesis linked to check, result, and update | deterministic linkage + small model + objective receipt |
| Decision-rationale coverage | one material decision | deterministic linkage + small model; deep adjudication on ambiguity |
| Requirement-action traceability | one requirement linked to action or artifact | deterministic linkage + retrieval + objective receipt |
| Open-loop closure | one loop through its closure horizon | deterministic linkage + small model; deep adjudication on ambiguity |
| Agent-claim grounding | one material completion claim | small model may link; objective evidence decides the solid value |
| Verification-strategy adequacy | one testable requirement and verification method | deterministic linkage + small model; deep adjudication on ambiguity |
| First-pass verification | first valid executable verification outcome | objective evidence only for the solid value |
| Verified-requirement coverage | requirements with fresh passing evidence or explicit acceptance | objective evidence only for the solid value |

Factor scales are binary, ordinal `0 / 0.5 / 1`, or exact proportions according
to the contract. The current session value is computed from current unique units
and sufficient statistics; historical radar snapshots are never averaged into a
new value. Applicability and value-conditional-on-applicability remain separate.
An open right-edge episode is `Pending` rather than a negative. A one-message
request can therefore measure relevant task-framing axes while later-interaction
metrics remain N/A or pending.

## Local model router

The live estimator is an external mixture-of-specialists router. It is not a
large native MoE and does not average ten unrelated scores.

1. Deterministic matching and BM25 select bounded candidate evidence first.
2. Three revision-pinned multilingual NLI encoders provide the EN/PL baseline.
3. English eligible cases may use pinned DeBERTa-small-long-NLI and
   ModernBERT-base zero-shot challengers.
4. High disagreement, neutral evidence, or manual deep analysis may invoke the
   pinned Qwen3 4B judge in 4-bit NF4.
5. Models execute serially in isolated child processes. Only typed probabilities,
   factor summaries, stage identity, quantization, and resource telemetry return.
6. Optional-model failure never erases deterministic values or successful small
   estimates. Small-model GPU exhaustion retries once on CPU. Deep-lane failure is
   a typed diagnostic failure.

The historical immutable ten-stage committee graph remains readable for old
receipts, but it is not executed by the live v35 estimator.

### Resource contract

- supported target: 8 GB GPU-class VRAM and up to 16 GB system RAM;
- per-child ceilings: 6,144 MiB peak VRAM and 8,192 MiB RSS;
- one GPU child at a time; no simultaneous weights;
- at least 1.5 GiB VRAM reserved for display and runtime buffers;
- at most 2,048 tokens per semantic episode;
- Qwen 4B always runs in a disposable 4-bit child;
- CPU-only or 8 GB RAM operation disables the deep lane.

Synthetic local hardware verification recorded the complete all-twenty pass with
all five small specialists and the selective Qwen child below the VRAM ceiling.
This is resource evidence, not model-quality calibration. The current cold
serial pass is still roughly one minute on the reference machine; the desired
warm-update, cold-update, and deep-lane p95 targets remain promotion gates. A
future persistent warm-small-encoder worker must retain the same privacy and
resource boundaries before those latency targets can be claimed.

## Distribution contract

For every metric, v35 persists a predictive receipt beside, never inside, the
measured receipt. Its state is one of `Unavailable`, `Experimental`,
`Calibrated`, `Out of distribution`, or `Execution error`. It contains only:

- mean, median, q05, q25, q75, and q95;
- applicability and pending mass;
- model disagreement and effective observation count;
- model-set, calibration, contract, and quantization identities;
- a fixed 20-bin density and content-free factor contributions in the detail API.

The parent deterministically draws 1,024 samples through the exact factor and
metric aggregation and stores summaries, never samples or raw logits. Raw model
softmax is an experimental feature, not confidence. Temperature/Dirichlet
calibration, a non-negative out-of-fold stacker, and conformalized 90% intervals
become eligible one metric at a time only after the required project/time-separated
holdout gates pass. A cohort mismatch becomes `Out of distribution` and withholds
the calibrated claim.

Outcome metrics may have an experimental forecast band, but only fresh scoped
objective receipts can create a solid verified-outcome measurement.

## Persistence, API, and privacy

Schema v35 is additive. Existing v1-v34 receipt bytes and checksums are unchanged;
there is no predictive backfill. New normalized rows are immutable, content-free,
and privacy-cascade with secure-delete and WAL verification. Stored data includes
only pseudonymous digests, typed states, sufficient statistics, distribution
summaries, version identities, and resource telemetry. It excludes transcript
text, snippets, prompts, generated explanations, source identifiers, and raw
logits.

The full run and bounded watch trajectory contain compact predictive summaries.
The authenticated metric-detail endpoint exposes the fixed density and factor
contributions for one run/metric. Old/new geometry is comparable only when the
contract, model set, calibration, quantization, provider and content schemas,
redactor, and analysis scope match.

The mini-window provides project/session/window navigation, a stable four-lens
radar, an explicit **Analyze now** action, progress and stage resource receipts,
and a changed-publication trajectory. Opening the window alone grants no source
read. It keeps the last sealed snapshot through transient failures.

## Provider boundary

Adapters are read-only and capability-driven. Codex is the reference adapter.
A future Claude Code adapter must use its documented local interfaces and emit
the same provider-neutral envelope. Unsupported provider capabilities become
typed unknown states. No transcript or derived content is sent to a cloud model.

## Verification and honest rollout state

Implemented now:

- all twenty contract identities and predictive receipts;
- exact measured-versus-predictive separation;
- EN/PL small-model routing and English long-context challengers;
- selective 4-bit Qwen lane with child resource enforcement;
- immutable v35 persistence, trajectory and metric-detail API;
- fixed-axis solid/dotted/50%/90% radar rendering;
- tests for unknown-not-zero, objective precedence, exact ownership, model
  resource failure, API validation, migration, privacy, and visual semantics.

Still deliberately not claimed:

- calibrated model truth or product eligibility;
- a representative 100-example active-learning set plus untouched 200-example
  holdout for every metric;
- p95 warm update at three seconds and cold update at eight seconds;
- a production persistent 60-second warm encoder process;
- Claude Code and generic adapter SDK support;
- proof that quantized Qwen preserves quality across the complete factor suite.

Promotion is per metric. It requires the locked macro-F1, class-recall, ECE,
selective-risk, interval-coverage, outcome-false-positive, and mixture-improvement
gates. If the mixture does not beat the best calibrated single expert, the single
expert wins. Public trajectory datasets can support stress tests, but cannot
replace metric-matched calibration labels.
