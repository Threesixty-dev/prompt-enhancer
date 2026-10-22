# Integrated model experiment preparation

Status: core 0.3.0 release candidate; no core artifact or experiment published.
Date: 2026-10-22.

## Task and baseline

Complete gateway evaluator coverage for the existing versioned Prompt Check,
Clarification and Rewrite experiments. The task branch starts from the selected
develop baseline at `65372e4`. The earlier embedding/classifier adapter prototype
is preserved in its original worktree and continued here. Existing desktop and
Bench runtime changes outside this branch are not part of the candidate.

Affected components: enhancement core evaluator composition, bounded gateway
transport and the shared execution/capability schemas. Relevant atlas boundaries
are W03/W07; this experiment does not close product or hardware qualification.

## Fixed comparison

Retain the six authored synthetic subjects and two policy variants from each of
the three existing workflow experiments: 12 attempts per workflow, 36 total.
Keep `codex-consumer` as the generation binding. Use one evaluator profile across
siblings and both original/candidate passes. Evaluation does not feed back into
the versioned prompt workflow.

| Role | Intended binding | Observation |
| --- | --- | --- |
| Generation | Existing dedicated Codex consumer | Workflow review/rewrite |
| Deterministic evaluation | `deterministic.v1` | Six existing prompt dimensions |
| Embedding evaluation | Pinned Qwen3 Embedding 0.6B gateway route | Cosine against an explicit synthetic target |
| NLI evaluation | Pinned mDeBERTa XNLI gateway route | Entailment, neutral or contradiction |
| Rerank evaluation | Pinned BGE reranker v2 M3 gateway route | Query/document pair relevance score |
| Independent rubric evaluation | Pinned Qwen3 4B gateway route | Acceptance-testability rubric label |

Qwen embeddings are the approved model choice for this run. The earlier plan's
MiniLM L6/L12 comparison is a different model choice; do not describe these runs
as that comparison. The model choice must be fixed in the imported revision.

For this coverage pilot, each original subject explicitly requests a patch and
tests. The shared synthetic target can therefore be "Provide a code patch and
unit tests for the requested change." NLI uses the declarative hypothesis "The
requested deliverables include a code patch and unit tests." These targets test
a shared deliverable dimension, not complete preservation of every case's
requirements. A later preservation study needs case-specific adjudicated targets.

## Implemented boundaries

- Embeddings and reranking use typed request bodies with fixed paths. The
  operator configures endpoints and credentials; experiments select aliases.
- Gateway model IDs may bind responses to the intended LiteLLM route. Missing
  or different route headers fail before accepting a response. This verifies
  routing, not the bytes of the remote model's weights.
- Unrecognized upstream model names, including possible weights paths, are not
  retained when route verification is configured. Reported model identity stays
  unknown; configured revision/license provenance remains explicitly configured.
- NLI uses Xinference's native paired-text interface with top-level `top_k: null`
  and `truncation: false`. It validates all three distinct labels and finite
  normalized scores before selecting a unique maximum. Missing or tied results
  remain unknown. The native response does not report model provenance.
- Reranking evaluates the candidate as one document against the explicit target.
  The finite score is descriptive and uncalibrated; it is not a probability or
  proof of requirement preservation. Ranking a collection of session candidates
  remains a separate workflow.
- Vectors and returned documents do not enter evaluator results. Known values,
  unknown values, categorical labels, abstentions and execution errors remain
  distinct. Before/after deltas require matching provenance.

## Release and execution prerequisites

The published `0.2.0` core lacks these adapters and the rerank evaluator kind.
The owner authorized the `0.3.0` release plan. Compatibility is included in each
workflow's immutable digest, so the unchanged prompt logic receives new manifest
versions: Prompt Check `1.1.0`, Clarification and Rewrite review `2.1.0`. All
earlier manifests and experiment pins remain intact.

1. Review and promote the `0.3.0` candidate and its generated contracts.
   The default dependency variant is sufficient for remote inference;
   model execution stays on the configured model server.
2. Publish and verify the immutable core artifact through Publish Core.
3. Deploy the matching Bench shared-contract bundle so API/worker admission
   recognizes the added rerank kind. Configure the worker's explicit evaluator aliases, model revisions,
   licenses, tokenizer revisions and current gateway route IDs. Qualify these
   exact bindings through the core, including its gateway access layer.
4. Create new revisions/generations of the three experiment definitions with
   the new core digest and fixed full evaluator profile. Preserve existing runs.
5. Keep the existing 180-second attempt limit and 4,000-character generation
   bound for the first preflight. Confirm model input limits for both evaluation
   passes; do not silently truncate an overlong rewrite. Measure actual stage
   durations before proposing any timeout change.
6. Run one preflight per workflow, then the remaining approved matrix after
   complete evaluator coverage is established.

Execution completion, evaluator coverage and assertion outcomes are separate.
The two existing deterministic nonregression assertions remain unchanged.
Categorical NLI/rubric observations do not become numeric assertions. Do not
add uncalibrated embedding/rerank thresholds merely to obtain a passing result.
Report every missing, unknown, abstained or failed evaluator explicitly.

## Evidence scope

Validation on 2026-10-22: 404 affected core, contract, workflow, transport and
Bench tests passed, including the loopback TLS tests. All eight retained
experiment definitions passed canonical validation. The repository privacy
scanner and whitespace diff check passed. Historical workflow digests remain
unchanged; new compatibility manifests preserve the same logic payloads.

Live gateway checks passed for chat, two finite 1,024-dimensional embeddings,
and two reranker scores with the relevant document first. Each response matched
its expected gateway route ID. The native NLI route returned valid three-label
probabilities and the expected class for entailment, neutral and contradiction
fixtures; an unauthenticated request was rejected with HTTP 401. The other three
routes were checked again successfully after NLI loaded.

The synthetic tests exercise typed transports, route-header refusal, malformed
vectors/scores, native NLI parsing, composition, and one shared core execution
with all five evaluator kinds before and after generation. Mocked responses
establish contract behavior only. Live gateway readiness and an actual Bench
experiment run are separate requirements; no such run is claimed by this file.

The live NLI check also exposed a gateway configuration distinction: the tested
API-created pass-through route did not resolve an environment-reference header.
Resolving the existing credential within the gateway and saving the supported
header value made inference succeed. That saved header needs an explicit update
when its upstream credential rotates. No credential belongs in this document,
experiment definitions, source control or verification output.
