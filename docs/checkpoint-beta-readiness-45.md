# Beta readiness checkpoint 45 — claim-grounding trajectory

Status: CP45d IN PROGRESS — CP45a/CP45c scoped verified; no capability promotion
(2026-09-09)

CP45a establishes the contracts foundation for the full `outcome.agent_claim_grounding`
trajectory. The live safe-event decoder currently exposes neither
`MATERIAL_CLAIM_OPPORTUNITIES` nor `MATERIAL_CLAIM_EVIDENCE_LINKS`. The
compatible Codex text source does contain complete agent `RESPONSE` text and normalized observed-check
completions, but there is not yet an exhaustive material-claim census or a
checked relation between claims, opportunities, links, and outcomes. The
measured-path operability inventory remains **18/20**; this checkpoint does
not change the operability catalog or promote a capability.

The intended evidence progression is:

1. **CP45a — contracts foundation (scoped verified complete).** A content-free
   census and provenance schema with tests. Unknown, incomplete, and overflow
   states remain distinct from an empty set or zero; no durable model stores
   fake receipts or claim prose.
2. **Native reviewed census.** An ephemeral native review must enumerate the
   entire assistant-clause census for the scoped source, window, and run, then
   persist only the bounded review receipt and provenance—not transcript
   content or a model-authored claim judgment.
3. **Checked evidence links.** Link reviewed claim opportunities to
   app-issued observed checks and native coverage review. The client or model
   cannot mint a pass; the adapter reuses the typed projection and preserves
   the existing authority boundary. Native confirmation establishes
   classification and coverage, not test outcome.
4. **Composition and fresh seal.** Complete source composition, readiness,
   API/UI, and persistence work, followed by fresh-seal integration. Only
   then can the claim-grounding path be considered for operability **19/20**;
   provider evidence, native acceptance, and release promotion remain separate
   gates.

The trajectory deliberately adds no semantic enum and widens no safe-event
capability. CP45a's final Root receipt records 43 tests passed in 1.25s
(`14b72a`): 11 owning tests, 8 adversarial tests, and the existing 24-test
baseline, with diff checks green. CP45a is scoped and verified; the native
census, UI, persistence, and remaining composition work keep whole CP45 in
progress. No production wiring, UI change, build, or browser proof is claimed.

## CP45b.1 — review-store foundation (scoped verified)

CP45b.1 adds a bounded, ephemeral review-store foundation over the existing
claim-grounding census contracts. `begin_review` obtains the current sealed
source through a server-owned resolver and returns the content-free manifest,
ephemeral review candidates, and a one-use receipt. `consume_review` requires
the receipt, the expected manifest identity, and a complete classification set;
it re-resolves the current source and rejects stale, expired, replayed, or
otherwise mismatched receipts. The store is process-local and does not establish
native confirmation or metric authority.

The actual native gate/API/UI, complete source composition, and persistence are
not yet wired. The measured-path operability inventory remains **18/20**;
CP45b.1 does not promote a capability or claim release readiness. Existing
CP45a records remain unchanged.

Root verification records 59 tests passed in 1.38s (`37fa81`), covering the
CP45b.1 implementation, review adversarial cases, CP45a foundations, and the
baseline metrics; the privacy receipt is `4dd0e2`. The two known CP34 database
artifact checks remain not green, while the bounded diff is green at `37fa81`.
No native HTTP gate, production source resolver, API/UI surface, persistence,
or metric projection wiring is claimed. The next step remains the actual
production native-census workflow; no claim metric has shipped.

## CP45b.2 — native-gated HTTP and shared API (scoped verified)

CP45b.2 wires the bounded claim-grounding review route through the existing
native confirmation boundary and exposes the matching shared API contract. The
begin operation is bound to the expected current `source_run_id` and
`source_window_fingerprint`; consume requires the one-use review receipt,
review fingerprint, manifest fingerprint, and a complete classification set.
Responses remain ephemeral/content-free at rest and are proposal-only: no
measured result, durable claim, or metric authority is established.

