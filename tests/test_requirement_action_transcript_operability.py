"""Synthetic proof that complete Claude transcripts can establish R8 action links.

The fixture below is deliberately local and fictional. It crosses the shipped
transcript adapter, metadata ingestion, safe-event projector, text source, and
reviewed requirement/action evidence services. It proves that composition, not
an actual provider, native UI, model, policy, or compatibility integration;
those external boundaries use constrained synthetic collaborators.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.application.analysis.model_ensemble import ModelExpertRole
from prompt_enhancer.application.analysis.requirement_action_evidence import (
    InMemoryRequirementActionReviewContextStore,
    REQUIREMENT_ACTION_DECISION_CONFIRMATION,
    REQUIREMENT_ACTION_EVIDENCE_FILE_VERSION,
    REQUIREMENT_ACTION_GUIDED_AUTHORING_CONFIRMATION,
    REQUIREMENT_ACTION_IMPORT_CONFIRMATION,
    REQUIREMENT_ACTION_REVIEW_CONFIRMATION,
    RequirementActionDecisionCommand,
    RequirementActionDecisionKind,
    RequirementActionEvidenceFileV1,
    RequirementActionEvidenceService,
    RequirementActionGuidedAuthoringCommand,
    RequirementActionLinkEntry,
    SealedRunRequirementActionSource,
)
from prompt_enhancer.application.analysis.requirement_plan_evidence import (
    InMemoryRequirementPlanReviewContextStore,
    REQUIREMENT_PLAN_DECISION_CONFIRMATION,
    REQUIREMENT_PLAN_REVIEW_CONFIRMATION,
    PlanCoordinate,
    RequirementDisposition,
    RequirementPlanDecisionCommand,
    RequirementPlanDecisionKind,
    RequirementPlanEvidenceService,
    RequirementPlanGuidedAuthoringCommand,
    RequirementEvidenceEntry,
    RequirementPlanProducer,
    SealedRunRequirementPlanSource,
)
from prompt_enhancer.application.analysis.semantic_units import SemanticUnitReconciler
from prompt_enhancer.application.analysis.session_model_ensemble import (
    MODEL_ENSEMBLE_CONFIRMATION,
    RequirementActionEvidenceSource,
    SessionModelEnsembleService,
)
from prompt_enhancer.application.analysis.text_contracts import (
    TextMessageKind,
    TextRole,
)
from prompt_enhancer.application.analysis.text_analysis_presets import (
    COACHING_PROFILE_V1,
)
from prompt_enhancer.application.analysis.text_source import (
    TextAnalysisPurpose,
    TextAnalysisSelection,
    TextSourceAccessGrant,
)
from prompt_enhancer.bootstrap import LocalApplication
from prompt_enhancer.database import Database
from prompt_enhancer.config import AppSettings
from prompt_enhancer.domain import DataTier, Provider
from prompt_enhancer.ingestion import IngestionService
from prompt_enhancer.infrastructure.identifiers import LocalArtifactIdFactory
from prompt_enhancer.infrastructure.providers.claude_code_hooks.text_source import (
    ClaudeTranscriptTextAnalysisSource,
)
from prompt_enhancer.infrastructure.providers.claude_code_hooks.transcript_adapter import (
    ClaudeTranscriptAdapter,
    parse_events,
)
from prompt_enhancer.infrastructure.providers.claude_code_hooks.transcript_reader import (
    ClaudeTranscriptReader,
    catalog_session_id_for,
)
from prompt_enhancer.infrastructure.text_models.model_ensemble import (
    MODEL_ENSEMBLE_RUNNER_SCHEMA_VERSION,
)
from prompt_enhancer.infrastructure.text_models.probabilistic_metrics import (
    LocalProbabilisticMetricRunner,
)
from prompt_enhancer.interfaces.http.browser_session import CSRF_HEADER
from prompt_enhancer.privacy import Pseudonymizer


NOW = datetime(2040, 1, 1, tzinfo=UTC)
RAW_SESSION_ID = "synthetic-claude-requirement-action-session"
CWD = "/srv/example/workspaces/requirement-action-proof"
TOKEN = "synthetic_requirement_action_proof_token_123456"


def _pseudonymizer() -> Pseudonymizer:
    return Pseudonymizer(bytes(range(32)))


def _stamp(second: int) -> str:
    return (NOW + timedelta(seconds=second)).isoformat().replace("+00:00", "Z")


def _row(kind: str, content: object, second: int) -> dict[str, object]:
    return {
        "type": kind,
        "timestamp": _stamp(second),
        "sessionId": RAW_SESSION_ID,
        "cwd": CWD,
        "version": "synthetic-claude-1",
        "message": {"role": kind, "content": content},
    }


def _write_complete_transcript(claude_home: Path) -> Path:
    project = claude_home / "projects" / "-srv-example-workspaces-requirement-action-proof"
    project.mkdir(parents=True)
    rows = (
        _row("user", "Add a retry boundary to the fictional uploader.", 0),
        _row(
            "assistant",
            [
                {
                    "type": "tool_use",
                    "id": "synthetic-plan",
                    "name": "TodoWrite",
                    "input": {"todos": [{"content": "Add retry boundary", "status": "pending"}]},
                },
                {
                    "type": "tool_use",
                    "id": "synthetic-write",
                    "name": "Write",
                    "input": {"file_path": "synthetic_uploader.py"},
                },
            ],
            1,
        ),
        _row(
            "user",
            [
                {"type": "tool_result", "tool_use_id": "synthetic-plan", "content": "ok", "is_error": False},
                {"type": "tool_result", "tool_use_id": "synthetic-write", "content": "ok", "is_error": False},
            ],
            2,
        ),
        _row("assistant", "The fictional retry boundary is present.", 3),
    )
    path = project / f"{RAW_SESSION_ID}.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def _write_malformed_transcript(claude_home: Path) -> Path:
    path = _write_complete_transcript(claude_home)
    malformed = {
        "type": "assistant",
        "timestamp": _stamp(4),
        "sessionId": RAW_SESSION_ID,
        "cwd": CWD,
        "version": "synthetic-claude-1",
        "message": {"content": [{"type": "tool_use", "id": "bad", "name": "Write", "input": "not-an-object"}]},
    }
    path.write_text(path.read_text(encoding="utf-8") + json.dumps(malformed) + "\n", encoding="utf-8")
    return path


class _AccessPolicy:
    def __init__(self, database: Database, session_id: str) -> None:
        self._database = database
        self._session_id = session_id

    def has_active_consent(self, provider: Provider, tier: DataTier) -> bool:
        return self._database.has_active_consent(provider, tier)

    def selection_is_indexed(
        self,
        provider: Provider,
        *,
        project_ids: frozenset[str],
        session_ids: frozenset[str],
    ) -> bool:
        session = self._database.get_session(self._session_id)
        return (
            provider is Provider.CLAUDE_CODE
            and not project_ids
            and session_ids == frozenset((self._session_id,))
            and session is not None
            and session.provider is provider
        )


class _Compatibility:
    def require_compatible(self, provider: str) -> object:
        if provider != Provider.CLAUDE_CODE.value:
            raise ValueError("synthetic fixture only composes Claude")
        return object()


def _execute(spec, stage, payload, device):  # type: ignore[no-untyped-def]
    """The sole model fake: deterministic rows with no model or network access."""

    rows = []
    for case in payload["cases"]:
        if stage in {"retrieval", "reranking"}:
            rows.append(
                {
                    "case_id": case["case_id"],
                    "scores": [
                        {"fragment_id": item, "score": 1.0 / (index + 1)}
                        for index, item in enumerate(case["candidate_ids"])
                    ],
                }
            )
        elif stage == ModelExpertRole.SCOPE_NLI.value:
            rows.append({"case_id": case["case_id"], "entailment": 0.9, "neutral": 0.05, "contradiction": 0.05})
        else:
            rows.append({"case_id": case["case_id"], "label": "present"})
    return {
        "schema_version": MODEL_ENSEMBLE_RUNNER_SCHEMA_VERSION,
        "model_key": spec.identity.model_key,
        "status": "completed",
        "error_code": None,
        "device": "cpu",
        "rows": rows,
        "runtime": {"inference_latency_ms": 1.0, "peak_cuda_allocated_mb": 0.0, "process_rss_after_load_and_inference_mb": 100.0},
    }


def _payload(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _metric(run):  # type: ignore[no-untyped-def]
    publication = run.receipt.metric_publication_v2
    assert publication is not None
    return next(item.state for item in publication.metrics if item.state.metric_key == "logic.requirement_action_traceability")


@pytest.mark.parametrize(
    ("link_completed_action", "expected_numerator"),
    ((True, 1), (False, 0)),
    ids=("reviewed-link", "reviewed-empty-link"),
)
@pytest.mark.parametrize("action_authoring", ("guided", "file"))
def test_complete_claude_transcript_reaches_known_r8_requirement_action_measurement(
    tmp_path: Path,
    link_completed_action: bool,
    expected_numerator: int,
    action_authoring: str,
) -> None:
    """Both supported authoring paths need complete reviewed links for R8."""

    claude_home = tmp_path / "synthetic-claude-home"
    path = _write_complete_transcript(claude_home)
    original_transcript_bytes = path.read_bytes()
    pseudonymizer = _pseudonymizer()
    identifiers = LocalArtifactIdFactory(pseudonymizer)
    session_id = catalog_session_id_for(pseudonymizer, RAW_SESSION_ID)
    database = Database(tmp_path / "synthetic.sqlite3")
    database.configure_local_artifact_id_factory(identifiers)
    database.initialize()
    database.grant_consent(Provider.CLAUDE_CODE, DataTier.REDACTED_CONTENT)

    # Actual provider adapter -> safe ingestion boundary.
    report = IngestionService(database, pseudonymizer).ingest(
        ClaudeTranscriptAdapter(pseudonymizer, claude_home=claude_home)
    )
    assert report.sessions_inserted == 1
    assert report.events_inserted > 0
    indexed = database.get_session(session_id)
    assert indexed is not None and indexed.events_complete is True

    reader = ClaudeTranscriptReader(pseudonymizer, claude_home=claude_home)
    source = ClaudeTranscriptTextAnalysisSource(pseudonymizer, locate=reader.locate)
    projector = LocalApplication(
        settings=AppSettings(home=tmp_path / "synthetic-composition"),
        database=database,
        pseudonymizer=pseudonymizer,
    ).create_typed_evidence_projector()
    clock = [NOW + timedelta(hours=1)]
    plan_contexts = InMemoryRequirementPlanReviewContextStore(
        clock=lambda: clock[0], monotonic_clock=lambda: 100.0
    )
    action_contexts = InMemoryRequirementActionReviewContextStore(
        clock=lambda: clock[0], monotonic_clock=lambda: 100.0, candidate_binding_key=b"s" * 32
    )
    models = database.model_ensemble_repository()
    ensemble = SessionModelEnsembleService(
        _AccessPolicy(database, session_id),
        models,
        lambda provider: source,
        _Compatibility(),
        identifiers,
        LocalProbabilisticMetricRunner(
            executor=_execute,
            device="cpu",
            deep_enabled=False,
            clock=lambda: clock[0],
        ),
        clock=lambda: clock[0],
        typed_evidence_projector=projector,
        semantic_unit_reconciler=SemanticUnitReconciler(identifiers),
        requirement_plan_evidence_reader=database.requirement_plan_evidence_repository(),
        requirement_plan_review_contexts=plan_contexts,
        requirement_action_evidence_reader=database.requirement_action_evidence_repository(),
        requirement_action_review_contexts=action_contexts,
    )

    first = ensemble.run(
        provider=Provider.CLAUDE_CODE,
        session_id=session_id,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="synthetic-transcript-plan-0001",
    )
    assert first.run.requirement_plan_evidence_binding is not None
    assert first.run.requirement_plan_evidence_binding.confirmation_id is None
    assert first.run.requirement_action_evidence_binding is not None
    assert (
        first.run.requirement_action_evidence_binding.evidence_source
        is RequirementActionEvidenceSource.UNAVAILABLE
    )

    # The sealed plan source and its proposal/decision storage are real.  The
    # review receipt below represents only the owned native user-presence step.
    plan_service = RequirementPlanEvidenceService(
        database.requirement_plan_evidence_repository(),
        SealedRunRequirementPlanSource(models, plan_contexts),
        identifiers,
        review_contexts=plan_contexts,
        clock=lambda: clock[0],
    )
    action_service = RequirementActionEvidenceService(
        database.requirement_action_evidence_repository(),
        SealedRunRequirementActionSource(models, action_contexts),
        identifiers,
        review_contexts=action_contexts,
        clock=lambda: clock[0],
    )
    app = create_app(
        settings=AppSettings(home=tmp_path / "synthetic-http"),
        database=database,
        api_token=TOKEN,
        requirement_plan_evidence_service=plan_service,
        requirement_action_evidence_service=action_service,
        user_presence_confirmation=lambda _request, _body: None,
    )
    plan_contract = plan_service.contract(session_id)
    user_clauses = [
        (message.message_sequence, clause)
        for message in plan_contract.source_manifest.messages
        if message.role is TextRole.USER and message.kind in {TextMessageKind.REQUEST, TextMessageKind.FEEDBACK}
        for clause in range(message.clause_count)
    ]
    plan_clauses = [
        (message.message_sequence, clause)
        for message in plan_contract.source_manifest.messages
        if message.role is TextRole.AGENT and message.kind is TextMessageKind.PLAN
        for clause in range(message.clause_count)
    ]
    assert len(user_clauses) == 1 and plan_clauses
    plan_base = f"/v1/sessions/{session_id}/requirement-plan-evidence"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        browser = client.get("/auth/session")
        native_headers = {
            CSRF_HEADER: browser.json()["csrf_token"],
            "Origin": "http://127.0.0.1",
        }
        guided_review = client.post(
            f"{plan_base}/guided-authoring/review",
            headers=native_headers,
            json={
                "expected_source_run_id": first.run.run_id,
                "source_window_fingerprint": plan_contract.source_window_fingerprint,
                "manifest_fingerprint": plan_contract.source_manifest.manifest_fingerprint,
                "expected_predecessor_confirmation_id": None,
                "confirmation": "open_exact_local_requirement_plan_guided_authoring",
            },
        )
        assert guided_review.status_code == 200
        guided = guided_review.json()
        guided_command = RequirementPlanGuidedAuthoringCommand(
            expected_source_run_id=first.run.run_id,
            source_window_fingerprint=plan_contract.source_window_fingerprint,
            expected_predecessor_confirmation_id=None,
            manifest_fingerprint=guided["manifest_fingerprint"],
            authoring_receipt_id=guided["authoring_receipt_id"],
            requirements=tuple(
                RequirementEvidenceEntry(
                    coordinate={"message_sequence": sequence, "clause_index": clause},
                    disposition=RequirementDisposition.LINKED,
                    plan_indexes=(0,),
                )
                for sequence, clause in user_clauses
            ),
            excluded_user_clauses=(),
            plan_items=tuple(
                PlanCoordinate(message_sequence=sequence, clause_index=clause)
                for sequence, clause in plan_clauses
            ),
            complete_user_clause_classification_acknowledged=True,
        )
        created = client.post(
            f"{plan_base}/guided-authoring/proposals",
            headers={
                API_TOKEN_HEADER: TOKEN,
                "Content-Type": "application/json",
                "Idempotency-Key": "synthetic-transcript-guided-plan-0001",
            },
            json=guided_command.model_dump(mode="json"),
        )
        assert created.status_code == 201
        plan_proposal_id = created.json()["proposal"]["proposal_id"]
        assert created.json()["proposal"]["producer_receipt"]["kind"] == "local_review_ui"
        plan_review = client.post(
            f"{plan_base}/proposals/{plan_proposal_id}/review",
            headers=native_headers,
            json={
                "expected_source_run_id": first.run.run_id,
                "confirmation": REQUIREMENT_PLAN_REVIEW_CONFIRMATION,
            },
        )
        assert plan_review.status_code == 200
        review_body = plan_review.json()
        plan_command = RequirementPlanDecisionCommand(
            expected_source_run_id=first.run.run_id,
            decision=RequirementPlanDecisionKind.CONFIRM,
            confirmation=REQUIREMENT_PLAN_DECISION_CONFIRMATION,
            review_receipt_id=review_body["review_receipt_id"],
            manifest_fingerprint=review_body["manifest_fingerprint"],
            reviewed_graph_fingerprint=review_body["reviewed_graph_fingerprint"],
            reviewed_candidate_set_fingerprint=(
                review_body["reviewed_candidate_set_fingerprint"]
            ),
            complete_review_acknowledged=True,
        )
        token_only = client.post(
            f"{plan_base}/proposals/{plan_proposal_id}/decision",
            headers={
                API_TOKEN_HEADER: TOKEN,
                "Idempotency-Key": "synthetic-transcript-plan-token-only-0001",
            },
            json=plan_command.model_dump(mode="json"),
        )
        assert token_only.status_code == 403
        plan_decision = client.post(
            f"{plan_base}/proposals/{plan_proposal_id}/decision",
            headers={
                **native_headers,
                "Idempotency-Key": "synthetic-transcript-plan-confirm-0001",
            },
            json=plan_command.model_dump(mode="json"),
        )
        assert plan_decision.status_code == 201

    clock[0] += timedelta(seconds=1)
    second = ensemble.run(
        provider=Provider.CLAUDE_CODE,
        session_id=session_id,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="synthetic-transcript-action-0002",
        reuse_latest=True,
        prior_run_id=first.run.run_id,
    )
    assert second.run.requirement_action_evidence_binding is not None
    assert second.run.requirement_action_evidence_binding.evidence_source is RequirementActionEvidenceSource.AWAITING_REVIEW

    action_contract = action_service.contract(session_id)
    context = source.read(
        selection=TextAnalysisSelection(provider=Provider.CLAUDE_CODE, session_id=session_id),
        grant=TextSourceAccessGrant(
            purpose=TextAnalysisPurpose.TEXT_ANALYSIS,
            provider=Provider.CLAUDE_CODE,
            session_id=session_id,
            data_tier=DataTier.REDACTED_CONTENT,
            per_run_confirmation_active=True,
            local_only=True,
            content_persistence_allowed=False,
        ),
        task_profile=COACHING_PROFILE_V1.task_profile,
    )
    assert context.action_descriptor_extraction_complete is True
    assert {
        item.source_reference_id for item in action_contract.candidate_manifest.actions
    } == {item.source_reference_id for item in context.action_descriptors}
    write_completion = next(
        item
        for item in context.action_descriptors
        if item.tool_name.get_secret_value() == "Write"
        and item.event_kind.value == "tool_end"
    )
    completed_action_index = next(
        candidate.candidate_index
        for candidate in action_contract.candidate_manifest.actions
        if candidate.source_reference_id == write_completion.source_reference_id
        and candidate.state.value == "completed"
    )

    action_base = f"/v1/sessions/{session_id}/requirement-action-evidence"
    action_proposal_id: str | None = None
    action_confirmation_id: str | None = None
    if action_authoring == "file":
        action_file = RequirementActionEvidenceFileV1(
            schema_version=REQUIREMENT_ACTION_EVIDENCE_FILE_VERSION,
            session_id=session_id,
            expected_source_run_id=action_contract.expected_source_run_id,
            source_window_fingerprint=action_contract.source_window_fingerprint,
            requirement_plan_confirmation_id=(
                action_contract.requirement_plan_confirmation_id
            ),
            requirement_plan_evidence_fingerprint=(
                action_contract.requirement_plan_evidence_fingerprint
            ),
            candidate_manifest_fingerprint=(
                action_contract.candidate_manifest.manifest_fingerprint
            ),
            expected_predecessor_confirmation_id=(
                action_contract.expected_predecessor_confirmation_id
            ),
            nonce=hashlib.sha256(b"synthetic-action-nonce").hexdigest(),
            created_at=clock[0],
            expires_at=clock[0] + timedelta(hours=1),
            producer=RequirementPlanProducer(
                kind="local_coding_agent",
                producer_id="synthetic-action-agent",
                producer_version="1",
                model_id="synthetic-local-model",
                authority="untrusted_provenance_claim",
            ),
            complete_requirement_enumeration=True,
            complete_action_candidate_enumeration=True,
            complete_requirement_link_classification=True,
            links=tuple(
                RequirementActionLinkEntry(
                    requirement_index=index,
                    action_candidate_indexes=(
                        (completed_action_index,) if link_completed_action else ()
                    ),
                )
                for index, _requirement in enumerate(action_contract.requirements)
            ),
            contains_action_state_claims=False,
            contains_objective_proof_claims=False,
            contains_metric_values=False,
            contains_prose=False,
            contains_paths=False,
        )
        action_bytes = _payload(action_file.model_dump(mode="json"))
        action_preview = action_service.preview(
            session_id=session_id, payload=action_bytes, now=clock[0]
        )
        action_proposal, _ = action_service.import_file(
            session_id=session_id,
            payload=action_bytes,
            expected_payload_sha256=action_preview.payload_sha256,
            confirmation=REQUIREMENT_ACTION_IMPORT_CONFIRMATION,
            idempotency_key="synthetic-transcript-action-import-0001",
            now=clock[0],
        )
        action_proposal_id = action_proposal.proposal.proposal_id

    with TestClient(app, base_url="http://127.0.0.1") as client:
        browser = client.get("/auth/session")
        native_headers = {
            CSRF_HEADER: browser.json()["csrf_token"],
            "Origin": "http://127.0.0.1",
        }
        if action_authoring == "guided":
            guided_action_review = client.post(
                f"{action_base}/guided-authoring/review",
                headers=native_headers,
                json={
                    "expected_source_run_id": second.run.run_id,
                    "source_window_fingerprint": action_contract.source_window_fingerprint,
                    "requirement_plan_confirmation_id": (
                        action_contract.requirement_plan_confirmation_id
                    ),
                    "requirement_plan_evidence_fingerprint": (
                        action_contract.requirement_plan_evidence_fingerprint
                    ),
                    "candidate_manifest_fingerprint": (
                        action_contract.candidate_manifest.manifest_fingerprint
                    ),
                    "expected_predecessor_confirmation_id": (
                        action_contract.expected_predecessor_confirmation_id
                    ),
                    "confirmation": REQUIREMENT_ACTION_GUIDED_AUTHORING_CONFIRMATION,
                },
            )
            assert guided_action_review.status_code == 200
            guided_action = guided_action_review.json()
            action_command = RequirementActionGuidedAuthoringCommand(
                expected_source_run_id=second.run.run_id,
                source_window_fingerprint=guided_action["source_window_fingerprint"],
                requirement_plan_confirmation_id=(
                    guided_action["requirement_plan_confirmation_id"]
                ),
                requirement_plan_evidence_fingerprint=(
                    guided_action["requirement_plan_evidence_fingerprint"]
                ),
                candidate_manifest_fingerprint=(
                    guided_action["candidate_manifest_fingerprint"]
                ),
                expected_predecessor_confirmation_id=(
                    guided_action["expected_predecessor_confirmation_id"]
                ),
                authoring_receipt_id=guided_action["authoring_receipt_id"],
                links=tuple(
                    RequirementActionLinkEntry(
                        requirement_index=index,
                        action_candidate_indexes=(
                            (completed_action_index,) if link_completed_action else ()
                        ),
                    )
                    for index, _requirement in enumerate(guided_action["requirements"])
                ),
                complete_requirement_link_classification_acknowledged=True,
            )
            action_created = client.post(
                f"{action_base}/guided-authoring/proposals",
                headers={
                    API_TOKEN_HEADER: TOKEN,
                    "Content-Type": "application/json",
                    "Idempotency-Key": "synthetic-transcript-guided-action-0001",
                },
                json=action_command.model_dump(mode="json"),
            )
            assert action_created.status_code == 201
            assert action_created.json()["proposal"]["decision"] is None
            assert (
                action_created.json()["proposal"]["producer_receipt"]["kind"]
                == "local_review_ui"
            )
            action_proposal_id = action_created.json()["proposal"]["proposal_id"]
        assert action_proposal_id is not None
        action_review = client.post(
            f"{action_base}/proposals/{action_proposal_id}/review",
            headers=native_headers,
            json={
                "expected_source_run_id": second.run.run_id,
                "confirmation": REQUIREMENT_ACTION_REVIEW_CONFIRMATION,
            },
        )
        assert action_review.status_code == 200
        review_body = action_review.json()
        action_decision = client.post(
            f"{action_base}/proposals/{action_proposal_id}/decision",
            headers={
                **native_headers,
                "Idempotency-Key": "synthetic-transcript-action-confirm-0001",
            },
            json=RequirementActionDecisionCommand(
                expected_source_run_id=second.run.run_id,
                decision=RequirementActionDecisionKind.CONFIRM,
                confirmation=REQUIREMENT_ACTION_DECISION_CONFIRMATION,
                review_receipt_id=review_body["review_receipt_id"],
                reviewed_graph_fingerprint=review_body["reviewed_graph_fingerprint"],
                candidate_manifest_fingerprint=(
                    review_body["candidate_manifest_fingerprint"]
                ),
                reviewed_candidate_set_fingerprint=(
                    review_body["reviewed_candidate_set_fingerprint"]
                ),
                reviewed_descriptor_set_fingerprint=(
                    review_body["reviewed_descriptor_set_fingerprint"]
                ),
                complete_review_acknowledged=True,
                all_requirements_and_candidates_acknowledged=True,
                all_linked_action_semantics_reviewed=True,
            ).model_dump(mode="json"),
        )
        assert action_decision.status_code == 201
        action_confirmation_id = action_decision.json()["proposal"]["decision_id"]

    clock[0] += timedelta(seconds=1)
    third = ensemble.run(
        provider=Provider.CLAUDE_CODE,
        session_id=session_id,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="synthetic-transcript-r8-0003",
        reuse_latest=True,
        prior_run_id=second.run.run_id,
    )
    assert third.run.requirement_action_evidence_binding is not None
    assert third.run.requirement_action_evidence_binding.evidence_source is RequirementActionEvidenceSource.REVIEWED_REQUIREMENT_ACTION
    assert third.run.requirement_action_evidence_binding.proposal_id == action_proposal_id
    assert third.run.requirement_action_evidence_binding.confirmation_id == action_confirmation_id
    metric = _metric(third.run)
    assert (metric.value_state.value, metric.numerator, metric.denominator) == (
        "known",
        expected_numerator,
        1,
    )
    assert path.read_bytes() == original_transcript_bytes


def test_malformed_transcript_cannot_establish_action_authority(
    tmp_path: Path,
) -> None:
    """Malformed transcript parsing reaches canonical unknown, not a value."""

    claude_home = tmp_path / "synthetic-claude-home"
    path = _write_malformed_transcript(claude_home)
    parsed = parse_events(path, RAW_SESSION_ID)
    assert parsed.complete is False
    assert parsed.action_descriptor_extraction_complete is False

    pseudonymizer = _pseudonymizer()
    session_id = catalog_session_id_for(pseudonymizer, RAW_SESSION_ID)
    reader = ClaudeTranscriptReader(pseudonymizer, claude_home=claude_home)
    source = ClaudeTranscriptTextAnalysisSource(pseudonymizer, locate=reader.locate)
    result = source.read(
        selection=TextAnalysisSelection(provider=Provider.CLAUDE_CODE, session_id=session_id),
        grant=TextSourceAccessGrant(
            purpose=TextAnalysisPurpose.TEXT_ANALYSIS,
            provider=Provider.CLAUDE_CODE,
            session_id=session_id,
            data_tier=DataTier.REDACTED_CONTENT,
            per_run_confirmation_active=True,
            local_only=True,
            content_persistence_allowed=False,
        ),
        task_profile=COACHING_PROFILE_V1.task_profile,
    )
    assert result.action_descriptor_extraction_complete is False

    identifiers = LocalArtifactIdFactory(pseudonymizer)
    database = Database(tmp_path / "synthetic-malformed.sqlite3")
    database.configure_local_artifact_id_factory(identifiers)
    database.initialize()
    database.grant_consent(Provider.CLAUDE_CODE, DataTier.REDACTED_CONTENT)
    report = IngestionService(database, pseudonymizer).ingest(
        ClaudeTranscriptAdapter(pseudonymizer, claude_home=claude_home)
    )
    assert report.sessions_inserted == 1
    clock = [NOW + timedelta(hours=1)]
    ensemble = SessionModelEnsembleService(
        _AccessPolicy(database, session_id),
        database.model_ensemble_repository(),
        lambda _provider: source,
        _Compatibility(),
        identifiers,
        LocalProbabilisticMetricRunner(
            executor=_execute,
            device="cpu",
            deep_enabled=False,
            clock=lambda: clock[0],
        ),
        clock=lambda: clock[0],
        typed_evidence_projector=LocalApplication(
            settings=AppSettings(home=tmp_path / "synthetic-malformed-composition"),
            database=database,
            pseudonymizer=pseudonymizer,
        ).create_typed_evidence_projector(),
        semantic_unit_reconciler=SemanticUnitReconciler(identifiers),
        requirement_plan_evidence_reader=(
            database.requirement_plan_evidence_repository()
        ),
        requirement_plan_review_contexts=InMemoryRequirementPlanReviewContextStore(
            clock=lambda: clock[0], monotonic_clock=lambda: 100.0
        ),
        requirement_action_evidence_reader=(
            database.requirement_action_evidence_repository()
        ),
        requirement_action_review_contexts=(
            InMemoryRequirementActionReviewContextStore(
                clock=lambda: clock[0],
                monotonic_clock=lambda: 100.0,
                candidate_binding_key=b"m" * 32,
            )
        ),
    )
    outcome = ensemble.run(
        provider=Provider.CLAUDE_CODE,
        session_id=session_id,
        confirmation=MODEL_ENSEMBLE_CONFIRMATION,
        idempotency_key="synthetic-malformed-action-0001",
    )
    assert outcome.run.requirement_action_evidence_binding is not None
    assert (
        outcome.run.requirement_action_evidence_binding.evidence_source
        is RequirementActionEvidenceSource.CANDIDATE_SOURCE_INCOMPLETE
    )
    metric = _metric(outcome.run)
    assert metric.value_state.value == "unknown"
