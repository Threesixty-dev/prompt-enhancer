from __future__ import annotations

from datetime import timedelta
import sqlite3

import pytest

from prompt_enhancer.application.analysis.claim_grounding_link_persistence import ClaimGroundingLinkConflictError
from prompt_enhancer.application.analysis.claim_grounding_link_review import (
    ClaimGroundingLinkObservedCompletionSnapshot, ClaimGroundingLinkReviewedDecision,
)
from prompt_enhancer.application.analysis.claim_grounding_links import ClaimLinkCoverageDecision
from prompt_enhancer.application.analysis.metric_publication_v2 import metric_publication_v2_fingerprint
from prompt_enhancer.database import Database, DatabaseInvariantError
from prompt_enhancer.infrastructure.sqlite.claim_grounding_census import SqliteClaimGroundingCensusRepository
from prompt_enhancer.infrastructure.sqlite.claim_grounding_links import SqliteClaimGroundingLinkRepository

from test_claim_grounding_census_repository import _census
from test_model_ensemble_r8_persistence import _r8_record, _r8_setup
from test_requirement_plan_evidence_persistence import ARTIFACT_IDS


def _repositories(database: Database):
    return (
        SqliteClaimGroundingCensusRepository(database._connection, database.initialize, identifiers=ARTIFACT_IDS),
        SqliteClaimGroundingLinkRepository(database._connection, database.initialize, identifiers=ARTIFACT_IDS),
    )


def _decision(census, *, provider: str, reference: str = "4" * 64,
              decision: ClaimLinkCoverageDecision = ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS,
              outcome: str = "passed") -> ClaimGroundingLinkReviewedDecision:
    completion = ClaimGroundingLinkObservedCompletionSnapshot(
        source_reference_id=reference, observed_sequence=3, provider=provider,
        check_kind="test", outcome=outcome, provider_execution_status="completed",
        exit_code=0 if outcome == "passed" else 1,
        source_completion_schema_version="observed-check-completion-v1",
        outcome_interpreter_version="pytest-exit-status-v1", classifier_version="local-command-rules-v1",
        normalizer_version="strict-shell-free-v2", rule_id="test.pytest",
    )
    return ClaimGroundingLinkReviewedDecision(
        session_id=census.census.session_id, census_id=census.census_id,
        candidate_id=census.census.classifications[0].candidate_id,
        source_run_id=census.census.source_run_id,
        source_window_fingerprint=census.census.source_window_fingerprint,
        census_fingerprint=census.census.census_fingerprint,
        manifest_fingerprint=census.manifest.manifest_fingerprint,
        observed_set_fingerprint="5" * 64, review_receipt_id="6" * 64,
        review_fingerprint="7" * 64,
        decision=decision,
        selected_check_references=() if decision is not ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS else (reference,),
        selected_observed_completions=() if decision is not ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS else (completion,),
    )


