"""Synthetic client/API journeys, privacy boundaries and admission recovery."""

import copy
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest

from enhancement_bench.api import create_app
from enhancement_bench.cli import parser
from enhancement_bench.definitions import RunPlan
from enhancement_bench.errors import BenchError
from enhancement_bench.operator_cli import execute
from enhancement_bench.private_io import read_json
from enhancement_bench.protocol import Contracts
from enhancement_bench.remote import BenchClient
from test_client_worker import make_worker

ORIGIN = "https://bench.example.com"


@pytest.fixture
def remote(store, publication, contracts, monkeypatch):
    publication.definition.autoRun = False
    store.import_publication(publication)
    monkeypatch.setenv("BENCH_URL", ORIGIN)
    monkeypatch.delenv("BENCH_CF_ACCESS_CLIENT_ID", raising=False)
    monkeypatch.delenv("BENCH_CF_ACCESS_CLIENT_SECRET", raising=False)
    state = {"requests": [], "loseAck": False}
    with TestClient(create_app(store, contracts, allowed_repositories=(), origin=ORIGIN)) as api:
        def send(request):
            state["requests"].append((request.method, request.url.path))
            response = api.request(request.method, request.url.raw_path.decode(), content=request.content, headers=dict(request.headers))
            if state["loseAck"] and request.method == "POST" and request.url.path == "/api/runs":
                state["loseAck"] = False
                raise httpx.ReadTimeout("example-private-transport-canary")
            return httpx.Response(response.status_code, content=response.content, headers=response.headers)
        def factory(origin=ORIGIN, **kwargs):
            return BenchClient(origin, transport=httpx.MockTransport(send), **kwargs)
        yield factory, state


def args(*values):
    return parser().parse_args(values)


def plan(publication):
    return RunPlan(stableId=publication.definition.stableId, revision=publication.definition.revision)


def test_preflight_checks_every_pair_without_enqueuing_or_claiming_readiness(remote, store, publication):
    factory, _ = remote
    with factory() as client:
        result = client.preflight(plan(publication))
    assert result["valid"] and result["attemptCount"] == 2
    assert result["checks"]["coreArtifact"] == "registered"
    assert result["executionReadiness"] == "unverified"
    assert result["checks"]["workerLiveness"] == result["checks"]["providerAuthentication"] == result["checks"]["modelReadiness"] == "unverified"
    assert result["queue"] == {"queued": 0, "running": 0, "cleanup": 0, "reconciliation": 0}
    assert not store.runs()


def test_preflight_and_submit_reject_same_invalid_override(remote, store, publication, tmp_path):
    factory, _ = remote
    value = plan(publication).model_copy(update={"overrides": plan(publication).overrides.model_copy(update={"subjectIds": ["example-unknown"]})})
    with factory() as client:
        for operation in (lambda: client.preflight(value), lambda: client.submit(value, tmp_path / "receipt.json")):
            with pytest.raises(BenchError, match="unknown_selection"):
                operation()
    assert not store.runs()


def test_lost_admission_acknowledgement_reuses_durable_identity(remote, store, publication, tmp_path):
    factory, state = remote
    receipt_path = tmp_path / "receipt.json"
    state["loseAck"] = True
    with factory() as client:
        with pytest.raises(BenchError, match="transport_unconfirmed"):
            client.submit(plan(publication), receipt_path)
        initial = read_json(receipt_path, private=True)
        assert initial["runId"] is None and initial["requestId"]
        first = store.runs()[0]["id"]
        receipt = client.submit(plan(publication), receipt_path)
        assert receipt["runId"] == first and receipt["requestId"] == initial["requestId"]
        request_count = len(state["requests"])
        assert client.submit(plan(publication), receipt_path) == receipt
        assert len(state["requests"]) == request_count
        changed = plan(publication).model_copy(update={"revision": "example-other"})
        with pytest.raises(BenchError, match="submission_receipt_mismatch"):
            client.submit(changed, receipt_path)
    assert len(store.runs()) == 1
    assert publication.definition.subjects[0].text not in receipt_path.read_text()


