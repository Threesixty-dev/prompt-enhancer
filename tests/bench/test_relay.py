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
    assert request.headers["User-Agent"] == "prompt-enhancer-bench/1.0"
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


def test_access_service_credentials_are_fixed_and_never_follow_redirects():
    received = []
    def upstream(request):
        received.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example.invalid"})
    app = create_app("https://gateway.example.invalid/v1", transport=httpx.MockTransport(upstream),
        access_client_id="example-access-id", access_client_secret="example-access-secret")
    with TestClient(app) as client:
        response = client.post("/v1/responses", json={}, headers={
            "Authorization": "Bearer example-model-key",
            "CF-Access-Client-Id": "example-untrusted-id",
            "CF-Access-Client-Secret": "example-untrusted-secret"})
    assert response.status_code == 502 and len(received) == 1
    assert received[0].headers["CF-Access-Client-Id"] == "example-access-id"
    assert received[0].headers["CF-Access-Client-Secret"] == "example-access-secret"
    assert received[0].headers["Authorization"] == "Bearer example-model-key"
    assert "example-access" not in response.text


@pytest.mark.parametrize("client_id,secret", [
    ("example-id", None), (None, "example-secret"), ("", "example-secret"),
    ("example-id", "example\r\nInjected: value"), ("example-id", "x" * 4097),
], ids=["missing-secret", "missing-id", "empty-id", "header-injection", "oversized"])
def test_access_configuration_rejects_partial_or_unsafe_credentials(client_id, secret):
    with pytest.raises(ValueError, match="gateway_access_credential_invalid"):
        create_app("https://gateway.example.invalid/v1", access_client_id=client_id,
                   access_client_secret=secret)
