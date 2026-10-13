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


def test_health_sends_only_bench_credentials_and_requires_exact_revision():
    env = environment()
    client = Client([{"ready": True, "schemaVersion": "bench.v1", "revision": "c" * 40},
                     {"ready": True, "schemaVersion": "bench.v1", "revision": env["DEPLOY_REVISION"]}])
    assert not deploy.ready(env, client, exact=True)
    assert deploy.ready(env, client, exact=True)
    for request in client.calls:
        assert request.full_url == "https://bench.example.com/health/ready"
        assert request.get_header("Authorization") is None
        assert request.get_header("Cf-access-client-id") == env["BENCH_CF_ACCESS_CLIENT_ID"]
        assert request.get_header("Cf-access-client-secret") == env["BENCH_CF_ACCESS_CLIENT_SECRET"]


def test_queued_or_old_healthy_container_cannot_pass_deployment():
    stale = {"ready": True, "schemaVersion": "bench.v1", "revision": "c" * 40}
    client = Client([stale, stale])
    clock = iter([0, 0, 150, 301])
    with pytest.raises(RuntimeError, match="bench_revision_health_timeout"):
        deploy.verify(environment(), client, monotonic=lambda: next(clock), sleep=lambda _: None)


def test_two_consecutive_health_checks_required_after_a_failure():
    ready = {"ready": True, "schemaVersion": "bench.v1", "revision": "a" * 40}
    client = Client([ready, OSError(), ready, ready])
    deploy.verify(environment(), client, monotonic=lambda: 0, sleep=lambda _: None)
    assert len(client.calls) == 4


def test_redirects_are_never_followed():
    assert deploy.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example.com") is None


def test_workflow_scopes_deployment_and_does_not_wait_for_unrelated_quality():
    config = yaml.safe_load((ROOT / ".github/workflows/bench-deploy.yml").read_text())
    triggers = config.get("on", config.get(True))
    assert triggers["push"]["branches"] == ["main"]
    assert config["concurrency"]["cancel-in-progress"] is False
    assert config["jobs"]["build-deploy"]["needs"] == "health-access"
    assert config["jobs"]["verify"]["needs"] == "build-deploy"
    assert "require_quality_run" not in str(config)
    steps = str(config["jobs"]["build-deploy"]["steps"])
    assert "scripts/deploy_bench.py deploy" in steps
    assert "ghcr.io" not in steps and "docker/build-push-action" not in steps
    assert "packages" not in str(config.get("permissions", {}))
    assert "packages" not in str(config["jobs"]["build-deploy"].get("permissions", {}))


@pytest.mark.parametrize("failure,expected", [
    (urllib.error.HTTPError("https://example.com/private", 403, "example-sensitive-body", {}, None), "HTTP 403"),
    (ValueError("example-sensitive-body"), "request_unconfirmed"),
    (RuntimeError("bench_health_access_unconfirmed"), "bench_health_access_unconfirmed"),
])
def test_cli_reports_safe_failure_reason_without_response_data(monkeypatch, capsys, failure, expected):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(deploy, "ready", fail)
    assert deploy.main(["check-health"]) == 1
    output = capsys.readouterr().err
    assert expected in output
    assert "example-sensitive-body" not in output and "example.com" not in output