def test_client_run_wait_inspect_and_export_from_receipt(remote, store, publication, contracts, result_template, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    factory, state = remote
    receipt = tmp_path / "receipt.json"
    common = ("--experiment", publication.definition.stableId, "--revision", publication.definition.revision)
    submitted, status = execute(args("run", *common, "--receipt", str(receipt)), client_factory=factory)
    assert status == 0 and submitted["admitted"] and submitted["receiptSaved"]
    worker, _, _ = make_worker(store, contracts, result_template)
    assert worker.step()
    for command in ("wait", "inspect"):
        report, status = execute(args(command, "--receipt", str(receipt)), client_factory=factory)
        assert status == 0 and report["status"] == "succeeded"
        assert report["technicalOutcomes"] == {"succeeded": 2}
        assert "enhanced_prompt" not in json.dumps(report) and "Original prompt" not in json.dumps(report)
    output = tmp_path / "export"
    receipt_data, status = execute(args("export", "--receipt", str(receipt), "--output", str(output)), client_factory=factory)
    assert status == 0 and receipt_data["rowCounts"]["attempts"] == 2
    assert receipt_data["rowCounts"]["metrics"] == 12 and not receipt_data["containsPromptText"]
    assert {p.name for p in output.iterdir()} == {"manifest.json", "analysis.json", "analysis.schema.json", "README.md", "runs.csv", "attempts.csv", "metrics.csv", "assertions.csv", "timings.csv", "errors.csv"}
    assert ("GET", "/api/client-contracts") in state["requests"]


def test_wait_timeout_does_not_cancel_or_resubmit(remote, publication, tmp_path):
    factory, state = remote
    with factory() as client:
        receipt = client.submit(plan(publication), tmp_path / "receipt.json")
    now = [0.0]
    with pytest.raises(BenchError, match="wait_timeout"):
        execute(args("wait", receipt["runId"], "--timeout", "1", "--poll-interval", "0.5"), client_factory=factory,
                clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
    assert state["requests"].count(("POST", "/api/runs")) == 1
    assert not any(path.endswith("/cancel") for _, path in state["requests"])


def test_wait_reports_assertions_separately_and_honors_optional_gate(remote, store, publication, contracts, result_template, tmp_path):
    factory, _ = remote
    with factory() as client:
        receipt = client.submit(plan(publication), tmp_path / "receipt.json")
    worker, core, _ = make_worker(store, contracts, result_template)
    core.fail_assertions = True
    worker.step()
    report, status = execute(args("wait", receipt["runId"]), client_factory=factory)
    assert status == 0 and report["assertionOutcome"] == "failed"
    _, status = execute(args("wait", receipt["runId"], "--require-assertions"), client_factory=factory)
    assert status == 3


def test_cancel_receipt_requires_later_stop_verification(remote, publication, tmp_path):
    factory, _ = remote
    path = tmp_path / "receipt.json"
    with factory() as client:
        client.submit(plan(publication), path)
    cancelled, code = execute(args("cancel", "--receipt", str(path)), client_factory=factory)
    assert code == 0 and cancelled["cancellationRequested"] and not cancelled["stopConfirmed"]
    report, code = execute(args("wait", "--receipt", str(path)), client_factory=factory)
    assert code == 3 and report["status"] == "cancelled" and not report["cleanupPending"]


def test_discovery_pages_and_selection_keep_content_private(remote, store, publication, tmp_path):
    factory, _ = remote
    catalog, _ = execute(args("experiments"), client_factory=factory)
    assert catalog["experiments"][0]["caseIds"] == [s.id for s in publication.definition.subjects]
    for i in range(3):
        with factory() as client:
            client.submit(plan(publication), tmp_path / f"receipt-{i}.json")
    first, _ = execute(args("runs", "--limit", "2"), client_factory=factory)
    second, _ = execute(args("runs", "--limit", "2", "--before", first["nextCursor"]), client_factory=factory)
    ids = [r["runId"] for r in first["runs"] + second["runs"]]
    assert len(ids) == len(set(ids)) == 3 and second["nextCursor"] is None
    assert publication.definition.subjects[0].text not in json.dumps(catalog | first)


@pytest.mark.parametrize("origin", ["http://bench.example.com", ORIGIN + "/api", ORIGIN + "?example=1", ORIGIN + "#example",
    "https://example:example@example.com", "https://example.com\\@127.0.0.1", "https://example.com:99999", "https://example.com\n"])
def test_invalid_origins_never_construct_transport(origin, monkeypatch):
    monkeypatch.setattr(httpx, "Client", lambda **_: pytest.fail("transport must not be reached"))
    with pytest.raises(BenchError, match="https_or_loopback_origin_required"):
        BenchClient(origin)


@pytest.mark.parametrize("status,body,headers,code", [
    (302, {}, {"Location": "https://other.example.com"}, "gateway_redirect_refused"),
    (401, {}, {}, "gateway_access_denied"), (403, {}, {}, "gateway_access_denied"),
    (200, {}, {"Content-Type": "text/html"}, "json_response_required"),
    (500, {"error": {"code": "example-private-canary"}}, {}, "bench_http_error"),
])
def test_transport_never_echoes_server_errors_or_follows_redirects(status, body, headers, code):
    calls = []
    def send(request):
        calls.append(request.url)
        return httpx.Response(status, json=body, headers=headers)
    with BenchClient(ORIGIN, transport=httpx.MockTransport(send)) as client:
        with pytest.raises(BenchError, match=code):
            client.request("GET", "/api/experiments")
    assert len(calls) == 1


@pytest.mark.parametrize("body", [b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'not-json'])
def test_malformed_json_is_a_content_free_error(body):
    with BenchClient(ORIGIN, transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body, headers={"Content-Type": "application/json"}))) as client:
        with pytest.raises(BenchError):
            client.request("GET", "/api/experiments")


