from __future__ import annotations

from datetime import timedelta
import sqlite3

import pytest

from prompt_enhancer.application.analysis.claim_grounding_evidence import (
    ClaimCensusCandidateManifestEntry, ClaimCensusClassification,
    ClaimCensusClassificationEntry, build_reviewed_claim_census,
)
from prompt_enhancer.application.analysis.claim_grounding_review import ClaimGroundingReviewConflictError
from prompt_enhancer.application.analysis.metric_publication_v2 import metric_publication_v2_fingerprint
from prompt_enhancer.database import Database, DatabaseInvariantError
from prompt_enhancer.infrastructure.sqlite.claim_grounding_census import SqliteClaimGroundingCensusRepository

from test_model_ensemble_r8_persistence import _r8_record, _r8_setup
from test_requirement_plan_evidence_persistence import ARTIFACT_IDS


def _repository(database: Database) -> SqliteClaimGroundingCensusRepository:
    return SqliteClaimGroundingCensusRepository(
        database._connection, database.initialize, identifiers=ARTIFACT_IDS
    )


def _census(source, publication, *, marker: str = "9"):
    candidate_id, message_id = marker * 64, ("e" if marker != "e" else "d") * 64
    candidates = (
        ClaimCensusCandidateManifestEntry(
            candidate_id=candidate_id, message_id=message_id,
            message_sequence=1, clause_index=0,
        ),
    )
    from prompt_enhancer.application.analysis.claim_grounding_evidence import ClaimCensusSourceManifest
    manifest = ClaimCensusSourceManifest(
        session_id=source.session_id, source_run_id=source.run_id,
        source_window_fingerprint=source.input_fingerprint,
        source_schema_version=source.source_schema_version,
        text_adapter_version=source.adapter_version, candidates=candidates,
        candidate_count=1,
        manifest_fingerprint=ARTIFACT_IDS.fingerprint(
            "claim-grounding-census-manifest-v1", (
                source.session_id, source.run_id, source.input_fingerprint,
                source.source_schema_version, source.adapter_version,
                "message-clause-coordinates-en-pl-v1", "claim-grounding-census-v1",
                "native-reviewed-agent-claim-census-v1", candidate_id, message_id, "1", "0",
            ),
        ),
    )
    census = build_reviewed_claim_census(
        manifest, classifications=(ClaimCensusClassificationEntry(
            candidate_id=candidate_id, classification=ClaimCensusClassification.MATERIAL_CLAIM,
        ),), identifiers=ARTIFACT_IDS,
    )
    return manifest, census, metric_publication_v2_fingerprint(publication)


