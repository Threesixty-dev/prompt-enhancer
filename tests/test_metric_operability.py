"""Exact release gates for the all-twenty metric operability catalog."""

from __future__ import annotations

from prompt_enhancer.application.analysis.metric_contract_v2 import (
    METRIC_CONTRACTS_V2,
    metric_contract_v2_set_fingerprint,
)
from prompt_enhancer.application.analysis.metric_operability import (
    METRIC_OPERABILITY_CATALOG_VERSION,
    MetricMeasuredPath,
    MetricNextStepCode,
    MetricShippedPathState,
    metric_operability_catalog,
)
from prompt_enhancer.application.analysis.requirement_verification_operability import (
    REVIEWED_REQUIREMENT_VERIFICATION_OPERABILITY,
    REVIEWED_REQUIREMENT_VERIFICATION_OPERABILITY_VERSION,
)
from prompt_enhancer.application.analysis.metric_projection_v2 import (
    METRIC_PROJECTION_V2_VERSION_8,
)
from prompt_enhancer.application.analysis.provider_evidence import (
    CURRENT_SAFE_EVENT_EVIDENCE_CAPABILITIES,
)
from prompt_enhancer.application.analysis.evidence_contracts import CapabilityKey
from prompt_enhancer.application.verification import (
    OBSERVED_CHECK_CLASSIFIER_VERSION,
    OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION,
    OBSERVED_CHECK_NORMALIZER_VERSION,
    OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION,
)
from prompt_enhancer.infrastructure.providers.codex_app_server.content_contracts import (
    TEXT_CONTENT_ADAPTER_VERSION,
    TEXT_CONTENT_SCHEMA_VERSION,
)
from prompt_enhancer.infrastructure.providers.codex_app_server.contracts import (
    SOURCE_SCHEMA_VERSION,
)
from prompt_enhancer.infrastructure.providers.codex_app_server.schema_preflight import (
    CODEX_TEXT_WINDOW_DECODER_DESCRIPTOR,
)
from prompt_enhancer.infrastructure.text_models.model_ensemble import (
    ensemble_expert_specs,
    probabilistic_challenger_specs,
)
from prompt_enhancer.infrastructure.text_models.probabilistic_metrics import (
    DISABLED_PROBABILISTIC_MODEL_KEYS,
)


PROFILE_PATHS = {
    "prompt.constraint_precision",
    "prompt.acceptance_testability",
    "prompt.deliverable_contract",
}

ADAPTER_GAPS = {
    "logic.hypothesis_test_linkage",
    "outcome.agent_claim_grounding",
}

EXPERIMENTAL_MODEL_PATHS = {
    "prompt.task_definition_coverage",
    "prompt.problem_evidence_quality",
    "prompt.context_sufficiency",
    "prompt.constraint_precision",
    "prompt.acceptance_testability",
    "prompt.deliverable_contract",
    "logic.decomposition_coverage",
    "logic.decision_rationale_coverage",
}


def test_operability_catalog_is_an_exact_all_twenty_partition() -> None:
    catalog = metric_operability_catalog()

    assert catalog.catalog_version == METRIC_OPERABILITY_CATALOG_VERSION
    assert catalog.projection_version == METRIC_PROJECTION_V2_VERSION_8
    assert catalog.contract_set_fingerprint == metric_contract_v2_set_fingerprint()
    assert catalog.total_metric_count == 20
    assert catalog.shipped_path_count == 18
    assert catalog.task_profile_configuration_gap_count == 0
    assert catalog.provider_adapter_gap_count == 2
    assert catalog.experimental_model_path_count == 8
    assert catalog.model_authoritative_metric_count == 0
    assert [entry.metric_key for entry in catalog.entries] == [
        contract.metric_key for contract in METRIC_CONTRACTS_V2
    ]
    assert [entry.contract_fingerprint for entry in catalog.entries] == [
        contract.fingerprint for contract in METRIC_CONTRACTS_V2
    ]
    assert all(not entry.measured_value_may_use_model_output for entry in catalog.entries)


def test_operability_catalog_names_every_configuration_and_adapter_gap() -> None:
    by_key = {entry.metric_key: entry for entry in metric_operability_catalog().entries}

    assert {
        key
        for key, entry in by_key.items()
        if entry.shipped_path_state
        is MetricShippedPathState.TASK_PROFILE_CONFIGURATION_REQUIRED
    } == set()
    assert {
        key
        for key, entry in by_key.items()
        if entry.shipped_path_state is MetricShippedPathState.PROVIDER_ADAPTER_REQUIRED
    } == ADAPTER_GAPS
    assert {
        key for key, entry in by_key.items() if entry.experimental_model_path
    } == EXPERIMENTAL_MODEL_PATHS
    assert all(
        by_key[key].measured_path is MetricMeasuredPath.DECLARED_TASK_PROFILE
        and by_key[key].shipped_path_state
        is MetricShippedPathState.AVAILABLE_WHEN_EVIDENCE_EXISTS
        for key in PROFILE_PATHS
    )

    first_pass = by_key["outcome.first_pass_verification"]
    assert first_pass.measured_path is MetricMeasuredPath.TASK_SCOPED_VERIFICATION
    assert (
        first_pass.shipped_path_state
        is MetricShippedPathState.AVAILABLE_WHEN_EVIDENCE_EXISTS
    )
    assert first_pass.experimental_model_path is False
    decomposition = by_key["logic.decomposition_coverage"]
    assert decomposition.measured_path is MetricMeasuredPath.REVIEWED_REQUIREMENT_PLAN
    assert decomposition.shipped_path_state is (
        MetricShippedPathState.AVAILABLE_WHEN_EVIDENCE_EXISTS
    )
    requirement_action = by_key["logic.requirement_action_traceability"]
    assert requirement_action.measured_path is (
        MetricMeasuredPath.REVIEWED_REQUIREMENT_ACTION
    )
    assert requirement_action.shipped_path_state is (
        MetricShippedPathState.AVAILABLE_WHEN_EVIDENCE_EXISTS
    )
    assert requirement_action.next_step_code.value == (
        "compose_requirement_action_evidence"
    )


