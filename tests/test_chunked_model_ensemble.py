from __future__ import annotations

from pydantic import SecretStr, ValidationError
import pytest

from prompt_enhancer.application.analysis.model_ensemble import (
    MODEL_ENSEMBLE_MAX_CHUNKS,
    ModelExpertRole,
    ModelMetricVote,
    ModelVoteState,
    SourceCoverageState,
    aggregate_chunk_metrics,
    build_ensemble_chunks,
    coaching_ensemble_metric_specs,
    committee_chunk_receipt,
)
from prompt_enhancer.application.analysis.text_contracts import (
    ApplicabilityBasis,
    EphemeralRedactedMessage,
    MetricApplicability,
    MetricApplicabilityDecision,
    P1TextAnalysisInput,
    TextLanguage,
    TextMessageKind,
    TextRole,
    TextTaskProfile,
)
from prompt_enhancer.application.analysis.coaching_baselines import (
    COACHING_METRIC_DEFINITIONS,
)
from prompt_enhancer.application.persistence import MetricValueState
from prompt_enhancer.domain import Provider
from prompt_enhancer.infrastructure.text_models.model_ensemble import (
    SerialModelEnsembleRunner,
    ensemble_expert_specs,
)


def _digest(char: str) -> str:
    return char * 64


def _context(*, complete: bool = True) -> P1TextAnalysisInput:
    decisions = tuple(
        MetricApplicabilityDecision(
            metric_key=definition.key,
            applicability=MetricApplicability.APPLICABLE,
            basis=ApplicabilityBasis.USER_SELECTED,
        )
        for definition in COACHING_METRIC_DEFINITIONS
    )
    messages = tuple(
        EphemeralRedactedMessage(
            message_id=f"{index + 1:064x}",
            sequence=index,
            role=TextRole.USER if index % 2 == 0 else TextRole.AGENT,
            kind=(
                TextMessageKind.REQUEST
                if index % 2 == 0
                else TextMessageKind.RESPONSE
            ),
            language=TextLanguage.ENGLISH,
            text=SecretStr((f"fictional segment {index} " * 260)[:5_200]),
        )
        for index in range(16)
    )
    return P1TextAnalysisInput(
        provider=Provider.SYNTHETIC,
        session_id=_digest("a"),
        provider_version="synthetic-provider-v1",
        adapter_version="synthetic-adapter-v1",
        source_schema_version="synthetic-source-v1",
        content_schema_version="synthetic-content-v1",
        redactor_version="synthetic-redactor-v1",
        text_extraction_complete=complete,
        available_message_kinds=frozenset(
            {TextMessageKind.REQUEST, TextMessageKind.RESPONSE}
        ),
        analysis_window_fingerprint=_digest("b"),
        focus_message_id=messages[-2].message_id,
        observed_message_count=len(messages),
        eligible_message_count=len(messages),
        messages=messages,
        task_profile=TextTaskProfile(applicability=decisions),
    )


def _vote(
    model: str,
    role: ModelExpertRole,
    state: ModelVoteState,
    *,
    chunk: int = 0,
    metric: str = "prompt.task_definition_coverage",
) -> ModelMetricVote:
    return ModelMetricVote(
        chunk_ordinal=chunk,
        metric_key=metric,
        model_key=model,
        role=role,
        state=state,
        raw_score=(1.0 if state is ModelVoteState.PRESENT else 0.0)
        if state in {ModelVoteState.PRESENT, ModelVoteState.ABSENT}
        else None,
        reason_code="synthetic_vote",
    )


def test_chunker_is_exhaustive_non_overlapping_and_bounded() -> None:
    context = _context()
    plan = build_ensemble_chunks(context)

    assert 1 < len(plan.chunks) <= MODEL_ENSEMBLE_MAX_CHUNKS
    assert plan.source_coverage_state is SourceCoverageState.COMPLETE_WINDOW
    assert plan.total_message_count == context.observed_message_count
    assert plan.total_character_count == sum(
        len(message.text.get_secret_value()) for message in context.messages
    )
    fragments = [item for chunk in plan.chunks for item in chunk.fragments]
    assert len({item.fragment_id for item in fragments}) == len(fragments)
    assert {item.source_message_id for item in fragments} == {
        item.message_id for item in context.messages
    }
    assert max(len(item.text.get_secret_value()) for item in fragments) <= 3_500
    assert repr(plan).find("fictional segment") == -1


