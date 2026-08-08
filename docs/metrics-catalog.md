# Metric catalog

Status: proposed definitions 0.1
Last reviewed: 2026-08-06

## Measurement rules

Every displayed value must carry:

- definition/version and unit;
- observation window and task type;
- source (`provider_reported`, `deterministic`, `human_label`, `classifier`, `llm_judge`, or `estimated`);
- coverage and missing count;
- uncertainty/confidence where applicable;
- privacy tier and model/redactor provenance;
- comparison baseline, if a delta is shown.

Evidence tiers:

- **A — operational evidence:** provider events, executable verification, VCS/CI facts, explicit human feedback.
- **B — calibrated inference:** a model or heuristic validated on representative in-domain data with an abstention path.
- **C — exploratory signal:** plausible coaching/research feature that must not influence a success score or people decision.

Privacy tiers:

- **P0:** content-free metadata.
- **P1:** locally redacted text or sensitive derived data.
- **P2:** raw local content; encrypted vault only.
- **P3:** redacted content approved for a named remote analysis run.

`unknown` is a valid value. It must never be silently converted to `0`, `false`, `failed`, or `completed`.

## Implemented P0 task metric pack

The initial `core.metadata.task` pack is deterministic, metadata-only, and
versioned independently from the broader research catalog. It currently emits:

| Key | Unit | Unknown rule |
|---|---|---|
| `task.workflow.session_count` | count | task revisions without sessions are rejected |
| `task.workflow.observed_event_count` | count | coverage is partial until every event stream is complete |
| `task.efficiency.cycle_time_ms` | milliseconds | unknown until every assigned session has an end time |
| `task.verification.observed_count` | count | coverage is partial until every event stream is complete |
| `task.verification.pass_rate` | ratio | unknown when no verification result is known |
| `task.usage.input_tokens` | tokens | unknown when no input-token observation is available |
| `task.usage.output_tokens` | tokens | unknown when no output-token observation is available |
| `task.usage.total_tokens` | tokens | unknown when no total-token observation is available |

Every run fingerprints the complete safe metadata snapshot and preserves its
engine, metric-pack, schema, evidence, and redactor provenance. A changed input
requires a new immutable run; reusing a retry key with changed evidence conflicts.

## Task and outcome semantics

Provider terminal state and task success are different:

```text
execution_state ∈ {completed, interrupted, failed, blocked, abandoned, unknown}
acceptance_state ∈ {accepted, partially_accepted, rejected, reopened, unknown}
verification_state ∈ {passed, failed, mixed, not_run, unknown}
```

An assistant message saying “done” changes none of these by itself.

Suggested evidence precedence:

1. explicit user acceptance/reopen/rejection;
2. CI, tests, build, lint, security checks, or artifact validators;
3. downstream merge/revert/incident evidence;
4. structured provider/tool terminal state;
5. calibrated requirement/evidence model;
6. LLM judge;
7. assistant self-report.

Do not compress the states into one success scalar in the MVP.

## A. Outcome and delivery evidence

