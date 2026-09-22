from __future__ import annotations
from datetime import UTC, datetime
from types import SimpleNamespace
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from prompt_enhancer.application.analysis.claim_grounding_link_review import ClaimGroundingLinkReview, ClaimGroundingLinkReviewConflictError, ClaimGroundingLinkReviewUnavailableError, ClaimObservedCheckPreview
from prompt_enhancer.application.analysis.claim_grounding_link_source import (
    ClaimGroundingLinkCandidateManifest, ClaimGroundingLinkMaterialCandidate,
    ClaimGroundingLinkObservedCheckMetadata, ClaimGroundingLinkSourceConflictError,
    ClaimGroundingLinkSourceUnavailableError,
)
from prompt_enhancer.application.analysis.claim_grounding_links import ClaimLinkCoverageDecision
from prompt_enhancer.interfaces.http.claim_grounding_link_review_routes import create_claim_grounding_link_review_router
from test_claim_grounding_link_review_adversarial import S, C, O, R, W, M

def review():
    return ClaimGroundingLinkReview(session_id=S,census_id="9"*64,candidate_id=C,source_run_id=R,source_window_fingerprint=W,census_fingerprint="3"*64,manifest_fingerprint="4"*64,observed_set_fingerprint=M,review_receipt_id="1"*64,review_fingerprint="2"*64,review_expires_at=datetime(2026,1,1,tzinfo=UTC),claim_clause=SecretStr("Synthetic claim"),observed_checks=(ClaimObservedCheckPreview(source_reference_id=O,observed_sequence=1,outcome="passed",tool_name=SecretStr("pytest"),invocation_preview=SecretStr("pytest -q"),effect_preview=SecretStr("exit 0")),))
class Service:
    def __init__(self, value=review()): self.value=value; self.calls=0
    def begin_review(self, **_): self.calls+=1; return self.value
    def candidate_manifest(self, **_): self.calls+=1; return candidate_manifest()
def client(service, confirm=lambda: None, auth=lambda: None):
    app=FastAPI(); app.include_router(create_claim_grounding_link_review_router(auth,confirm,service)); return TestClient(app)
def payload(): return {"census_id":"9"*64,"candidate_id":C,"selected_check_references":[]}

def candidate_manifest():
    return ClaimGroundingLinkCandidateManifest(
        session_id=S, census_id="9" * 64, source_run_id=R,
        source_window_fingerprint=W, census_fingerprint="3" * 64,
        manifest_fingerprint="4" * 64, observed_set_fingerprint=M,
        source_schema_version="synthetic-v1", text_adapter_version="synthetic-v1",
        observed_set_schema_version="claim-grounding-observed-set-v1",
        observed_set_policy_version="native-reviewed-claim-link-coverage-v1",
        material_candidates=(ClaimGroundingLinkMaterialCandidate(
            candidate_id=C, message_id="d" * 64, message_sequence=1, clause_index=0,
        ),),
        observed_checks=(ClaimGroundingLinkObservedCheckMetadata(
            source_reference_id=O, observed_sequence=1, provider="codex", check_kind="test",
            outcome="passed", provider_execution_status="completed", exit_code=0,
            source_completion_schema_version="observed-check-completion-v1",
            outcome_interpreter_version="pytest-exit-status-v1",
            classifier_version="local-command-rules-v1",
            normalizer_version="strict-shell-free-v2", rule_id="test.pytest",
        ),),
    )

def test_native_denial_and_auth_denial_happen_before_service():
    denied=lambda: (_ for _ in ()).throw(HTTPException(403, "denied")); svc=Service(); c=client(svc, confirm=denied)
    assert c.post(f"/v1/sessions/{S}/claim-grounding-review/links/begin",json=payload()).status_code in (401,403); assert svc.calls==0
    svc=Service(); c=client(svc, auth=denied); assert c.post(f"/v1/sessions/{S}/claim-grounding-review/links/begin",json=payload()).status_code in (401,403); assert svc.calls==0

def test_success_returns_explicit_nonmetric_preview_flags():
    svc=Service(); response=client(svc).post(f"/v1/sessions/{S}/claim-grounding-review/links/begin",json=payload()); body=response.json()
    assert response.status_code==200 and body["proposal_only"] is True and body["measured"] is False and body["metric_authority_established"] is False and body["content_persisted"] is False and body["claim_clause"] == "Synthetic claim" and body["observed_checks"][0]["tool_name"] == "pytest" and body["observed_checks"][0]["invocation_preview"] == "pytest -q" and svc.calls==1
    schema=client(Service()).app.openapi()["components"]["schemas"]["ClaimGroundingLinkReviewDto"]
    assert schema["properties"]["review_expires_at"]["format"] == "date-time"
    assert schema["properties"]["observed_checks"]["items"]["$ref"].endswith("ClaimGroundingLinkObservedCheckDto")

