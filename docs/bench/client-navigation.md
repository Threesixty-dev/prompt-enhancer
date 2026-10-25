# Bench pages and run forms

Task: bench client navigation and schema-driven run overrides, 2026-10-13.
Baseline: `origin/develop` at `aeefb03`, with the existing Cloudflare-only access
changes integrated as a prerequisite. The client opens directly after the gateway
admits the request. There is no application token prompt or token storage.
Affected atlas scope: W05/W06 user journeys, bounded to the standalone bench;
this does not implement or accept the general workflow engine gates.

## Explicit quality assertions - 2026-10-25

- Task / atlas / gate: `bench-assertion-visibility`, bounded W05/B10 presentation.
  Approved source baseline: reviewed develop `6a9c9be`.
- Reproduction / outcome: individual assertion rules and observations were
  available only in collapsed result JSON. History and matrix cells emphasized
  successful execution even when a recorded quality assertion failed. Readers
  now see execution and assertion outcomes independently in both places.
- Allowed files / implementation: Bench static rendering, its explicit asset
  allowlist, synthetic browser/API checks and evidence documentation. A shared
  assertion renderer adds a prominent run summary before diagrams and settings,
  with failed-check links to the affected attempts. Each attempt exposes every
  configured check, evaluator, metric, expected rule, threshold, recorded outcome,
  observed value and before/after context before its prompts and model details.
- Preserved contracts: the UI reads recorded outcomes without recalculating
  pass/fail. Thresholds and numeric observations retain their precision, including
  zero and tiny negative values. Unknown, not evaluated, not recorded and no
  assertions configured remain distinct. Missing candidate, abstention and
  incompatible evaluator identities use existing measurement explanations.
  Missing detailed failure evidence remains visible as a limitation.
- Checks / completion criterion: 116 affected desktop/mobile checks and 27 API
  checks pass with synthetic fixtures. Coverage includes successful execution
  with failed quality, both supported operators, exact zero, small changes,
  unavailable readings, absent results/configuration, reordered checks, escaped
  text, refresh, preserved disclosures, keyboard links, mobile width and no
  accidental submissions. Existing navigation, workflow, history and recovery
  checks pass. JavaScript syntax, privacy, atlas and whitespace checks pass.
- Evidence / resource bound: browser and API integration evidence, one browser
  worker and owned loopback fixture servers. Synthetic desktop/mobile previews
  were inspected outside the repository. Initial server startup was blocked by
  the sandbox's loopback restriction; the same checks ran with that permission.
  A pending-state label and CSS ordering were refined before final verification.
- Result / owner decisions: local candidate prepared for review; source
  publication, promotion and API/UI deployment remain pending. No core release,
  metric change, model request, experiment rerun or recovery action is required.
  Stored results and W05/B10 acceptance are unchanged; owned test servers stop
  after their checks.

## Expand prompts in the variations matrix - 2026-10-25

- Scope / baseline: W05/B10 presentation, reviewed develop `fe1cb67`.
- Reproduction: attempt details could expand, but the clipped prompt in the
  Run variations matrix had no expansion control of its own.
- Change: each case now has explicit Expand prompt / Collapse prompt controls
  on experiment, run setup and result pages. Full text uses a focusable scroll
  area. Expansion remains independent per case and survives run refresh.
  Matrix and attempt-detail disclosure controls share a visible button outline.
- Evidence: a synthetic regression fails before the repair and covers all three
  page types, keyboard controls, exact full text, independent state, refresh,
  mobile width and zero accidental run submissions.
  All 32 affected desktop/mobile checks, syntax and privacy checks pass.
- Boundary: source review and API/UI deployment remain pending. Inputs,
  results, execution and W05/B10 acceptance are unchanged.
- Follow-up: expansion deployed through PRs #109/#110. From reviewed develop
  `d3db087`, the owner-requested styling refinement makes the shared disclosure
  a small muted text control with no fill or border, a smaller plus/minus and
  a hover underline. Keyboard focus remains visible. All four focused
  desktop/mobile expansion checks and JavaScript syntax checks pass.
  This CSS-only refinement awaits source promotion and API/UI deployment.