| Metric | Tier | Privacy | Definition | Main caution |
|---|---:|---:|---|---|
| Execution state | A | P0 | Provider/task terminal state with end reason | Completion is not correctness |
| Acceptance state | A | P0 | Explicit user/UI/issue/PR acceptance, partial acceptance, rejection, or reopen | Often missing; unknown is expected |
| Verification state | A | P0 | Final observed executable checks: passed, failed, mixed, not run, unknown | A narrow test suite is incomplete evidence |
| Verification pass ratio | A | P0 | Passed checks / checks with observed outcomes | Weighting very different checks equally can mislead |
| First-pass verification | A | P0 | Whether the first meaningful verification after implementation passed | Normalize by task/check type |
| Requirement coverage | B | P1 | Requirements linked to at least one delivered artifact/action / extracted requirements | Requirement extraction errors propagate |
| Evidence-backed requirement coverage | B | P1 | Requirements with strong verification evidence / extracted requirements | “Action taken” is weaker than verified |
| Acceptance-criteria pass ratio | A/B | P0/P1 | Criteria with observed passing evidence / criteria with evaluable evidence | Unevaluable criteria remain unknown |
| Artifact completeness | A/B | P0/P1 | Required artifacts observed and nonempty / artifacts requested | Presence does not prove quality |
| Reopen rate | A | P0 | Accepted tasks later reopened / accepted tasks with follow-up visibility | Requires a defined observation window |
| Revert rate | A | P0 | Delivered changes substantially reverted in window / delivered changes | Reverts can reflect changed requirements |
| Escaped-defect proxy | A | P0 | Post-acceptance defect/failing check linked to the task | Linkage is imperfect and lagged |
| Delivery confidence | B | P1 | Calibrated probability from evidence features, with abstention | Never present as guaranteed correctness |
| LLM fulfillment judgment | C | P1/P3 | Dimension-specific rubric with cited evidence spans | Judge bias; cannot override A-tier evidence |

## B. Time, token, and cost efficiency

| Metric | Tier | Privacy | Definition | Main caution |
|---|---:|---:|---|---|
| Cycle time | A | P0 | Task/session end minus start | Includes breaks unless activity is segmented |
| Active time | A | P0 | Provider-reported active time or union of active event intervals | Provider definitions differ |
| Waiting time | A/B | P0 | Cycle time minus active time and known user-away intervals | Estimated if presence is unavailable |
| Time to first action | A | P0 | First tool/action timestamp minus first user request | Planning before action can be valuable |
| Time to first verification | A | P0 | First meaningful check timestamp minus first implementation action | Research/design tasks may have no executable check |
| Verification-to-finish time | A | P0 | Task end minus first verification | Large values can show rework or thoroughness |
| Turns per task | A | P0 | User/assistant turns within the normalized task boundary | Provider turn semantics differ |
| Input tokens | A/B | P0 | Provider-reported input tokens; tokenizer estimate only as a separately labeled fallback | Never mix reported and estimated series |
| Cached input tokens | A | P0 | Provider-reported cache-read input tokens | Not all providers/surfaces expose it |
| Cache creation tokens | A | P0 | Provider-reported cache-write/creation input tokens | Provider-specific category |
| Output tokens | A/B | P0 | Provider-reported output tokens or labeled estimate | More/fewer output tokens is not inherently better |
| Reasoning output tokens | A | P0 | Provider-reported reasoning category, if exposed | May be unavailable or non-comparable |
| Cache hit ratio | A | P0 | Cached input / (uncached input + cached input), with provider semantics | Exclude records with unknown categories |
| Tokens per accepted task | A | P0 | Total reported tokens / accepted tasks within one task stratum | Undefined when acceptance is unobserved |
| Verified outcomes per 1M tokens | A/B | P0 | Count of tasks meeting specified evidence threshold / tokens | Must report threshold and task mix |
| Estimated cost | B | P0 | Provider-reported cost or versioned price table × token categories | Subscription tokens are not API cost |
| Cost per accepted task | B | P0 | Estimated/provider cost / accepted tasks within stratum | Same acceptance/task-mix caveats |
| Tool latency p50/p95 | A | P0 | Distribution of completed tool durations | Split by tool and environment |
| Model/API latency p50/p95 | A | P0 | Provider request/turn latency distribution | Network and provider load dominate |
| Critical-path duration | B | P0 | Longest dependency path in the event graph | Requires reliable concurrency edges |
| Parallelism utilization | B | P0 | Concurrent useful work time / available concurrent capacity | High parallelism can create duplicate work |
| Inference-cache hit ratio | A | P0 | Reused analysis runs / eligible runs | Cache correctness depends on complete version key |

Efficiency comparisons must be stratified by task type and complexity. “Fewer tokens” is not a goal when it lowers verified outcomes.

## C. Workflow, flow, and rework

