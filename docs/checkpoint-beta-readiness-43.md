# Beta readiness checkpoint 43 — saved-message search recovery

Status: SCOPED AUTOMATED IMPLEMENTATION COMPLETE; owner and release
acceptance pending (2026-09-09)

CP43 records the saved-message search recovery and validation seam.  The historical
migration tests now reconstruct a genuine bounded v30 database from the
current synthetic v32 fixture: v31/v32 schema objects and their migration
ledger/checksum rows are removed together, leaving contiguous v1–v30 history.
The upgrade then exercises the production v31 backfill and confirms that
retained visible event text is indexed while metadata-only sessions remain
absent.  The rollback test injects a failing v31 migration after the same
valid v30 reconstruction and confirms the database remains at v30.  No
production migration validation was changed or bypassed.

Saved-message pagination keeps the snapshot boundary authoritative.  A
restart is required when a later page is incompatible with the first page;
stale results and load-more are disabled rather than silently reused, while
Search and Start search again remain actionable.  The four client-success
drift predicates are: result snapshot mismatch, result total mismatch, result
limit mismatch, and a duplicate session_id across pages.  A quiet user refusal
remains quiet and does not trigger hidden retry, navigation, or provider/model
work.

Scoped evidence: the 10-test backend search run is green (`4981e0`), and the
frontend dialog/catalog-rail plus search API run is green with 57 tests
(`07d997`). Build and TypeScript validation also passed (`70289d`, with the
usual 500k warning). General built-loopback browser regression passed 29/29
in 30.6s (`255fb0`), with cleanup confirmed, listener released, temporary
artifacts removed, and zero model runtimes; this is general regression, not
dedicated pagination-drift browser proof. This is not a full beta or release
acceptance claim; real providers/models, native owner acceptance, and release
cleanliness remain outside this checkpoint. Privacy scan `0fa9dc` is not
green: exactly two known synthetic CP34 prohibited database artifacts remain,
with no new findings.
