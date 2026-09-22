from __future__ import annotations

import hashlib
import hmac

import pytest
from pydantic import SecretStr

from prompt_enhancer.application.analysis.claim_grounding_evidence import (
    ClaimCensusClassification,
    ClaimCensusClassificationEntry,
    ClaimCensusSourceManifest,
    ReviewedClaimCensus,
    derive_claim_census_source_manifest,
    validate_claim_census_source_manifest,
    validate_reviewed_claim_census,
)
from prompt_enhancer.application.analysis.text_contracts import (
    EphemeralRedactedMessage,
    P1TextAnalysisInput,
    TextLanguage,
    TextMessageKind,
    TextRole,
    TextTaskProfile,
)
from prompt_enhancer.domain import Provider


SESSION, RUN, WINDOW = "1" * 64, "2" * 64, "3" * 64


class SyntheticIds:
    def fingerprint(self, namespace: str, values: tuple[str, ...]) -> str:
        return hmac.new(
            b"synthetic-claim-grounding-adversarial-key",
            "\x1f".join((namespace, *values)).encode(),
            hashlib.sha256,
        ).hexdigest()


def source_context() -> P1TextAnalysisInput:
    request = EphemeralRedactedMessage(
        message_id="4" * 64,
        sequence=1,
        role=TextRole.USER,
        kind=TextMessageKind.REQUEST,
        language=TextLanguage.ENGLISH,
        text=SecretStr("Synthetic request."),
    )
    response = EphemeralRedactedMessage(
        message_id="5" * 64,
        sequence=2,
        role=TextRole.AGENT,
        kind=TextMessageKind.RESPONSE,
        language=TextLanguage.ENGLISH,
        text=SecretStr("Implemented synthetic feature. Notes only."),
    )
    return P1TextAnalysisInput(
        provider=Provider.SYNTHETIC,
        session_id=SESSION,
        provider_version="synthetic.1",
        adapter_version="synthetic-adapter.1",
        source_schema_version="synthetic-source.1",
        content_schema_version="synthetic-content.1",
        redactor_version="synthetic-redactor.1",
        text_extraction_complete=True,
        available_message_kinds=frozenset({TextMessageKind.REQUEST, TextMessageKind.RESPONSE}),
        analysis_window_fingerprint=WINDOW,
        focus_message_id=request.message_id,
        observed_message_count=2,
        eligible_message_count=2,
        messages=(request, response),
        task_profile=TextTaskProfile(applicability=()),
    )


def manifest_with(
    entries: tuple[dict[str, object], ...], *, source_schema_version: str = "synthetic-source.1"
) -> ClaimCensusSourceManifest:
    return ClaimCensusSourceManifest(
        session_id=SESSION,
        source_run_id=RUN,
        source_window_fingerprint=WINDOW,
        source_schema_version=source_schema_version,
        text_adapter_version="synthetic-adapter.1",
        candidates=entries,
        candidate_count=len(entries),
        manifest_fingerprint="6" * 64,
    )


def reviewed(manifest: ClaimCensusSourceManifest, candidate_ids: tuple[str, ...]) -> ReviewedClaimCensus:
    entries = tuple(
        sorted(
            (
                ClaimCensusClassificationEntry(
                    candidate_id=candidate_id,
                    classification=ClaimCensusClassification.MATERIAL_CLAIM,
                )
                for candidate_id in candidate_ids
            ),
            key=lambda entry: entry.candidate_id,
        )
    )
    fingerprint = SyntheticIds().fingerprint(
        "claim-grounding-reviewed-census-v1",
        (
            manifest.manifest_fingerprint,
            SESSION,
            RUN,
            WINDOW,
            *(f"{entry.candidate_id}:{entry.classification.value}:-" for entry in entries),
        ),
    )
    return ReviewedClaimCensus(
        manifest_fingerprint=manifest.manifest_fingerprint,
        session_id=SESSION,
        source_run_id=RUN,
        source_window_fingerprint=WINDOW,
        classifications=entries,
        complete_candidate_classification_acknowledged=True,
        census_fingerprint=fingerprint,
    )


def test_rejects_duplicate_candidate_id_across_coordinates() -> None:
    duplicate = "7" * 64
    with pytest.raises(ValueError):
        manifest_with(
            (
                {"candidate_id": duplicate, "message_id": "8" * 64, "message_sequence": 2, "clause_index": 0},
                {"candidate_id": duplicate, "message_id": "8" * 64, "message_sequence": 2, "clause_index": 1},
            )
        )


def test_rejects_duplicate_coordinates_with_different_candidate_ids() -> None:
    with pytest.raises(ValueError):
        manifest_with(
            (
                {"candidate_id": "7" * 64, "message_id": "8" * 64, "message_sequence": 2, "clause_index": 0},
                {"candidate_id": "9" * 64, "message_id": "8" * 64, "message_sequence": 2, "clause_index": 0},
            )
        )


def test_rejects_noncontiguous_clause_indices() -> None:
    with pytest.raises(ValueError):
        manifest_with(
            (
                {"candidate_id": "7" * 64, "message_id": "8" * 64, "message_sequence": 2, "clause_index": 0},
                {"candidate_id": "9" * 64, "message_id": "8" * 64, "message_sequence": 2, "clause_index": 2},
            )
        )


def test_rejects_freeform_unsafe_source_version() -> None:
    with pytest.raises(ValueError):
        manifest_with(
            ({"candidate_id": "7" * 64, "message_id": "8" * 64, "message_sequence": 2, "clause_index": 0},),
            source_schema_version="synthetic source/unsafe",
        )


@pytest.mark.parametrize("mutation", ["coordinates", "version", "fingerprint"])
def test_rejects_tampered_manifest_authority(mutation: str) -> None:
    manifest, _ = derive_claim_census_source_manifest(
        source_context(), source_run_id=RUN, identifiers=SyntheticIds()
    )
    if mutation == "coordinates":
        candidate = manifest.candidates[0].model_copy(update={"clause_index": 1})
        tampered = manifest.model_copy(update={"candidates": (candidate, *manifest.candidates[1:])})
    elif mutation == "version":
        tampered = manifest.model_copy(update={"source_schema_version": "synthetic-source.2"})
    else:
        tampered = manifest.model_copy(update={"manifest_fingerprint": "a" * 64})
    with pytest.raises(ValueError):
        validate_claim_census_source_manifest(tampered, identifiers=SyntheticIds())


def test_rejects_changed_classification_with_original_fingerprint() -> None:
    manifest, ephemeral = derive_claim_census_source_manifest(
        source_context(), source_run_id=RUN, identifiers=SyntheticIds()
    )
    original = reviewed(manifest, tuple(item.candidate_id for item in ephemeral))
    changed = original.model_copy(
        update={
            "classifications": (
                ClaimCensusClassificationEntry(
                    candidate_id=original.classifications[0].candidate_id,
                    classification=ClaimCensusClassification.EXCLUDED,
                    exclusion_reason="not_a_completion_or_verification_claim",
                ),
                *original.classifications[1:],
            )
        }
    )
    with pytest.raises(ValueError):
        validate_reviewed_claim_census(changed, manifest, identifiers=SyntheticIds())