| Metric | Tier | Privacy | Definition | Main caution |
|---|---:|---:|---|---|
| Tool failure ratio | A | P0 | Failed tool calls / calls with known outcomes | User cancellation and expected negative tests need separate codes |
| Retry density | A/B | P0/P1 | Semantically equivalent repeated actions / action count | Similar actions may target different hypotheses |
| Correction turns | B | P1 | User turns that correct a prior agent assumption/output | Classifier needs human calibration |
| Clarification turns | B | P1 | Agent questions that resolve missing task information | Clarification can be good, not failure |
| Preventable clarification ratio | C | P1 | Clarifications attributable to prompt omissions / clarifications | Counterfactual and subjective |
| Test-fix cycles | A/B | P0 | Alternations from failing verification to changes to re-verification | Phase segmentation must be versioned |
| Time in failing state | A | P0 | Time between first failing check and the next passing equivalent check | Equivalent-check mapping can be hard |
| Edit churn | A/B | P0 | Added + removed lines over net delivered change, with zero-net handling | Generated/moved files inflate counts |
| Revert/undo ratio | A/B | P0 | Agent-authored changes later reversed within the task / changes | Legitimate exploration is not waste |
| Reopened-file ratio | A | P0 | Files edited in separated phases / files edited | Some central files are expected hotspots |
| Read-before-write ratio | A | P0 | Modified files with a prior observed read / modified files | Provider may not expose implicit IDE context |
| Verification share | A | P0 | Verification-related active time or events / total active time/events | A target ratio is task-dependent |
| Generation-to-verification ratio | A | P0 | Implementation actions / verification actions | Not a quality score |
| Plan-to-action latency | A | P0 | First implementation action minus plan completion | Some tasks require no explicit plan |
| Plan revision count | A/B | P0/P1 | Material plan changes per task | Revisions can indicate learning |
| Decision reversal count | B | P1 | Explicit decisions later reversed without requirement change | Requires temporal/scope-aware state tracking |
| Scope expansion count | B | P1 | Actions/artifacts not traceable to a request, requirement, or needed verification | Hidden dependencies may justify expansion |
| Context compactions | A | P0 | Provider-observed compaction events per task | Context-window sizes differ |
| Compaction timing | A | P0 | Token/turn position and phase at each compaction | Missing token fields reduce comparability |
| Post-compaction recovery cost | B | P1 | Repeated context/restatement/actions after compaction | Causal attribution is uncertain |
| Approval denial ratio | A | P0 | Denied approval requests / approval requests | Strict policies can intentionally raise it |
| Blocked-time ratio | A/B | P0 | Time awaiting permission/user/external state / cycle time | Provider states may be incomplete |
| Handoff completeness | B | P1 | Required summary/evidence fields present at agent/subagent handoff | Rubric is workflow-specific |
| Process conformance | B | P0/P1 | Distance from a task-type reference process, using process mining | Deviations can be beneficial innovations |
| Bottleneck contribution | B | P0 | Share of cycle time attributable to a phase/tool/state | Show confidence and overlaps |

## D. Prompt structure and specification quality

These dimensions describe the request. They do not describe the user's intelligence or worth.

