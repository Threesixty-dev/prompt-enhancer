from __future__ import annotations
from dataclasses import replace
from types import SimpleNamespace
import pytest
from prompt_enhancer.application.analysis.claim_grounding_link_source import CurrentClaimGroundingLinkSourceResolver, ClaimGroundingLinkSourceConflictError, ClaimGroundingLinkSourceUnavailableError
from prompt_enhancer.application.analysis.claim_grounding_census import ClaimGroundingCensusNotFoundError
from prompt_enhancer.application.analysis.claim_grounding_links import build_source_bound_observed_check_set
from prompt_enhancer.application.analysis.metric_publication_v2 import metric_publication_v2_fingerprint
from prompt_enhancer.domain import Provider
from test_claim_grounding_links import _completion, _record, _Ids
from test_metric_publication_v2 import _publish
from test_claim_grounding_census_repository import _census, _r8_record, _r8_setup, _repository
from test_claim_grounding_census_repository import ARTIFACT_IDS

class Census:
    def __init__(self, record): self.record = record; self.calls = 0
    def get(self, census_id):
        self.calls += 1
        return self.record if census_id == self.record.census_id else (_ for _ in ()).throw(ClaimGroundingCensusNotFoundError("missing"))

class Runs:
    def __init__(self, *runs): self.runs = list(runs)
    def get_latest(self, session_id): return self.runs.pop(0) if len(self.runs) > 1 else self.runs[0]

class Contexts:
    def __init__(self, values=()): self.values = tuple(values)
    def active_observed_check_candidates(self, **_kwargs): return self.values

class MissingContexts:
    def active_observed_check_candidates(self, **_kwargs): raise RuntimeError("context missing")

def run(record, publication, *, session_id=None, run_id=None, window=None, provider=Provider.CODEX):
    return SimpleNamespace(session_id=session_id or record.census.session_id, run_id=run_id or record.census.source_run_id, input_fingerprint=window or record.census.source_window_fingerprint, source_schema_version=record.manifest.source_schema_version, adapter_version=record.manifest.text_adapter_version, provider=provider, receipt=SimpleNamespace(metric_publication_v2=publication))

def resolver(record, *runs, completions=()):
    publication = _publish(()); fp = metric_publication_v2_fingerprint(publication); record = replace(record, expected_publication_fingerprint=fp)
    return CurrentClaimGroundingLinkSourceResolver(Census(record), Runs(*(runs or (run(record, publication),))), Contexts(completions), _Ids()), record, publication

def test_matching_source_is_content_free_and_explicitly_non_authoritative():
    record = _record(); source, record, publication = resolver(record); result = source.current_source(session_id=record.census.session_id, census_id=record.census_id)
    assert result.proposal_only and not result.measured and not result.metric_authority_established and not result.content_persisted
    assert result.observed_set.local_only and not result.observed_set.content_persisted

@pytest.mark.parametrize("session_id,census_id", [("bad", "9"*64), ("a"*64, "bad")])
def test_malformed_or_cross_session_census_is_unavailable(session_id, census_id):
    record = _record(); source, record, _ = resolver(record)
    with pytest.raises(ClaimGroundingLinkSourceUnavailableError): source.current_source(session_id=session_id, census_id=census_id)

def test_valid_cross_session_id_and_missing_census_are_denied():
    record = _record(); source, record, _ = resolver(record)
    with pytest.raises(ClaimGroundingLinkSourceUnavailableError): source.current_source(session_id="e" * 64, census_id=record.census_id)
    with pytest.raises(ClaimGroundingLinkSourceUnavailableError): source.current_source(session_id=record.census.session_id, census_id="8" * 64)

def test_missing_context_and_observed_provider_mismatch_fail_closed():
    record = _record(); publication = _publish(()); fp = metric_publication_v2_fingerprint(publication); record = replace(record, expected_publication_fingerprint=fp); base = run(record, publication)
    with pytest.raises(ClaimGroundingLinkSourceUnavailableError): CurrentClaimGroundingLinkSourceResolver(Census(record), Runs(base), MissingContexts(), _Ids()).current_source(session_id=record.census.session_id, census_id=record.census_id)
    result = CurrentClaimGroundingLinkSourceResolver(Census(record), Runs(base), Contexts(()), _Ids()).current_source(session_id=record.census.session_id, census_id=record.census_id)
    assert result.observed_set.completions == ()
    with pytest.raises(ClaimGroundingLinkSourceUnavailableError): CurrentClaimGroundingLinkSourceResolver(Census(record), Runs(run(record, publication, provider=Provider.CLAUDE_CODE)), Contexts((_completion("a" * 64),)), _Ids()).current_source(session_id=record.census.session_id, census_id=record.census_id)

def test_observed_context_overflow_is_unavailable():
    record = _record(); publication = _publish(()); record = replace(record, expected_publication_fingerprint=metric_publication_v2_fingerprint(publication))
    with pytest.raises(ClaimGroundingLinkSourceUnavailableError): CurrentClaimGroundingLinkSourceResolver(Census(record), Runs(run(record, publication)), Contexts(tuple(_completion(str(i).zfill(64)) for i in range(4001))), _Ids()).current_source(session_id=record.census.session_id, census_id=record.census_id)

