# Beta readiness checkpoint 34 — observed completion foundation

Status: IN PROGRESS. This checkpoint records the bounded CP34 observed-
completion foundation; it does not declare beta, release, provider, native, or
model readiness.

## Scope

CP34a is local, ephemeral observed-completion extraction and interpretation.
It yields a content-free completion candidate only when a strict command
classifier admits the invocation and the same observed provider execution
supplies a terminal, trustworthy result. It does not yet publish or append an
objective requirement result. Generic tool transport success, assistant
completion prose, a typed event without execution facts, and caller-supplied
opaque receipt identifiers are not objective proof.

The issuer remains content-free outside its in-memory boundary: no raw
commands, output, paths, or provider payloads are persisted. CP34b now adds a
bounded current-source candidate manifest, native exact-clause and exact-check
review, a literal human full-criterion-coverage acknowledgement, and a
server-derived objective result. The result retains the provider-reported
observed sequence and outcome, while a distinct content-free receipt reference
binds the native coverage review. CP34c makes that distinction restart-readable
through a versioned, sealed observed-check provenance sidecar; it does not add
raw command or output persistence.
Existing generic `SafeEvent` projection and historical requirement-verification
authorities remain separate and unchanged.

## Audited boundary and adversarial cases

The existing safe-event projector maps a boolean `SafeEvent.success` to a
tri-state verification outcome, but does not validate command semantics,
exit-code shape, terminal status, or evaluability. The existing requirement
verification result issuer fingerprints caller-provided opaque receipt IDs and
does not authenticate an underlying execution receipt. These are useful
historical contracts, not CP34a completion authority.

Independent CP34a tests cover the intended fail-closed boundary: exact command
signatures require observed terminal execution; missing, boolean, string,
fractional, or contradictory exit results remain ineligible; running or
unknown statuses remain unresolved; pytest exits 2–5 do not become objective
check failures; collection, help, dry-run, list, version, and watch modes do
not become objective passes; compound/interpreted/unknown commands abstain;
and the generic `SafeEvent` path remains unaffected.

## Evidence

Historical baseline only: root reported 43 frozen source-review/evidence/
persistence checks (`db0b0f`) and 182 classifier/ingress checks across
`tests/test_verification_classifier.py` and `tests/test_codex_text_ingress.py`
(`551e6c`). These receipts are not CP34a implementation proof.

CP34a automated validation is now green: root reports 251/251 across
`tests/test_observed_check_completion.py`,
`tests/test_observed_check_completion_independent.py`,
`tests/test_verification_classifier.py`, and
`tests/test_codex_text_ingress.py` (`a567b2`). Compatibility coverage is
55/55 across `tests/test_session_reader.py`,
`tests/test_claude_text_source.py`, and
`tests/test_metric_projection_v7.py` (`dd7161`). Root also reports the final
privacy scan green (`e078a2`) and clean diff check (`8db33e`). This foundation
accepts direct pytest only, with strict terminal exit codes 0/1; generic tool
success remains non-objective. No lint tool was available and no installation
was performed.

CP34 overall remains IN PROGRESS: CP34b actual criterion review, exact
full-criterion selection, native review, and server-issued objective result are
implemented at the backend boundary. Root's independent CP34b backend gate is
27/27 green across the new review, API, and synthetic service/SQLite coverage
(`00c124`); the existing persistence file is 17/17 green (`2a1c7e`), and the
source/review/API baseline is 296/296 green (`623131`). The synthetic
service/SQLite proof begins at a validated sealed context; it is not a
provider-to-UI end-to-end claim. The owner-facing UI integration and synthetic
browser coverage are now implemented and validated below; owner, native,
privacy, built-loopback, and release/beta acceptance remain open.

CP34c backend integrity evidence is green. M65
adds a separate content-free observed-check provenance sidecar without changing
legacy authority drafts, result hashes, or seals. The observed append writes
the sidecar and parent authority in one SQLite transaction; replay and the
local read route verify the exact binding. Focused synthetic evidence covers
passed and check-failed issuance, replay, direct child-delete refusal, the
production `delete_for_privacy` source-run cleanup path, and restart reader
rejection of a valid-shaped, digest-mismatched sidecar (2/2 observed E2E,
`c0f32a`). A fault-injected sidecar insert leaves neither parent nor child
record (1/1, `d379cf`). M65 clean-v64 upgrade/rollback, strict numeric input,
and populated-v64 authority/reference/seal/ledger preservation without
backfill are green (7/7, `8d5db6`). The local read route has direct success,
authentication, foreign-session/unknown 404, and private-header coverage.
Root's final combined CP34c integrity gate is 18/18 green (`f9bf81`). The
current-head migration expectation sweep is green after correcting only the
v62/v63 fixture teardown for the new M65 sidecar (the two guided modules 4/4,
`325677`). Root reports the source baseline 252 passed (`d350fe`), review/API
baseline 25 passed (`9b20e1`), OpenAPI 6/6 (`0a411f`), API 8/8 (`b1a3a4`),
frontend 49/49 (`8c5e5f`), production build (`4e2956`), bundle budget
(`3adebd6`), and beta-metrics browser 8/8 (`fac2d1`).

CP34c owner-facing frontend provenance details are now implemented and
targeted-validated: the earlier strict parser/transport/panel gate was 52/52,
the focused panel regression is 32/32 (`45cbf0`), the latest four-file
frontend gate is 63/63 (`5bc422`), and the synthetic beta-metrics browser gate
is 10/10 (`f54d63`). The production build passed (`fdf621`) and bundle budget
passed (`04c179`). Non-test or unknown objective results explain that
direct-pytest provenance is unavailable and that this is not a failed check;
they do not render a disclosure or issue a provenance read. TEST passed/failed
receipts retain the on-demand, identity-bound details and historical 404
handling. The historical snapshot remains unchanged; stale transport responses
are ignored.

The corrected built-loopback gate is 28/28 green (`74f7e4`): its listener
released, temporary state was removed, runtime cleanup completed, and zero
model runtimes remained. A standalone synthetic seed/head proof is also green
(`33ec74`). The fixture publishes a sealed canonical head through the normal
watch lease path, then disables that watch and verifies it is not claimable.
The built UI shows a sealed fictional verification binding while native result
actions are unavailable and makes zero protected POSTs. This is a cold-state,
native-unavailable proof only; it is not positive native review or objective
issuance evidence. Privacy is currently OPEN/RED: the latest scan (`b755ae`)
found only two residual synthetic `.tmp-cp34-privacy` databases, and cleanup
is blocked by policy. Owner/native walkthrough and release/beta acceptance
remain open. No real provider data, models, network services, native execution,
restart, commit, or durable raw execution content is part of this checkpoint.
