# UI card review backlog

Status: frozen inventory; visual reproduction pending

The in-app browser could not be automated against localhost because its URL
security policy rejected the page. This inventory therefore comes from the
actual route map, component tree, CSS, tests, and current diff. It does not
claim that a visual defect exists until that defect is reproduced in the
rendered application.

The application currently contains 18 routed or window shells and roughly 60
distinct card, panel, drawer, and dialog work units. The current r7 tranche
directly changes only the canonical metric/evidence workflow and metric
operability surfaces.

## Rules for every card checkpoint

Each later card checkpoint must remain independent and use this sequence:

1. Reproduce the issue on localhost and record the route, viewport, theme, and
   data state without copying private session content.
2. Inspect ready, loading, empty, unavailable, error, and stale states that the
   card actually supports.
3. Check desktop and mobile widths, light and dark themes, keyboard focus,
   accessible names, wrapping, clipping, and action feedback.
4. Agree on the intended copy and interaction before editing.
5. Change only that card or one inseparable card group.
6. Run focused tests, TypeScript, build, privacy, and diff checks.
7. Restart localhost, review the result, and stop for approval.

Unknown or missing evidence must stay unknown. UI repair must not turn missing
values into zero, promote provider capability, weaken native review, or expose
raw transcript content.

## Dependency-ordered backlog

