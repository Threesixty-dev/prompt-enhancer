"""Synthetic deployment boundaries, including stale health and credential isolation."""

import json
from pathlib import Path
import sys
import urllib.error

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import deploy_bench as deploy


def environment():
    return {
        "DEPLOY_REVISION": "a" * 40, "DEPLOY_BRANCH": "main",
        "BENCH_COOLIFY_URL": "https://controller.example.com",
        "BENCH_COOLIFY_SERVICE_UUID": "example-service", "BENCH_COOLIFY_API_UUID": "example-api",
        "COOLIFY_TOKEN": "example-controller-not-a-secret",
        "COOLIFY_ACCESS_CLIENT_ID": "example-controller-id",
        "COOLIFY_ACCESS_CLIENT_SECRET": "example-controller-secret",
        "BENCH_PUBLIC_URL": "https://bench.example.com",
        "BENCH_CF_ACCESS_CLIENT_ID": "example-bench-id",
        "BENCH_CF_ACCESS_CLIENT_SECRET": "example-bench-secret",
    }


class Response:
    status = 200

    def __init__(self, value):
        self.value = json.dumps(value).encode()

    def read(self, size):
        return self.value[:size]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class Client:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    def open(self, request, **kwargs):
        self.calls.append(request)
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return Response(value)


def test_only_the_source_revision_and_selected_api_are_changed():
    env = environment()
    image = "local/enhancement-bench:api-" + env["DEPLOY_REVISION"]
    app = {"uuid": "example-api", "name": "bench-api", "image": "example-old-image"}
    client = Client([app, {"key": "BENCH_SOURCE_REVISION"}, {}, {**app, "image": image}, {}])
    deploy.deploy(env, client)
    assert [r.method for r in client.calls] == ["GET", "PATCH", "PATCH", "GET", "POST"]
    assert client.calls[1].full_url.endswith("/services/example-service/envs")
    assert json.loads(client.calls[1].data) == {
        "key": "BENCH_SOURCE_REVISION", "value": env["DEPLOY_REVISION"], "is_literal": True,
    }
    assert json.loads(client.calls[2].data) == {"image": image}
    assert client.calls[-1].full_url.endswith("/applications/example-api/start?force=true")
    assert all(r.full_url.startswith("https://controller.example.com/api/v1/services/example-service/") for r in client.calls)
    assert all(r.get_header("Authorization") == "Bearer " + env["COOLIFY_TOKEN"] for r in client.calls)
    assert all("bench-worker" not in r.full_url and "latest=true" not in r.full_url for r in client.calls)


@pytest.mark.parametrize("variable", [
    {}, {"key": "ANOTHER_VARIABLE"}, {"key": "BENCH_SOURCE_REVISION", "value": "b" * 40},
])
def test_unconfirmed_source_revision_never_starts_a_build(variable):
    client = Client([{"uuid": "example-api", "name": "bench-api"}, variable])
    with pytest.raises(RuntimeError, match="source_revision_unconfirmed"):
        deploy.deploy(environment(), client)
    assert len(client.calls) == 2


def test_missing_source_configuration_never_changes_the_image():
    missing = urllib.error.HTTPError("https://controller.example.com", 404, "", {}, None)
    client = Client([{"uuid": "example-api", "name": "bench-api"}, missing])
    with pytest.raises(urllib.error.HTTPError):
        deploy.deploy(environment(), client)
    assert len(client.calls) == 2


def test_wrong_resource_fails_before_any_write():
    client = Client([{"uuid": "example-api", "name": "bench-worker"}])
    with pytest.raises(RuntimeError, match="target_mismatch"):
        deploy.deploy(environment(), client)
    assert len(client.calls) == 1


@pytest.mark.parametrize("key,value", [
    ("DEPLOY_BRANCH", "develop"), ("DEPLOY_REVISION", "main"),
    ("BENCH_COOLIFY_URL", "https://controller.example.com/path"),
    ("BENCH_COOLIFY_API_UUID", "../example"), ("COOLIFY_TOKEN", "example\nsecret"),
    ("COOLIFY_ACCESS_CLIENT_SECRET", ""),
])
def test_invalid_configuration_never_reaches_network(key, value):
    env = {**environment(), key: value}
    client = Client([])
    with pytest.raises(ValueError):
        deploy.deploy(env, client)
    assert client.calls == []


def test_pin_must_be_read_back_before_start():
    app = {"uuid": "example-api", "name": "bench-api", "image": "example-old-image"}
    client = Client([app, {"key": "BENCH_SOURCE_REVISION"}, {}, app])
    with pytest.raises(RuntimeError, match="image_pin_unconfirmed"):
        deploy.deploy(environment(), client)
    assert len(client.calls) == 4


NOW = 1_790_000_000_000


def healthy_app(**changes):
    return {"uuid": "example-api", "name": "bench-api", "status": "running:healthy",
            "image": "local/enhancement-bench:api-" + "a" * 40, **changes}


def receipt(timestamp=NOW, revision="a" * 40):
    return f"BENCH_READY_V1 revision={revision} time_ms={timestamp}"


