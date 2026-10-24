# Architecture atlas

Audit date: 2026-10-08. This is a contributor map, not a beta certificate.

The October 24 [ACP schema candidate](../bench/robustness-experiment.md#revision-2-smoke-result-and-acp-schema-candidate---2026-10-24)
records the first revision-2 smoke failure and verified partial-result export.
Core 0.3.4 proposes forwarding the full schema as ACP guidance while retaining
strict parsing. A failing-before regression and 152 passing affected tests
supplement MA18/W02/W03/W07; source review, release and live qualification remain
open. The frozen observation and acceptance statuses remain unchanged.

The October 24 [core 0.3.3 qualification revision](../bench/robustness-experiment.md#revision-2-task-card---2026-10-24)
records the completed release/deployment prerequisites and prepares immutable
definitions for the 240-attempt matrix with separate NLI boundary smoke checks.
Bounded definition and synthetic integration evidence supplements MA18/W07;
review, confirmed recovery, live qualification and independent onboarding remain
open. The frozen observation and acceptance statuses remain unchanged.

The October 24 [Bench readiness correction](../bench/continuous-deployment.md#readiness-verification-correction---2026-10-24)
uses separate controller-health and authenticated Bench-revision checks. Bounded
synthetic and loopback evidence supplements R26/W02/W07; review and hosted
verification remain open, and acceptance statuses are unchanged.

The October 24 [NLI input admission candidate](../bench/nli-input-admission.md)
adds exact local paired-token checks and explicit unknown readings for oversized
inputs. Its synthetic tests and offline packaged probe supplement MA18/W03/W05/W07;
source review, release and live qualification remain open. The frozen observation
and acceptance statuses are unchanged.

The October 23 [Bench client/export candidate](../bench/client.md) adds a shared
API preflight, durable admission receipts and versioned private analysis tables.
Its synthetic recovery/CLI/export evidence supplements MA18/W02/W05/W07; live
qualification and independent onboarding remain open.

The October 23 [Bench handoff correction](../bench/handoff.md) propagates failed
workflow steps to execution failures and explains historical contradictions in
the UI. Its synthetic core/HTTP/storage/browser evidence supplements
MA18/W02/W05/W07; the dated observation and acceptance statuses remain unchanged.

The October 23 [Bench evaluator coverage candidate](../bench/evaluator-coverage.md)
records a versioned coding-cue correction and explicit unscored-result displays.
Its bounded synthetic evidence supplements MA18/W03/W05/W07 without changing
the frozen source observation, existing evaluator pins or acceptance statuses.

The October 18 owner-approved [development CI policy](../ci-quality-gate.md)
makes full backend/frontend, Bench browser/runtime and hosted-container checks
manual. Fast integrity/privacy and PR metadata checks remain automatic, with
definition checks for Experiment PRs and existing deployment validation retained.
The bounded scheduling checks supplement R26 without accepting release gates.

The October 18 [versioned workflow implementation](../bench/versioned-workflows.md)
records the owner-approved component/workflow split and fixed v2 experiment pins.
It preserves v1 history and documents the prompt-only Bench transport separately
from the extracted session workflow libraries. The frozen atlas observation and
broader workflow acceptance gates remain unchanged.

The owner's subsequent logic adjustment gives rewrite/clarification workflow
version `2.0.0` the pre-Bench score, context-inference and optional review/rewrite
sequence. The UI identifies their ordered steps and retains the old v1 Bench
flows under explicit legacy labels. Evidence is recorded in the same task guide.

The October 14 [core version resolution candidate](../bench/core-version-resolution.md)
and proposed [ADR 0026](../adr/0026-core-version-resolution-at-run-creation.md)
move Bench image binding to new-Run admission while retaining historical digests.
The bounded W02/W07/WP08 evidence does not change the frozen atlas observation or
accept general workflow/runtime gates. The core release workflow registers the
verified artifact for future Runs after its offline runtime probe succeeds.

The October 14 [CI path selection](../ci-quality-gate.md#scheduling-and-deployment-reuse)
uses a pinned GitHub Action and shared YAML filters for affected-component checks.
Experiment JSON selects contract/identity/privacy validation separately from
Bench browser, image and runtime verification.
Its bounded synthetic evidence supplements R26 without changing acceptance gates.

The October 14 [separate core publication task](../bench/core-publication.md)
records the optional manual core-release workflow and resolve-only Experiment
delivery. Its bounded synthetic evidence supplements W02/W07/WP08 tooling without
altering the frozen atlas observation or accepting broader runtime gates.

The October 14 [Bench stats preview correction](../bench/client-navigation.md#stats-preview-and-dedicated-charts---2026-10-14)
places a compact overview above list filters and moves full charts to dedicated
global/revision-scoped stats routes. Its synthetic evidence supplements W02/W05
presentation; aggregation, the frozen atlas observation and acceptance gates
remain unchanged.

The October 14 [Bench model and variation presentation](../bench/client-navigation.md#model-details-and-run-variations---2026-10-14)
adds visible configured/recorded model identities and a case-by-variant attempt
matrix to the owner-selected develop baseline. Its bounded synthetic backend and
browser evidence supplements W02/W05 presentation context; the frozen October 8
source observation, general workflow statuses and acceptance gates stay unchanged.

A later feature-branch proposal, [ADR 0024](../adr/0024-inference-provider-boundary.md),
separates inference providers from local runtime ownership. Its October 9 tests
and scope are recorded separately; the October 8 source observation stays frozen.

The October 12 [core/bench integration review](../bench/integration-review.md)
and proposed [ADR 0025](../adr/0025-enhancement-experiment-boundary.md) add a
versioned enhancement flow and private experiment bench. They record later
source, browser and container evidence separately from this dated atlas and do
not close the general workflow, real-model or release gates.

The October 13 [bench client navigation](../bench/client-navigation.md) candidate
adds dedicated experiment/run pages and schema-driven run forms, with local
synthetic evidence recorded in the readiness ledger. It preserves gateway-only
access and leaves this dated atlas and general workflow acceptance unchanged.

The October 13 [Experiment publication task](../bench/experiment-publication.md)
records the JSON push workflow and domain terminology correction. Its local
checks and observed automatic Run establish bounded publication evidence. The
Action ends at import acknowledgement; Test Bench owns execution and results.
Broader CI and owner review remain open. The dated atlas observation is unchanged.

The October 13 [Bench deployment Action](../bench/continuous-deployment.md)
reconciles the pending Bench source and deploys only the API/client from main.
Its focused evidence is recorded in the journal; broader acceptance is unchanged.

## Start here

The October 14 [Bench history filters and charts](../bench/client-navigation.md#history-filters-and-charts---2026-10-14)
add bounded metadata filters, activity/status charts and paired metric summaries
to the standalone Bench. The readiness ledger records local synthetic evidence;
this later W02/W05 presentation work does not alter the dated atlas observation
or accept the general workflow gates.

1. Read the [system map](../images/architecture-overview.png).
2. Find the component ID in the [feature catalog](feature-catalog.md).
3. Check its evidence level, source publication state and next acceptance step.
4. Use [change recipes](change-recipes.md) to identify the files and tests.
5. Take one [bounded task](remaining-work.md), with owner review before merge.

Designers should also read the [journey/state handoff](design-handoff.md).
For prompts, tool payloads and storage, read the [session-data lifecycle](session-data-lifecycle.md).
The explicit [team prompt-review requirement](../work-packages/team-prompt-review.md)
belongs to R30's planned product milestone, not delivered functionality.

The [readiness matrix](../product-readiness-matrix-2026-09-12.md) remains the
authority for requirement acceptance. This atlas is a dated projection of code,
existing tests and that ledger. The [journal](../beta-progress-journal.md) records
execution history. Accepted architecture decisions live in [ADRs](../adr/README.md).
Updating this map never closes a gate by itself.

## Read the colors correctly

| Color | Meaning | What it does not establish |
| --- | --- | --- |
| Green — ready | The bounded component contract has recorded passing evidence; read the node's evidence scope. | Full user journey, every model, installation or beta approval. |
| Yellow — partial | Real implementation exists but a required integration, qualification, correction or acceptance step remains. | A mock, or proof the complete journey works. |
| Red — absent | The stated capability is planned but its required implementation/composition is absent. | That all supporting libraries or seams are absent. |
| Grey — mock | Deliberately synthetic/demo/test implementation. | A usable production integration. |

Color is independent of scope: required, experimental or deferred. A deferred
feature can have real partial code; an experimental feature is not automatically
a mock. Labels repeat the colors so the diagrams remain usable without color.
No percentage of green nodes is a release-completion percentage.

## Which source was inspected?

Two baselines are deliberately distinguished:

- Published source reference: `origin/main` at `bfb67b6`, freshly fetched on the
  audit date. The private repository metadata was checked separately.
- Development observation: `acdf0e5` plus 747 preserved changed/untracked files.
  This is not a clean commit or a distributable artifact. A separate five-file
  setup-recovery cohort is also uncommitted and was not included in this branch.

The catalog binds referenced implementation/test files to SHA-256 values and
reports whether each path is identical after CRLF-to-LF normalization, different from, or absent on the
published baseline. A path existing on main does not imply identical behavior.
Unpublished paths are shown as code text rather than broken clickable links.
`sha256` binds exact observed bytes; `normalized_sha256` binds LF-normalized text;
`main_sha256` binds Git blob bytes. Different raw hashes can therefore have the
same normalized content. No other semantic normalization is applied.
The documentation branch carries this map and its rendering tooling only;
it does not secretly publish those pending implementations.

## System shape and design patterns

Prompt Enhancer is a local modular monolith with explicit adapters around
provider access, SQLite, model runtimes, HTTP/MCP, native windows and filesystem
effects. `bootstrap.py` composes the backend; the HTTP app mounts bounded routes.
The React shell selects feature slices and uses shared API/platform adapters.
This is the governing pattern, not a claim that every file follows it perfectly.

Three execution lanes must stay distinct:

| Lane | Input and authority | Persistence and output |
| --- | --- | --- |
| Analytics | Consented, read-only provider signals; minimized/redacted before ordinary storage. | Versioned evidence, metrics and provenance; unknowns remain states. |
| Authored Agent | User's selected workspace and local chat; protected operations require exact native approval. | Private project/chat store and verified tool/artifact receipts. |
| Multimodel workflows | Planned typed local graphs; immutable revision and input bindings, bounded owned workers. | Planned private run/attempt/artifact store; explicit reviewed export. |

The trusted metric dependency graph is implemented analysis infrastructure.
It is **not** the planned user-editable multimodel workflow graph. The existing
project automation scheduler is also not that workflow engine.

Important patterns already present include ports/adapters, typed DTO boundaries,
explicit composition, consent/capability checks, immutable analysis snapshots,
optimistic revision checks, single-use approval receipts, owned subprocesses,
and separate command/query projections over SQLite. The design uses ordinary
transactional state; it is not universal event sourcing or microservices.

## Data and authority boundaries

Provider sessions remain external, read-only inputs. Authored Agent history is a
different store and retention decision. Model outputs are interpretations, not
objective evidence. Native presence cannot be synthesized by browser tests,
API clients or MCP. A model name in a catalog is not proof of genuine inference.

The runtime owner must confirm process-tree exit before releasing authority or
resource leases. Planned workflow workers must coexist with chat/research
runtimes without silently changing their selected model. Update evaluation and
signature verification are separate from executing an installer.

## What this audit validates

Static source/route/test inventory, source publication comparisons, design
consistency, documentation links, diagram/catalog consistency, and selected
synthetic contract/privacy checks. Existing dated runtime evidence is identified
as historical. No private provider data, personal app, GPU model, installation,
certificate trust or real update was used during this documentation audit.

See [validation](validation.md) for exact results and limits. There is no claim
that every source function or every UI state was dynamically exercised.

## Domain diagrams

Each PNG is readable without Mermaid. SVGs are editable and link node IDs to the catalog.

| Domain | PNG | Editable SVG |
| --- | --- | --- |
| System | [Overview](../images/architecture-overview.png) | [SVG](../images/architecture-overview.svg) |
| Analytics | [Pipeline](../images/architecture-metrics.png) | [SVG](../images/architecture-metrics.svg) |
| Twenty metrics | [Contracts](../images/architecture-contracts.png) | [SVG](../images/architecture-contracts.svg) |
| Agent | [Chat, tools, MCP](../images/architecture-agent.png) | [SVG](../images/architecture-agent.svg) |
| Workflows | [Engine and model families](../images/architecture-workflows.png) | [SVG](../images/architecture-workflows.svg) |
| Composer | [Workflow enhancement](../images/architecture-composer.png) | [SVG](../images/architecture-composer.svg) |
| Distribution | [Native and release](../images/architecture-release.png) | [SVG](../images/architecture-release.svg) |

The [route and source census](surfaces.md) covers all declared route families,
feature directories and HTTP route modules, including large-file hotspots.

## Maintaining the atlas

`atlas.json` is the editable graph/catalog input. It records component IDs,
dependencies, source/test references, status, scope, gap and next action.
`source-observation.json` is a generated, content-free source binding and census.
The generated catalog and PNG/SVG diagrams derive from those inputs.

After implementation, update the authoritative ledger first, then the affected
atlas nodes and evidence. Regenerate and review diagrams; changed PNGs need exact
hash approval in the existing privacy scanner. Do not add broad image exclusions.
The repository skill routes an agent through this workflow:
[prompt-enhancer-development](../../.agents/skills/prompt-enhancer-development/SKILL.md).
