from __future__ import annotations

import hashlib
import hmac

import pytest

from prompt_enhancer.application.analysis.claim_grounding_evidence import (
    ClaimCensusClassification, ClaimCensusClassificationEntry, ClaimCensusExclusionReason,
    ReviewedClaimCensus, build_reviewed_claim_census, derive_claim_census_source_manifest, validate_claim_census_source_manifest, validate_reviewed_claim_census,
)
from prompt_enhancer.application.analysis.text_contracts import (
    EphemeralRedactedMessage, P1TextAnalysisInput, TextLanguage, TextMessageKind, TextRole, TextTaskProfile,
)
from prompt_enhancer.domain import Provider
from pydantic import SecretStr

S, R, W = "1" * 64, "2" * 64, "3" * 64

class Ids:
    def fingerprint(self, namespace: str, values: tuple[str, ...]) -> str:
        return hmac.new(b"synthetic-claim-census-key", "\x1f".join((namespace, *values)).encode(), hashlib.sha256).hexdigest()

def context(*, complete: bool = True, response: str | None = "Implemented synthetic feature. Notes only.") -> P1TextAnalysisInput:
    request = EphemeralRedactedMessage(message_id="4" * 64, sequence=1, role=TextRole.USER, kind=TextMessageKind.REQUEST, language=TextLanguage.ENGLISH, text=SecretStr("Synthetic request."))
    messages = (request,) if response is None else (request, EphemeralRedactedMessage(message_id="5" * 64, sequence=2, role=TextRole.AGENT, kind=TextMessageKind.RESPONSE, language=TextLanguage.ENGLISH, text=SecretStr(response)))
    kinds = frozenset({TextMessageKind.REQUEST} if response is None else {TextMessageKind.REQUEST, TextMessageKind.RESPONSE})
    return P1TextAnalysisInput(provider=Provider.SYNTHETIC, session_id=S, provider_version="synthetic.1", adapter_version="synthetic-adapter.1", source_schema_version="synthetic-source.1", content_schema_version="synthetic-content.1", redactor_version="synthetic-redactor.1", text_extraction_complete=complete, available_message_kinds=kinds, analysis_window_fingerprint=W, focus_message_id=request.message_id, observed_message_count=len(messages), eligible_message_count=len(messages), messages=messages, task_profile=TextTaskProfile(applicability=()))

def census(manifest, classifications):
    return build_reviewed_claim_census(manifest, classifications=tuple(classifications), identifiers=Ids())

def unvalidated_census(manifest, classifications):
    return ReviewedClaimCensus(manifest_fingerprint=manifest.manifest_fingerprint, session_id=S, source_run_id=R, source_window_fingerprint=W, classifications=tuple(sorted(classifications, key=lambda item: item.candidate_id)), complete_candidate_classification_acknowledged=True, census_fingerprint="9" * 64)

def test_complete_response_clause_partition_and_prose_privacy() -> None:
    manifest, ephemeral = derive_claim_census_source_manifest(context(), source_run_id=R, identifiers=Ids())
    assert manifest.candidate_count == 2
    assert "Implemented" not in manifest.model_dump_json()
    assert "Implemented" not in ephemeral[0].model_dump_json()
    reviewed = census(manifest, [ClaimCensusClassificationEntry(candidate_id=ephemeral[0].candidate_id, classification=ClaimCensusClassification.MATERIAL_CLAIM), ClaimCensusClassificationEntry(candidate_id=ephemeral[1].candidate_id, classification=ClaimCensusClassification.EXCLUDED, exclusion_reason=ClaimCensusExclusionReason.NON_ASSERTIVE_STATUS_OR_QUALIFICATION)])
    validate_reviewed_claim_census(reviewed, manifest, identifiers=Ids())

def test_explicit_empty_census_is_valid_only_when_no_response_candidates() -> None:
    manifest, _ = derive_claim_census_source_manifest(context(response=None), source_run_id=R, identifiers=Ids())
    # No response candidates is an explicit, structurally complete zero set.
    assert manifest.candidate_count == 0
    validate_reviewed_claim_census(census(manifest, []), manifest, identifiers=Ids())