def test_readiness_uses_only_controller_credentials_and_bounded_logs(capsys):
    client = Client([healthy_app(), {"logs": "example-private-canary\n" + receipt()}])
    assert deploy.ready_receipt(environment(), client, not_before_ms=NOW, now_ms=NOW) == NOW
    for request in client.calls:
        assert request.full_url.startswith("https://controller.example.com/api/v1/services/example-service/")
        assert request.get_header("Cf-access-client-id") == "example-controller-id"
        assert request.get_header("Cf-access-client-secret") == "example-controller-secret"
    assert client.calls[-1].full_url.endswith("/applications/example-api/logs?lines=20")
    assert "example-private-canary" not in capsys.readouterr().out


@pytest.mark.parametrize("line", [
    receipt(revision="b" * 40), receipt(NOW - 1), receipt(NOW + 5_001),
    "prefix " + receipt(), receipt() + " extra", "ready", "",
])
def test_wrong_stale_future_or_malformed_receipts_cannot_pass(line):
    client = Client([healthy_app(), {"logs": line}])
    assert deploy.ready_receipt(environment(), client, not_before_ms=NOW, now_ms=NOW) is None


def test_old_receipt_expires_even_if_it_followed_deployment():
    client = Client([healthy_app(), {"logs": receipt(NOW - 90_001)}])
    assert deploy.ready_receipt(environment(), client, not_before_ms=NOW - 100_000, now_ms=NOW) is None


@pytest.mark.parametrize("changes", [
    {"status": "running:unhealthy"}, {"status": "running:unknown"}, {"status": "exited:unhealthy"},
    {"image": "local/enhancement-bench:api-" + "b" * 40},
])
def test_unhealthy_or_wrong_image_never_passes(changes):
    client = Client([healthy_app(**changes)])
    assert deploy.ready_receipt(environment(), client, not_before_ms=NOW, now_ms=NOW) is None
    assert len(client.calls) == 1


def test_repeated_receipt_is_not_two_health_checks():
    client = Client([healthy_app(), {"logs": receipt()}, healthy_app(), {"logs": receipt()}])
    clock = iter([0, 0, 150, 301])
    with pytest.raises(RuntimeError, match="bench_revision_health_timeout"):
        deploy.verify(environment(), client, monotonic=lambda: next(clock), sleep=lambda _: None,
                      wall_time_ns=lambda: NOW * 1_000_000)


def test_two_new_receipts_required_after_a_health_failure():
    values = []
    for timestamp in [NOW, None, NOW, NOW + 1, NOW + 2]:
        values.extend([healthy_app(), {"logs": receipt(timestamp)}] if timestamp else [healthy_app(status="running:unhealthy")])
    client = Client(values)
    deploy.verify(environment(), client, monotonic=lambda: 0, sleep=lambda _: None,
                  wall_time_ns=lambda: NOW * 1_000_000)
    assert len(client.calls) == 9


def test_controller_access_error_fails_without_polling_for_five_minutes():
    failure = urllib.error.HTTPError("https://controller.example.com", 403, "", {}, None)
    client = Client([failure])
    with pytest.raises(urllib.error.HTTPError):
        deploy.verify(environment(), client)
    assert len(client.calls) == 1


def test_redirects_are_never_followed():
    assert deploy.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example.com") is None


def test_workflow_scopes_deployment_and_does_not_wait_for_unrelated_quality():
    config = yaml.safe_load((ROOT / ".github/workflows/bench-deploy.yml").read_text())
    triggers = config.get("on", config.get(True))
    assert triggers["push"]["branches"] == ["main"]
    assert config["concurrency"]["cancel-in-progress"] is False
    assert set(config["jobs"]) == {"changes", "build-deploy"}
    selection = config["jobs"]["changes"]
    assert "environment" not in selection and "secrets." not in str(selection)
    assert "bench/deploy_changes.py" in str(selection)
    assert config["jobs"]["build-deploy"]["needs"] == "changes"
    assert "needs.changes.outputs.deploy == 'true'" in config["jobs"]["build-deploy"]["if"]
    assert config["jobs"]["build-deploy"]["environment"] == "production"
    assert "BENCH_CF_ACCESS" not in str(config) and "check-health" not in str(config)
    assert "require_quality_run" not in str(config)
    steps = str(config["jobs"]["build-deploy"]["steps"])
    assert "scripts/deploy_bench.py deploy" in steps
    assert "ghcr.io" not in steps and "docker/build-push-action" not in steps
    assert "packages" not in str(config.get("permissions", {}))
    assert "packages" not in str(config["jobs"]["build-deploy"].get("permissions", {}))


@pytest.mark.parametrize("failure,expected", [
    (urllib.error.HTTPError("https://example.com/private", 403, "example-sensitive-body", {}, None), "HTTP 403"),
    (ValueError("example-sensitive-body"), "request_unconfirmed"),
    (RuntimeError("bench_revision_health_timeout"), "bench_revision_health_timeout"),
])
def test_cli_reports_safe_failure_reason_without_response_data(monkeypatch, capsys, failure, expected):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(deploy, "inspect_target", fail)
    assert deploy.main(["check-controller"]) == 1
    output = capsys.readouterr().err
    assert expected in output
    assert "example-sensitive-body" not in output and "example.com" not in output


def test_cli_deployment_waits_for_readiness_before_success(monkeypatch):
    calls = []
    monkeypatch.setattr(deploy, "deploy", lambda *_: NOW)
    monkeypatch.setattr(deploy, "verify", lambda *args, **kwargs: calls.append(kwargs))
    assert deploy.main(["deploy"]) == 0
    assert calls == [{"not_before_ms": NOW}]
