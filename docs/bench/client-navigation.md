# Bench pages and run forms

Task: bench client navigation and schema-driven run overrides, 2026-10-13.
Baseline: `origin/develop` at `aeefb03`, with the existing Cloudflare-only access
changes integrated as a prerequisite. The client opens directly after the gateway
admits the request. There is no application token prompt or token storage.
Affected atlas scope: W05/W06 user journeys, bounded to the standalone bench;
this does not implement or accept the general workflow engine gates.

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
- `/experiments/{id}/runs/new?revision={revision}` configures a run. An optional
  `from` run identity prefills the saved effective settings for a reconciled
  terminal run. Submission retains `retryOf` and a stable request identity for
  retries of the same submitted settings.
- `/experiments/{id}/runs/{runId}` shows that run's status, attempts and results.
  Rerun with changes opens the form; it does not immediately execute a run.

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