## Compact attempt prompt details - 2026-10-25

- Scope / baseline: W05/B10 presentation, reviewed develop `2ba83f1`.
- Reproduction: the deployed matrix preview was compact, but attempt details
  still rendered the entire original and enhanced prompts. A long synthetic
  prompt reproduced a detail panel more than 6,500 pixels tall.
- Change: both attempt prompts now start with a bounded, three-line preview.
  Native disclosures reveal the complete text and allow it to be collapsed
  again. Original and enhanced expansions are independent and survive refresh;
  an absent candidate retains the existing unavailable message.
- Evidence: the new long-prompt regression fails before the repair and passes
  on desktop and mobile. It checks default height, keyboard expansion, exact
  original/enhanced text, independent collapse, refresh and viewport width.
  All 40 affected browser checks, JavaScript syntax and privacy checks pass.
- Boundary: source review and API/UI deployment remain pending. This changes
  presentation only; saved inputs, model calls, results and W05/B10 acceptance
  are unchanged.

## Compact prompt previews and experiment navigation - 2026-10-25

- Scope / baseline: W05/B10 presentation, reviewed develop `2de0075`.
- Change: Run variations limits each prompt preview to three lines with an
  ellipsis. The shared style covers experiment details, run setup and run results;
  complete prompts remain available in the existing prompt details. Run results
  also provide a **View experiment** action beside Refresh, linked to the saved
  experiment revision even when a newer revision is available.
- Evidence: 38 desktop/mobile navigation, run-label and variation checks pass,
  including keyboard activation of the revision-preserving link. A separate
  synthetic preview with more than 20,000 characters shows three visible lines
  at desktop and mobile widths; a short prompt remains fully visible.
- Boundary: PRs #105/#106 completed source promotion and verified API/UI deployment.
  Experiment inputs, stored results and W05/B10 acceptance are unchanged.

## Run labels show the selected scope - 2026-10-25

- Task / atlas / gate: selected-run labels, bounded W05/B10 presentation.
  Reviewed source baseline: develop `b22f92f`, following PRs #100/#101.
- Reproduction / outcome: history used the full experiment title as each run's
  headline, so a one-pair run appeared to execute the full matrix. A run now
  shows its workflow, selected case and selected variant; larger selections
  show their case/variant counts. The selected attempt count appears directly
  below. The parent experiment retains its title and is explicitly labelled;
  the result page separately labels the full experiment matrix.
- Allowed files / implementation: Bench configuration projection, UI helpers
  and run rendering, synthetic history/browser tests and evidence documentation.
  The read-only history projection adds bounded subject IDs from the immutable
  effective snapshot. Run headings and history share one label formatter.
- Preserved contracts: stored definitions, snapshots, results, execution,
  recovery and metrics are unchanged. There is no migration, new dependency,
  experiment revision or core release. Older responses without case IDs use
  known counts; missing configuration remains unknown and never borrows cases
  from an experiment's defaults.
- Checks / completion criterion: 105 affected backend tests and 50 desktop/mobile
  checks pass. Coverage includes one-pair and multi-pair selections, different
  selections of the same experiment, missing historical metadata, 80-character
  identifiers, restart persistence, content exclusion, keyboard navigation,
  refresh, revision scope, reruns and viewport width. JavaScript syntax,
  privacy, atlas generation and whitespace checks pass.
- Evidence / resource bound: synthetic integration and installed-Chrome browser
  checks; one browser worker and owned loopback fixture servers. An initial
  fixture used the wrong context field; another incorrectly included detail
  payloads in history. Both fixtures were corrected to the existing API contract.
  The sandbox denied loopback binding; the same bounded checks then ran with
  permission to start their owned local servers.
- Result / owner decisions: candidate prepared for source review, promotion and
  API/UI deployment. Runtime verification remains separate. No experiment was
  executed or reconciled for this repair; general W05/B10 acceptance is unchanged.

## Stale results after connection loss - 2026-10-24