def test_first_or_second_read_run_window_or_publication_drift_conflicts():
    record = _record(); source, record, publication = resolver(record)
    for altered in (run(record, publication, run_id="a"*64), run(record, publication, window="b"*64), run(record, publication.model_copy(update={"publication_version": publication.publication_version + 1}))):
        with pytest.raises(ClaimGroundingLinkSourceConflictError):
            CurrentClaimGroundingLinkSourceResolver(Census(record), Runs(run(record, publication), altered), Contexts(()), _Ids()).current_source(session_id=record.census.session_id, census_id=record.census_id)

def test_first_read_drift_is_fenced_before_context_access():
    record = _record(); _, record, publication = resolver(record)
    for altered in (run(record, publication, run_id="a" * 64), run(record, publication, window="b" * 64), run(record, publication.model_copy(update={"publication_version": publication.publication_version + 1}))):
        census = Census(record)
        with pytest.raises(ClaimGroundingLinkSourceConflictError):
            CurrentClaimGroundingLinkSourceResolver(census, Runs(altered), Contexts((_completion("a" * 64),)), _Ids()).current_source(session_id=record.census.session_id, census_id=record.census_id)

def test_malformed_identifiers_do_not_access_census_repository():
    record = _record(); census = Census(record); publication = _publish(()); record = replace(record, expected_publication_fingerprint=metric_publication_v2_fingerprint(publication))
    source = CurrentClaimGroundingLinkSourceResolver(census, Runs(run(record, publication)), Contexts(()), _Ids())
    for session_id, census_id in (("bad", record.census_id), (record.census.session_id, "bad")):
        with pytest.raises(ClaimGroundingLinkSourceUnavailableError): source.current_source(session_id=session_id, census_id=census_id)
    assert census.calls == 0

def test_real_sqlite_saved_census_hydrates_against_latest_model_repository(tmp_path):
    database, source, plan, action, service, verification = _r8_setup(tmp_path)
    run_record = _r8_record(source.session_id, run_character="f", request_character="1", plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    database.model_ensemble_repository().save_completed(run_record)
    publication = run_record.receipt.metric_publication_v2
    assert publication is not None
    manifest, census, publication_fingerprint = _census(run_record, publication)
    repository = _repository(database)
    created, issued = repository.issue(census_id="9" * 64, census=census, manifest=manifest, idempotency_key_digest="8" * 64, command_fingerprint="7" * 64, expected_publication_fingerprint=publication_fingerprint, created_at=run_record.receipt.completed_at)
    assert issued is True
    class Adapter:
        def get(self, census_id): return repository.get(census_id)
    resolver = CurrentClaimGroundingLinkSourceResolver(Adapter(), database.model_ensemble_repository(), Contexts(()), ARTIFACT_IDS)
    result = resolver.current_source(session_id=run_record.session_id, census_id=created.census_id)
    assert result.source_run_id == run_record.run_id and result.source_window_fingerprint == run_record.input_fingerprint
    assert result.census_fingerprint == census.census_fingerprint
    assert result.proposal_only and not result.measured and not result.metric_authority_established and not result.content_persisted

def test_source_schema_and_adapter_mismatch_are_rejected():
    record = _record(); source, record, publication = resolver(record)
    for field in ("source_schema_version", "adapter_version"):
        altered = run(record, publication); setattr(altered, field, "synthetic-other-v1")
        with pytest.raises(ClaimGroundingLinkSourceConflictError): CurrentClaimGroundingLinkSourceResolver(Census(record), Runs(altered), Contexts(()), _Ids()).current_source(session_id=record.census.session_id, census_id=record.census_id)


def test_candidate_manifest_is_current_complete_and_content_free():
    record = _record()
    source, record, _ = resolver(record, completions=(_completion("a" * 64),))
    result = source.candidate_manifest(
        session_id=record.census.session_id, census_id=record.census_id,
    )
    material = {
        item.candidate_id for item in record.census.classifications
        if item.classification.value == "material_claim"
    }
    assert {item.candidate_id for item in result.material_candidates} == material
    assert result.manifest_fingerprint == record.manifest.manifest_fingerprint
    assert result.census_fingerprint == record.census.census_fingerprint
    assert result.observed_checks[0].source_reference_id == "a" * 64
    assert result.observed_checks[0].outcome == "passed"
    assert result.proposal_only and not result.measured and not result.metric_authority_established
    assert "Synthetic claim" not in repr(result)
    assert "pytest -q" not in repr(result)


def test_candidate_manifest_allows_empty_checks_but_fences_stale_and_cross_session():
    record = _record()
    source, record, publication = resolver(record)
    result = source.candidate_manifest(
        session_id=record.census.session_id, census_id=record.census_id,
    )
    assert result.observed_checks == ()
    stale = CurrentClaimGroundingLinkSourceResolver(
        Census(record), Runs(run(record, publication), run(record, publication), run(record, publication, window="b" * 64)),
        Contexts(()), _Ids(),
    )
    with pytest.raises(ClaimGroundingLinkSourceConflictError):
        stale.candidate_manifest(session_id=record.census.session_id, census_id=record.census_id)
    with pytest.raises(ClaimGroundingLinkSourceUnavailableError):
        source.candidate_manifest(session_id="e" * 64, census_id=record.census_id)
