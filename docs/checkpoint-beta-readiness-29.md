# Beta-readiness checkpoint 29

Status date: 2026-09-08

Status: **automated CP29 slice complete; final root privacy/diff passed and
owner review remains pending; not a beta, v1, native, or release claim.**

## Scope and current truth

CP29 adds a bounded, plan-first guided authoring path for requirement-to-plan
evidence. A locally authenticated user can request a native-confirmed read of
the exact current, bounded source clauses, classify every eligible user clause,
and submit only a content-free graph. The resulting proposal is deliberately
inert: its producer receipt is `local_review_ui` with the explicitly
untrusted `untrusted_local_authoring_commitment` authority. It has no decision
and cannot create a metric value.

The existing separate native proposal review and native confirm/reject decision
remain the only path to reviewed plan authority. Source receipts are one-shot,
wall-clock and monotonic-expiring, and bind the exact run, window, manifest,
candidate set, and predecessor confirmation. A changed, foreign, stale, or
rebound receipt is refused. File-v1 import behavior remains agent-producer
only and unchanged.

Migration 63 widens only the durable proposal/seal producer checks to preserve
the distinction between legacy local-agent imports and guided local review.
It uses a guarded SQLite rebuild with foreign-key checking and restores the
closed seven-object attached guard/index inventory. Focused regression work
caught and repaired omission of the proposal-seal completeness trigger from
that inventory; the repaired migration preserves the critical completeness,
immutability, privacy-delete, source-exact, and index protections.

A fresh synthetic analysis after a guided confirmed plan is able to consume
that reviewed plan and expose the subsequent requirement-action review
contract. This does not turn an assistant completion statement into task
success, does not claim an objective metric value on import, and does not prove
provider, native-host, or release readiness.

## Evidence boundary

Focused guided and transcript coverage is 9 tests (`1aabb1`); migration
coverage is 2 tests (`43d0b0`); and the four repaired legacy safety negatives
are green (`002abe`). Frontend evidence currently includes 34 existing tests
(`48db2f`), 11 new tests (`ea6dcd`), and 6 browser checks (`4b08e2`). The API
receipt is `5db589`; the privacy receipt is `ec6652` and predates the latest
UI edits.

The production build is green (`af2d52`). Strict E2E, API generation, and
bundle validation are green (`181ed3`) with the established shell and initial
Agent bundle caps unchanged. The focused frontend five-file receipt is green
(`e5f903`), broader frontend evidence is recorded (`3606a7`), and strict
TypeScript is green (`dc2ef5`). Browser coverage is 6/6 (`4b08e2`); built-loopback is
27/27 (`f90487`, listener released, synthetic temporary state removed, no
model runtime). The final root privacy/diff gate passed (`7ea9db`); the checked
listener ports were also clear (`300aad`).

The authoritative aggregate backend run reported 65 passed and two stale
latest-schema expectations (`f241eb`). Those M63 latest-head expectations were
corrected; `python -m pytest tests/test_requirement_plan_evidence_migration.py
-q` then passed 3 tests (`1efb29`). This is not an aggregate 67-pass claim.

The bounded evidence commands cover the guided/HTTP and transcript composition
tests, the requirement-plan migration file, focused frontend checks, browser
journeys, OpenAPI generation, strict E2E, bundle validation, the production
build, built-loopback cleanup, and privacy. They establish synthetic local
behavior only; they do not exercise a real provider, model, native decision,
or release package.

No real provider data, native interaction, model execution, persistent local
database upgrade, application restart, install, commit, or push is claimed.
All exercised data is synthetic and no transcript, path, screenshot, or other
private content is recorded here.

## Open owner gates

1. Open the guided source review with native presence and inspect the exact
   current bounded clauses.
2. Classify every user clause as a requirement or an exclusion with any
   required exclusion basis; include the applicable plan clauses and links.
3. Create the inert proposal, then use the separate native exact review and
   confirm/reject decision; run fresh analysis before relying on it downstream.
4. Retain final privacy/diff (`7ea9db`) and the clear listener check (`300aad`)
   as automated evidence without closing beta.
5. Retain broader owner decisions for native behavior, provider evidence, and
   beta/release scope as open gates.

## Next bounded candidate

Guided requirement-action authoring is not implemented. It remains a proposed
next slice and must not be inferred from guided requirement-plan authoring.
