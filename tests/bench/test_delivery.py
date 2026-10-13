"""Publication delivery authenticates only at the external gateway."""

import httpx
import pytest

from enhancement_bench import cli


@pytest.mark.parametrize("gateway", [False, True])
def test_delivery_uses_same_origin_and_optional_gateway_credentials(monkeypatch, tmp_path, publication, contracts, gateway):
    envelope = tmp_path / "publication.json"
    envelope.write_text(publication.model_dump_json())
    monkeypatch.setattr("sys.argv", ["enhancement-bench", "deliver", str(envelope)])
    monkeypatch.setattr(cli, "default_contracts", lambda: contracts.directory)
    monkeypatch.setenv("BENCH_DELIVERY_URL", "https://bench.example.com/")
    for key in ("BENCH_CF_ACCESS_CLIENT_ID", "BENCH_CF_ACCESS_CLIENT_SECRET", "BENCH_IMPORT_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    if gateway:
        monkeypatch.setenv("BENCH_CF_ACCESS_CLIENT_ID", "example-client-id")
        monkeypatch.setenv("BENCH_CF_ACCESS_CLIENT_SECRET", "example-client-secret")
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(202, json={"imported": True, "runId": None})

    client_type = httpx.Client

    def client(**settings):
        assert settings == {"timeout": 30, "follow_redirects": False, "trust_env": False}
        return client_type(transport=httpx.MockTransport(respond), **settings)

    monkeypatch.setattr(cli.httpx, "Client", client)
    cli.main()
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://bench.example.com/api/publications"
    assert request.headers["origin"] == "https://bench.example.com"
    assert "authorization" not in request.headers
    if gateway:
        assert request.headers["cf-access-client-id"] == "example-client-id"
        assert request.headers["cf-access-client-secret"] == "example-client-secret"
    else:
        assert "cf-access-client-id" not in request.headers
        assert "cf-access-client-secret" not in request.headers


def test_partial_gateway_credentials_fail_before_delivery(monkeypatch, tmp_path, publication, contracts, capsys):
    envelope = tmp_path / "publication.json"
    envelope.write_text(publication.model_dump_json())
    monkeypatch.setattr("sys.argv", ["enhancement-bench", "deliver", str(envelope)])
    monkeypatch.setattr(cli, "default_contracts", lambda: contracts.directory)
    monkeypatch.setenv("BENCH_DELIVERY_URL", "https://bench.example.com")
    monkeypatch.setenv("BENCH_CF_ACCESS_CLIENT_ID", "example-client-id")
    monkeypatch.delenv("BENCH_CF_ACCESS_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(cli.httpx, "Client", lambda **_: pytest.fail("unexpected delivery"))
    with pytest.raises(SystemExit):
        cli.main()
    assert capsys.readouterr().out == "gateway_credentials_incomplete\n"