def test_repository_restarts_replays_and_rejects_tampering(tmp_path) -> None:
    database, source, plan, action, service, verification = _r8_setup(tmp_path)
    run = _r8_record(source.session_id, run_character="f", request_character="1",
                     plan_snapshot=plan, action_snapshot=action,
                     verification_snapshot=verification)
    database.model_ensemble_repository().save_completed(run)
    publication = run.receipt.metric_publication_v2
    assert publication is not None
    manifest, census, publication_fingerprint = _census(run, publication)
    repository = _repository(database)
    created, issued = repository.issue(
        census_id="9" * 64, census=census, manifest=manifest,
        idempotency_key_digest="8" * 64, command_fingerprint="7" * 64,
        expected_publication_fingerprint=publication_fingerprint,
        created_at=run.receipt.completed_at + timedelta(seconds=1),
    )
    assert issued is True
    replay, issued = repository.issue(
        census_id="9" * 64, census=census, manifest=manifest,
        idempotency_key_digest="8" * 64, command_fingerprint="7" * 64,
        expected_publication_fingerprint=publication_fingerprint,
        created_at=run.receipt.completed_at + timedelta(seconds=9),
    )
    assert issued is False and replay == created
    # A fresh command cannot turn a caller-supplied publication digest into
    # authority; the transaction compares it to the current sealed source.
    with pytest.raises(ClaimGroundingReviewConflictError):
        repository.issue(
            census_id="a" * 64, census=census, manifest=manifest,
            idempotency_key_digest="b" * 64, command_fingerprint="c" * 64,
            expected_publication_fingerprint="d" * 64,
            created_at=run.receipt.completed_at,
        )
    with database._connection(readonly=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM claim_grounding_reviewed_censuses").fetchone()[0] == 1
    restarted = Database(database.path); restarted.configure_local_artifact_id_factory(ARTIFACT_IDS)
    assert _repository(restarted).get("9" * 64) == created
    with pytest.raises(ClaimGroundingReviewConflictError):
        repository.issue(census_id="9" * 64, census=census, manifest=manifest,
                         idempotency_key_digest="8" * 64, command_fingerprint="6" * 64,
                         expected_publication_fingerprint=publication_fingerprint,
                         created_at=run.receipt.completed_at)
    with sqlite3.connect(database.path) as connection:
        connection.execute("DROP TRIGGER claim_grounding_reviewed_census_classifications_no_update")
        connection.execute("UPDATE claim_grounding_reviewed_census_classifications SET candidate_id=?", ("6" * 64,))
        connection.commit()
    with pytest.raises(DatabaseInvariantError):
        _repository(restarted).get("9" * 64)


def test_replay_survives_newer_source_but_fresh_old_issue_fails(tmp_path) -> None:
    database, source, plan, action, _service, verification = _r8_setup(tmp_path)
    first = _r8_record(source.session_id, run_character="f", request_character="1",
                       plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    runs = database.model_ensemble_repository(); runs.save_completed(first)
    publication = first.receipt.metric_publication_v2; assert publication is not None
    manifest, census, publication_fingerprint = _census(first, publication)
    repository = _repository(database)
    issued, created = repository.issue(census_id="9" * 64, census=census, manifest=manifest,
                                       idempotency_key_digest="8" * 64, command_fingerprint="7" * 64,
                                       expected_publication_fingerprint=publication_fingerprint,
                                       created_at=first.receipt.completed_at)
    assert created is True
    newer = _r8_record(source.session_id, run_character="d", request_character="4",
                        plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    newer = newer.model_copy(update={"receipt": newer.receipt.model_copy(
        update={"completed_at": first.receipt.completed_at + timedelta(minutes=1)}
    )})
    runs.save_completed(newer)
    replay, created = repository.issue(census_id="9" * 64, census=census, manifest=manifest,
                                       idempotency_key_digest="8" * 64, command_fingerprint="7" * 64,
                                       expected_publication_fingerprint=publication_fingerprint,
                                       created_at=newer.receipt.completed_at)
    assert created is False and replay == issued
    recovered = repository.get_by_idempotency(session_id=source.session_id, idempotency_key_digest="8" * 64)
    assert recovered == issued and recovered.command_fingerprint == "7" * 64
    with pytest.raises(ClaimGroundingReviewConflictError):
        repository.issue(census_id="a" * 64, census=census, manifest=manifest,
                         idempotency_key_digest="b" * 64, command_fingerprint="c" * 64,
                         expected_publication_fingerprint=publication_fingerprint,
                         created_at=newer.receipt.completed_at)


def test_page_snapshot_bounds_membership_and_rollback(tmp_path, monkeypatch) -> None:
    database, source, plan, action, _service, verification = _r8_setup(tmp_path)
    run = _r8_record(source.session_id, run_character="f", request_character="1",
                     plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    database.model_ensemble_repository().save_completed(run)
    publication = run.receipt.metric_publication_v2; assert publication is not None
    repository = _repository(database)
    for ordinal, marker in enumerate(("4", "5")):
        manifest, census, fingerprint = _census(run, publication, marker=marker)
        _record, created = repository.issue(census_id=("9" if ordinal == 0 else "8") * 64,
                                            census=census, manifest=manifest,
                                            idempotency_key_digest=("7" if ordinal == 0 else "6") * 64,
                                            command_fingerprint=("5" if ordinal == 0 else "4") * 64,
                                            expected_publication_fingerprint=fingerprint,
                                            created_at=run.receipt.completed_at + timedelta(seconds=ordinal))
        assert created is True
    first, snapshot = repository.list_page(source.session_id, limit=1, offset=0)
    second, same_snapshot = repository.list_page(source.session_id, limit=1, offset=1, snapshot=snapshot)
    assert (len(first) == len(second) == 1 and snapshot == same_snapshot
            and first[0].census_id != second[0].census_id)
    for bad_limit, bad_offset in ((True, 0), (1.0, 0), (1, False), (1, 0.0)):
        with pytest.raises(ValueError):
            repository.list_page(source.session_id, limit=bad_limit, offset=bad_offset)
    manifest, census, fingerprint = _census(run, publication, marker="6")
    repository.issue(census_id="a" * 64, census=census, manifest=manifest,
                     idempotency_key_digest="b" * 64, command_fingerprint="c" * 64,
                     expected_publication_fingerprint=fingerprint,
                     created_at=run.receipt.completed_at - timedelta(seconds=1))
    with pytest.raises(ClaimGroundingReviewConflictError):
        repository.list_page(source.session_id, limit=1, offset=0, snapshot=snapshot)
    original = repository._required_record
    def fail_after_write(*args):
        raise RuntimeError("synthetic post-write failure")
    monkeypatch.setattr(repository, "_required_record", fail_after_write)
    manifest, census, fingerprint = _census(run, publication, marker="7")
    with pytest.raises(RuntimeError):
        repository.issue(census_id="d" * 64, census=census, manifest=manifest,
                         idempotency_key_digest="e" * 64, command_fingerprint="f" * 64,
                         expected_publication_fingerprint=fingerprint,
                         created_at=run.receipt.completed_at)
    monkeypatch.setattr(repository, "_required_record", original)
    with database._connection(readonly=True) as connection:
        for table in ("claim_grounding_reviewed_censuses", "claim_grounding_reviewed_census_classifications", "claim_grounding_reviewed_census_seals"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE census_id=?", ("d" * 64,)).fetchone()[0] == 0  # noqa: S608


def test_missing_seal_and_latest_missing_r8_fail_closed(tmp_path) -> None:
    database, source, plan, action, _service, verification = _r8_setup(tmp_path)
    run = _r8_record(source.session_id, run_character="f", request_character="1",
                     plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    database.model_ensemble_repository().save_completed(run)
    publication = run.receipt.metric_publication_v2; assert publication is not None
    manifest, census, fingerprint = _census(run, publication)
    repository = _repository(database)
    repository.issue(census_id="9" * 64, census=census, manifest=manifest,
                     idempotency_key_digest="8" * 64, command_fingerprint="7" * 64,
                     expected_publication_fingerprint=fingerprint, created_at=run.receipt.completed_at)
    with sqlite3.connect(database.path) as connection:
        connection.execute("DROP TRIGGER claim_grounding_reviewed_census_seals_privacy_delete_only")
        connection.execute("DELETE FROM claim_grounding_reviewed_census_seals")
        connection.commit()
    with pytest.raises(DatabaseInvariantError):
        repository.get("9" * 64)
    with database._connection() as connection:
        connection.execute("DROP TRIGGER session_metric_r8_seals_privacy_delete_only")
        connection.execute("DELETE FROM session_model_ensemble_metric_publication_v2_seals_r8 WHERE run_id=?", (run.run_id,))
        connection.commit()
    manifest, census, fingerprint = _census(run, publication, marker="6")
    with pytest.raises(ClaimGroundingReviewConflictError):
        repository.issue(census_id="a" * 64, census=census, manifest=manifest,
                         idempotency_key_digest="b" * 64, command_fingerprint="c" * 64,
                         expected_publication_fingerprint=fingerprint, created_at=run.receipt.completed_at)
