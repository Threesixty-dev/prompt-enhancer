from __future__ import annotations

from datetime import timedelta

import pytest

from prompt_enhancer.application.analysis.claim_grounding_link_review import (
    ClaimGroundingLinkObservedCompletionSnapshot,
    ClaimGroundingLinkReviewedDecision,
)
from prompt_enhancer.application.analysis.claim_grounding_link_persistence import ClaimGroundingLinkConflictError
from prompt_enhancer.application.analysis.claim_grounding_links import ClaimLinkCoverageDecision
from prompt_enhancer.database import DatabaseInvariantError
from prompt_enhancer.infrastructure.sqlite.claim_grounding_census import SqliteClaimGroundingCensusRepository
from prompt_enhancer.infrastructure.sqlite.claim_grounding_links import SqliteClaimGroundingLinkRepository
from test_claim_grounding_census_repository import _census, _r8_record, _r8_setup
from test_requirement_plan_evidence_persistence import ARTIFACT_IDS

S = "a" * 64
OTHER_S = "b" * 64
LINK = "c" * 64
IDEM = "d" * 64
COMMAND = "e" * 64
REF = "f" * 64


def _repositories(tmp_path):  # type: ignore[no-untyped-def]
    database, source, plan, action, _service, verification = _r8_setup(tmp_path)
    run = _r8_record(source.session_id, run_character="f", request_character="1", plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    database.model_ensemble_repository().save_completed(run)
    publication = run.receipt.metric_publication_v2
    assert publication is not None
    manifest, census, publication_fingerprint = _census(run, publication)
    census_repo = SqliteClaimGroundingCensusRepository(database._connection, database.initialize, identifiers=ARTIFACT_IDS)
    census_record, _ = census_repo.issue(census_id="1" * 64, census=census, manifest=manifest, idempotency_key_digest="2" * 64, command_fingerprint="3" * 64, expected_publication_fingerprint=publication_fingerprint, created_at=run.receipt.completed_at + timedelta(seconds=1))
    link_repo = SqliteClaimGroundingLinkRepository(database._connection, database.initialize, identifiers=ARTIFACT_IDS)
    return database, run, census_record, publication_fingerprint, link_repo, plan, action, verification


def _decision(census_record, run, *, decision=ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS, session_id=None, reference=REF):
    session_id = census_record.census.session_id if session_id is None else session_id
    return ClaimGroundingLinkReviewedDecision(
        session_id=session_id, census_id=census_record.census_id, candidate_id="9" * 64,
        source_run_id=run.run_id, source_window_fingerprint=run.input_fingerprint,
        census_fingerprint=census_record.census.census_fingerprint,
        manifest_fingerprint=census_record.manifest.manifest_fingerprint,
        observed_set_fingerprint="8" * 64, review_receipt_id="9" * 64,
        review_fingerprint="0" * 64, decision=decision,
        selected_check_references=() if decision is not ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS else (reference,),
        selected_observed_completions=() if decision is not ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS else (ClaimGroundingLinkObservedCompletionSnapshot(source_reference_id=reference, observed_sequence=1, provider="codex", check_kind="test", outcome="passed", provider_execution_status="completed", exit_code=0, source_completion_schema_version="observed-check-completion-v1", outcome_interpreter_version="pytest-exit-status-v1", classifier_version="local-command-rules-v1", normalizer_version="strict-shell-free-v2", rule_id="test.pytest"),),
    )


def test_repository_roundtrip_replay_and_session_isolation(tmp_path) -> None:
    database, run, census, publication, repository, _plan, _action, _verification = _repositories(tmp_path)
    decision = _decision(census, run)
    created, issued = repository.issue(link_review_id=LINK, reviewed_decision=decision, idempotency_key_digest=IDEM, command_fingerprint=COMMAND, expected_publication_fingerprint=publication, created_at=run.receipt.completed_at + timedelta(seconds=2))
    assert issued is True
    replay, replayed = repository.issue(link_review_id=LINK, reviewed_decision=decision, idempotency_key_digest=IDEM, command_fingerprint=COMMAND, expected_publication_fingerprint=publication, created_at=run.receipt.completed_at + timedelta(seconds=3))
    assert replayed is False and replay.link_review_id == created.link_review_id
    assert repository.get(session_id=census.census.session_id, link_review_id=LINK) is not None
    assert repository.get(session_id=OTHER_S, link_review_id=LINK) is None
    assert repository.get_by_idempotency(session_id=OTHER_S, idempotency_key_digest=IDEM) is None


def test_repository_rejects_mutated_decision_and_idempotency_conflicts(tmp_path) -> None:
    _database, run, census, publication, repository, _plan, _action, _verification = _repositories(tmp_path)
    decision = _decision(census, run)
    repository.issue(link_review_id=LINK, reviewed_decision=decision, idempotency_key_digest=IDEM, command_fingerprint=COMMAND, expected_publication_fingerprint=publication, created_at=run.receipt.completed_at + timedelta(seconds=2))
    with pytest.raises(ClaimGroundingLinkConflictError):
        repository.issue(link_review_id="1" * 64, reviewed_decision=_decision(census, run, decision=ClaimLinkCoverageDecision.UNRESOLVED), idempotency_key_digest=IDEM, command_fingerprint="2" * 64, expected_publication_fingerprint=publication, created_at=run.receipt.completed_at + timedelta(seconds=3))
    object.__setattr__(decision, "measured", True)
    with pytest.raises(ValueError):
        repository.issue(link_review_id="2" * 64, reviewed_decision=decision, idempotency_key_digest="3" * 64, command_fingerprint="4" * 64, expected_publication_fingerprint=publication, created_at=run.receipt.completed_at + timedelta(seconds=3))


def test_repository_requires_latest_source_fence_without_older_fallback(tmp_path) -> None:
    database, run, census, publication, repository, plan, action, verification = _repositories(tmp_path)
    newer = _r8_record(run.session_id, run_character="d", request_character="4", plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    newer = newer.model_copy(update={"receipt": newer.receipt.model_copy(update={"completed_at": run.receipt.completed_at + timedelta(minutes=1)})})
    database.model_ensemble_repository().save_completed(newer)
    with pytest.raises(ClaimGroundingLinkConflictError):
        repository.issue(link_review_id=LINK, reviewed_decision=_decision(census, run), idempotency_key_digest=IDEM, command_fingerprint=COMMAND, expected_publication_fingerprint=publication, created_at=run.receipt.completed_at + timedelta(seconds=2))


@pytest.mark.parametrize(
    ("label", "trigger", "table", "column", "value"),
    (
        ("schema", "claim_grounding_link_reviews_no_update", "claim_grounding_link_reviews", "schema_version", "forged-schema"),
        ("policy", "claim_grounding_link_reviews_no_update", "claim_grounding_link_reviews", "policy_version", "forged-policy"),
        ("local", "claim_grounding_link_review_references_no_update", "claim_grounding_link_review_selected_references", "local_only", 0),
        ("content", "claim_grounding_link_review_references_no_update", "claim_grounding_link_review_selected_references", "content_persistence_allowed", 1),
    ),
)
def test_repository_rejects_forged_provenance_flags_and_versions_on_hydration(
    tmp_path, label, trigger, table, column, value
) -> None:  # type: ignore[no-untyped-def]
    workdir = tmp_path / label
    workdir.mkdir()
    database, run, census, publication, repository, _plan, _action, _verification = _repositories(workdir)
    decision = _decision(census, run)
    repository.issue(link_review_id=LINK, reviewed_decision=decision, idempotency_key_digest=IDEM,
                     command_fingerprint=COMMAND, expected_publication_fingerprint=publication,
                     created_at=run.receipt.completed_at + timedelta(seconds=2))
    with database._connection() as connection:
        connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(f"UPDATE {table} SET {column}=? WHERE link_review_id=?", (value, LINK))
        connection.commit()
    with pytest.raises(DatabaseInvariantError):
        repository.get(session_id=census.census.session_id, link_review_id=LINK)


def test_repository_rejects_float_exit_code_even_when_equal_to_zero(tmp_path) -> None:
    _database, run, census, publication, repository, _plan, _action, _verification = _repositories(tmp_path)
    decision = _decision(census, run)
    object.__setattr__(decision.selected_observed_completions[0], "exit_code", 0.0)
    with pytest.raises(ValueError):
        repository.issue(link_review_id=LINK, reviewed_decision=decision, idempotency_key_digest=IDEM,
                         command_fingerprint=COMMAND, expected_publication_fingerprint=publication,
                         created_at=run.receipt.completed_at + timedelta(seconds=2))