def test_contract_discovery_uses_current_schemas_and_refuses_external_refs(contracts):
    payload = contracts.payload()
    assert Contracts.from_payload(payload).payload() == payload
    changed = copy.deepcopy(payload)
    changed["schemas"]["execute-request"]["$ref"] = "https://example.com/remote-schema"
    with pytest.raises(BenchError, match="remote_contracts_invalid"):
        Contracts.from_payload(changed)


@pytest.mark.parametrize("reference", ["#/$defs/example-missing", "#/properties/subject"])
def test_contract_discovery_rejects_unresolvable_or_unsupported_local_refs(contracts, reference):
    payload = copy.deepcopy(contracts.payload())
    payload["schemas"]["execute-request"]["properties"]["subject"]["$ref"] = reference
    with pytest.raises(BenchError, match="remote_contracts_invalid"):
        Contracts.from_payload(payload)


def test_cli_errors_are_json_and_never_echo_invalid_input(monkeypatch, capsys):
    from enhancement_bench.cli import main
    monkeypatch.setattr("sys.argv", ["enhancement-bench", "example-private-canary"])
    with pytest.raises(SystemExit) as exited:
        main()
    captured = capsys.readouterr()
    assert exited.value.code == 2 and captured.err == "" and "example-private-canary" not in captured.out
    assert json.loads(captured.out)["error"]["code"] == "invalid_arguments"


def test_receipt_durability_failure_prevents_admission(remote, publication, tmp_path, monkeypatch):
    import enhancement_bench.private_io as files
    factory, state = remote
    def fail(_):
        raise OSError("example-private-canary")
    monkeypatch.setattr(files, "sync_directory", fail)
    with factory() as client, pytest.raises(BenchError, match="file_write_failed"):
        client.submit(plan(publication), tmp_path / "receipt.json")
    assert not state["requests"] and not (tmp_path / "receipt.json").exists()