def test_default_safe_event_authority_is_explicit_and_minimal() -> None:
    assert CURRENT_SAFE_EVENT_EVIDENCE_CAPABILITIES == frozenset(
        {
            CapabilityKey.TOOL_EVENTS,
            CapabilityKey.VERIFICATION_EVENTS,
            CapabilityKey.VERIFICATION_TASK_OPPORTUNITIES,
            CapabilityKey.VERIFICATION_TASK_EVIDENCE_LINKS,
        }
    )


def test_reviewed_requirement_verification_path_is_conditional_and_non_model() -> None:
    """The catalog names a complete path, never a session-ready result."""

    entry = next(
        item
        for item in metric_operability_catalog().entries
        if item.metric_key == "outcome.verified_requirement_coverage"
    )

    assert entry.measured_path is MetricMeasuredPath.REVIEWED_REQUIREMENT_VERIFICATION
    assert entry.shipped_path_state is MetricShippedPathState.AVAILABLE_WHEN_EVIDENCE_EXISTS
    assert entry.next_step_code is MetricNextStepCode.ISSUE_REVIEWED_OBSERVED_CHECK
    assert entry.measured_value_may_use_model_output is False


def test_reviewed_requirement_verification_descriptor_is_closed_and_non_authoritative() -> None:
    descriptor = REVIEWED_REQUIREMENT_VERIFICATION_OPERABILITY

    assert (
        descriptor.descriptor_version
        == REVIEWED_REQUIREMENT_VERIFICATION_OPERABILITY_VERSION
    )
    assert descriptor.provider == "codex"
    assert descriptor.decoder_key == CODEX_TEXT_WINDOW_DECODER_DESCRIPTOR.decoder_key
    assert descriptor.decoder_version == CODEX_TEXT_WINDOW_DECODER_DESCRIPTOR.decoder_version
    assert descriptor.text_adapter_version == TEXT_CONTENT_ADAPTER_VERSION
    assert descriptor.text_schema_version == TEXT_CONTENT_SCHEMA_VERSION
    assert descriptor.source_schema_version == SOURCE_SCHEMA_VERSION
    assert descriptor.completion_schema_version == OBSERVED_CHECK_COMPLETION_SCHEMA_VERSION
    assert descriptor.completion_classifier_version == OBSERVED_CHECK_CLASSIFIER_VERSION
    assert descriptor.completion_normalizer_version == OBSERVED_CHECK_NORMALIZER_VERSION
    assert (
        descriptor.completion_outcome_interpreter_version
        == OBSERVED_CHECK_OUTCOME_INTERPRETER_VERSION
    )
    assert descriptor.verification_projection_version == (
        "reviewed-requirement-verification-objective-projection-v1"
    )
    assert descriptor.sealed_metric_projection_version == METRIC_PROJECTION_V2_VERSION_8
    assert (
        descriptor.requires_complete_source,
        descriptor.requires_native_review,
        descriptor.requires_full_criterion_coverage_acknowledgment,
        descriptor.requires_fresh_sealed_source_binding,
        descriptor.provider_reported_outcome_only,
        descriptor.model_authority,
    ) == (True, True, True, True, True, False)


def test_live_model_router_is_exactly_three_small_experts_plus_optional_qwen() -> None:
    legacy = ensemble_expert_specs()
    assert len(legacy) == 10
    assert {item.identity.model_key for item in legacy[:6]} == {
        "multilingual_e5_small",
        "multilingual_e5_base",
        "bge_m3",
        "qwen3_embedding_06b",
        "bge_reranker_v2_m3",
        "qwen3_reranker_06b",
    }
    assert all(not item.identity.contributes_to_decision for item in legacy[:6])
    assert tuple(item.identity.model_key for item in legacy[6:9]) == (
        "mdeberta_xnli",
        "multilingual_minilmv2_l6_nli",
        "multilingual_minilmv2_l12_nli",
    )
    assert legacy[9].identity.model_key == "qwen3_4b_rubric"
    challengers = probabilistic_challenger_specs()
    assert {item.identity.model_key for item in challengers} == {
        "deberta_small_long_nli",
        "modernbert_base_zeroshot",
    }
    assert DISABLED_PROBABILISTIC_MODEL_KEYS == {
        item.identity.model_key for item in challengers
    }
