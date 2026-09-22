"""Durable, content-free claim-link proposal records; never metric authority."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from .claim_grounding_link_review import ClaimGroundingLinkReviewedDecision


class ClaimGroundingLinkPersistenceError(RuntimeError): pass
class ClaimGroundingLinkConflictError(ClaimGroundingLinkPersistenceError): pass
class ClaimGroundingLinkNotFoundError(ClaimGroundingLinkPersistenceError): pass


@dataclass(frozen=True, slots=True)
class ClaimGroundingLinkRecord:
    """One native-reviewed candidate decision with selected normalized outputs.

    This is a proposal/provenance record only.  It does not assert complete
    census coverage, a measured result, or metric authority.
    """
    link_review_id: str
    reviewed_decision: ClaimGroundingLinkReviewedDecision
    idempotency_key_digest: str
    command_fingerprint: str
    expected_publication_fingerprint: str
    selected_evidence_fingerprint: str
    issuance_seal: str
    created_at: datetime
    metadata_persisted: Literal[True] = field(default=True, init=False)
    candidate_prose_persisted: Literal[False] = field(default=False, init=False)
    proposal_only: Literal[True] = field(default=True, init=False)
    measured: Literal[False] = field(default=False, init=False)
    metric_authority_established: Literal[False] = field(default=False, init=False)


class ClaimGroundingLinkRepository(Protocol):
    def issue(self, *, link_review_id: str,
              reviewed_decision: ClaimGroundingLinkReviewedDecision,
              idempotency_key_digest: str, command_fingerprint: str,
              expected_publication_fingerprint: str,
              created_at: datetime) -> tuple[ClaimGroundingLinkRecord, bool]: ...

    def get(self, *, session_id: str,
            link_review_id: str) -> ClaimGroundingLinkRecord | None: ...

    def get_by_idempotency(self, *, session_id: str,
                           idempotency_key_digest: str) -> ClaimGroundingLinkRecord | None: ...
