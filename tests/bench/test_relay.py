import httpx
import pytest
from fastapi.testclient import TestClient

from enhancement_bench.relay import create_app, gateway_url


def test_gateway_bridge_streams_only_to_configured_endpoint_with_callers_key():
    received = []

    def upstream(request):
        received.append(request)
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"},
                              content=b'data: {"example":"fictional"}\n\ndata: [DONE]\n\n')

    app = create_app("https://gateway.example.invalid/v1", transport=httpx.MockTransport(upstream))
    with TestClient(app) as client:
        response = client.post("/v1/responses", json={"model": "example-model", "input": "Fictional widget"},
            headers={"Authorization": "Bearer example-restricted-token", "Host": "untrusted.example.invalid",
                     "X-Example-Secret": "example-unrelated-token"})
    assert response.status_code == 200 and response.text.endswith("[DONE]\n\n")
    assert response.headers["cache-control"] == "no-store"
    request = received[0]
    assert str(request.url) == "https://gateway.example.invalid/v1/responses"
    assert request.headers["host"] == "gateway.example.invalid"
    assert request.headers["authorization"] == "Bearer example-restricted-token"
    assert "X-Example-Secret" not in request.headers


@pytest.mark.parametrize("path,method,headers,body,status", [
    ("/v1/responses", "POST", {}, {}, 401),
    ("/v1/files", "POST", {"Authorization": "Bearer example-token"}, {}, 403),
    ("/v1/responses?url=https://example.com", "POST", {"Authorization": "Bearer example-token"}, {}, 403),
    ("/v1/responses", "DELETE", {"Authorization": "Bearer example-token"}, {}, 403),
])
def test_relay_rejects_unapproved_routes_without_egress(path, method, headers, body, status):
    received = []
    app = create_app("https://gateway.example.invalid/v1",
                     transport=httpx.MockTransport(lambda request: received.append(request)))
    with TestClient(app) as client:
        assert client.request(method, path, json=body, headers=headers).status_code == status
    assert not received


def test_relay_bounds_input_and_sanitizes_upstream_errors():
    received = []

    def upstream(request):
        received.append(request)
        return httpx.Response(302, headers={"Location": "https://example.invalid/unapproved"},
                              content=b"example-private-upstream-diagnostic")

    app = create_app("https://gateway.example.invalid/v1", transport=httpx.MockTransport(upstream))
    headers = {"Authorization": "Bearer example-token", "Content-Type": "application/json"}
    with TestClient(app) as client:
        assert client.post("/v1/responses", content=b"x" * 1_000_001, headers=headers).status_code == 413
        assert not received
        response = client.post("/v1/responses", json={}, headers=headers)
        assert response.status_code == 502 and "example-private-upstream-diagnostic" not in response.text
    assert len(received) == 1


@pytest.mark.parametrize("endpoint", ["http://gateway.example.invalid/v1", "https://gateway.example.invalid",
    "https://example-token@gateway.example.invalid/v1", "https://gateway.example.invalid/v1?token=example"])
def test_gateway_binding_requires_https_v1_without_embedded_credentials(endpoint):
    with pytest.raises(ValueError):
        gateway_url(endpoint)