| ID | Surface | Main components | Code-established state | Visual work still required |
| --- | --- | --- | --- | --- |
| UI-00 | Application shell and primitives | `App`, route error/loading boundaries, navigation, `AsyncState`, `Dialog`, `Disclosure`, `EmptyState`, `Tabs`, status/coverage primitives | Direct application and primitive tests | Establish spacing, typography, theme, focus, and loading/error conventions before card-specific polish |
| UI-01 | Project catalog | project cards, metric coverage, selection/comparison | Search, sorting, bounded selection, aggregate and incompatibility states tested | Review card hierarchy, selection density, empty/error presentation, desktop/mobile |
| UI-02 | Project workspace | masthead, metric category deck, project facts, timeline, session cards | Route/focus, bounded scope, planned and missing-analysis states tested | Review navigation hierarchy, compact masthead, deck scanability, session-card density |
| UI-03 | Canonical model-ensemble shell | `ModelEnsemblePanel`, run/watch controls, definitions alert | Frozen shell repair; truthful receipt authority, serialized/context-safe controls, terminal/retry states, and responsive/a11y regressions are covered ([checkpoint note](ui-card-checkpoints/UI-03-model-ensemble-shell.md)) | User visual review remains pending; then keep nested metric-card changes in UI-04+ |
| UI-04 | Metric workspace | `MetricWorkspace`, exact-value board, lens controls, snapshot/comparison context | Strict run, state, reason, denominator, and selection contracts tested | Review information density, responsive layout, selected/focused states, unknown versus measured emphasis |
| UI-05 | Metric radar and knowledge | `ModelEnsembleRadar`, `MetricKnowledgeCard`, `MetricExplainer`, context facts | Focus/hover/pin/Escape and exact guidance tested | Review overlay placement, readability, pointer/focus behavior, long copy, mobile layout |
| UI-06 | Metric history and model stages | `MetricHistoryDrawer`, `ModelConstellationDrawer` | History/comparability and model-stage contracts tested | Review disclosure affordance, tables/lists, long identities, comparison readability |
| UI-07 | Generic evidence import | `MetricEvidenceFilePanel`, definitions alert | Media/schema/import and confirmed-state behavior tested | Review file flow, error copy, compact/full hierarchy, action feedback |
| UI-08 | Requirement-plan evidence | `RequirementPlanEvidencePanel` | Fresh r5/r6/r7 contract, preview/import, native review/confirm/reject, stale reset tested | Review complete clause set, exclusions/bases, links, long coordinates, acknowledgement clarity, mobile/full/compact modes |
| UI-09 | Requirement-action evidence | `RequirementActionEvidencePanel` | Strict descriptors, metadata, memberships, native receipt, semantic acknowledgement, stale reset tested | Highest current visual risk: inspect long escaped text, full opaque IDs, dense indices, nested memberships, wrapping, clipping, light/dark and mobile/full/compact modes |
| UI-10 | Quality profile | `QualityProfileView`, `QualityRadar`, metric board, analyze/share dialogs | Lenses, exact profile semantics, preview identity, focus traps tested | Review radar/board relationship, empty/unknown states, dialogs, mobile information hierarchy |
| UI-11 | Session metric surroundings | `SessionRadarCard`, session timeline/transcript, coaching, model judge, model-link experiment | Most nested panels have direct tests; radar card is mainly composite-covered | Review competing disclosures and primary-action hierarchy around the canonical metric panel |
| UI-12 | Local sources | Codex and Claude source cards, bounded controls, readiness, project/session selector | Consent, bounds, labels, capabilities, empty/error states tested | Review source-card parity, truth-copy density, selection/editor flow, mobile layout |
| UI-13 | Overview and session catalog | four overview tiles, next steps, session rows | Independent loading/ready/unavailable and navigation tested | Review scanability, unavailable values, row density, empty/search states |
| UI-14 | Jobs and automation | job cards/detail, health/filter controls, project grant/readiness panels | Strong direct and viewport tests | Review progress hierarchy, destructive-action clarity, dense failure/recovery copy |
| UI-15 | Prompt checks, calibration, models | prompt cue/commentary cards, rating workspace, hardware/runtime/model cards and chat | Core workflows and gating tested | Review complex forms, history tables/plots, local-model provenance, small-screen behavior |
| UI-16 | Reviewed tasks and task flow | task summary, observation cards, provenance, board cards, audit/lifecycle controls | Task-flow browser coverage is strong; task summary/provenance are weakly targeted | Review task-detail hierarchy first, then board/timeline density and lifecycle confirmation |
| UI-17 | Research lab | operability panel, metric/method/model cards, inventory, compatibility | Operability and inventory direct; some compatibility coverage is composite | Preserve honest 16/0/4 messaging while reviewing tabs, card density, unknown/unavailable states |
| UI-18 | Agent workspace | history/settings, team folders, conversation/tool activity, approvals, diff review | Agent/workspace workflows tested; `TeamFoldersPanel` lacks targeted coverage | Review streaming/tool/diff hierarchy, approval prominence, compact window; add TeamFolders coverage before redesign |
| UI-19 | Team and social | readiness cards, aggregates, member visibility, conversations, file offers, transfer controls | Extensive state and responsive coverage | Review privacy language, suppressed/denied states, dialogs, mobile multi-pane navigation |
| UI-20 | Secondary windows and experiments | live mini window, model-ensemble overlay, local model-link and other experimental panels | Overlay has strong viewport/a11y coverage; live window is directly tested | Review window chrome, compact-mode consistency, disconnect/retry states, experimental labeling |

## First recommended visual tranche

Start with UI-03 through UI-09 because those are the only card surfaces changed
by the stabilized r7 tranche. Use this internal order:

1. Model-ensemble shell and metric workspace.
2. Radar, knowledge card, history, and model-stage drawers.
3. Generic evidence import.
4. Requirement-plan evidence.
5. Requirement-action evidence in full and compact modes.

Only after those surfaces are visually stable should work expand to unrelated
project, source, task, agent, team, or social cards.

## Coverage gaps to close when reached

- No screenshot visual-regression tests exist.
- `RequirementActionEvidencePanel` has no real-browser visual flow despite its
  long exact strings and nested receipt/membership content.
- `TeamFoldersPanel`, `SessionRadarCard`, `TaskSummary`, and `ProvenancePanel`
  have the weakest targeted component coverage.
- Several routes have strong unit semantics but no route-level responsive
  check: Overview, Sessions, Calibration, Models, Local Sources, and the live
  mini window.

These are backlog priorities, not claims that the cards are currently broken.