def test_malformed_and_oversize_body_use_private_safe_errors_without_echo():
    svc=Service(); confirmations=[]; c=client(svc, confirm=lambda: confirmations.append(True)); bad=c.post(f"/v1/sessions/{S}/claim-grounding-review/links/begin",content='{"census_id":"not-valid"}',headers={"content-type":"application/json"}); assert bad.status_code==422 and "not-valid" not in bad.text and bad.headers["cache-control"]=="no-store, private" and confirmations == [] and svc.calls == 0
    confirmations.clear(); huge='{"census_id":"'+"a"*64+'","candidate_id":"'+C+'","selected_check_references":[] ,"junk":"'+"x"*(4*1024*1024)+'"}'
    assert c.post(f"/v1/sessions/{S}/claim-grounding-review/links/begin",content=huge,headers={"content-type":"application/json"}).status_code==413 and svc.calls == 0 and confirmations == []

def test_source_failures_map_to_private_fixed_errors():
    for error, status, code in ((ClaimGroundingLinkReviewUnavailableError("x"),404,"claim_grounding_link_review_unavailable"),(ClaimGroundingLinkReviewConflictError("x"),409,"claim_grounding_link_review_conflict"),(ClaimGroundingLinkSourceUnavailableError("x"),404,"claim_grounding_link_review_unavailable"),(ClaimGroundingLinkSourceConflictError("x"),409,"claim_grounding_link_review_conflict")):
        svc=Service(); svc.value=error
        # use a service that raises, rather than returning the exception object
        class Raising(Service):
            def begin_review(self, **_): self.calls+=1; raise error
        response=client(Raising()).post(f"/v1/sessions/{S}/claim-grounding-review/links/begin",json=payload()); assert response.status_code==status and response.json()["detail"]["code"] == code and response.json()["detail"]["message"] != "x"


def test_candidate_manifest_is_read_only_private_and_never_exposes_prose_or_tool_preview():
    denied = lambda: (_ for _ in ()).throw(HTTPException(403, "native should not run"))
    svc = Service()
    response = client(svc, confirm=denied).get(
        f"/v1/sessions/{S}/claim-grounding-review/links/candidates/{'9' * 64}"
    )
    assert response.status_code == 200 and svc.calls == 1
    assert response.headers["cache-control"] == "no-store, private"
    body = response.json()
    assert body["material_candidates"][0] == {
        "candidate_id": C, "message_id": "d" * 64,
        "message_sequence": 1, "clause_index": 0,
    }
    assert body["observed_checks"][0]["outcome"] == "passed"
    serialized = response.text.casefold()
    for prohibited in ("claim_clause", "invocation", "effect_preview", "synthetic claim"):
        assert prohibited not in serialized


def test_candidate_manifest_maps_stale_and_cross_session_failures_safely():
    for error, status, code in (
        (ClaimGroundingLinkSourceConflictError("private"), 409, "claim_grounding_link_review_conflict"),
        (ClaimGroundingLinkSourceUnavailableError("private"), 404, "claim_grounding_link_review_unavailable"),
    ):
        class Raising(Service):
            def candidate_manifest(self, **_):
                self.calls += 1
                raise error
        response = client(Raising()).get(
            f"/v1/sessions/{S}/claim-grounding-review/links/candidates/{'9' * 64}"
        )
        assert response.status_code == status
        assert response.json()["detail"]["code"] == code
        assert "private" not in response.text


def test_candidate_manifest_auth_and_unexpected_failures_are_private_and_safe():
    denied = lambda: (_ for _ in ()).throw(HTTPException(403, "denied"))
    svc = Service()
    response = client(svc, auth=denied).get(
        f"/v1/sessions/{S}/claim-grounding-review/links/candidates/{'9' * 64}"
    )
    assert response.status_code in (401, 403) and svc.calls == 0

    class Unexpected(Service):
        def candidate_manifest(self, **_):
            self.calls += 1
            raise RuntimeError("synthetic database diagnostic")
    response = client(Unexpected()).get(
        f"/v1/sessions/{S}/claim-grounding-review/links/candidates/{'9' * 64}"
    )
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["detail"] == {
        "code": "claim_grounding_link_review_unavailable",
        "message": "claim-grounding link review is unavailable",
    }
    assert "synthetic database diagnostic" not in response.text