- Task / atlas scope: W05 presentation, based on reviewed develop `ca1af3a`.
  A failed refresh left previously rendered results visible with only a generic
  transport error. The failure was reproduced with a synthetic network abort.
- Candidate: explicitly label retained results as potentially out of date and
  offer **Reload to reconnect**. A successful manual or automatic refresh clears
  the notice. Repeated failures preserve keyboard focus on the reconnect button;
  late failures from an older route cannot replace the current page's notice.
- Boundary: existing results, metrics, admission receipts, server execution and
  authentication policy retain their behavior. Reconnection reads the current
  run and never resubmits it. The running qualification uses its frozen deployment.
- Evidence: six desktop/mobile checks cover network failure, a gateway HTML
  response, an expired JSON session, manual/automatic recovery, reload, preserved
  measurements, focus, viewport width and zero run submissions. Twenty existing
  navigation/form/polling checks also pass. JavaScript syntax checks pass.
- Resource / acceptance boundary: one test worker and an owned loopback fixture
  server with fictional data. Source review, promotion and deployed verification
  remain required; general workflow and independent onboarding gates stay open.

## Stats preview and dedicated charts - 2026-10-14

- Task / atlas scope: correct the Bench homepage and experiment run-list
  hierarchy; bounded W02/W05 presentation on `develop` baseline `994ed34`.
- User outcome: a compact Stats overview precedes the list filters and run
  cards. It shows matching runs, planned attempts, execution counts and daily
  activity. View all stats opens a dedicated page with the complete charts and
  its own Filter stats form; Back to runs retains the applied filters.
- Navigation: `/stats` covers global history; `/experiments/{id}/stats` retains
  the selected revision. Opening stats drops the pagination cursor, while
  browser Back restores the original list URL. Apply/Reset stays on the stats
  page. Deep links, reload and polling preserve the selected scope.
- Boundary: existing summary aggregation, paired metric semantics and privacy
  projection remain unchanged. This only adds client navigation, shell routes
  and compact presentation; there is no schema or execution change.
- Evidence: 184 Bench backend tests and 38 desktop/mobile browser checks pass,
  including preview ordering, keyboard navigation, filter carryover, pagination
  restoration, stats reload/reset and scoped routes. JavaScript syntax, privacy
  and whitespace checks pass. Synthetic desktop/mobile previews and full stats
  pages were visually inspected with no horizontal overflow.
- Resource / completion boundary: one browser test worker and owned loopback
  fixture servers; temporary dependency links removed and fixture servers
  stopped. Local checks use no provider calls or production data. Hosted
  deployment evidence remains separate; general acceptance gates are unchanged.

## History filters and charts - 2026-10-14

- Task / atlas scope: full-history filters and descriptive charts on the Bench
  homepage and experiment-revision run list; bounded W02/W05 presentation.
- Approved baseline: owner-selected `develop` at `56ddc38`, on feature branch
  `codex/bench-filters-charts`. Existing privacy and execution contracts remain.
- User outcome: filter execution status, experiment/revision, trigger, saved
  generation/evaluation model alias and inclusive UTC creation dates. The
  experiment page fixes its experiment and selected revision. Apply/Reset,
  pagination, reload and Back/Forward preserve the selected scope; applying a
  filter starts at the newest matching page. Polling preserves draft controls.
- Charts: run totals, planned case-by-variant attempts, execution status and
  daily creation counts. Totals/statuses cover every matching run, independently
  of pagination. Daily activity covers up to 30 UTC days ending on the selected
  end date (otherwise today, or a future selected start date). Daily values are
  available as a table; status bars are keyboard-accessible filter links.
- Metric comparisons: selectable metric and evaluation scope, paired Before/
  After means, paired delta, variant/model breakdown and generation-model
  breakdown on a shared scale. Groups separate experiment revision, core
  version, evaluator identity/kind/provenance, metric, variant, model alias and
  generation provenance. Numeric observations require known values, identical
  before/after evaluator provenance and a recorded comparable delta. Zero stays
  zero; missing, categorical and non-comparable values are excluded and counted.
  Attempts without results do not contribute. Counts and limitations appear
  beside the charts; these descriptive averages do not rank models or infer
  task success. Case subsets and run overrides may differ.