@pytest.mark.parametrize("mutation", ["partial", "duplicate", "foreign"])
def test_rejects_nonexact_census_partitions(mutation: str) -> None:
    manifest, ephemeral = derive_claim_census_source_manifest(context(), source_run_id=R, identifiers=Ids())
    first = ClaimCensusClassificationEntry(candidate_id=ephemeral[0].candidate_id, classification=ClaimCensusClassification.MATERIAL_CLAIM)
    second = ClaimCensusClassificationEntry(candidate_id=ephemeral[1].candidate_id, classification=ClaimCensusClassification.MATERIAL_CLAIM)
    if mutation == "partial": reviewed = unvalidated_census(manifest, [first])
    elif mutation == "duplicate":
        with pytest.raises(ValueError, match="unique"):
            census(manifest, [first, first])
        return
    else: reviewed = unvalidated_census(manifest, [first, ClaimCensusClassificationEntry(candidate_id="8" * 64, classification=ClaimCensusClassification.MATERIAL_CLAIM)])
    with pytest.raises(ValueError, match="classify every exact"):
        validate_reviewed_claim_census(reviewed, manifest, identifiers=Ids())

def test_rejects_incomplete_stale_and_foreign_source() -> None:
    with pytest.raises(ValueError, match="complete text extraction"):
        derive_claim_census_source_manifest(context(complete=False), source_run_id=R, identifiers=Ids())
    manifest, ephemeral = derive_claim_census_source_manifest(context(), source_run_id=R, identifiers=Ids())
    reviewed = census(manifest, [ClaimCensusClassificationEntry(candidate_id=item.candidate_id, classification=ClaimCensusClassification.MATERIAL_CLAIM) for item in ephemeral])
    stale = reviewed.model_copy(update={"source_run_id": "6" * 64})
    with pytest.raises(ValueError, match="another sealed source"):
        validate_reviewed_claim_census(stale, manifest, identifiers=Ids())

def test_rejects_tampered_manifest_and_census_fingerprints() -> None:
    manifest, ephemeral = derive_claim_census_source_manifest(context(), source_run_id=R, identifiers=Ids())
    with pytest.raises(ValueError, match="manifest fingerprint"):
        validate_claim_census_source_manifest(manifest.model_copy(update={"manifest_fingerprint": "a" * 64}), identifiers=Ids())
    reviewed = census(manifest, [ClaimCensusClassificationEntry(candidate_id=item.candidate_id, classification=ClaimCensusClassification.MATERIAL_CLAIM) for item in ephemeral])
    with pytest.raises(ValueError, match="census fingerprint"):
        validate_reviewed_claim_census(reviewed.model_copy(update={"census_fingerprint": "b" * 64}), manifest, identifiers=Ids())
    with pytest.raises(ValueError, match="inconsistent sequence"):
        validate_claim_census_source_manifest(manifest.model_copy(update={"candidates": (manifest.candidates[0].model_copy(update={"message_sequence": 99}), *manifest.candidates[1:])}), identifiers=Ids())

def test_rejects_duplicate_or_noncontiguous_candidate_coordinates() -> None:
    manifest, _ = derive_claim_census_source_manifest(context(), source_run_id=R, identifiers=Ids())
    payload = manifest.model_dump()
    payload["candidates"] = [
        {**manifest.candidates[0].model_dump(), "candidate_id": "a" * 64},
        {**manifest.candidates[0].model_dump(), "candidate_id": "b" * 64},
    ]
    payload["candidate_count"] = 2
    with pytest.raises(ValueError, match="unique"):
        type(manifest).model_validate(payload)

def test_rejects_two_message_ids_at_one_sequence() -> None:
    manifest, _ = derive_claim_census_source_manifest(context(), source_run_id=R, identifiers=Ids())
    payload = manifest.model_dump()
    payload["candidates"] = [
        manifest.candidates[0].model_dump(),
        {**manifest.candidates[1].model_dump(), "message_id": "a" * 64, "message_sequence": manifest.candidates[0].message_sequence},
    ]
    with pytest.raises(ValueError, match="sequence has inconsistent identity"):
        type(manifest).model_validate(payload)

def test_rejects_prose_in_source_version_metadata() -> None:
    manifest, _ = derive_claim_census_source_manifest(context(), source_run_id=R, identifiers=Ids())
    with pytest.raises(ValueError, match="safe identifier"):
        type(manifest).model_validate({**manifest.model_dump(), "source_schema_version": "synthetic source prose is forbidden"})

def test_overflow_fails_closed() -> None:
    # 101 response messages × 128 clauses exceeds the bounded census capacity.
    text = ". ".join("synthetic" for _ in range(128))
    base = context(response=text)
    messages = tuple(base.messages[:1]) + tuple(base.messages[1].model_copy(update={"message_id": f"{i:064x}", "sequence": i + 2}) for i in range(101))
    oversized = base.model_copy(update={"messages": messages, "observed_message_count": len(messages), "eligible_message_count": len(messages)})
    with pytest.raises(ValueError, match="bounded candidate"):
        derive_claim_census_source_manifest(oversized, source_run_id=R, identifiers=Ids())
