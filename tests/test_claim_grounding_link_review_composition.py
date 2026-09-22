from __future__ import annotations
from fastapi.testclient import TestClient
import pytest
from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.config import AppSettings
from test_claim_grounding_link_review_api import review
from test_claim_grounding_link_review_adversarial import S, C, O
TOKEN = "synthetic-token-" + "x" * 24
def payload(): return {"census_id": "9" * 64, "candidate_id": C, "selected_check_references": []}

class Service:
    def __init__(self): self.calls=0; self.closed=0
    def begin_review(self, **_): self.calls+=1; return review()
    def close(self): self.closed+=1

def headers(client):
    auth=client.get("/auth/session").json(); return {"Origin":"http://127.0.0.1","X-Prompt-Enhancer-CSRF":auth["csrf_token"]}

def test_absent_service_keeps_route_unavailable(tmp_path):
    with TestClient(create_app(settings=AppSettings(home=tmp_path), api_token=TOKEN), base_url="http://127.0.0.1") as client:
        assert client.post(f"/v1/sessions/{S}/claim-grounding-review/links/begin", json=payload()).status_code == 404

def test_present_service_mounts_native_gated_route_and_closes_once(tmp_path):
    service=Service(); app=create_app(settings=AppSettings(home=tmp_path), api_token=TOKEN, claim_grounding_link_review_service=service, user_presence_confirmation=lambda _request, _body: None)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response=client.post(f"/v1/sessions/{S}/claim-grounding-review/links/begin", headers=headers(client), json=payload())
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store, private" and response.json()["proposal_only"] is True
        assert service.calls == 1
    assert service.closed == 1

def test_cleanup_failure_is_reported_as_typed_runtime_component(tmp_path):
    class Failing(Service):
        def close(self): self.closed += 1; raise RuntimeError("synthetic cleanup failure")
    service=Failing(); app=create_app(settings=AppSettings(home=tmp_path), api_token=TOKEN, claim_grounding_link_review_service=service)
    with pytest.raises(RuntimeError, match="runtime_component_shutdown_failed"):
        with TestClient(app, base_url="http://127.0.0.1"):
            pass
    assert service.closed == 1 and "claim_grounding_link_review_service" in {item.value for item in app.state.runtime_lifecycle.shutdown_failures}