def _issued(tmp_path):
    database, source, plan, action, _service, verification = _r8_setup(tmp_path)
    run = _r8_record(source.session_id, run_character="f", request_character="1",
                     plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    database.model_ensemble_repository().save_completed(run)
    publication = run.receipt.metric_publication_v2; assert publication is not None
    manifest, reviewed, publication_fp = _census(run, publication)
    censuses, links = _repositories(database)
    census, _ = censuses.issue(census_id="9" * 64, census=reviewed, manifest=manifest,
        idempotency_key_digest="8" * 64, command_fingerprint="7" * 64,
        expected_publication_fingerprint=publication_fp, created_at=run.receipt.completed_at)
    return database, run, links, census, publication_fp


def test_link_repository_roundtrip_replay_restart_and_selected_subset(tmp_path) -> None:
    database, run, links, census, publication = _issued(tmp_path)
    decision = _decision(census, provider=run.provider.value)
    record, created = links.issue(link_review_id="a" * 64, reviewed_decision=decision,
        idempotency_key_digest="b" * 64, command_fingerprint="c" * 64,
        expected_publication_fingerprint=publication, created_at=run.receipt.completed_at + timedelta(seconds=1))
    assert created and record.reviewed_decision.selected_check_references == ("4" * 64,)
    replay, created = links.issue(link_review_id="a" * 64, reviewed_decision=decision,
        idempotency_key_digest="b" * 64, command_fingerprint="c" * 64,
        expected_publication_fingerprint=publication, created_at=run.receipt.completed_at + timedelta(seconds=2))
    assert not created and replay == record
    restarted = Database(database.path); restarted.configure_local_artifact_id_factory(ARTIFACT_IDS)
    assert _repositories(restarted)[1].get(session_id=census.census.session_id, link_review_id="a" * 64) == record
    assert _repositories(restarted)[1].get(session_id="d" * 64, link_review_id="a" * 64) is None


def test_link_repository_conflicts_rolls_back_and_rejects_tampering(tmp_path, monkeypatch) -> None:
    database, run, links, census, publication = _issued(tmp_path)
    decision = _decision(census, provider=run.provider.value)
    original = links._required_record
    monkeypatch.setattr(links, "_required_record", lambda *args: (_ for _ in ()).throw(RuntimeError("synthetic failure")))
    with pytest.raises(RuntimeError):
        links.issue(link_review_id="a" * 64, reviewed_decision=decision, idempotency_key_digest="b" * 64,
            command_fingerprint="c" * 64, expected_publication_fingerprint=publication, created_at=run.receipt.completed_at)
    monkeypatch.setattr(links, "_required_record", original)
    with database._connection(readonly=True) as connection:
        for table in ("claim_grounding_link_reviews", "claim_grounding_link_review_selected_references", "claim_grounding_link_review_seals"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0  # noqa: S608
    record, _ = links.issue(link_review_id="a" * 64, reviewed_decision=decision, idempotency_key_digest="b" * 64,
        command_fingerprint="c" * 64, expected_publication_fingerprint=publication, created_at=run.receipt.completed_at)
    with pytest.raises(ClaimGroundingLinkConflictError):
        links.issue(link_review_id="a" * 64, reviewed_decision=decision, idempotency_key_digest="b" * 64,
            command_fingerprint="d" * 64, expected_publication_fingerprint=publication, created_at=run.receipt.completed_at)
    with pytest.raises(ClaimGroundingLinkConflictError):
        links.issue(link_review_id="a" * 64, reviewed_decision=_decision(census, provider=run.provider.value, reference="d" * 64),
            idempotency_key_digest="b" * 64, command_fingerprint="c" * 64,
            expected_publication_fingerprint=publication, created_at=run.receipt.completed_at)
    with sqlite3.connect(database.path) as connection:
        connection.execute("DROP TRIGGER claim_grounding_link_review_references_no_update")
        connection.execute("UPDATE claim_grounding_link_review_selected_references SET observed_sequence=4")
        connection.commit()
    with pytest.raises(DatabaseInvariantError):
        links.get(session_id=census.census.session_id, link_review_id=record.link_review_id)


@pytest.mark.parametrize("decision_kind,outcome", [
    (ClaimLinkCoverageDecision.REVIEWED_NO_SUPPORT, None),
    (ClaimLinkCoverageDecision.UNRESOLVED, None),
    (ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS, "check_failed"),
])
def test_link_repository_preserves_closed_negative_and_failed_observed_decisions(tmp_path, decision_kind, outcome) -> None:
    database, run, links, census, publication = _issued(tmp_path)
    decision = _decision(census, provider=run.provider.value, decision=decision_kind,
                         outcome="passed" if outcome is None else outcome)
    marker = {ClaimLinkCoverageDecision.REVIEWED_NO_SUPPORT: "a",
              ClaimLinkCoverageDecision.UNRESOLVED: "b",
              ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS: "c"}[decision_kind]
    record, created = links.issue(link_review_id=marker * 64, reviewed_decision=decision,
        idempotency_key_digest=("d" if marker != "d" else "e") * 64,
        command_fingerprint="e" * 64, expected_publication_fingerprint=publication,
        created_at=run.receipt.completed_at)
    assert created and record.reviewed_decision.decision is decision_kind
    if outcome is None:
        assert record.reviewed_decision.selected_observed_completions == ()
    else:
        assert record.reviewed_decision.selected_observed_completions[0].outcome == "check_failed"


def test_link_repository_replay_survives_newer_source_but_new_old_source_issue_fails(tmp_path) -> None:
    database, source, plan, action, _service, verification = _r8_setup(tmp_path)
    first = _r8_record(source.session_id, run_character="f", request_character="1",
        plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    runs = database.model_ensemble_repository(); runs.save_completed(first)
    publication = first.receipt.metric_publication_v2; assert publication is not None
    manifest, reviewed, publication_fp = _census(first, publication)
    censuses, links = _repositories(database)
    census, _ = censuses.issue(census_id="9" * 64, census=reviewed, manifest=manifest,
        idempotency_key_digest="8" * 64, command_fingerprint="7" * 64,
        expected_publication_fingerprint=publication_fp, created_at=first.receipt.completed_at)
    decision = _decision(census, provider=first.provider.value)
    original, _ = links.issue(link_review_id="a" * 64, reviewed_decision=decision,
        idempotency_key_digest="b" * 64, command_fingerprint="c" * 64,
        expected_publication_fingerprint=publication_fp, created_at=first.receipt.completed_at)
    newer = _r8_record(source.session_id, run_character="d", request_character="4",
        plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    newer = newer.model_copy(update={"receipt": newer.receipt.model_copy(
        update={"completed_at": first.receipt.completed_at + timedelta(minutes=1)})})
    runs.save_completed(newer)
    replay, created = links.issue(link_review_id="a" * 64, reviewed_decision=decision,
        idempotency_key_digest="b" * 64, command_fingerprint="c" * 64,
        expected_publication_fingerprint=publication_fp, created_at=newer.receipt.completed_at)
    assert not created and replay == original
    with pytest.raises(ClaimGroundingLinkConflictError):
        links.issue(link_review_id="d" * 64, reviewed_decision=decision,
            idempotency_key_digest="e" * 64, command_fingerprint="f" * 64,
            expected_publication_fingerprint=publication_fp, created_at=newer.receipt.completed_at)


def test_link_repository_requires_current_r8_publication(tmp_path) -> None:
    database, run, links, census, publication = _issued(tmp_path)
    with database._connection() as connection:
        connection.execute("DROP TRIGGER session_metric_r8_seals_privacy_delete_only")
        connection.execute("DELETE FROM session_model_ensemble_metric_publication_v2_seals_r8 WHERE run_id=?", (run.run_id,))
        connection.commit()
    with database._connection(readonly=True) as connection:
        assert connection.execute(
            "SELECT 1 FROM session_model_ensemble_metric_publication_v2_seals_r8 WHERE run_id=?",
            (run.run_id,),
        ).fetchone() is None
    with pytest.raises(ClaimGroundingLinkConflictError):
        links.issue(link_review_id="a" * 64, reviewed_decision=_decision(census, provider=run.provider.value),
            idempotency_key_digest="b" * 64, command_fingerprint="c" * 64,
            expected_publication_fingerprint=publication, created_at=run.receipt.completed_at)
