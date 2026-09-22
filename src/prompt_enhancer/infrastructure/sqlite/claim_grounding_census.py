"""Durable, content-free storage for reviewed claim-grounding censuses."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import hmac
import sqlite3

from ...application.analysis.claim_grounding_evidence import (
    ClaimCensusCandidateManifestEntry, ClaimCensusClassification,
    ClaimCensusClassificationEntry, ClaimCensusExclusionReason,
    ClaimCensusSourceManifest, ReviewedClaimCensus,
    validate_claim_census_source_manifest, validate_reviewed_claim_census,
)
from ...application.analysis.claim_grounding_census import (
    ClaimGroundingCensusPageSnapshot, ClaimGroundingCensusRecord,
)
from ...application.analysis.claim_grounding_review import ClaimGroundingReviewConflictError
from ...database import DatabaseInvariantError
from ..identifiers import LocalArtifactIdFactory
from ._common import ConnectionScope, from_iso, require_safe_id, to_iso

_ISSUANCE_SEAL_VERSION = "claim-grounding-census-issuance-seal-v1"
_PAGE_SNAPSHOT_VERSION = "claim-grounding-census-page-snapshot-v1"
_MAX_PAGE_SIZE, _MAX_OFFSET = 200, 1_000_000


def _issuance_seal(ids: LocalArtifactIdFactory, *, census_id: str,
                   census: ReviewedClaimCensus, manifest: ClaimCensusSourceManifest,
                   idempotency_key_digest: str, command_fingerprint: str,
                   expected_publication_fingerprint: str, created_at: str) -> str:
    return ids.fingerprint(_ISSUANCE_SEAL_VERSION, (
        census_id, census.session_id, census.source_run_id,
        census.source_window_fingerprint, manifest.manifest_fingerprint,
        census.census_fingerprint, idempotency_key_digest, command_fingerprint,
        expected_publication_fingerprint, created_at, census.schema_version,
        census.policy_version, census.issuer_version,
    ))


def _snapshot_id(ids: LocalArtifactIdFactory, *, session_id: str, total: int,
                 high_water_created_at: datetime | None,
                 high_water_census_id: str | None) -> str:
    return ids.fingerprint(_PAGE_SNAPSHOT_VERSION, (
        session_id, str(total), "none" if high_water_created_at is None
        else to_iso(high_water_created_at), high_water_census_id or "none",
    ))


class SqliteClaimGroundingCensusRepository:
    def __init__(self, connection_scope: ConnectionScope,
                 ensure_initialized: Callable[[], None], *,
                 identifiers: LocalArtifactIdFactory) -> None:
        self._connection_scope = connection_scope
        self._ensure_initialized = ensure_initialized
        self._identifiers = identifiers

    def issue(self, *, census_id: str, census: ReviewedClaimCensus,
              manifest: ClaimCensusSourceManifest, idempotency_key_digest: str,
              command_fingerprint: str, expected_publication_fingerprint: str,
              created_at: datetime) -> tuple[ClaimGroundingCensusRecord, bool]:
        """Atomically issue only against the present latest sealed source.

        Idempotent recovery intentionally happens before this current-source
        fence, so a retry recovers its original historical binding unchanged.
        """
        for value in (census_id, idempotency_key_digest, command_fingerprint,
                      expected_publication_fingerprint):
            require_safe_id(value)
        validate_reviewed_claim_census(census, manifest, identifiers=self._identifiers)
        created_at_text = to_iso(created_at)
        self._ensure_initialized()
        with self._connection_scope() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """SELECT census_id,command_fingerprint,source_run_id,
                              source_window_fingerprint,manifest_fingerprint,
                              census_fingerprint,expected_publication_fingerprint
                       FROM claim_grounding_reviewed_censuses
                       WHERE session_id=? AND idempotency_key_digest=?""",
                    (census.session_id, idempotency_key_digest),
                ).fetchone()
                if existing is not None:
                    if (existing["census_id"] != census_id
                        or not hmac.compare_digest(existing["command_fingerprint"], command_fingerprint)
                        or existing["source_run_id"] != census.source_run_id
                        or existing["source_window_fingerprint"] != census.source_window_fingerprint
                        or existing["manifest_fingerprint"] != census.manifest_fingerprint
                        or existing["census_fingerprint"] != census.census_fingerprint
                        or existing["expected_publication_fingerprint"] != expected_publication_fingerprint):
                        raise ClaimGroundingReviewConflictError("claim census idempotency key conflicts")
                    record = self._required_record(connection, census_id)
                    connection.commit()
                    return record, False
                current = connection.execute(
                    """WITH latest AS (
                         SELECT run.run_id,run.input_fingerprint
                         FROM session_model_ensemble_runs run
                         JOIN session_model_ensemble_seals seal ON seal.run_id=run.run_id
                         WHERE run.session_id=?
                         ORDER BY run.completed_at DESC,run.run_id DESC LIMIT 1
                       ) SELECT latest.run_id,latest.input_fingerprint,
                                publication.projection_fingerprint
                         FROM latest
                         LEFT JOIN session_model_ensemble_metric_publication_v2_seals_r8 publication
                           ON publication.run_id=latest.run_id""",
                    (census.session_id,),
                ).fetchone()
                if (current is None or current["run_id"] != census.source_run_id
                    or current["input_fingerprint"] != census.source_window_fingerprint
                    or current["projection_fingerprint"] is None
                    or not hmac.compare_digest(current["projection_fingerprint"], expected_publication_fingerprint)):
                    raise ClaimGroundingReviewConflictError("claim census source authority changed")
                seal = _issuance_seal(
                    self._identifiers, census_id=census_id, census=census, manifest=manifest,
                    idempotency_key_digest=idempotency_key_digest,
                    command_fingerprint=command_fingerprint,
                    expected_publication_fingerprint=expected_publication_fingerprint,
                    created_at=created_at_text,
                )
                connection.execute(
                    """INSERT INTO claim_grounding_reviewed_censuses(
                         census_id,session_id,source_run_id,source_window_fingerprint,
                         manifest_fingerprint,source_schema_version,text_adapter_version,
                         clause_algorithm,text_extraction_complete,census_fingerprint,
                         expected_publication_fingerprint,idempotency_key_digest,
                         command_fingerprint,candidate_count,created_at,schema_version,
                         policy_version,issuer_version,local_only,content_persisted)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,0)""",
                    (census_id, census.session_id, census.source_run_id,
                     census.source_window_fingerprint, census.manifest_fingerprint,
                     manifest.source_schema_version, manifest.text_adapter_version,
                     manifest.clause_algorithm, 1, census.census_fingerprint,
                     expected_publication_fingerprint, idempotency_key_digest,
                     command_fingerprint, len(manifest.candidates), created_at_text,
                     census.schema_version, census.policy_version, census.issuer_version),
                )
                coordinates = {item.candidate_id: item for item in manifest.candidates}
                connection.executemany(
                    """INSERT INTO claim_grounding_reviewed_census_classifications(
                         census_id,ordinal,candidate_id,message_id,message_sequence,
                         clause_index,classification,exclusion_reason)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    ((census_id, ordinal, item.candidate_id,
                      coordinates[item.candidate_id].message_id,
                      coordinates[item.candidate_id].message_sequence,
                      coordinates[item.candidate_id].clause_index,
                      item.classification.value,
                      None if item.exclusion_reason is None else item.exclusion_reason.value)
                     for ordinal, item in enumerate(census.classifications)),
                )
                connection.execute(
                    """INSERT INTO claim_grounding_reviewed_census_seals(
                         census_id,candidate_count,manifest_fingerprint,census_fingerprint,
                         expected_publication_fingerprint,issuance_seal,sealed_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (census_id, len(manifest.candidates), census.manifest_fingerprint,
                     census.census_fingerprint, expected_publication_fingerprint,
                     seal, created_at_text),
                )
                record = self._required_record(connection, census_id)
                connection.commit()
                return record, True
            except sqlite3.IntegrityError as error:
                connection.rollback()
                raise ClaimGroundingReviewConflictError("claim census persistence conflicts") from error
            except Exception:
                connection.rollback()
                raise

    def get(self, census_id: str) -> ClaimGroundingCensusRecord | None:
        self._ensure_initialized(); require_safe_id(census_id)
        with self._connection_scope(readonly=True) as connection:
            connection.execute("BEGIN")
            try:
                record = self._get_record(connection, census_id)
                connection.commit()
                return record
            except Exception:
                connection.rollback(); raise

    def get_by_idempotency(self, *, session_id: str,
                           idempotency_key_digest: str) -> ClaimGroundingCensusRecord | None:
        self._ensure_initialized(); require_safe_id(session_id); require_safe_id(idempotency_key_digest)
        with self._connection_scope(readonly=True) as connection:
            connection.execute("BEGIN")
            try:
                row = connection.execute("SELECT census_id FROM claim_grounding_reviewed_censuses WHERE session_id=? AND idempotency_key_digest=?", (session_id, idempotency_key_digest)).fetchone()
                record = None if row is None else self._required_record(connection, row["census_id"])
                connection.commit()
                return record
            except Exception:
                connection.rollback(); raise

    def list_page(self, session_id: str, *, limit: int, offset: int,
                  snapshot: ClaimGroundingCensusPageSnapshot | None = None) -> tuple[tuple[ClaimGroundingCensusRecord, ...], ClaimGroundingCensusPageSnapshot]:
        self._ensure_initialized(); require_safe_id(session_id)
        if (not isinstance(limit, int) or isinstance(limit, bool)
            or not isinstance(offset, int) or isinstance(offset, bool)
            or not 1 <= limit <= _MAX_PAGE_SIZE or not 0 <= offset <= _MAX_OFFSET):
            raise ValueError("claim census page is outside its bound")
        with self._connection_scope(readonly=True) as connection:
            connection.execute("BEGIN")
            try:
                if snapshot is None:
                    boundary = connection.execute("SELECT created_at,census_id FROM claim_grounding_reviewed_censuses WHERE session_id=? ORDER BY created_at DESC,census_id DESC LIMIT 1", (session_id,)).fetchone()
                    total = int(connection.execute("SELECT COUNT(*) AS total FROM claim_grounding_reviewed_censuses WHERE session_id=?", (session_id,)).fetchone()["total"])
                    at = None if boundary is None else from_iso(boundary["created_at"])
                    ident = None if boundary is None else boundary["census_id"]
                    snapshot = ClaimGroundingCensusPageSnapshot(_snapshot_id(self._identifiers, session_id=session_id, total=total, high_water_created_at=at, high_water_census_id=ident), total, at, ident)
                elif not hmac.compare_digest(snapshot.snapshot_id, _snapshot_id(self._identifiers, session_id=session_id, total=snapshot.total, high_water_created_at=snapshot.high_water_created_at, high_water_census_id=snapshot.high_water_census_id)):
                    raise ClaimGroundingReviewConflictError("claim census page snapshot is invalid")
                if snapshot.total == 0:
                    if snapshot.high_water_created_at is not None or snapshot.high_water_census_id is not None:
                        raise ClaimGroundingReviewConflictError("claim census page snapshot is invalid")
                    connection.commit(); return (), snapshot
                if snapshot.high_water_created_at is None or snapshot.high_water_census_id is None:
                    raise ClaimGroundingReviewConflictError("claim census page snapshot is incomplete")
                current_total = int(connection.execute(
                    """SELECT COUNT(*) AS total FROM claim_grounding_reviewed_censuses
                       WHERE session_id=? AND (created_at<? OR (created_at=? AND census_id<=?))""",
                    (session_id, to_iso(snapshot.high_water_created_at),
                     to_iso(snapshot.high_water_created_at), snapshot.high_water_census_id),
                ).fetchone()["total"])
                if current_total != snapshot.total:
                    raise ClaimGroundingReviewConflictError("claim census page snapshot changed")
                rows = connection.execute(
                    """SELECT census_id FROM claim_grounding_reviewed_censuses
                       WHERE session_id=? AND (created_at<? OR (created_at=? AND census_id<=?))
                       ORDER BY created_at DESC,census_id DESC LIMIT ? OFFSET ?""",
                    (session_id, to_iso(snapshot.high_water_created_at), to_iso(snapshot.high_water_created_at), snapshot.high_water_census_id, limit, offset)).fetchall()
                result = tuple(self._required_record(connection, item["census_id"]) for item in rows)
                connection.commit(); return result, snapshot
            except Exception:
                connection.rollback(); raise

    def _required_record(self, connection: sqlite3.Connection, census_id: str) -> ClaimGroundingCensusRecord:
        record = self._get_record(connection, census_id)
        if record is None:
            raise DatabaseInvariantError("claim census record is missing")
        return record

    def _get_record(self, connection: sqlite3.Connection, census_id: str) -> ClaimGroundingCensusRecord | None:
        row = connection.execute(
            """SELECT census.*,seal.candidate_count AS sealed_candidate_count,
                      seal.manifest_fingerprint AS sealed_manifest_fingerprint,
                      seal.census_fingerprint AS sealed_census_fingerprint,
                      seal.expected_publication_fingerprint AS sealed_publication_fingerprint,
                      seal.issuance_seal,seal.sealed_at
               FROM claim_grounding_reviewed_censuses census LEFT JOIN claim_grounding_reviewed_census_seals seal ON seal.census_id=census.census_id WHERE census.census_id=?""", (census_id,)).fetchone()
        if row is None:
            return None
        if (row["sealed_candidate_count"] is None or int(row["candidate_count"]) != int(row["sealed_candidate_count"])
            or row["manifest_fingerprint"] != row["sealed_manifest_fingerprint"]
            or row["census_fingerprint"] != row["sealed_census_fingerprint"]
            or row["expected_publication_fingerprint"] != row["sealed_publication_fingerprint"]
            or row["created_at"] != row["sealed_at"] or int(row["text_extraction_complete"]) != 1
            or int(row["local_only"]) != 1 or int(row["content_persisted"]) != 0):
            raise DatabaseInvariantError("claim census seal is incomplete")
        created_at = from_iso(row["created_at"])
        if created_at is None:
            raise DatabaseInvariantError("claim census time is missing")
        classified = connection.execute("SELECT ordinal,candidate_id,message_id,message_sequence,clause_index,classification,exclusion_reason FROM claim_grounding_reviewed_census_classifications WHERE census_id=? ORDER BY ordinal", (census_id,)).fetchall()
        if len(classified) != int(row["candidate_count"]):
            raise DatabaseInvariantError("claim census classifications are incomplete")
        candidates = tuple(sorted((ClaimCensusCandidateManifestEntry(candidate_id=x["candidate_id"], message_id=x["message_id"], message_sequence=int(x["message_sequence"]), clause_index=int(x["clause_index"])) for x in classified), key=lambda x: (x.message_sequence, x.clause_index, x.candidate_id)))
        manifest = ClaimCensusSourceManifest(session_id=row["session_id"], source_run_id=row["source_run_id"], source_window_fingerprint=row["source_window_fingerprint"], source_schema_version=row["source_schema_version"], text_adapter_version=row["text_adapter_version"], clause_algorithm=row["clause_algorithm"], text_extraction_complete=True, candidates=candidates, candidate_count=int(row["candidate_count"]), manifest_fingerprint=row["manifest_fingerprint"], schema_version=row["schema_version"], policy_version=row["policy_version"], local_only=True, content_persisted=False)
        census = ReviewedClaimCensus(manifest_fingerprint=row["manifest_fingerprint"], session_id=row["session_id"], source_run_id=row["source_run_id"], source_window_fingerprint=row["source_window_fingerprint"], classifications=tuple(ClaimCensusClassificationEntry(candidate_id=x["candidate_id"], classification=ClaimCensusClassification(x["classification"]), exclusion_reason=None if x["exclusion_reason"] is None else ClaimCensusExclusionReason(x["exclusion_reason"])) for x in classified), complete_candidate_classification_acknowledged=True, census_fingerprint=row["census_fingerprint"], issuer_version=row["issuer_version"], schema_version=row["schema_version"], policy_version=row["policy_version"], local_only=True, content_persisted=False)
        try:
            validate_claim_census_source_manifest(manifest, identifiers=self._identifiers)
            validate_reviewed_claim_census(census, manifest, identifiers=self._identifiers)
        except ValueError as error:
            raise DatabaseInvariantError("claim census reconstruction is invalid") from error
        expected = _issuance_seal(self._identifiers, census_id=row["census_id"], census=census, manifest=manifest, idempotency_key_digest=row["idempotency_key_digest"], command_fingerprint=row["command_fingerprint"], expected_publication_fingerprint=row["expected_publication_fingerprint"], created_at=row["created_at"])
        if not hmac.compare_digest(row["issuance_seal"], expected):
            raise DatabaseInvariantError("claim census issuance seal is invalid")
        return ClaimGroundingCensusRecord(row["census_id"], census, manifest, row["idempotency_key_digest"], row["command_fingerprint"], row["expected_publication_fingerprint"], created_at)


__all__ = ("ClaimGroundingCensusPageSnapshot", "ClaimGroundingCensusRecord", "SqliteClaimGroundingCensusRepository")
