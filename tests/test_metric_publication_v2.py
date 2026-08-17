"""Synthetic tests for the canonical V2 metric publication seam."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib

import pytest
from pydantic import SecretStr, ValidationError

from prompt_enhancer.application.analysis.metric_contract_v2 import (
    EvidenceAuthority,
    METRIC_CONTRACTS_V2,
    MetricValueStateV2,
    metric_contract_v2,
)
from prompt_enhancer.application.analysis.metric_guidance import (
    GuidanceBasis,
    GuidanceStateClass,
)
from prompt_enhancer.application.analysis.metric_projection_v2 import (
    project_metric_states_v2,
)
from prompt_enhancer.application.analysis.metric_publication_v2 import (
    METRIC_PUBLICATION_V2_KEY,
    REASON_DENOMINATOR_NOT_OPPORTUNITY_OWNED,
    REASON_MODEL_ASSISTED_NOT_PUBLISHABLE,
    REASON_RESULT_ABSENT,
    REASON_RESULT_STATE_UNPUBLISHABLE,
    REASON_RUBRIC_DENOMINATOR_MISMATCH,
    MetricPublicationSource,
    MetricPublicationV2,
    publish_metric_states_v2,
    rehydrate_metric_states_v2,
)
from prompt_enhancer.application.analysis.objective_metric_projection import (
    OBJECTIVE_EVIDENCE_METRIC_KEYS,
    ObjectiveMetricOverride,
)
from prompt_enhancer.application.analysis.semantic_units import (
    SemanticUnitReconciler,
)
from prompt_enhancer.application.analysis.text_contracts import (
    EphemeralRedactedMessage,
    P1TextAnalysisInput,
    TextLanguage,
    TextMessageKind,
    TextRole,
    TextTaskProfile,
)
from prompt_enhancer.application.persistence import (
    MetricValueState,
    SessionAnalysisResultRecord,
    SessionMetricAggregation,
    SessionMetricApplicability,
    SessionMetricDirection,
)
from prompt_enhancer.domain import (
    DataTier,
    MetricObservation,
    MetricSource,
    Provider,
)


NOW = datetime(2040, 3, 4, 9, 0, tzinfo=UTC)
OBJECTIVE_KEYS = frozenset(OBJECTIVE_EVIDENCE_METRIC_KEYS)
RUBRIC_KEYS = (
    "prompt.task_definition_coverage",
    "prompt.problem_evidence_quality",
    "prompt.context_sufficiency",
)


def _id(label: str) -> str:
    return hashlib.sha256(f"synthetic-publication:{label}".encode()).hexdigest()


class _SyntheticIdFactory:
    def fingerprint(self, namespace: str, values: tuple[str, ...]) -> str:
        return hashlib.sha256("\x1f".join((namespace, *values)).encode()).hexdigest()

    def fingerprint_secret(
        self,
        namespace: str,
        values: tuple[str, ...],
        secret: SecretStr,
    ) -> str:
        return hashlib.sha256(
            "\x1f".join((namespace, *values, secret.get_secret_value())).encode()
        ).hexdigest()


IDS = _SyntheticIdFactory()


def _message(
    label: str,
    sequence: int,
    role: TextRole,
    kind: TextMessageKind,
    text: str,
    *,
    language: TextLanguage = TextLanguage.ENGLISH,
) -> EphemeralRedactedMessage:
    return EphemeralRedactedMessage(
        message_id=_id(label),
        sequence=sequence,
        role=role,
        kind=kind,
        language=language,
        text=SecretStr(text),
    )


def _context(
    messages: tuple[EphemeralRedactedMessage, ...],
    *,
    label: str,
) -> P1TextAnalysisInput:
    focus = next(
        message
        for message in reversed(messages)
        if message.role is TextRole.USER
        and message.kind in {TextMessageKind.REQUEST, TextMessageKind.FEEDBACK}
    )
    return P1TextAnalysisInput(
        provider=Provider.SYNTHETIC,
        session_id=_id("session"),
        provider_version="synthetic.1",
        adapter_version="synthetic-adapter.1",
        source_schema_version="synthetic-source.1",
        content_schema_version="synthetic-content.1",
        redactor_version="synthetic-redactor.1",
        text_extraction_complete=True,
        available_message_kinds=frozenset(message.kind for message in messages),
        analysis_window_fingerprint=_id(f"window:{label}"),
        focus_message_id=focus.message_id,
        observed_message_count=len(messages),
        eligible_message_count=len(messages),
        messages=messages,
        task_profile=TextTaskProfile(applicability=()),
    )


def _result(
    key: str,
    *,
    value_state: MetricValueState = MetricValueState.KNOWN,
    numerator: int | None = 2,
    denominator: int | None = 3,
    explanation_code: str = "rubric_factors",
    error_code: str | None = None,
    model_id: str | None = None,
    version: int = 2,
) -> SessionAnalysisResultRecord:
    known = value_state is MetricValueState.KNOWN
    return SessionAnalysisResultRecord(
        observation=MetricObservation(
            key=key,
            version=version,
            numeric_value=(
                None
                if not known or numerator is None or denominator is None
                else numerator / denominator
            ),
            unit="ratio",
            source=MetricSource.DETERMINISTIC,
            observed_count=3,
            eligible_count=3,
            coverage=1.0,
        ),
        value_state=value_state,
        direction=SessionMetricDirection.HIGHER_IS_BETTER,
        applicability=(
            SessionMetricApplicability.APPLICABLE
            if value_state is not MetricValueState.NOT_APPLICABLE
            else SessionMetricApplicability.NOT_APPLICABLE
        ),
        aggregation_method=SessionMetricAggregation.RATIO_OF_SUMS,
        metric_schema_version=1,
        evidence_data_tier=DataTier.REDACTED_CONTENT,
        fraction_numerator=numerator if known else None,
        fraction_denominator=denominator if known else None,
        explanation_code=explanation_code,
        error_code=error_code,
        algorithm_id="rules.en-pl.coaching-observables",
        algorithm_version="2",
        model_id=model_id,
        model_revision=None if model_id is None else "0" * 40,
        model_license=None if model_id is None else "example-license-1.0",
        tokenizer_id=None if model_id is None else "example/local-tokenizer",
        computed_at=NOW,
    )


def _by_key(publication: MetricPublicationV2) -> dict[str, object]:
    return {item.state.metric_key: item for item in publication.metrics}


def _publish(results, **kwargs) -> MetricPublicationV2:
    return publish_metric_states_v2(
        rehydrate_metric_states_v2(results, **kwargs),
        source=MetricPublicationSource.PERSISTED_RUN_REHYDRATION,
    )


def test_publication_always_lists_every_metric_in_registry_order() -> None:
    publication = _publish(())

    assert publication.publication_key == METRIC_PUBLICATION_V2_KEY
    assert len(publication.metrics) == len(METRIC_CONTRACTS_V2) == 20
    assert tuple(item.state.metric_key for item in publication.metrics) == tuple(
        contract.metric_key for contract in METRIC_CONTRACTS_V2
    )
    # An empty run is entirely unknown, never a wall of zeroes.
    assert publication.known_count == 0
    assert publication.unknown_count == 20
    assert all(item.state.numeric_value is None for item in publication.metrics)
    assert all(item.guidance.numerator is None for item in publication.metrics)
    assert all(
        item.guidance.basis is GuidanceBasis.READINESS
        for item in publication.metrics
    )


def test_absent_result_is_unknown_with_a_fixed_reason_not_zero() -> None:
    publication = _publish((_result("prompt.task_definition_coverage", numerator=3),))
    by_key = _by_key(publication)

    published = by_key["prompt.task_definition_coverage"]
    missing = by_key["prompt.context_sufficiency"]

    assert published.state.value_state is MetricValueStateV2.KNOWN
    assert missing.state.value_state is MetricValueStateV2.UNKNOWN
    assert missing.state.explanation_code == REASON_RESULT_ABSENT
    assert missing.state.statistics.eligible_count == 0
    assert missing.guidance.state_class is GuidanceStateClass.EVIDENCE_UNRESOLVED


def test_rubric_result_republishes_only_with_the_reviewed_factor_denominator() -> None:
    aligned = metric_contract_v2("prompt.task_definition_coverage")
    assert len(aligned.factors) == 3

    publication = _publish(
        (
            _result("prompt.task_definition_coverage", numerator=2, denominator=3),
            _result("prompt.context_sufficiency", numerator=5, denominator=9),
        )
    )
    by_key = _by_key(publication)

    good = by_key["prompt.task_definition_coverage"]
    assert good.state.value_state is MetricValueStateV2.KNOWN
    assert (good.state.numerator, good.state.denominator) == (2, 3)
    assert good.state.numeric_value == pytest.approx(2 / 3)
    assert good.state.statistics.met_count == 2
    assert good.state.statistics.not_met_count == 1
    assert good.guidance.state_class is GuidanceStateClass.KNOWN_IMPROVE

    mismatched = by_key["prompt.context_sufficiency"]
    assert mismatched.state.value_state is MetricValueStateV2.UNKNOWN
    assert mismatched.state.explanation_code == REASON_RUBRIC_DENOMINATOR_MISMATCH


def test_lexical_v1_denominators_never_become_owned_opportunities() -> None:
    withheld_keys = tuple(
        contract.metric_key
        for contract in METRIC_CONTRACTS_V2
        if contract.metric_key not in OBJECTIVE_KEYS
        and contract.metric_key not in RUBRIC_KEYS
    )
    assert len(withheld_keys) == 12

    publication = _publish(
        tuple(_result(metric_key, numerator=1, denominator=1) for metric_key in withheld_keys)
    )
    by_key = _by_key(publication)

    for metric_key in withheld_keys:
        published = by_key[metric_key]
        assert published.state.value_state is MetricValueStateV2.UNKNOWN, metric_key
        assert published.state.explanation_code == (
            REASON_DENOMINATOR_NOT_OPPORTUNITY_OWNED
        )
        assert published.state.numeric_value is None


def test_objective_lane_is_fail_closed_against_stored_conversational_ratios() -> None:
    publication = _publish(
        tuple(
            _result(metric_key, numerator=1, denominator=1)
            for metric_key in sorted(OBJECTIVE_KEYS)
        )
    )
    by_key = _by_key(publication)

    assert publication.objective_measured_count == 0
    for metric_key in OBJECTIVE_KEYS:
        published = by_key[metric_key]
        assert published.state.value_state is MetricValueStateV2.UNKNOWN, metric_key
        assert published.state.explanation_code == "typed_objective_absent"
        assert published.state.evidence_authority is (
            EvidenceAuthority.OBJECTIVE_RECEIPT
        )
        assert published.guidance.state_class is (
            GuidanceStateClass.OBJECTIVE_EVIDENCE_MISSING
        )


def test_typed_evidence_lane_is_the_only_objective_publisher() -> None:
    publication = _publish(
        (),
        objective_overrides={
            "outcome.verified_requirement_coverage": ObjectiveMetricOverride(
                value_state=MetricValueState.KNOWN,
                explanation_code="typed_requirement_verification_links",
                numerator=2,
                denominator=2,
                resolved_opportunity_count=2,
                eligible_opportunity_count=2,
                met_opportunity_count=2,
            ),
            "outcome.first_pass_verification": ObjectiveMetricOverride(
                value_state=MetricValueState.UNKNOWN,
                explanation_code="typed_first_verification_unresolved",
                resolved_opportunity_count=1,
                eligible_opportunity_count=3,
                met_opportunity_count=1,
            ),
        },
    )
    by_key = _by_key(publication)

    covered = by_key["outcome.verified_requirement_coverage"]
    assert covered.state.value_state is MetricValueStateV2.KNOWN
    assert covered.guidance.basis is GuidanceBasis.MEASURED
    assert covered.guidance.state_class is GuidanceStateClass.KNOWN_RETAIN
    assert publication.objective_measured_count == 1

    censored = by_key["outcome.first_pass_verification"]
    assert censored.state.value_state is MetricValueStateV2.PENDING
    assert censored.state.numeric_value is None
    assert censored.state.censoring_lower_bound == pytest.approx(1 / 3)
    assert censored.state.censoring_upper_bound == pytest.approx(1.0)
    assert censored.guidance.state_class is GuidanceStateClass.PENDING_CLOSURE


def test_model_assisted_result_cannot_publish_a_value() -> None:
    publication = _publish(
        (
            _result(
                "prompt.task_definition_coverage",
                numerator=3,
                denominator=3,
                model_id="example/local-rubric",
            ),
        )
    )
    published = _by_key(publication)["prompt.task_definition_coverage"]

    assert published.state.value_state is MetricValueStateV2.UNKNOWN
    assert published.state.explanation_code == (
        REASON_MODEL_ASSISTED_NOT_PUBLISHABLE
    )
    assert published.guidance.basis is GuidanceBasis.READINESS


def test_optional_neural_failure_preserves_its_code_without_blocking_others() -> None:
    publication = _publish(
        (
            # An optional local rubric stage timed out for one metric only.
            _result(
                "prompt.problem_evidence_quality",
                value_state=MetricValueState.EXECUTION_ERROR,
                numerator=None,
                denominator=None,
                explanation_code="model_committee_nli_failed",
                error_code="model_committee_nli_failed",
                model_id="example/local-rubric",
            ),
            _result("prompt.task_definition_coverage", numerator=3, denominator=3),
        ),
        objective_overrides={
            "outcome.agent_claim_grounding": ObjectiveMetricOverride(
                value_state=MetricValueState.KNOWN,
                explanation_code="typed_claim_grounding_links",
                numerator=1,
                denominator=1,
                resolved_opportunity_count=1,
                eligible_opportunity_count=1,
                met_opportunity_count=1,
            ),
        },
    )
    by_key = _by_key(publication)

    failed = by_key["prompt.problem_evidence_quality"]
    assert failed.state.value_state is MetricValueStateV2.EXECUTION_ERROR
    assert failed.state.explanation_code == "model_committee_nli_failed"
    assert failed.guidance.basis is GuidanceBasis.METHOD_ONLY

    # The deterministic and objective results still publish normally.
    assert (
        by_key["prompt.task_definition_coverage"].state.value_state
        is MetricValueStateV2.KNOWN
    )
    assert (
        by_key["outcome.agent_claim_grounding"].state.value_state
        is MetricValueStateV2.KNOWN
    )
    assert publication.execution_error_count == 1
    assert publication.known_count == 2
    assert len(publication.metrics) == 20


def test_duplicated_stored_metric_rows_are_ambiguous_not_averaged() -> None:
    publication = _publish(
        (
            _result("prompt.task_definition_coverage", numerator=3, denominator=3),
            _result("prompt.task_definition_coverage", numerator=0, denominator=3),
        )
    )
    published = _by_key(publication)["prompt.task_definition_coverage"]

    assert published.state.value_state is MetricValueStateV2.UNKNOWN
    assert published.state.explanation_code == REASON_RESULT_STATE_UNPUBLISHABLE


def test_stored_not_applicable_and_abstained_states_are_preserved() -> None:
    publication = _publish(
        (
            _result(
                "prompt.task_definition_coverage",
                value_state=MetricValueState.NOT_APPLICABLE,
                numerator=None,
                denominator=None,
                explanation_code="no_opportunity_observed",
            ),
            _result(
                "prompt.context_sufficiency",
                value_state=MetricValueState.ABSTAINED,
                numerator=None,
                denominator=None,
                explanation_code="message_kind_unavailable",
            ),
        )
    )
    by_key = _by_key(publication)

    not_applicable = by_key["prompt.task_definition_coverage"]
    assert not_applicable.state.value_state is MetricValueStateV2.NOT_APPLICABLE
    assert not_applicable.guidance.state_class is GuidanceStateClass.NO_OPPORTUNITY

    abstained = by_key["prompt.context_sufficiency"]
    assert abstained.state.value_state is MetricValueStateV2.ABSTAINED
    assert abstained.state.explanation_code == "message_kind_unavailable"
    assert abstained.guidance.state_class is (
        GuidanceStateClass.EVIDENCE_COVERAGE_ABSTAINED
    )
    # A diagnostic intent cannot be proved absent, so V2 keeps it unknown.
    assert by_key["prompt.problem_evidence_quality"].state.value_state is (
        MetricValueStateV2.UNKNOWN
    )


@pytest.mark.parametrize(
    ("language", "request_text", "response_text"),
    (
        (
            TextLanguage.ENGLISH,
            "Implement the fictional widget export.",
            "For the widget export, run a regression test; it must pass with exactly 3 rows.",
        ),
        (
            TextLanguage.POLISH,
            "Zaimplementuj fikcyjny widget eksport.",
            "Dla widget eksport uruchom test regresji; wynik musi przejść dokładnie 3 wiersze.",
        ),
    ),
)
def test_live_projection_publishes_identical_guidance_for_en_and_pl(
    language: TextLanguage,
    request_text: str,
    response_text: str,
) -> None:
    context = _context(
        (
            _message(
                "live-request",
                1,
                TextRole.USER,
                TextMessageKind.REQUEST,
                request_text,
                language=language,
            ),
            _message(
                "live-response",
                2,
                TextRole.AGENT,
                TextMessageKind.RESPONSE,
                response_text,
                language=language,
            ),
        ),
        label=f"live-{language.value}",
    )
    reconciliation = SemanticUnitReconciler(IDS).reconcile(context).reconciliation

    publication = publish_metric_states_v2(
        project_metric_states_v2(
            context=context,
            reconciliation=reconciliation,
            id_factory=IDS,
        ),
        source=MetricPublicationSource.LIVE_PROJECTION,
    )
    by_key = _by_key(publication)

    assert publication.source is MetricPublicationSource.LIVE_PROJECTION
    assert len(publication.metrics) == 20
    strategy = by_key["outcome.verification_strategy_adequacy"]
    assert strategy.state.value_state is MetricValueStateV2.KNOWN
    assert strategy.state.numerator == 1 and strategy.state.denominator == 1
    assert strategy.guidance.state_class is GuidanceStateClass.KNOWN_RETAIN
    assert strategy.guidance.basis is GuidanceBasis.EXPERIMENTAL
    assert strategy.guidance.action_template_id == (
        "action.retain.outcome.verification_strategy_adequacy.v1"
    )
    # A stated strategy is conversational, so it never becomes objective proof.
    assert publication.objective_measured_count == 0


def test_publication_rejects_an_objective_metric_resolved_conversationally() -> None:
    publication = _publish(())
    metrics = list(publication.metrics)
    index = next(
        position
        for position, item in enumerate(metrics)
        if item.state.metric_key == "outcome.first_pass_verification"
    )
    laundered = _publish(
        (),
    ).metrics[index]
    forged_state = laundered.state.model_copy(
        update={
            "value_state": MetricValueStateV2.KNOWN,
            "numerator": 1,
            "denominator": 1,
            "numeric_value": 1.0,
            "censoring_lower_bound": 1.0,
            "censoring_upper_bound": 1.0,
            "statistics": laundered.state.statistics.model_copy(
                update={
                    "denominator_basis": (
                        metric_contract_v2(
                            "prompt.task_definition_coverage"
                        ).denominator_basis
                    ),
                    "capability_available": True,
                    "eligible_count": 1,
                    "met_count": 1,
                }
            ),
        }
    )
    metrics[index] = laundered.model_copy(
        update={
            "state": forged_state,
            "guidance": laundered.guidance.model_copy(
                update={
                    "value_state": MetricValueStateV2.KNOWN,
                    "state_class": GuidanceStateClass.KNOWN_RETAIN,
                    "basis": GuidanceBasis.MEASURED,
                    "numerator": 1,
                    "denominator": 1,
                    "eligible_count": 1,
                    "met_count": 1,
                }
            ),
        }
    )

    with pytest.raises(ValidationError, match="conversational material"):
        publication.model_copy(update={"metrics": tuple(metrics)}).model_validate(
            {
                **publication.model_dump(),
                "metrics": [item.model_dump() for item in metrics],
                "known_count": 1,
                "unknown_count": 19,
                "objective_measured_count": 1,
            }
        )


def test_publication_rejects_incomplete_or_reordered_metric_sets() -> None:
    publication = _publish(())
    payload = publication.model_dump()

    with pytest.raises(ValidationError, match="at least 20 items"):
        MetricPublicationV2.model_validate(
            {
                **payload,
                "metrics": payload["metrics"][:19],
                "unknown_count": 19,
            }
        )

    reversed_metrics = list(reversed(payload["metrics"]))
    with pytest.raises(ValidationError, match="registry order"):
        MetricPublicationV2.model_validate(
            {**payload, "metrics": reversed_metrics}
        )

    with pytest.raises(ValidationError, match="counts are inconsistent"):
        MetricPublicationV2.model_validate({**payload, "unknown_count": 3})

    with pytest.raises(ValidationError, match="fingerprint is stale"):
        MetricPublicationV2.model_validate(
            {**payload, "contract_set_fingerprint": "c" * 64}
        )


def test_publication_serialization_is_content_free() -> None:
    payload = _publish(
        (_result("prompt.task_definition_coverage", numerator=3, denominator=3),)
    ).model_dump_json()

    lowered = payload.casefold()
    for prohibited in (
        "prompt_text",
        "excerpt",
        "filesystem_path",
        "raw_content",
        "session_id",
        "message_id",
    ):
        assert prohibited not in lowered
    assert all(
        item.state.product_metric_eligible is False
        for item in _publish(()).metrics
    )
