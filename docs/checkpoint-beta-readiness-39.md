# CP39 — reviewed directory-move artifact projection

Status: IN PROGRESS (automated implementation and scoped validation complete;
owner, native, privacy, release, and beta acceptance remain open). This
checkpoint adds truthful client handling for the server-issued directory-move
artifact projection. A verified filesystem move still does not claim that
subtree contents were enumerated or reviewed.

The frontend decoder now requires the exact `artifact_projection` state
(`not_applicable`, `complete`, or `recovery_required`) and the bounded
`artifact_versions_advanced` count. `complete` requires a positive count;
the other states require zero, with a maximum of 100 advanced versions.
The workspace UI reports updated tracking, unresolved recovery, or no tracked
artifacts without offering a retry-move/recovery button. MCP guidance matches
the same distinction and does not claim directory contents were reviewed.

## Targeted evidence

- Historical RED reproduction at `a1c8f6`: the filesystem subtree moved, but
  captured nested artifact heads remained on their old paths. The regression
  is synthetic and includes service recomposition/restart plus immutable
  pre-move versions; the later production fix is covered by the green results
  below.
- Backend artifact/directory focused validation: 40/40, receipt `7b382f`.
  The original focused directory regression also passed at root receipt
  `7dfbfa`; this is not a whole-application integration result. Independent policy regressions are
  5/5 in 2.07s, covering archived preservation, removed exclusion, exact
  segment matching, foreign-session intent refusal, and all-heads-unchanged
  stale CAS.
- Final frozen module ledger: 151/151 in 65.23s, receipt `e633a5`, across
  artifact (35), directory (9), policy (5), local (57), and lifecycle (45)
  checks.
  This is a split, overlapping total rather than an additive suite count.
  The earlier 149/149 ledger (`d24ecd` / terminal `100141`) remains an
  interim receipt. Build `030503`, bundle `639510`, schema `d55fea`,
  TypeScript `6a1b40`, and API drift `d85b29` are green.
- Independent decoder validation: 31/31, receipt `63263b`.
- Generated-schema TypeScript gate: `6a1b40`; API drift check: `d85b29`.
- Frontend workspace/MCP focused subset: 325/325 across four files in 20.17s
  (overlapping subset, not additive), including success, not-applicable,
  recovery-required, malformed, and over-limit projection cases.
- Synthetic intercepted browser matrix: 4/4 in 17.4s using
  `npm run test:e2e:intercepted -- --workers=1 --grep "reports (complete|recovery_required) after a reviewed folder move"`.
  It covers 320px and 1440px, asserts the updated folder path, the complete
  count or recovery explanation, exactly one apply request, no retry-move
  affordance, and no horizontal overflow. Fixture servers were released;
  ports 4173 and 4175 were absent afterward.

## Remaining boundary

The final general built regression is 29/29 (`3cac22`) with listener/runtime/
temporary-state cleanup, zero models, and no server failure. Source-budget,
concurrency, and warning checks now have targeted coverage; Terra's final
backend recovery items remain under integration review. The owner click-later
boundary still covers folder movement, artifact history, and interrupted
resume without a native claim. Privacy remains OPEN/RED: the latest scan
(`05e478`) found exactly two known synthetic `.tmp-cp34-privacy` metrics
databases and no new finding. The synthetic `.tmp-cp39-lifecycle` directory
is a known leftover, not a scanner finding. Native acceptance, owner, release,
and broad-beta gates are not claimed. No provider, model, native process, or
external network activity is used by this checkpoint.