def test_incomplete_source_is_preserved_not_promoted_to_complete() -> None:
    plan = build_ensemble_chunks(_context(complete=False))
    assert plan.source_coverage_state is SourceCoverageState.INCOMPLETE_SOURCE


def test_all_twenty_metric_specs_are_versioned_and_distinct() -> None:
    specs = coaching_ensemble_metric_specs()
    assert len(specs) == len(COACHING_METRIC_DEFINITIONS) == 20
    assert len({item.metric_key for item in specs}) == 20
    assert all(item.retrieval_query and item.entailment_hypothesis and item.rubric for item in specs)


def test_committee_accepts_supported_present_and_absent_decisions() -> None:
    promoted = frozenset({"minilm_l6", "minilm_l12"})
    present = committee_chunk_receipt(
        chunk_ordinal=0,
        metric_key="prompt.task_definition_coverage",
        rubric_vote=_vote("qwen_rubric", ModelExpertRole.STRUCTURED_RUBRIC, ModelVoteState.PRESENT),
        nli_votes=(
            _vote("minilm_l6", ModelExpertRole.SCOPE_NLI, ModelVoteState.PRESENT),
            _vote("minilm_l12", ModelExpertRole.SCOPE_NLI, ModelVoteState.PRESENT),
            _vote("mdeberta", ModelExpertRole.SCOPE_NLI, ModelVoteState.ABSENT),
        ),
        contributing_nli_model_keys=promoted,
    )
    absent = committee_chunk_receipt(
        chunk_ordinal=1,
        metric_key="prompt.task_definition_coverage",
        rubric_vote=_vote("qwen_rubric", ModelExpertRole.STRUCTURED_RUBRIC, ModelVoteState.ABSENT, chunk=1),
        nli_votes=(
            _vote("minilm_l6", ModelExpertRole.SCOPE_NLI, ModelVoteState.ABSTAIN, chunk=1),
            _vote("minilm_l12", ModelExpertRole.SCOPE_NLI, ModelVoteState.ABSENT, chunk=1),
            _vote("mdeberta", ModelExpertRole.SCOPE_NLI, ModelVoteState.PRESENT, chunk=1),
        ),
        contributing_nli_model_keys=promoted,
    )

    assert present.value_state is MetricValueState.KNOWN
    assert (present.numerator, present.denominator) == (1, 1)
    assert absent.value_state is MetricValueState.KNOWN
    assert (absent.numerator, absent.denominator) == (0, 1)


def test_committee_disagreement_abstains_and_diagnostic_model_cannot_decide() -> None:
    receipt = committee_chunk_receipt(
        chunk_ordinal=0,
        metric_key="prompt.task_definition_coverage",
        rubric_vote=_vote("qwen_rubric", ModelExpertRole.STRUCTURED_RUBRIC, ModelVoteState.PRESENT),
        nli_votes=(
            _vote("minilm_l6", ModelExpertRole.SCOPE_NLI, ModelVoteState.ABSENT),
            _vote("minilm_l12", ModelExpertRole.SCOPE_NLI, ModelVoteState.ABSENT),
            _vote("mdeberta", ModelExpertRole.SCOPE_NLI, ModelVoteState.PRESENT),
        ),
        contributing_nli_model_keys=frozenset({"minilm_l6", "minilm_l12"}),
    )
    assert receipt.value_state is MetricValueState.ABSTAINED
    assert receipt.reason_code == "model_committee_disagreement"


def test_session_aggregate_is_ratio_of_valid_chunks_not_model_logits() -> None:
    promoted = frozenset({"minilm_l6", "minilm_l12"})
    receipts = []
    for chunk, rubric_state, nli_state in (
        (0, ModelVoteState.PRESENT, ModelVoteState.PRESENT),
        (1, ModelVoteState.ABSENT, ModelVoteState.ABSENT),
        (2, ModelVoteState.ABSTAIN, ModelVoteState.ABSTAIN),
    ):
        receipts.append(
            committee_chunk_receipt(
                chunk_ordinal=chunk,
                metric_key="prompt.task_definition_coverage",
                rubric_vote=_vote("qwen_rubric", ModelExpertRole.STRUCTURED_RUBRIC, rubric_state, chunk=chunk),
                nli_votes=(
                    _vote("minilm_l6", ModelExpertRole.SCOPE_NLI, nli_state, chunk=chunk),
                    _vote("minilm_l12", ModelExpertRole.SCOPE_NLI, nli_state, chunk=chunk),
                    _vote("mdeberta", ModelExpertRole.SCOPE_NLI, ModelVoteState.PRESENT, chunk=chunk),
                ),
                contributing_nli_model_keys=promoted,
            )
        )
    aggregate = aggregate_chunk_metrics(tuple(receipts))[0]
    assert aggregate.value_state is MetricValueState.KNOWN
    assert (aggregate.numerator, aggregate.denominator) == (1, 2)
    assert aggregate.numeric_value == 0.5
    assert aggregate.abstained_chunk_count == 1
    assert aggregate.product_metric_eligible is False


