# Bench pages and run forms

Task: bench client navigation and schema-driven run overrides, 2026-10-13.
Baseline: `origin/develop` at `aeefb03`, with the existing Cloudflare-only access
changes integrated as a prerequisite. The client opens directly after the gateway
admits the request. There is no application token prompt or token storage.
Affected atlas scope: W05/W06 user journeys, bounded to the standalone bench;
this does not implement or accept the general workflow engine gates.

## User journey

- `/experiments` lists experiments. Cards are ordinary links to experiment pages.
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
Run identities are checked against the selected experiment and revision. Both
the run list and experiment-card status are scoped to the displayed revision;
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