Root verification records the server integration at `f42789` (16.27s), the
schema byte-exact check at `2c7a45` (1 passed), and frontend API generation
verification at `dcb8a4`. The shared frontend parser/transport tests record 9
tests passed in 2.25s (`c4ad4d`); synthetic confirmation adapters exercised the
native gate contract, not real native proof. The measured-path operability
inventory remains **18/20**. Broader root transport regression records 216
tests passed in 3.78s (`bf3222`). CP45b.3 panel/UI work remains separately
scoped; no persistence or measured promotion is claimed. Prior CP45a/CP45b.1
receipts remain unchanged.

## CP45b.3 — panel/UI and shared API surface (scoped automated verified)

CP45b.3's bounded UI/API surface is automated verified, not a whole-CP45
completion claim. The fresh independent backend combined record is 58 tests
passed in 5.73s (`042a05`). The fresh frontend record is 69 tests passed in
6.81s (`ea686f`), across six files. The real-app TypeScript check is
`047964`; the production build is `7db36b`, with the clear `8765` listener
receipt and gate passed. The API check is `203a99`.

The general disposable built-browser smoke records 29 tests passed in 31.8s
(`e6e5e0`), with cleanup confirmed: listener released, zero model runtimes,
temporary artifacts removed, and server failure false. It is not proof of a
dedicated real native claim journey. The fresh privacy scan is `34817e` and
fails only on the same two known CP34 database-artifact fixtures; no new
findings were reported. The prior privacy receipt `331d9e` remains unchanged.
CP45b.3 does not establish durable persistence,
native journey proof, a measured metric, or release readiness. The
measured-path operability inventory remains **18/20**.

## CP45c — durable reviewed census (scoped automated verified)

CP45c is scoped automated verified, not a whole-CP45 completion receipt. M66 has
scoped migration coverage: Root records 4 tests passed in 2.87s (`5cff17`),
covering an actual synthetic M65-to-M66 upgrade plus synthetic source-binding,
enum/exclusion, count/coordinate, immutable-seal, and privacy-cascade
invariants. The bounded SQLite repository now has scoped synthetic evidence:
Root records 8 tests passed in 16.86s (`95f339`), covering current/newer-source
and current-publication fencing,
restart recovery, exact replay and idempotency metadata, missing-seal failure,
page bounds and snapshot membership changes, and atomic rollback. A prior
cross-regression records 14 tests passed in 17.13s (`d0e99c`). These are
repository-level synthetic checks only; no real native proof is implied.

The durable reservation/application service core and API/bootstrap composition
now have scoped independent evidence. The durable API/bootstrap verification
records 7 tests passed in 22.43s (`45e9a0`), including real-SQLite HTTP
persistence/replay, restarted-database recovery, cross-session 404 isolation,
stale-source no-row behavior, oversized preflight rejection before native
confirmation, and unknown-outcome handling, plus 2 bootstrap checks. The
schema verification records 6 tests passed in 60.97s (`25bdf9`), covering the
exact durable routes, request locations/bounds, and DTO privacy/flag contract.
An independent existing review API, objective projection, typed evidence, and
metric-operability verification records 31 tests passed in 14.11s (`f65ceb`).
These records do not establish live native proof or promotion.

The repository persists only reviewed census identities, closed
classifications and exclusion reasons, source/run/window and publication
fingerprints, versions, counts, and keyed authority metadata. These
classifications remain sensitive derived data even when no candidate prose is
stored; persistence must not describe them as anonymous or erase their
provenance. The application service core is implemented and independently
verified as noted above, and durable HTTP/bootstrap composition is now
scoped-verified. The shared frontend parser, transport, older review flows,
and metric-workspace surface have an independent verification record of 46
tests passed in 7.03s (`8b98f2`). The durable UI is now implemented and scoped
automated verified, including controlled disclosure, unknown recovery,
bounded snapshot pagination, classification privacy flags, and read-only
saved-list behavior. Observed-check linkage and fresh-seal integration remain
separate verification work; these records are supporting checks, not a CP45
completion or release receipt.

The remaining work moved to CP45d is:

1. Complete observed-check linkage and fresh-seal integration; neither may
   imply measured success or metric authority without objective evidence.
2. Obtain real native journey, app-restart, and build evidence, then issue a
   fresh integration/promotion receipt.