- API boundary: optional `summary=true` extends the existing bounded `/api/runs`
  read. Parameterized filters precede stable cursor pagination; one read
  transaction supplies the page and summaries. Only counts, numeric metrics and
  allowed identity fields are returned, excluding prompt/context text, target
  text, instructions, request bodies and operation identities. Model suggestions
  are capped at 200; metric groups are capped at 200, with a visible truncation
  notice directing users to narrow filters. Legacy requests retain their shape.
- Evidence: 182 Bench backend tests and 36 desktop/mobile browser checks pass;
  syntax, privacy and whitespace checks pass. Synthetic visual inspection covers
  desktop/mobile layouts. Tests cover history beyond 100 runs, scoped cursor
  pagination, model overrides, date boundaries and invalid ranges, extreme dates,
  paired weighting, unknown/zero values, evaluator version separation, bounded
  output, content exclusion, filters across navigation, empty recovery, keyboard
  chart navigation, stale responses and polling preservation.
- Resource / completion boundary: one browser test worker and owned loopback
  fixture servers, with installed Chrome. No provider calls, deployment, source
  publication or production data inspection. Owner review and release remain
  separate; general B/W/WP gates are unchanged.

## Model details and run variations - 2026-10-14

- Task / scope: Bench model visibility and case-by-variant explanation; W05
  presentation and W02 immutable run evidence within the existing Bench only.
- Approved baseline: owner-selected `develop` at `97b128f`.
- User outcome: experiment cards, run cards and detail pages expose generation
  and evaluation model aliases separately. Attempt results show recorded provider,
  model, reported model, model revision and identity source for generation and
  both evaluation passes. Scripted and deterministic work explicitly uses no
  model; absent provenance remains unknown.
- Change: a data-derived cases x variants matrix numbers each attempt. For the
  clarification example it reads `2 cases / 2 variants / 4 attempts`. Both
  variants retain `script.clarify.v1`, with their distinct clarification focus.
  Before/After is explained as comparison inside an attempt, not extra cases.
  The form updates the matrix when selections, steering or model aliases change;
  reruns retain the saved subset and aliases. Result cells show recorded status
  and provide keyboard-accessible links to the matching attempt.
- Boundary: run lists receive a bounded `configuration` projection of each
  immutable run snapshot. It includes counts and model bindings, never subject
  text/context, instructions, evaluator targets, requests or result bodies.
  Experiment defaults cannot replace run overrides. No schema migration or model
  execution behavior changes.
- Verification: 162 Bench backend tests and 28 desktop/mobile browser checks
  pass. Synthetic coverage includes model overrides and legacy inheritance,
  summary content exclusion, the two-by-two matrix, selection changes, empty
  selections, reruns, keyboard navigation, status refresh, missing attempts and
  provenance, separate before/after evaluator identities, and viewport overflow.
  JavaScript syntax, repository privacy scanning and whitespace checks pass. Desktop/mobile layout was also
  visually inspected using synthetic data outside the repository.
- Resource bound: one owned loopback fixture server and one browser test worker;
  installed Chrome was selected because bundled Chromium was unavailable. An
  alternate loopback port avoided an existing listener. No provider/model calls,
  deployment or publication were performed. Owner review remains open; no
  general workflow or release gate changes.

## User journey

- `/experiments` shows All runs above the experiment cards. Run rows open
  results; experiment cards open experiment pages. The run list includes every
  experiment and revision, newest first, with ten rows per page. Older runs
  continues the history; Newest runs returns to the beginning.
- `/experiments/{id}?revision={revision}` shows one revision, its units,
  subjects and runs for that revision. New run opens a separate form.
- `/stats` and `/experiments/{id}/stats?revision={revision}` show full run
  statistics with their own filters, reached from the compact list preview.
- `/experiments/{id}/runs/new?revision={revision}` configures a run. An optional
  `from` run identity prefills the saved effective settings for a reconciled
  terminal run. Submission retains `retryOf` and a stable request identity for
  retries of the same submitted settings.