| Metric | Tier | Privacy | Definition | Main caution |
|---|---:|---:|---|---|
| Goal explicitness | B | P1 | Presence and clarity of the desired outcome | Short conversational follow-ups inherit context |
| Context sufficiency | B | P1 | Required background available at decision time | Only observable context can be scored |
| Constraint coverage | B | P1 | Detected relevant constraints that are explicit | “Relevant” depends on task type |
| Acceptance-criteria presence | A/B | P1 | Explicit observable completion conditions | Not every exploratory task should have fixed criteria |
| Output-contract presence | A/B | P1 | Requested artifact, format, location, audience, or interface | Inherited conventions may supply it |
| Input/artifact grounding | A/B | P1 | Referenced files, URLs, examples, errors, or datasets available to the agent | Availability differs from relevance |
| Requirement atomicity | B | P1 | Requirements separable into independently traceable clauses | Over-splitting harms meaning |
| Decomposition quality | B/C | P1 | Dependencies and subgoals form a coherent solvable sequence | LLM rubric needs task-stratified validation |
| Ambiguity density | B | P1 | Ambiguous terms/clauses per requirement or 100 tokens | Domain shorthand may be precise to experts |
| Unresolved-reference count | A/B | P1 | Pronouns/placeholders/“that thing” without a resolvable antecedent | Dialogue context must be included |
| Contradictory-constraint candidates | B | P1 | Scope/time-aware NLI or invariant conflicts | Candidate, not proven contradiction |
| Priority explicitness | A/B | P1 | Conflicting goals have stated priority/tradeoff | Absence matters only when conflict exists |
| Safety/privacy constraint presence | A/B | P1 | Relevant data/action safety boundaries are explicit | Do not reward boilerplate unrelated to task |
| Assumption budget | B | P1 | Material unspecified choices the agent must infer | Some autonomy is intentional |
| Example usefulness | B | P1 | Examples cover edge/format/behavior cases without conflicting with rules | More examples are not always better |
| Prompt novelty | B | P1 | Distance from the user's prior prompts within task strata | Novelty is not quality |
| Prompt length | A | P1 | Tokens/characters after redaction | Display as context only, never a quality score |
| Template adherence | A/B | P1 | Required template fields present and internally consistent | Only applicable when a template is chosen |
| Verifiability | B | P1 | Fraction of requested outcomes that admit observable evidence | Research/creative tasks need different evidence |
| Requirement change rate | A/B | P1 | Added/changed/removed requirements over turns | Legitimate discovery must be distinguished from drift |

## E. Conversation logic, coherence, and traceability

| Metric | Tier | Privacy | Definition | Main caution |
|---|---:|---:|---|---|
| Requirement-to-action traceability | B | P1 | Requested requirements linked to implementation/research actions | Similarity alone is not causation |
| Action-to-evidence traceability | B | P1 | Material actions linked to checks/artifacts/review evidence | Some non-code actions lack executable checks |
| Unsupported-claim ratio | B | P1 | Outcome/factual claims without a cited event, artifact, or source | Evidence extraction coverage matters |
| Scoped contradiction candidates | B | P1 | NLI conflicts after conditioning on time, branch, environment, speaker, and modality | Never use raw NLI probability as fact |
| State consistency | B | P1 | Typed facts/invariants remain coherent across updates | Last-write and supersession rules are domain-specific |
| Entity continuity | B | P1 | Key requirements/artifacts/entities persist through relevant phases | Topic changes can be intentional |
| Local semantic continuity | B | P1 | Adjacent phase/turn embedding continuity | High continuity can also mean repetition |
| Topic-switch rate | B | P1 | Material topic transitions per active turn/minute | Multi-part tasks legitimately switch topics |
| Requirement drift | B | P1 | Distance between current plan/output and the latest authoritative requirements | Needs change-point and authority handling |
| Plan adherence | B | P1 | Planned work items completed, explicitly revised, or left unresolved | Blind adherence is not always desirable |
| Decision rationale coverage | B/C | P1 | Material decisions with constraints, alternatives, or evidence | Lightweight tasks need less ceremony |
| Question resolution rate | B | P1 | Explicit questions resolved or marked blocked / questions raised | Some questions remain intentionally open |
| Repetition/redundancy | B | P1 | Near-duplicate semantic content not adding state/evidence | Restatement can aid compaction/recovery |
| Information gain | C | P1 | Novel requirements/evidence/decisions per turn relative to known state | Sensitive to extractor quality |
| Response relevance | B | P1 | Response spans linked to current request/requirements | Long context makes relevance multi-objective |
| Summary faithfulness | B | P1 | Decisions, constraints, actions, numbers, and entities preserved without unsupported additions | ROUGE alone is insufficient |
| Compaction recall | B | P1 | Authoritative requirements/decisions/evidence retained after summary/compaction | Requires source-linked gold annotations |
| Abstention coverage | A | P0 | Fraction of eligible inferred judgments that abstained | Pair with risk on non-abstained cases |

