# Versioned core components and workflows

The owner-approved design is [ADR 0027](../adr/0027-versioned-core-components-and-workflows.md).
The source candidate is core `0.3.0`; publication and runtime qualification are
separate. Existing experiment files, definition identities and run snapshots are
not rewritten.

## Boundaries

| Layer | Owns | Does not receive |
| --- | --- | --- |
| `core/` | Prompt metrics/cues, context inference, review formatting/parsing, clarification, session factor selection/projection, pair-score validation | Session discovery, application configuration or persistence |
| `workflows/` | Fixed composition, branching, defaults, supported settings, workflow identity | Harness evaluations, assertions or their results |
| Configured adapters | Provider/model aliases, typed calls, process lifetime and cleanup | Request-supplied endpoints, credentials or executable steps |
| Bench execution wrapper | Before/after judging, assertions, timing, cancellation and durable results | Authority to change the selected workflow's implementation |
| App wrapper | Consent, redaction preview, source access and metrics-only persistence | Automatic publication or replacement of user drafts |

The Prompt Check app uses the extracted components through compatibility imports.
The existing session-analysis runner and session-link adapter use the extracted
workflow compositions. `PromptWorkflowRunner` can also be called directly with
`PromptWorkflowInput`; its input type contains no harness configuration.

## Available compositions

| Workflow | Version | Steps | Input/output |
| --- | --- | --- | --- |
| `prompt-check` | `1.0.0` | Score prompt, infer context, optional model review/rewrite | Prompt/context -> diagnostics, findings and optional rewrite |
| `prompt-rewrite` | `2.0.0` | Score prompt, infer context, optional model review/rewrite | Same review contract; default policy focuses on clearer wording and testability |
| `prompt-clarify` | `2.0.0` | Score prompt, infer context, optional model review/rewrite | Same review contract; default policy focuses on missing details and clarification questions |
| `session-analysis` | `1.0.0` | Select factors, three sequential NLI steps, conditional adjudication, projection | Prepared redacted chunk plan -> experimental metric receipt |
| `session-links` | `1.0.0` | Embedding, reranking of the same pairs, validation | Prepared pairs -> model scores |

All three current prompt workflows follow the pre-Bench logical sequence. The
review sees the same deterministic findings and inferred context, uses one model
call and may return findings without a rewritten prompt. Their default policies
express different review goals. No configured model yields diagnostics/context
only. No classifier, embedding or reranker is added to prompt enhancement.

The earlier `prompt-rewrite` version `1.0.0` (score -> direct rewrite) and
`prompt-clarify` version `1.0.0` (score -> deterministic placeholders) remain available for
existing pins with their original digests and behavior. The UI labels them
**Direct rewrite (Bench legacy)** and **Rule-based clarification (Bench legacy)**.
Current labels are **Prompt Check (pre-Bench flow)**, **Rewrite review (pre-Bench
flow)** and **Clarification review (pre-Bench flow)**. Experiment, run setup and
result pages display the ordered logic steps. Use a new experiment revision to
adopt an adjusted workflow; no existing definition is migrated automatically.

Bench's current text-subject transport exposes the three prompt workflows.
The session workflows remain library/app compositions with their existing typed
inputs. They are not coerced into prompt rewrites or advertised as executable by
the text-subject Bench endpoint. A future session-input transport needs its own
contract and harness evaluation; it can reuse these components and workflows.

Prompt workflow manifests live in `workflows/catalog.py` and are exported to
`contracts/enhancement/workflows.json`. Each manifest includes exact step
implementations, input/output contracts, defaults, allowed configuration slots,
compatible core range and a definition digest. A changed manifest needs a new
workflow version. Catalog presentation labels are separate from the behavior
digest, so clearer wording does not rebind historical workflows. A changed core
build needs a new core version. The prompt workflow versions support stable
`0.2.x` cores; an experiment still pins one exact
version and image. Session workflows expose independent version and step metadata
on their classes; their existing result contracts are preserved.

Core `0.3.x` adds gateway harness evaluators without changing prompt workflow
logic. Its manifest versions are Prompt Check `1.1.0`, direct rewrite and
rule-based clarification `1.1.0`, and review rewrite/clarification `2.1.0`.
The compatibility range is part of the digest, so these are new manifests rather
than changes to existing pins. The catalog retains every `0.2.x` manifest for
historical Bench definitions; the current core rejects incompatible older pins.

## Experiment contract

Use `bench-experiment/v2` for the new boundary:

- `workflow`: workflow ID, exact version and definition SHA-256 from the catalog.
- `enhancerVersion`: exact core version.
- `coreBuild`: immutable image digest, dependency variant and verified build-input
  SHA-256 from a registered core release receipt.
- `evaluatorProfile` and `harnessAssertions`: fixed for the experiment revision.
- `units`: variants of this one workflow. Their strategy must match its manifest.
- `baseStepSettings` and unit `stepSettings`: model/provider binding, versioned
  policy instructions and generation parameters for declared model steps.

The existing parameters, objective and steering fields remain supported where
the selected workflow uses them. All pre-Bench-flow versions use the `review`
step's policy and reject the legacy objective/steering controls. Their fixed
strategy is `prompt.check.v1`; the workflow reference distinguishes their default
policies. Legacy v1 rewrite/clarification numeric objective targets refer to
internal evaluator ID `diagnostics`, never to
the harness evaluator IDs. A step cannot replace its implementation or add other
steps. Model aliases resolve through the core's explicit configuration.