- `/experiments/{id}/runs/{runId}` shows that run's status, attempts and results.
  Rerun with changes opens the form; it does not immediately execute a run.

Run titles describe the saved selection, for example
`Prompt Check / example-sparse / concise`, with
`Selected: 1 case / 1 variant / 1 attempt` underneath. A selection with multiple
cases or variants uses counts for those dimensions. The full experiment's title
is parent metadata, and its complete matrix is labelled separately on results.
These display labels are computed on read, so existing runs receive them too.

The server serves the shell at these exact routes, so reloads and deep links
work. Browser Back/Forward and modified link clicks retain normal navigation.
Run identities are checked against the selected experiment and revision. Experiment-page
run lists and experiment-card status are scoped to the displayed revision;
a revision with no runs does not inherit another revision's history or status.
Late responses from an abandoned page cannot replace the active page.

## Form contract

Experiment parameter schemas drive number, text, boolean, enum, object and array
controls. Objective, steering and consumer fields use the authoritative execution
schema through the authenticated, read-only `/api/run-form-schema` endpoint.
No JSON input editor is needed. Read-only JSON results and run settings remain available in collapsed
detail sections.

Each selected unit has its own effective parameters, objective, steering and
model alias. Subject and unit checkboxes retain the saved subset on rerun.
Nullable controls distinguish provider defaults/unknowns from explicit numbers,
including zero. Absent optional values remain omitted. Schema limits are applied
in the form; the existing API and execution contracts remain authoritative.
The form freezes its revision and values while open; background refresh does not
replace controls, overwrite a draft or silently select a newly published revision.

## Refresh behavior

The previous client recreated every result panel every three seconds and each
new panel replayed its fade-in animation. This client skips unchanged snapshots
and removes that panel animation. Changed run data preserves each disclosure by
a stable run/attempt key. Reconciliation input retains its existing focus guard.

## Evidence scope

Required checks: bench backend tests, desktop/mobile browser journeys, JavaScript
syntax and the repository privacy scanner. Browser checks cover typed overrides,
null/zero, rerun inheritance, validation, route isolation, deep links, stale
responses, and DOM identity across two polling intervals. Fixtures are synthetic;
no real sessions, provider calls or deployment are part of these checks.

Local validation: 92 backend tests and 14 desktop/mobile browser checks pass;
JavaScript syntax passes. Chrome inspection opens the synthetic form directly
without a login. Results are recorded in the readiness ledger and progress
journal. Owner review and deployment remain separate from local verification.


## All runs and labels - 2026-10-13

Run rows identify the experiment, revision, run, trigger, status and creation
time. Metadata labels have stronger weight and contrast throughout the client.
The read-only run endpoint accepts a bounded `limit` (1-100) and a `before` run
identity, returning `nextCursor` when more history exists. Ordering by creation
time and identity keeps equal timestamps stable and avoids shifting older pages
when a new run arrives. The overview URL preserves its cursor across reloads;
polling updates that page and leaves unchanged rows in place.

Local synthetic checks: 98 backend tests and 20 desktop/mobile browser checks
pass, including history beyond 100 runs, equal timestamps, concurrent insertion,
invalid page bounds, cross-experiment/revision listing, empty history, direct
result navigation and unchanged DOM identity during polling. JavaScript syntax
passes. This is local UI evidence; it does not establish deployment or model
qualification.

## Diagnostics-only chart identity - 2026-10-23

- Scope: MA18/W02/W05 presentation, based on reviewed develop `977cc641`.
- Defect: paired charts labelled an explicitly skipped optional model as an
  unknown model alias. The stored review already distinguished these states.
- Correction: carry the recorded review state into comparison metadata and keep
  diagnostics-only observations separate from absent historical model metadata.
  The UI labels only explicit `no_active_model` as no model; unknown stays unknown.
- Evidence: 21 synthetic history/aggregation tests and 12 desktop/mobile browser
  checks pass, including both states in the same chart and unchanged paired means.
- Bounds: no model call, stored-result mutation or scientific-score change. Owner
  review, promotion and deployed presentation verification remain separate gates.