## F. Design and technical-decision quality

These are rubric dimensions backed by cited conversation/artifact evidence. They are not universal code-quality facts.

| Metric | Tier | Privacy | Definition | Main caution |
|---|---:|---:|---|---|
| Problem framing | B/C | P1 | Actors, boundary, desired behavior, and constraints are explicit | Exploratory work evolves framing |
| Alternative coverage | B/C | P1 | Material alternatives and tradeoffs considered | Trivial decisions need no alternatives matrix |
| Interface-contract coverage | B | P1 | Inputs, outputs, errors, invariants, and versioning specified where relevant | Artifact inspection is stronger than conversation text |
| Change-surface proportionality | B | P1 | Modified components trace to requested behavior or required support | Refactoring can reduce future risk |
| Testability | B | P1 | Design exposes observable acceptance and failure conditions | Some UX qualities require human studies |
| Observability | B | P1 | Critical states/failures have safe diagnostic signals | More logging can violate privacy |
| Failure-mode coverage | B/C | P1 | Relevant failure, rollback, partial-success, and recovery cases considered | Use task-specific risk taxonomy |
| Security/privacy-by-design | B | P1 | Threats, data flow, least privilege, retention, and deletion are addressed | Checklist presence is not implementation correctness |
| Dependency justification | B | P1 | New dependencies have necessity, license, maintenance, and supply-chain evidence | Automated metadata can be stale |
| Migration/compatibility coverage | B | P1 | Schema/API/provider changes have detection, fallback, and migration behavior | Only relevant for persistent/public interfaces |
| Maintainability evidence | B/C | P1 | Cohesion, ownership, documentation, tests, and complexity evidence | Avoid subjective style scoring |
| Decision reversibility | B/C | P1 | High-uncertainty choices preserve an exit path or rollback | Irreversible choices may still be necessary |

## G. Affect, workload, and interaction quality

These metrics are **C-tier private coaching signals**. They must be disabled in team exports and never used for performance ranking.

| Metric | Privacy | Definition | Main caution |
|---|---:|---|---|
| Expressed affect distribution | P1 | Calibrated multi-label probabilities such as confusion, annoyance, disappointment, satisfaction | Text is not a direct measurement of mood |
| Friction episode rate | P1 | Affect candidates combined with repeated corrections, failures, and retries | Observable friction may be technical, not emotional |
| Correction burden | P1 | User effort spent restating/correcting relative to total user input | Long corrections may be highly productive |
| Interruption count | P0/P1 | User/provider interruptions and resumptions | Cause often unknown |
| Workload self-report | P1 | Optional user-entered short scale, never inferred | Self-report should remain private |
| Trust calibration gap | P1 | Difference between user confidence and verified outcome over repeated tasks | Requires voluntary labels and careful interpretation |
| Overreliance candidate rate | P1 | Accepted outputs lacking expected verification for risk class | Candidate only; expected checks vary |
| Underreliance candidate rate | P1 | Rejected/reworked outputs later supported by strong evidence | Counterfactual and difficult to validate |
| Toxicity/abuse safety event | P1 | Separate safety classifier/explicit report | Never treat as productivity or competence |

## H. Privacy, safety, and provenance