The measured-path operability inventory remains **18/20**; whole CP45 and
beta remain incomplete, with no real native or app-restart proof in this
slice; production build evidence exists but is not a native-journey receipt.
The known privacy-scanner gate remains not green for the two CP34
database-artifact fixtures. All CP45a/CP45b receipts remain unchanged,
including `14b72a`, `95f339`, and `d0e99c`.

## CP45d — observed-check linkage (in progress)

CP45d's pure typed-link and source-scope slice is verified: 109 tests passed in
1.64s (receipt `74d06b`). Follow-on actual SQLite source-plus-links coverage
records 19 tests passed in 6.67s (receipt `1bed02`). These checks establish
source-bound typed composition and preserve the keyed proposal boundary; they
do not establish native authority, model execution, restart proof, objective
test outcome, or metric promotion. Existing production build evidence remains
build evidence only, not proof of a native claim journey.

The lifecycle review remains in progress. The latest six-suite Root review
supersedes `f663d6` and `ef11b3` with 52 tests passed in 6.38s under `-W error`
(receipt `398881`), covering pure links/source/review/adversarial/route
coverage, full identity and canonical-descriptor commitments, and typed
preflight. Root's bootstrap and real-`create_app` composition receipt
`f2869b` records 4 tests passed in 12.30s, validating factory/context/identity
construction, route absent/present behavior, successful browser preview,
one-shot cleanup, and typed close failure. The begin route is now production
API/bootstrap-wired, but not UI-wired. The four
historically reproduced issues in receipt `d6565b`—missing receipt-source
read, stale reservation reuse under a frozen clock, close-during-begin
resurrection, and begin-after-close—are fixed and are not current blockers.
The post-source expiry fence and token allocation before mutation are also
implemented. Full source/census binding, schema export/client generation, UI,
durable coverage and projection, bounded session-revocation state, and broader
native acceptance remain pending. The measured-path operability inventory
remains **18/20**; no metric promotion, model, or app-restart evidence is
claimed. Whole CP45 and beta remain incomplete.

The CP45d schema/client slice is now independently verified. Exported and
generated schema completeness records six schema tests passed in 101.84s
(receipt `2d5282`), and the API contract check passed (receipt `90ade1`). The
typed client method and strict frontend review parser add nine passing tests as
reported above. The broader regression record is 7162d332, with all tests
passing in 4.95s. These receipts establish typed contract coverage only; the
dedicated transport tests remain in progress. UI, durable coverage/projection,
and native acceptance remain pending. No metrics promotion, beta completion,
app-restart evidence, or model/provider execution is claimed; the measured-path
operability inventory remains **18/20**.

The frontend app typecheck was rerun after correcting the strict parser's
validated-object narrowing and passed with no diagnostics
(`npm exec -- tsc --noEmit -p tsconfig.app.json`). The dedicated parser suite
also remains green at 9 tests passed. This is a corrected client verification
record; it does not change the pending transport, UI, durable projection, or
native-acceptance gates.

The content-free candidate-selection endpoint is now backend-verified: `GET
/v1/sessions/{session_id}/claim-grounding-review/links/candidates/{census_id}`
returns the exact material-candidate subset and normalized observed-check
metadata, without claim prose, tool text, requirement-opportunity dependency,
or native confirmation. Root's backend receipt `98eea349` records four source,
review, and API suites passed in 6.82s, including authorization denial,
private/read-only behavior, and source-drift fencing. The frontend contract and
transport contract suites record three suites passed in 4.29s (`4fcc2f23`),
including candidate parsing, and the actual app typecheck passed (`7f7054`).
The candidate schema export/client generation is now complete. The read-only
candidate GET transport records two client suites passed in 2.72s (Root receipt
`b826b4`); this is transport-contract evidence only and does not prove a
native journey. The attached, collapsed current-saved-source UI child is now
implemented with content-free candidate/check selection, 50-row pagination,
at most 128 selected checks, and a native-gated ephemeral preview that may
show command/effect text only after that gate. It has no durable link save,
no outcome issuance, and no metric authority or promotion.

