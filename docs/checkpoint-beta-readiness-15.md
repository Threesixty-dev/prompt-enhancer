# Beta-readiness checkpoint 15

Status date: 2026-09-08

This checkpoint records the bounded Project Catalog retrieval-cap slice. It is
not beta, v1, latency, provider-access, model, calibration, native, packaging,
or release certification.

## Scope

The analytics Project Catalog (not Agent chats) now separates the first 100
session retrieval page from the 30-row rendering bound. An explicit control
fetches the next 100-session page. Loaded project counts, search, and sorting
are truthful and scoped only to validated loaded records; they do not claim to
represent all providers or all provider caches.

Each retrieved page is validated before it is admitted to the current loaded
view; the API provides offset paging rather than a shared catalog revision.
Wrong limit/offset,
unexpected keys, invalid rows, and duplicate session IDs (within a page or
across pages) are refused fail-closed while previously loaded pages remain
visible. A 15-second local deadline, explicit cancellation, and manual retry
cover the initial and subsequent page requests without treating cancellation
or timeout as an empty result.

Selection and comparison remain valid across append and filter changes. A
catalog reload or transport-identity replacement clears selection and
comparison state, aborts/fences outstanding work, and prevents late responses
from repopulating the replaced view. No metric calculation or aggregate
contract changed in this slice.

## Evidence boundary

Bounded automated implementation is complete. The owning and adjacent
frontend receipt is **53/53 across six files in 13.79s**, including 40 catalog
tests without double-counting. Synthetic browser coverage is **6/6 in 6.8s**
and the Python harness is **6/6 in 9.71s**. The production build, full
TypeScript check, strict E2E/API checks, and bundle budget pass. The exact
focused frontend command was:

`npm test -- --run src/features/project-catalog src/features/session-catalog src/features/metric-coverage src/shared/ui/BoundedListPager.test.tsx`

The synthetic browser, Python harness, and real loopback acceptance commands
also passed; the final loopback receipt is **23/23 in 27.9s**, comprising 22
healthy zero-interception API journeys plus one explicit CP14 asset-fault
containment case. Cleanup confirmed listener release, runtime cleanup,
temporary-state removal, zero remaining model runtimes, and no server-thread
failure. CI workflow is unchanged; loopback configuration now uses an explicit
two-spec array. No CP15 speed claim is made; CP14 byte budgets remain the
reference. Owner checks remain pending. No native-app, provider, model,
hardware, metric-calibration, packaging, or release certification is claimed.

Command brief: `npm run build`; `npm run check:api`;
`npm run check:bundle-budget`; `npm run test:e2e:loopback:browser`; and
`npm run test:e2e:loopback`.

## Owner checks (maximum four)

1. With a synthetic 100+ session catalog, confirm the initial page is bounded
   to 30 rendered cards and the explicit next-page control requests offset
   100.
2. Filter for a label present only on a later loaded page and confirm loaded
   counts/search remain scoped to validated records.
3. Exercise cancellation, timeout, malformed/duplicate-page refusal, and
   manual retry; confirm the last validated snapshot remains visible.
4. Select and compare across append/filter, then reload or replace transport;
   confirm selection/comparison clears and late old responses are ignored.

## Next pointer

CP16 — bounded Sessions Catalog read reliability — addressed this follow-on.
Its bounded automated implementation is complete with owner review pending;
current status and evidence are recorded in
[checkpoint-beta-readiness-16](checkpoint-beta-readiness-16.md).