| Metric | Tier | Privacy | Definition | Main caution |
|---|---:|---:|---|---|
| Secret detection count | A/B | P0 | Detected secret types/counts before persistence; matched values never stored | Recall is never guaranteed |
| PII detection count | A/B | P0 | Detected PII types/counts before persistence | A count can itself be sensitive in small cohorts |
| Redaction coverage | B | P0 | Synthetic/human-labeled sensitive spans removed / sensitive spans | Production truth is unobservable; report benchmark scope |
| Redaction false-positive rate | B | P0 | Benign spans redacted / benign spans in labeled set | Excess redaction harms analysis utility |
| Canary leakage | A | P0 | Any synthetic canary byte found beyond allowed in-memory stage | Release gate: expected zero |
| Risky tool attempt rate | A/B | P0 | Policy-defined risky operations attempted / tool calls | Policy and risk class must be visible |
| Permission escalation count | A | P0 | Changes to more permissive modes or boundary crossings | Some are deliberate and approved |
| Remote exposure volume | A | P0 | Redacted characters/tokens and field types sent by destination/model | Volume is not sensitivity; show both |
| Remote approval coverage | A | P0 | Remote runs with valid explicit policy/grant / remote runs | Expected 100% |
| Provenance completeness | A | P0 | Metric/model results with complete version/source fields / results | Expected 100% |
| Unknown-event rate | A | P0 | Unrecognized provider records / parsed records | Rising rate signals adapter drift |
| Parser rejection rate | A | P0 | Records rejected by reason / records encountered | Never log rejected content |
| Deletion completeness | A | P0 | Derived/cached artifacts removed in deletion tests / artifacts expected | Release gate: expected 100% |
| Retention-policy violations | A | P0 | Records beyond configured retention / eligible records | Expected zero |
| Small-cohort suppression coverage | A | P0 | Team queries correctly suppressing cohorts below threshold / such queries | Threshold alone does not guarantee anonymity |

## I. Longitudinal progress and experiments

| Metric | Tier | Privacy | Definition | Main caution |
|---|---:|---:|---|---|
| Task-stratified rolling median | A/B | P0/P1 | Rolling median within stable task/model/repository strata | Sparse strata create noisy views |
| EWMA trend | B | P0/P1 | Exponentially weighted mean with displayed smoothing parameter | Visual trend is not causal evidence |
| Robust z-score | B | P0/P1 | Deviation from median/MAD baseline within stratum | Baseline drift needs monitoring |
| Retrospective change point | B | P0/P1 | PELT/ruptures candidate with penalty and minimum segment shown | Algorithm finds statistical, not causal, changes |
| Online drift alert | B | P0/P1 | ADWIN/BOCPD alert with false-alarm settings | Multiple monitoring inflates alerts |
| Regression rate | A/B | P0/P1 | Tasks falling below a versioned evidence threshold after prior stable period | Task mix and provider changes confound it |
| Intervention delta | B | P0/P1 | Matched/randomized before-after difference by task stratum | Label observational results clearly |
| Standardized effect size | B | P0/P1 | Robust/paired effect with bootstrap interval | Practical significance matters more than p-value |
| Model calibration error | B | P0 | ECE/Brier/reliability curve on current labeled window | ECE binning can hide local failures |
| Selective risk | B | P0 | Error among non-abstained predictions at each coverage level | Report full risk-coverage curve |
| Cohort/task mix shift | A/B | P0 | Distribution change in task type, complexity, language, provider, model | Needed before interpreting trends |
| Metric-definition discontinuity | A | P0 | Boundary where event/metric/model versions changed | Never draw one continuous trend across it without recomputation |

## Complexity normalization

Comparisons should condition on observable complexity rather than inventing a single perfect difficulty score. Suggested strata/features:

- task type and requested artifact;
- repository/language/framework;
- number of requirements and referenced files;
- initial failing checks or issue severity;
- changed-file/line scope after delivery (used carefully to avoid leakage);
- need for research/network/external coordination;
- user-marked complexity;
- model/provider/version and permission/sandbox mode.

For personal trends, prefer within-stratum matched comparisons, generalized estimating equations, or hierarchical/mixed-effects models. Display confidence intervals and sample size. Do not claim an intervention caused improvement from a simple time-series correlation.

## No default composite score

The default dashboard should present a compact vector:

```text
Outcome evidence | Verification | Cycle efficiency | Rework
Prompt specification | Requirement traceability | Safety | Workload (private)
```

If a user later creates a composite, it must be user-named, use visible versioned weights, preserve underlying dimensions, exclude C-tier signals by default, and never be used for employee ranking.