`unitStepSettings` is the run-override map. Fields merge within each step;
`binding`, `policy` and `generation` objects replace whole objects. A null step
field inherits the workflow/experiment setting. Inside a generation object, an
explicit null `max_tokens` or `temperature` remains provider-managed. Omitted
review controls use the pre-Bench defaults (1100 tokens, temperature 0.2,
thinking disabled); the actual values are recorded in its step receipt. An
explicit null step `enable_thinking` leaves that control to the provider. ACP
rejects token/temperature/thinking controls it cannot enforce; select explicit
nulls when using that provider.

The browser displays fixed pins and exposes only supported settings. Changing a
workflow, core build or harness evaluation requires a new experiment revision
and generation. Model/evaluator roles remain explicit; a deterministic evaluator
does not invoke an LLM.

`bench/examples/example-versioned-review.json` is an offline authoring example:
one fictional case, one review variant, a fictional model alias and image digest,
deterministic harness evaluation, and `autoRun: false`. It is outside automatic
publication. `example-versioned-rewrite.json` and
`example-versioned-clarify.json` demonstrate the adjusted `2.0.0` workflows with
the same offline restrictions. Their artifact and model bindings are not
runtime-qualified.

## Results and compatibility

Workflow diagnostics and their provenance live in `workflow_result`, separately
from harness `before`, `after`, `deltas` and assertions. Prompt Check preserves the
pre-Bench instructions, rich cue fractions, context selection and strict response
parser. A valid review may have no rewrite. No candidate is fabricated in that
case: after measurements are absent, deltas/assertions remain unknown. Invalid
review replies retain diagnostics with `reply_invalid`; confirmed model failure
retains `model_error`. The [handoff correction candidate](handoff.md) propagates
these failed steps to an execution failure while preserving the receipt and
completed before measurements. Historical results keep their stored status; the
candidate UI explains a nested failure even when that status says succeeded.
Uncertain remote execution and cancellation still follow
the execution manager's cleanup/quarantine policy. The newer redactor's privacy
fix is intentionally retained.

The v1 enhancement protocol gains optional workflow fields. Legacy requests
without them keep their historical evaluate/generate/evaluate behavior, including
the original generation context. New requests require matching workflow
capabilities, version and digest. Result validation checks the workflow reference
and effective settings as well as the existing identity and text hashes.

Database schema 3 adds an immutable artifact receipt archive. It does not rewrite
definitions, request hashes or run snapshots. v2 import verifies the exact pinned
receipt, and later runs keep that image even when the version catalog points at
a replacement. v1 definitions retain their previous run-time resolution rules.

## Local validation - 2026-10-18

Owner-requested logic alignment follow-up:

- All 372 affected core/Prompt Check/Bench tests pass. The final policy-version
  correction for a skipped review passes 62 focused regression checks.
- All 48 desktop/mobile browser checks pass, including flow names, ordered steps,
  new review-model controls, result pages and retained legacy presentation.
- Each of the three review workflows matches the same six pre-Bench synthetic
  cases for scores, inferred context and model-facing input. The two new defaults
  add an explicit rewrite/clarification focus to the original review policy.
- Six offline experiment definitions validate. Existing v1 workflow digests and
  logical behavior have explicit regression coverage. Privacy/OpenAPI, JavaScript
  syntax, shared-schema, architecture-generation and whitespace checks pass.

Earlier component-extraction evidence (overlapping suites, not additive):

- Affected backend suites: 517 passed, two Windows-specific owned-process tests
  skipped. One existing `SyntaxWarning` remains. A focused
  follow-up after the legacy message-bound and malformed-parameter corrections
  passes 111 tests; these overlapping runs are not added together.
- Bench browser suite: 42 passed across desktop/mobile using installed Chrome.
  Four workflow checks also pass after the final schema export.
- Pre-Bench parity: six authored synthetic cases were evaluated against Prompt
  Check source at `6fa1100e01e37f477ca7b65daba51706927f2502`. Metrics, inferred
  context, model-facing input and policy SHA match. The newer redactor remains
  the intentional privacy difference; no model quality equivalence is claimed.
- Integration: a synthetic Bench worker reaches the real core HTTP application,
  persists its result and confirms cleanup using an in-process HTTP transport
  and synthetic container runtime. A separate owned loopback CLI smoke passes.
- Four synthetic definitions, JavaScript syntax, exported shared contracts,
  architecture generation, repository privacy scanning and whitespace checks
  pass. Legacy definition serialization, migration and immutable v2 build pins
  have regression coverage.

All inference is synthetic. These checks do not qualify a model, a deployed
container, session-input Bench execution or the general workflow product gates.
The standalone prompt runner relies on its caller for timeout/process ownership;
Bench supplies that boundary through the execution manager and provider adapters.

## Task card

Task ID / atlas nodes / gates: versioned-workflows; MA18, W01-W08, WP01-WP08.
Baseline: owner-selected develop `dbd5bf1c1164593245b3d7e7286849b251687354`.
Outcome: reusable components and versioned prompt workflows with fixed experiment
bindings and independent harness judgments. Existing app/privacy contracts stay
compatible through the extraction.
Allowed changes: core/workflows, compatibility imports, shared contracts, Bench
definition/store/protocol/form integration, synthetic tests and documentation.
Evidence scope: offline synthetic unit/integration, historical Prompt Check
golden fixtures, immutable migration, owned loopback HTTP and browser tests.
No actual models, production databases, provider sessions or deployments are used.
Completion: targeted suites, synthetic privacy checks, exported schemas, existing
definition validation and responsive Bench browser checks pass.
Owner decisions: source review, final release version and publication remain
separate. No source publication, release, deployment or merge is performed here.
Broader generic session-input Bench, real-model, device and W/WP product gates
remain open; this bounded implementation does not claim those capabilities.
