# Beta readiness checkpoint 35 — requirement-plan cold-context recovery

Status: AUTOMATED TARGETED GATES PASS; overall beta readiness remains IN
PROGRESS. This checkpoint narrows a cold-start and TTL-expiry recovery path;
it does not declare beta, release, provider, native, or model readiness.

## Scope

Requirement-plan authoring review text remains a bounded, TTL-only in-memory
context. It is intentionally not restored from a sealed publication, so a
cold start or expiry cannot expose prior source clauses. CP35 distinguishes
that condition from a missing sealed publication and from a persistence read
failure without adding content storage, automatic analysis, or a fallback
authority path.

The authenticated contract endpoint now returns content-free HTTP 404 detail
`requirement_plan_review_context_missing` with the recovery message
“requirement-plan review context is missing or expired.” A missing sealed
publication retains its existing `requirement_plan_evidence_not_found` 404;
repository failures retain their existing 503. The intended UI response is a
truthful unavailable state that requires a fresh analysis to establish a new
review context, never a same-run Retry, loaded, or ready authoring surface.

## Current evidence

Focused backend coverage is green: the missing and expired context cases,
legacy no-publication 404, and generic 503 mapping passed 2/2 (`c04119`). The
full owning backend files are 28/28 green (`ea7d6a`), and frontend contract and
recovery rendering coverage is 36/36 green (`770513`), including neutral
compact capability wording. Production build (`534d05`) and bundle budget
(`70ccff`) are green; the build confirmed port 8765 was absent. The fresh
built-loopback gate is 28/28 green (`eab410`) with terminal cleanup (`ca8957`):
listener release, temporary removal, runtime cleanup, and zero models all
passed. Privacy remains OPEN/RED: its latest scan (`b755ae`) found two residual
synthetic `.tmp-cp34-privacy` databases.

Owner/native walkthrough, provider execution, release, beta, and v1
acceptance remain unverified. No real provider data, models, native execution,
restart, or durable source text is part of this checkpoint.
