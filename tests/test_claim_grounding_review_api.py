from __future__ import annotations

from fastapi.testclient import TestClient
from test_claim_grounding_review import SESSION, RUN, WINDOW, _Ids, _context

from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.application.analysis.claim_grounding_evidence import (
    derive_claim_census_source_manifest,
)
from prompt_enhancer.application.analysis.claim_grounding_review import (
    ClaimGroundingReviewService,
)
from prompt_enhancer.config import AppSettings


TOKEN = "example_claim_grounding_api_token_do_not_use_123456789"
SESSION = "1" * 64


class _NeverCalled:
    def __init__(self) -> None: self.closed = False
    def begin_review(self, **_values):  # type: ignore[no-untyped-def]
        raise AssertionError("native gate must run before review materialization")

    def consume_review(self, **_values):  # type: ignore[no-untyped-def]
        raise AssertionError("native gate must run before receipt consumption")

    def close(self) -> None:
        self.closed = True


class _ProjectedSource:
    def current_source_for_review(self, *, session_id: str, expected_source_run_id: str, expected_source_window_fingerprint: str):  # type: ignore[no-untyped-def]
        assert (session_id, expected_source_run_id, expected_source_window_fingerprint) == (SESSION, RUN, WINDOW)
        return derive_claim_census_source_manifest(_context(), source_run_id=RUN, identifiers=_Ids())


def _review_service() -> ClaimGroundingReviewService:
    return ClaimGroundingReviewService(_ProjectedSource(), _Ids())


def test_native_gate_precedes_claim_review_source_or_receipt_access(tmp_path) -> None:
    app = create_app(
        settings=AppSettings(home=tmp_path), api_token=TOKEN,
        claim_grounding_review_service=_NeverCalled(),
        user_presence_confirmation=lambda _request, _body: None,
    )
    headers = {API_TOKEN_HEADER: TOKEN, "Content-Type": "application/json"}
    with TestClient(app, base_url="http://127.0.0.1") as client:
        begin = client.post(
            f"/v1/sessions/{SESSION}/claim-grounding-review/begin",
            headers=headers,
            json={"expected_source_run_id": "2" * 64, "expected_source_window_fingerprint": "3" * 64},
        )
        consume = client.post(
            f"/v1/sessions/{SESSION}/claim-grounding-review/consume",
            headers=headers,
            json={},
        )
    assert begin.status_code == 403
    assert consume.status_code == 403


def test_native_browser_happy_path_consumes_typed_classifications_once(tmp_path) -> None:
    app = create_app(
        settings=AppSettings(home=tmp_path), claim_grounding_review_service=_review_service(),
        user_presence_confirmation=lambda _request, _body: None,
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        browser = client.get("/auth/session")
        headers = {"Origin": "http://127.0.0.1", "X-Prompt-Enhancer-CSRF": browser.json()["csrf_token"]}
        begin = client.post(
            f"/v1/sessions/{SESSION}/claim-grounding-review/begin", headers=headers,
            json={"expected_source_run_id": RUN, "expected_source_window_fingerprint": WINDOW},
        )
        assert begin.status_code == 200
        assert begin.headers["cache-control"] == "no-store, private"
        opened = begin.json()
        assert opened["candidates"] and opened["content_persisted"] is False
        consume_payload = {
            "review_receipt_id": opened["review_receipt_id"],
            "review_fingerprint": opened["review_fingerprint"],
            "manifest_fingerprint": opened["manifest"]["manifest_fingerprint"],
            "classifications": [
                {"candidate_id": item["candidate_id"], "classification": "material_claim"}
                for item in opened["candidates"]
            ],
        }
        consumed = client.post(f"/v1/sessions/{SESSION}/claim-grounding-review/consume", headers=headers, json=consume_payload)
        assert consumed.status_code == 200
        assert consumed.json()["proposal_only"] is True
        assert consumed.json()["measured"] is False
        replay = client.post(f"/v1/sessions/{SESSION}/claim-grounding-review/consume", headers=headers, json=consume_payload)
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "claim_grounding_review_conflict"


def test_oversize_json_is_rejected_before_native_presence_or_source(tmp_path) -> None:
    calls: list[bytes] = []
    app = create_app(
        settings=AppSettings(home=tmp_path), claim_grounding_review_service=_NeverCalled(),
        user_presence_confirmation=lambda _request, body: calls.append(body),
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        browser = client.get("/auth/session")
        response = client.post(
            f"/v1/sessions/{SESSION}/claim-grounding-review/begin",
            headers={
                "Origin": "http://127.0.0.1",
                "X-Prompt-Enhancer-CSRF": browser.json()["csrf_token"],
                "Content-Type": "application/json",
            },
            content=b"{" + b"x" * (4 * 1_048_576),
        )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "claim_grounding_review_too_large"
    assert calls == []


def test_media_and_malformed_json_return_closed_errors_without_echo(tmp_path) -> None:
    calls: list[bytes] = []
    app = create_app(settings=AppSettings(home=tmp_path), claim_grounding_review_service=_NeverCalled(), user_presence_confirmation=lambda _request, body: calls.append(body))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        browser = client.get("/auth/session")
        headers = {"Origin": "http://127.0.0.1", "X-Prompt-Enhancer-CSRF": browser.json()["csrf_token"]}
        media = client.post(f"/v1/sessions/{SESSION}/claim-grounding-review/begin", headers={**headers, "Content-Type": "text/plain"}, content=b"secret-body")
        malformed = client.post(f"/v1/sessions/{SESSION}/claim-grounding-review/begin", headers={**headers, "Content-Type": "application/json"}, content=b'{"broken"')
    assert media.status_code == 415
    assert media.json()["detail"]["code"] == "claim_grounding_review_media_type_required"
    assert malformed.status_code == 422
    assert malformed.json()["detail"] == {"code": "claim_grounding_review_invalid", "message": "claim-grounding review is invalid"}
    assert "secret-body" not in media.text and "broken" not in malformed.text
    assert calls == [b'{"broken"']


def test_missing_csrf_blocks_before_claim_source(tmp_path) -> None:
    app = create_app(settings=AppSettings(home=tmp_path), claim_grounding_review_service=_NeverCalled(), user_presence_confirmation=lambda _request, _body: None)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.get("/auth/session")
        response = client.post(
            f"/v1/sessions/{SESSION}/claim-grounding-review/begin",
            headers={"Origin": "http://127.0.0.1", "Content-Type": "application/json"},
            json={"expected_source_run_id": RUN, "expected_source_window_fingerprint": WINDOW},
        )
    assert response.status_code == 403


def test_openapi_declares_bounded_manual_json_request_shapes(tmp_path) -> None:
    app = create_app(
        settings=AppSettings(home=tmp_path), api_token=TOKEN,
        claim_grounding_review_service=_NeverCalled(),
    )
    paths = app.openapi()["paths"]
    begin = paths["/v1/sessions/{session_id}/claim-grounding-review/begin"]["post"]
    consume = paths["/v1/sessions/{session_id}/claim-grounding-review/consume"]["post"]
    assert begin["requestBody"]["required"] is True
    assert set(begin["requestBody"]["content"]) == {"application/json"}
    assert consume["requestBody"]["content"]["application/json"]["schema"]["properties"]["classifications"]


def test_application_lifecycle_closes_ephemeral_review_service(tmp_path) -> None:
    service = _NeverCalled()
    app = create_app(settings=AppSettings(home=tmp_path), api_token=TOKEN, claim_grounding_review_service=service)
    with TestClient(app, base_url="http://127.0.0.1"):
        assert service.closed is False
    assert service.closed is True
