"""SQLite persistence for immutable, content-free reviewed claim links."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import hmac
import sqlite3

from ...application.analysis.claim_grounding_evidence import ClaimCensusClassification
from ...application.analysis.claim_grounding_link_persistence import (
    ClaimGroundingLinkConflictError, ClaimGroundingLinkRecord,
)
from ...application.analysis.claim_grounding_link_review import (
    ClaimGroundingLinkObservedCompletionSnapshot,
    ClaimGroundingLinkReviewedDecision,
)
from ...application.analysis.claim_grounding_links import ClaimLinkCoverageDecision
from ...database import DatabaseInvariantError
from ..identifiers import LocalArtifactIdFactory
from ._common import ConnectionScope, from_iso, require_safe_id, require_utc, to_iso
from .claim_grounding_census import SqliteClaimGroundingCensusRepository

_SEAL_VERSION = "claim-grounding-link-issuance-seal-v1"
_EVIDENCE_VERSION = "claim-grounding-link-selected-evidence-v1"
_DECISION_SCHEMA = "claim-grounding-link-reviewed-decision-v1"
_DECISION_POLICY = "native-reviewed-claim-link-coverage-v1"
_MAX_SELECTED = 128
_PROVIDERS = frozenset(("codex", "claude_code", "synthetic"))
_RULES = frozenset(("test.pytest", "test.py_test"))


def _completion_parts(item: ClaimGroundingLinkObservedCompletionSnapshot) -> tuple[str, ...]:
    return (item.source_reference_id, str(item.observed_sequence), item.provider,
            item.check_kind, item.outcome, item.provider_execution_status,
            str(item.exit_code), item.source_completion_schema_version,
            item.outcome_interpreter_version, item.classifier_version,
            item.normalizer_version, item.rule_id, "1", "0")


def _selected_evidence_fingerprint(ids: LocalArtifactIdFactory, *,
                                   decision: ClaimGroundingLinkReviewedDecision) -> str:
    return ids.fingerprint(_EVIDENCE_VERSION, (
        decision.session_id, decision.census_id, decision.candidate_id,
        decision.source_run_id, decision.source_window_fingerprint,
        decision.census_fingerprint, decision.manifest_fingerprint,
        decision.observed_set_fingerprint, decision.decision.value,
        *decision.selected_check_references,
        *(part for item in decision.selected_observed_completions
          for part in _completion_parts(item)),
    ))


def _issuance_seal(ids: LocalArtifactIdFactory, *, link_review_id: str,
                   decision: ClaimGroundingLinkReviewedDecision,
                   idempotency_key_digest: str, command_fingerprint: str,
                   expected_publication_fingerprint: str,
                   selected_evidence_fingerprint: str, created_at: str) -> str:
    return ids.fingerprint(_SEAL_VERSION, (
        link_review_id, decision.session_id, decision.census_id,
        decision.candidate_id, decision.source_run_id,
        decision.source_window_fingerprint, decision.census_fingerprint,
        decision.manifest_fingerprint, expected_publication_fingerprint,
        decision.observed_set_fingerprint, selected_evidence_fingerprint,
        decision.review_receipt_id, decision.review_fingerprint,
        decision.decision.value, *decision.selected_check_references,
        idempotency_key_digest, command_fingerprint, created_at,
        decision.schema_version, decision.policy_version, "1", "0", "1", "0", "0",
        *(part for item in decision.selected_observed_completions
          for part in _completion_parts(item)),
    ))


def _checked_decision(value: ClaimGroundingLinkReviewedDecision) -> ClaimGroundingLinkReviewedDecision:
    """Clone primitive fields so frozen/dataclass construction cannot bypass bounds."""
    if not isinstance(value, ClaimGroundingLinkReviewedDecision):
        raise ValueError("claim link decision is invalid")
    for identity in (value.session_id, value.census_id, value.candidate_id,
                     value.source_run_id, value.source_window_fingerprint,
                     value.census_fingerprint, value.manifest_fingerprint,
                     value.observed_set_fingerprint, value.review_receipt_id,
                     value.review_fingerprint):
        require_safe_id(identity)
    try:
        decision_kind = ClaimLinkCoverageDecision(value.decision)
    except (TypeError, ValueError) as error:
        raise ValueError("claim link decision is invalid") from error
    refs = tuple(value.selected_check_references)
    if len(refs) > _MAX_SELECTED or tuple(sorted(refs)) != refs or len(set(refs)) != len(refs):
        raise ValueError("claim link references are invalid")
    for reference in refs: require_safe_id(reference)
    if (decision_kind is ClaimLinkCoverageDecision.LINKED_OBSERVED_CHECKS) != bool(refs):
        raise ValueError("claim link decision is incomplete")
    completions: list[ClaimGroundingLinkObservedCompletionSnapshot] = []
    if len(value.selected_observed_completions) != len(refs):
        raise ValueError("claim link provenance is incomplete")
    for completion in value.selected_observed_completions:
        if not isinstance(completion, ClaimGroundingLinkObservedCompletionSnapshot):
            raise ValueError("claim link provenance is invalid")
        require_safe_id(completion.source_reference_id)
        if (isinstance(completion.observed_sequence, bool)
            or not isinstance(completion.observed_sequence, int)
            or not 0 <= completion.observed_sequence <= 4_000_000_000
            or completion.provider not in _PROVIDERS or completion.check_kind != "test"
            or completion.outcome not in ("passed", "check_failed")
            or completion.provider_execution_status != "completed"
            or isinstance(completion.exit_code, bool) or not isinstance(completion.exit_code, int)
            or completion.exit_code not in (0, 1)
            or ((completion.outcome == "passed") != (completion.exit_code == 0))
            or completion.source_completion_schema_version != "observed-check-completion-v1"
            or completion.outcome_interpreter_version != "pytest-exit-status-v1"
            or completion.classifier_version != "local-command-rules-v1"
            or completion.normalizer_version != "strict-shell-free-v2"
            or completion.rule_id not in _RULES
            or completion.local_only is not True
            or completion.content_persistence_allowed is not False):
            raise ValueError("claim link provenance is invalid")
        completions.append(ClaimGroundingLinkObservedCompletionSnapshot(
            source_reference_id=completion.source_reference_id,
            observed_sequence=completion.observed_sequence, provider=completion.provider,
            check_kind=completion.check_kind, outcome=completion.outcome,
            provider_execution_status=completion.provider_execution_status,
            exit_code=completion.exit_code,
            source_completion_schema_version=completion.source_completion_schema_version,
            outcome_interpreter_version=completion.outcome_interpreter_version,
            classifier_version=completion.classifier_version,
            normalizer_version=completion.normalizer_version, rule_id=completion.rule_id,
        ))
    if tuple(item.source_reference_id for item in completions) != refs:
        raise ValueError("claim link provenance does not match selected references")
    if (value.coverage_review_acknowledged is not True or value.schema_version != _DECISION_SCHEMA
        or value.policy_version != _DECISION_POLICY or value.proposal_only is not True
        or value.measured is not False or value.metric_authority_established is not False
        or value.content_persisted is not False):
        raise ValueError("claim link decision flags are invalid")
    return ClaimGroundingLinkReviewedDecision(
        session_id=value.session_id, census_id=value.census_id, candidate_id=value.candidate_id,
        source_run_id=value.source_run_id, source_window_fingerprint=value.source_window_fingerprint,
        census_fingerprint=value.census_fingerprint, manifest_fingerprint=value.manifest_fingerprint,
        observed_set_fingerprint=value.observed_set_fingerprint,
        review_receipt_id=value.review_receipt_id, review_fingerprint=value.review_fingerprint,
        decision=decision_kind, selected_check_references=refs,
        selected_observed_completions=tuple(completions),
    )


class SqliteClaimGroundingLinkRepository:
    def __init__(self, connection_scope: ConnectionScope,
                 ensure_initialized: Callable[[], None], *,
                 identifiers: LocalArtifactIdFactory) -> None:
        self._connection_scope = connection_scope
        self._ensure_initialized = ensure_initialized
        self._identifiers = identifiers

    def issue(self, *, link_review_id: str, reviewed_decision: ClaimGroundingLinkReviewedDecision,
              idempotency_key_digest: str, command_fingerprint: str,
              expected_publication_fingerprint: str,
              created_at: datetime) -> tuple[ClaimGroundingLinkRecord, bool]:
        for value in (link_review_id, idempotency_key_digest, command_fingerprint,
                      expected_publication_fingerprint): require_safe_id(value)
        checked = _checked_decision(reviewed_decision)
        created_at_text = to_iso(require_utc(created_at))
        self._ensure_initialized()
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT link_review_id FROM claim_grounding_link_reviews WHERE session_id=? AND idempotency_key_digest=?",
                    (checked.session_id, idempotency_key_digest),
                ).fetchone()
                if existing is not None:
                    record = self._required_record(connection, checked.session_id, existing["link_review_id"])
                    if (record.link_review_id != link_review_id or record.reviewed_decision != checked
                        or not hmac.compare_digest(record.command_fingerprint, command_fingerprint)
                        or not hmac.compare_digest(record.expected_publication_fingerprint, expected_publication_fingerprint)):
                        raise ClaimGroundingLinkConflictError("claim link idempotency key conflicts")
                    connection.commit(); return record, False
                self._validate_current_source(connection, checked, expected_publication_fingerprint)
                selected_fp = _selected_evidence_fingerprint(self._identifiers, decision=checked)
                seal = _issuance_seal(self._identifiers, link_review_id=link_review_id, decision=checked,
                    idempotency_key_digest=idempotency_key_digest, command_fingerprint=command_fingerprint,
                    expected_publication_fingerprint=expected_publication_fingerprint,
                    selected_evidence_fingerprint=selected_fp, created_at=created_at_text)
                connection.execute(
                    """INSERT INTO claim_grounding_link_reviews(
                         link_review_id,session_id,census_id,candidate_id,source_run_id,
                         source_window_fingerprint,census_fingerprint,manifest_fingerprint,
                         expected_publication_fingerprint,observed_set_fingerprint,
                         selected_evidence_fingerprint,review_receipt_id,review_fingerprint,
                         decision,selected_count,idempotency_key_digest,command_fingerprint,created_at,
                         schema_version,policy_version,metadata_persisted,candidate_prose_persisted,
                         proposal_only,measured,metric_authority_established)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0,1,0,0)""",
                    (link_review_id, checked.session_id, checked.census_id, checked.candidate_id,
                     checked.source_run_id, checked.source_window_fingerprint,
                     checked.census_fingerprint, checked.manifest_fingerprint,
                     expected_publication_fingerprint, checked.observed_set_fingerprint,
                     selected_fp, checked.review_receipt_id, checked.review_fingerprint,
                     checked.decision.value, len(checked.selected_check_references),
                     idempotency_key_digest, command_fingerprint, created_at_text,
                     checked.schema_version, checked.policy_version),
                )
                connection.executemany(
                    """INSERT INTO claim_grounding_link_review_selected_references(
                         link_review_id,ordinal,source_reference_id,observed_sequence,provider,
                         check_kind,observed_outcome,provider_execution_status,exit_code,
                         source_completion_schema_version,outcome_interpreter_version,
                         classifier_version,normalizer_version,rule_id,local_only,
                         content_persistence_allowed)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    ((link_review_id, ordinal, item.source_reference_id, item.observed_sequence,
                      item.provider, item.check_kind, item.outcome, item.provider_execution_status,
                      item.exit_code, item.source_completion_schema_version,
                      item.outcome_interpreter_version, item.classifier_version,
                      item.normalizer_version, item.rule_id, 1, 0)
                     for ordinal, item in enumerate(checked.selected_observed_completions)),
                )
                connection.execute(
                    """INSERT INTO claim_grounding_link_review_seals(
                         link_review_id,selected_count,census_id,candidate_id,census_fingerprint,
                         manifest_fingerprint,expected_publication_fingerprint,observed_set_fingerprint,
                         selected_evidence_fingerprint,issuance_seal,sealed_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (link_review_id, len(checked.selected_check_references), checked.census_id,
                     checked.candidate_id, checked.census_fingerprint, checked.manifest_fingerprint,
                     expected_publication_fingerprint, checked.observed_set_fingerprint,
                     selected_fp, seal, created_at_text),
                )
                record = self._required_record(connection, checked.session_id, link_review_id)
                connection.commit(); return record, True
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise ClaimGroundingLinkConflictError("claim link persistence conflicts") from error
            except Exception:
                connection.rollback(); raise

    def get(self, *, session_id: str, link_review_id: str) -> ClaimGroundingLinkRecord | None:
        require_safe_id(session_id); require_safe_id(link_review_id); self._ensure_initialized()
        with self._connection_scope(readonly=True) as connection:
            connection.execute("BEGIN")
            try:
                result = self._get_record(connection, session_id, link_review_id)
                connection.commit(); return result
            except Exception:
                connection.rollback(); raise

    def get_by_idempotency(self, *, session_id: str, idempotency_key_digest: str) -> ClaimGroundingLinkRecord | None:
        require_safe_id(session_id); require_safe_id(idempotency_key_digest); self._ensure_initialized()
        with self._connection_scope(readonly=True) as connection:
            connection.execute("BEGIN")
            try:
                row = connection.execute("SELECT link_review_id FROM claim_grounding_link_reviews WHERE session_id=? AND idempotency_key_digest=?", (session_id, idempotency_key_digest)).fetchone()
                result = None if row is None else self._required_record(connection, session_id, row["link_review_id"])
                connection.commit(); return result
            except Exception:
                connection.rollback(); raise

    def _validate_current_source(self, connection: sqlite3.Connection,
                                 decision: ClaimGroundingLinkReviewedDecision,
                                 expected_publication_fingerprint: str) -> None:
        parent = self._parent_record(connection, decision)
        if (parent.census.session_id != decision.session_id
            or parent.census.source_run_id != decision.source_run_id
            or parent.census.source_window_fingerprint != decision.source_window_fingerprint
            or parent.census.census_fingerprint != decision.census_fingerprint
            or parent.manifest.manifest_fingerprint != decision.manifest_fingerprint
            or parent.expected_publication_fingerprint != expected_publication_fingerprint
            or not any(item.candidate_id == decision.candidate_id and item.classification is ClaimCensusClassification.MATERIAL_CLAIM for item in parent.census.classifications)):
            raise ClaimGroundingLinkConflictError("claim link parent changed")
        row = connection.execute(
            """WITH latest AS (
                 SELECT run.run_id,run.input_fingerprint,run.provider FROM session_model_ensemble_runs run
                 JOIN session_model_ensemble_seals seal ON seal.run_id=run.run_id
                 WHERE run.session_id=? ORDER BY run.completed_at DESC,run.run_id DESC LIMIT 1)
               SELECT latest.run_id,latest.input_fingerprint,latest.provider,publication.projection_fingerprint
               FROM latest LEFT JOIN session_model_ensemble_metric_publication_v2_seals_r8 publication
                 ON publication.run_id=latest.run_id""", (decision.session_id,)).fetchone()
        if (row is None or row["run_id"] != decision.source_run_id
            or row["input_fingerprint"] != decision.source_window_fingerprint
            or row["projection_fingerprint"] is None
            or not hmac.compare_digest(row["projection_fingerprint"], expected_publication_fingerprint)):
            raise ClaimGroundingLinkConflictError("claim link source authority changed")
        if any(item.provider != row["provider"] for item in decision.selected_observed_completions):
            raise ClaimGroundingLinkConflictError("claim link provenance provider changed")

    def _parent_record(self, connection: sqlite3.Connection,
                       decision: ClaimGroundingLinkReviewedDecision):
        census = SqliteClaimGroundingCensusRepository(
            self._connection_scope, self._ensure_initialized, identifiers=self._identifiers
        )._required_record(connection, decision.census_id)
        return census

    def _required_record(self, connection: sqlite3.Connection, session_id: str,
                         link_review_id: str) -> ClaimGroundingLinkRecord:
        record = self._get_record(connection, session_id, link_review_id)
        if record is None: raise DatabaseInvariantError("claim link record is missing")
        return record

    def _get_record(self, connection: sqlite3.Connection, session_id: str,
                    link_review_id: str) -> ClaimGroundingLinkRecord | None:
        row = connection.execute(
            """SELECT h.*,s.selected_count AS sealed_selected_count,s.census_id AS sealed_census_id,
                      s.candidate_id AS sealed_candidate_id,s.census_fingerprint AS sealed_census_fingerprint,
                      s.manifest_fingerprint AS sealed_manifest_fingerprint,
                      s.expected_publication_fingerprint AS sealed_publication_fingerprint,
                      s.observed_set_fingerprint AS sealed_observed_set_fingerprint,
                      s.selected_evidence_fingerprint AS sealed_evidence_fingerprint,
                      s.issuance_seal,s.sealed_at
               FROM claim_grounding_link_reviews h LEFT JOIN claim_grounding_link_review_seals s
                 ON s.link_review_id=h.link_review_id
               WHERE h.session_id=? AND h.link_review_id=?""", (session_id, link_review_id)).fetchone()
        if row is None: return None
        if (row["sealed_selected_count"] is None or int(row["selected_count"]) != int(row["sealed_selected_count"])
            or row["census_id"] != row["sealed_census_id"] or row["candidate_id"] != row["sealed_candidate_id"]
            or row["census_fingerprint"] != row["sealed_census_fingerprint"]
            or row["manifest_fingerprint"] != row["sealed_manifest_fingerprint"]
            or row["expected_publication_fingerprint"] != row["sealed_publication_fingerprint"]
            or row["observed_set_fingerprint"] != row["sealed_observed_set_fingerprint"]
            or row["selected_evidence_fingerprint"] != row["sealed_evidence_fingerprint"]
            or row["created_at"] != row["sealed_at"]
            or int(row["metadata_persisted"]) != 1 or int(row["candidate_prose_persisted"]) != 0
            or int(row["proposal_only"]) != 1 or int(row["measured"]) != 0
            or int(row["metric_authority_established"]) != 0
            or row["schema_version"] != _DECISION_SCHEMA
            or row["policy_version"] != _DECISION_POLICY):
            raise DatabaseInvariantError("claim link seal is incomplete")
        refs = connection.execute(
            "SELECT * FROM claim_grounding_link_review_selected_references WHERE link_review_id=? ORDER BY ordinal",
            (link_review_id,)).fetchall()
        if (len(refs) != int(row["selected_count"])
            or [int(item["ordinal"]) for item in refs] != list(range(len(refs)))):
            raise DatabaseInvariantError("claim link provenance is incomplete")
        if any(int(item["local_only"]) != 1
               or int(item["content_persistence_allowed"]) != 0
               or item["source_completion_schema_version"] != "observed-check-completion-v1"
               or item["outcome_interpreter_version"] != "pytest-exit-status-v1"
               or item["classifier_version"] != "local-command-rules-v1"
               or item["normalizer_version"] != "strict-shell-free-v2"
               for item in refs):
            raise DatabaseInvariantError("claim link provenance flags are invalid")
        try:
            decision = ClaimGroundingLinkReviewedDecision(
                session_id=row["session_id"], census_id=row["census_id"], candidate_id=row["candidate_id"],
                source_run_id=row["source_run_id"], source_window_fingerprint=row["source_window_fingerprint"],
                census_fingerprint=row["census_fingerprint"], manifest_fingerprint=row["manifest_fingerprint"],
                observed_set_fingerprint=row["observed_set_fingerprint"], review_receipt_id=row["review_receipt_id"],
                review_fingerprint=row["review_fingerprint"], decision=ClaimLinkCoverageDecision(row["decision"]),
                selected_check_references=tuple(item["source_reference_id"] for item in refs),
                selected_observed_completions=tuple(ClaimGroundingLinkObservedCompletionSnapshot(
                    source_reference_id=item["source_reference_id"], observed_sequence=int(item["observed_sequence"]),
                    provider=item["provider"], check_kind=item["check_kind"], outcome=item["observed_outcome"],
                    provider_execution_status=item["provider_execution_status"], exit_code=int(item["exit_code"]),
                    source_completion_schema_version=item["source_completion_schema_version"],
                    outcome_interpreter_version=item["outcome_interpreter_version"], classifier_version=item["classifier_version"],
                    normalizer_version=item["normalizer_version"], rule_id=item["rule_id"],
                ) for item in refs),
            )
            decision = _checked_decision(decision)
        except (TypeError, ValueError) as error:
            raise DatabaseInvariantError("claim link reconstruction is invalid") from error
        parent = self._parent_record(connection, decision)
        if (parent.census.session_id != decision.session_id or parent.census.source_run_id != decision.source_run_id
            or parent.census.source_window_fingerprint != decision.source_window_fingerprint
            or parent.census.census_fingerprint != decision.census_fingerprint
            or parent.manifest.manifest_fingerprint != decision.manifest_fingerprint
            or parent.expected_publication_fingerprint != row["expected_publication_fingerprint"]
            or not any(item.candidate_id == decision.candidate_id and item.classification is ClaimCensusClassification.MATERIAL_CLAIM for item in parent.census.classifications)):
            raise DatabaseInvariantError("claim link parent binding is invalid")
        provider = connection.execute(
            "SELECT provider FROM session_model_ensemble_runs WHERE run_id=? AND session_id=?",
            (decision.source_run_id, decision.session_id),
        ).fetchone()
        if provider is None or any(item.provider != provider["provider"] for item in decision.selected_observed_completions):
            raise DatabaseInvariantError("claim link provenance provider is invalid")
        evidence = _selected_evidence_fingerprint(self._identifiers, decision=decision)
        if not hmac.compare_digest(row["selected_evidence_fingerprint"], evidence):
            raise DatabaseInvariantError("claim link evidence seal is invalid")
        expected = _issuance_seal(self._identifiers, link_review_id=link_review_id, decision=decision,
            idempotency_key_digest=row["idempotency_key_digest"], command_fingerprint=row["command_fingerprint"],
            expected_publication_fingerprint=row["expected_publication_fingerprint"],
            selected_evidence_fingerprint=evidence, created_at=row["created_at"])
        if not hmac.compare_digest(row["issuance_seal"], expected):
            raise DatabaseInvariantError("claim link issuance seal is invalid")
        created = from_iso(row["created_at"])
        if created is None: raise DatabaseInvariantError("claim link time is missing")
        return ClaimGroundingLinkRecord(link_review_id, decision, row["idempotency_key_digest"],
            row["command_fingerprint"], row["expected_publication_fingerprint"], evidence,
            row["issuance_seal"], created)
