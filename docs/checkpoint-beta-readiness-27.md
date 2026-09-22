# Beta-readiness checkpoint 27

Status date: 2026-09-08

Status: **bounded implementation and automated validation complete; owner
review remains pending.**

## Scope

CP27 records two metric-operability corrections discovered while checking the
real reviewed-action boundary:

1. the service now establishes the prerequisite requirement-plan ordering
   before composing the reviewed action proposal; and
2. schema migration 62 extends only the exact action-proposal source-authority
   trigger so an otherwise valid current R8 seal is admitted alongside the
   existing R6 and R7 seals.

Migration 62 is append-only. Earlier migrations and their checksums remain
immutable. The trigger change does not add server rollback, session mutation,
model activation, or provider authority.

## Current operability truth

The current catalog is `metric-operability-v5` at **17 shipped conditional
paths, 0 task-profile gaps, 3 provider/extractor or release-composition gaps,
8 experimental model paths, and 0 model-authoritative metrics**. The new
seventeenth path is scoped to a complete Claude transcript, confirmed plan,
and native-reviewed links. Synthetic proof and a faked native interaction do
not constitute a real provider, native, model, or release claim.

The guided reviewed-proposal UX is still missing. The app can preserve the
typed authority boundary and import an inert proposal, but CP27 does not claim
that a person can complete the full guided proposal journey from the UI.

## Evidence boundary

Known linked coverage is **1/1**, with full proof **2/2**, in root receipt
`81cb3c`. The initial false first-sealed-run behavior was caught in receipts
`8b3f23` and `b516ab`; the old trigger's rejection of a valid R8 seal was then
isolated in `efc7cf` and corrected by M62. Expanded core/catalog/API/hook/live
verification is **37/37** (`080b75`), frontend coverage is **289/289**
(`4d4d5e`), backend owning coverage is **129/129 in 79.14s** (`df59d8`),
and the build is green (`d48bee`); API, strict-E2E, and bundle validation are
green in `cabb47` with caps unchanged; OpenAPI export is **6/6 in 71.56s**
(`e7e17b`) and final strict E2E is green (`2ac186`). Corrected browser
coverage is **13/13 in 7.4s** (`db9efd`). Built disposable loopback is
**27/27 in 32.4s**
(`2d1f5e`), with startup, failure-component, listener, temporary-state,
cleanup, and zero-runtime checks green. Schema-upgrade coverage is **51 cases**
(`688b79`) and OpenAPI export is **6/6** (`e7e17b`); final privacy passed in
**8.04s** (`c07a6e`). No real model was run and
the native interaction was synthetic/faked, so no provider or release claim
is implied.

The schema-expectation maintenance updates only latest `SCHEMA_VERSION`,
post-initialize `PRAGMA user_version`, and migration-ledger-head assertions
in tests. Historical seed versions, rollback boundaries, frozen checksums,
and the existing M62 test remain unchanged. Root’s focused schema-upgrade
selection passed all 49 functions; no production or migration source was
changed by this maintenance slice.

## Known next work

The guided proposal UX remains the next product gap. The Find-next composer
pointer interception discovered in CP27 is queued for CP28 and is explicitly
not fixed or hidden by this checkpoint.

## Owner checks (maximum four)

1. Confirm the current operability page reports v5 at 17/0/3 and keeps the
   three remaining provider/composition gaps visible.
2. Review the exact R8 action-admission boundary when a separately authorized
   provider proof is available; do not treat synthetic/native-faked evidence
   or M62 alone as provider proof.
3. Confirm the missing guided proposal UX is visible as an open gap rather
   than represented by a hidden or automatic action.
4. Reproduce the saved-message Find-next overlap only under the separately
   scoped CP28 investigation.

No real model, native client, live database migration, restart, commit, or
push is claimed.