The latest four UI-plus-transport suites passed in 6.49s (Root receipt
`35c6b8`). The UI remains **in progress**, not a final native or visual
acceptance record: immediate-render masking for an in-place source/transport
replacement is still being corrected, and the scoped tests do not substitute
for browser-build, app-restart, model/provider execution, or real native-user
journey evidence. Durable linkage, projection, native acceptance, metric
promotion, app-restart/model evidence, whole CP45, and beta completion remain
pending.

The latest four-suite UI/transport record `9f42be39` passed in 5.85s, and the
production build passed under `d34df3` with the `8765` listener absent after
cleanup; the existing >500 KB chunk warning remains. The link child is now
scoped automated verified with current-source binding, content-free selection,
bounded candidate/check surfaces, native-gated ephemeral preview, and
state-owned owner fencing. No dedicated StrictMode/layout-effect probe is
claimed, and this is not native visual/browser acceptance evidence. Durable
link saving/projection, native acceptance, metric promotion, app-restart/model
evidence, whole CP45, and beta completion remain pending.

## CP45e — durable link foundation (review in progress)

The M67 schema migration foundation is now implemented and under review. The
immutable reservation snapshot is implemented in the application layer, while
the repository, native persistence API/UI, and metric projection are not yet
implemented. The per-claim append-only history must persist only the selected completion
subset and its normalized content-free provenance, never claim prose or tool
text. Because a selected subset cannot recompute the full
`observed_set_fingerprint`, each event must retain the full source-set
commitment separately and carry a keyed selected-evidence fingerprint/seal for
the persisted subset.

Preview begin is not write approval. A separate native-confirmed persist step
must reserve the immutable source snapshot, recheck the sealed publication
fence, and require a keyed issuance seal. Idempotent replay must be checked
before acquiring a fresh reservation, including when the original ephemeral
receipt has expired; identical command fingerprints return the existing
immutable event, while mismatches conflict. The insert of the append-only event
and selected-reference provenance is atomic with the current sealed source
fence. History rows remain proposal-only and non-measured: metadata persistence
is explicit (`metadata_persisted=true`, `candidate_prose_persisted=false`), and
no ambiguous `content_persisted=false` claim is used for persisted metadata.
There is no implicit latest-record promotion; complete coverage and any future
metric projection remain separate reviewed operations.

CP45e reservation progress is scoped-verified: the immutable content-free
reservation snapshot captures the exact reviewed decision, selected normalized
completion provenance, and all source/review bindings. Its non-metric flags are
constructor-locked; command mutation is rejected; release/finalize clear the
reservation; and expired/stale snapshots are denied. Root receipt `9c301b`
records 51 tests passed in 7.62s (Terra's focused record). The migration
adversarial suite independently records 11 synthetic SQLite tests passed in
0.92s. Repository behavior, atomic publication/source-fence writes,
idempotent recovery, native-confirmed persistence API/UI, and metric projection
remain separate work. No durable link save or metric promotion exists yet.

The schema slice is now scoped verified: Root's six-suite M66/M67, independent
adversarial, census-repository, review, and review-adversarial record reports
54 tests passed in 29.19s (`6cd501`), with clean bounded diff verification
(`72bfb2`). Coverage includes full synthetic schema 66→67 upgrade with sealed
parent preservation, malformed timestamp rejection, and `INSERT OR REPLACE`
append-only protections. The next checkpoint is repository-level atomic issue,
idempotent replay/recovery, and keyed-seal behavior, followed separately by the
native-confirmed save path. Native persistence API/UI, metric projection,
promotion, and beta completion remain pending.

The durable-link repository is scoped-verified by split evidence, not by a
single green combined run. The combined root receipt `16c45e` records 14
passed and 1 failed in 81.99s; the failure was a synthetic missing-publication
deletion fixture whose commit was absent. The corrected focused rerun is
`d2bf76` (1 passed in 6.07s), Terra's owning repository slice is 7 passed in
39.37s, and the agent adversarial file is 8 passed in 32.11s. These receipts
do not claim a fully green combined suite. Service orchestration/API/UI
saving remains unimplemented. The release-facing distribution gates are
tracked in `docs/checkpoint-beta-distribution.md`.