def test_vote_contract_rejects_scores_for_abstentions() -> None:
    with pytest.raises(ValidationError):
        ModelMetricVote(
            chunk_ordinal=0,
            metric_key="prompt.task_definition_coverage",
            model_key="qwen_rubric",
            role=ModelExpertRole.STRUCTURED_RUBRIC,
            state=ModelVoteState.ABSTAIN,
            raw_score=0.4,
            reason_code="synthetic_vote",
        )


def test_ten_expert_inventory_is_fixed_serial_and_process_releasable() -> None:
    experts = ensemble_expert_specs()
    assert len(experts) == 10
    assert tuple(item.identity.ordinal for item in experts) == tuple(range(10))
    assert tuple(item.identity.role for item in experts) == (
        *(ModelExpertRole.RETRIEVAL for _ in range(4)),
        *(ModelExpertRole.RERANKING for _ in range(2)),
        *(ModelExpertRole.SCOPE_NLI for _ in range(3)),
        ModelExpertRole.STRUCTURED_RUBRIC,
    )
    assert {item.identity.model_key for item in experts} == {
        "multilingual_e5_small",
        "multilingual_e5_base",
        "bge_m3",
        "qwen3_embedding_06b",
        "bge_reranker_v2_m3",
        "qwen3_reranker_06b",
        "mdeberta_xnli",
        "multilingual_minilmv2_l6_nli",
        "multilingual_minilmv2_l12_nli",
        "qwen3_4b_rubric",
    }


def test_serial_runner_uses_all_ten_models_and_returns_shadow_chunk_average() -> None:
    calls: list[tuple[int, str]] = []

    def execute(spec, stage, payload, device):  # type: ignore[no-untyped-def]
        calls.append((spec.identity.ordinal, stage))
        rows = []
        for case in payload["cases"]:
            if stage in {"retrieval", "reranking"}:
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "scores": [
                            {"fragment_id": identifier, "score": 1.0 / (index + 1)}
                            for index, identifier in enumerate(case["candidate_ids"])
                        ],
                    }
                )
            elif stage == "scope_nli":
                diagnostic = spec.identity.model_key == "mdeberta_xnli"
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "entailment": 0.05 if diagnostic else 0.9,
                        "neutral": 0.05,
                        "contradiction": 0.9 if diagnostic else 0.05,
                    }
                )
            else:
                rows.append({"case_id": case["case_id"], "label": "present"})
        return {
            "schema_version": 1,
            "model_key": spec.identity.model_key,
            "status": "completed",
            "error_code": None,
            "device": "cuda",
            "rows": rows,
            "runtime": {
                "inference_latency_ms": 1.0,
                "peak_cuda_allocated_mb": 2.0,
                "process_rss_after_load_and_inference_mb": 3.0,
            },
        }

    plan = build_ensemble_chunks(_context())
    specs = coaching_ensemble_metric_specs()[:3]
    receipt = SerialModelEnsembleRunner(executor=execute, device="cuda").run(
        plan, specs
    )

    assert calls == [
        (ordinal, ensemble_expert_specs()[ordinal].identity.role.value)
        for ordinal in range(10)
    ]
    assert len(receipt.experts) == 10
    assert all(item.unloaded_after_stage for item in receipt.experts)
    assert len(receipt.metrics) == 3
    assert all(item.value_state is MetricValueState.KNOWN for item in receipt.metrics)
    assert all(item.numeric_value == 1.0 for item in receipt.metrics)
    assert all(item.product_metric_eligible is False for item in receipt.metrics)
    serialized = receipt.model_dump_json()
    assert "fictional segment" not in serialized
    assert '"content_persisted":false' in serialized