def test_lost_local_acknowledgement_write_preserves_recoverable_receipt(remote, store, publication, tmp_path, monkeypatch):
    import enhancement_bench.remote as module
    factory, _ = remote
    original = module.write_json
    def fail(path, value, *, replace=False):
        if replace:
            raise BenchError("file_write_failed")
        original(path, value)
    monkeypatch.setattr(module, "write_json", fail)
    path = tmp_path / "receipt.json"
    with factory() as client, pytest.raises(BenchError, match="file_write_failed"):
        client.submit(plan(publication), path)
    assert read_json(path)["runId"] is None and len(store.runs()) == 1
    monkeypatch.setattr(module, "write_json", original)
    with factory() as client:
        assert client.submit(plan(publication), path)["runId"] == store.runs()[0]["id"]
    assert len(store.runs()) == 1


def test_preflight_reports_cleanup_holds_without_clearing_them(remote, store, publication, tmp_path):
    factory, _ = remote
    with factory() as client:
        receipt = client.submit(plan(publication), tmp_path / "receipt.json")
        store.claim()
        before = store.run(receipt["runId"])
        check = client.preflight(plan(publication))
    assert check["queue"]["running"] == 1 and check["queue"]["cleanup"] == 1
    assert store.run(receipt["runId"]) == before


def test_preflight_refuses_unregistered_core_without_admission(remote, store, publication):
    factory, _ = remote
    with store.transaction() as db:
        db.execute("DELETE FROM core_images")
    with factory() as client, pytest.raises(BenchError, match="core_version_unavailable"):
        client.preflight(plan(publication))
    assert not store.runs()


def test_response_limits_are_enforced(remote, monkeypatch):
    import enhancement_bench.remote as module
    factory, _ = remote
    monkeypatch.setattr(module, "MAX_RESPONSE_BYTES", 8)
    with factory() as client, pytest.raises(BenchError, match="response_too_large"):
        client.request("GET", "/api/experiments")


def test_remote_preflight_cannot_add_private_fields(remote, publication, monkeypatch):
    factory, _ = remote
    with factory() as client:
        value = client.preflight(plan(publication))
        value["example-private-canary"] = "not-for-output"
        monkeypatch.setattr(client, "request", lambda *a, **kw: value)
        with pytest.raises(BenchError, match="response_contract_invalid"):
            client.preflight(plan(publication))


def test_cli_subprocess_journey_over_owned_loopback_without_checkout_cwd(store, publication, contracts, result_template, tmp_path):
    import os
    import socket
    import subprocess
    import sys
    import threading
    import time
    import uvicorn

    publication.definition.autoRun = False
    store.import_publication(publication)
    worker, _, _ = make_worker(store, contracts, result_template)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(create_app(store, contracts, allowed_repositories=(), origin=origin),
        host="127.0.0.1", port=port, access_log=False, log_level="critical", lifespan="off"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    root = Path(__file__).resolve().parents[2]
    environment = {"PATH": os.defpath, "PYTHONPATH": str(root / "bench/src"), "PYTHONDONTWRITEBYTECODE": "1", "BENCH_URL": origin}
    def command(*arguments):
        result = subprocess.run([sys.executable, "-m", "enhancement_bench.cli", *arguments],
            cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout
        assert result.stderr == ""
        value = json.loads(result.stdout)
        assert value["schemaVersion"] == "bench-cli/v1" and value["ok"]
        assert publication.definition.subjects[0].text not in result.stdout
        return value["data"]
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started
        selection = ("--experiment", publication.definition.stableId, "--revision", publication.definition.revision)
        assert command("preflight", *selection)["attemptCount"] == 2
        receipt = tmp_path / "submission.json"
        result = command("run", *selection, "--receipt", str(receipt))
        assert command("run", *selection, "--receipt", str(receipt))["runId"] == result["runId"]
        assert len(store.runs()) == 1 and worker.step()
        assert command("wait", "--receipt", str(receipt))["technicalOutcomes"] == {"succeeded": 2}
        assert command("inspect", "--receipt", str(receipt))["status"] == "succeeded"
        exported = command("export", "--receipt", str(receipt), "--output", str(tmp_path / "analysis"))
        assert exported["rowCounts"]["metrics"] == 12
        assert command("schema", "analysis")["properties"]["schemaVersion"]["const"] == "bench-analysis/v2"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
    assert not thread.is_alive()
