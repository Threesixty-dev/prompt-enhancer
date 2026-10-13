import copy
import importlib.util
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import httpx
import pytest
import yaml

from enhancement_bench.api import create_app
from enhancement_bench.cli import deliver_publication
from enhancement_bench.definitions import Definition, Experiment, ExperimentUnit, Unit
from enhancement_bench.errors import BenchError

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://bench.example.com"
IMAGE = "registry.example.com/example/enhancer@sha256:" + "a" * 64


def publisher():
    spec = importlib.util.spec_from_file_location("experiment_publisher", ROOT / "bench/ci.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_domain_names_preserve_v1_identity(publication):
    assert Definition is Experiment and Unit is ExperimentUnit
    assert isinstance(publication.definition, Experiment)
    assert isinstance(publication.definition.units[0], ExperimentUnit)


def test_delivery_queues_one_run_and_duplicate_delivery_does_not_repeat(
        monkeypatch, store, contracts, publication, result_template):
    from test_client_worker import make_worker

    app = create_app(store, contracts, allowed_repositories=(IMAGE.split("@", 1)[0],),
                     origin=ORIGIN)
    original_client = httpx.Client
    with TestClient(app, base_url=ORIGIN) as api:
        def send(request):
            assert request.headers["origin"] == ORIGIN
            assert "authorization" not in request.headers
            response = api.post(request.url.path, content=request.content,
                                headers=dict(request.headers))
            return httpx.Response(response.status_code, json=response.json())

        def client(**kwargs):
            kwargs.setdefault("transport", httpx.MockTransport(send))
            return original_client(**kwargs)

        monkeypatch.setattr(httpx, "Client", client)
        first = deliver_publication(publication, ORIGIN + "/")
        assert first["imported"] and first["runId"]
        worker, _, _ = make_worker(store, contracts, result_template)
        assert worker.step()
        assert store.run(first["runId"])["status"] == "succeeded"
        repeated = deliver_publication(publication, ORIGIN)
        assert not repeated["imported"] and repeated["runId"] == first["runId"]
        assert len(store.runs()) == 1 and not worker.step()


@pytest.mark.parametrize("endpoint", ["http://bench.example.com", "https://example:example@example.com",
                                     ORIGIN + "/api", ORIGIN + "?example=1", ORIGIN + "#example"])
def test_invalid_delivery_origin_never_sends_credentials(publication, monkeypatch, endpoint):
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: pytest.fail("network must not be reached"))
    with pytest.raises(BenchError, match="https_delivery_origin_required"):
        deliver_publication(publication, endpoint)


def test_access_credentials_are_paired_and_redirects_are_not_followed(publication, monkeypatch):
    with pytest.raises(BenchError, match="gateway_credentials_incomplete"):
        deliver_publication(publication, ORIGIN, access_client_id="example-client")
    original_client = httpx.Client
    requests = []

    def send(request):
        requests.append(request)
        assert request.headers["CF-Access-Client-Id"] == "example-client"
        assert request.headers["CF-Access-Client-Secret"] == "example-not-a-secret"
        return httpx.Response(302, headers={"Location": "https://other.example.com"})

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(
        transport=httpx.MockTransport(send), **kwargs))
    with pytest.raises(BenchError, match="publication_delivery_failed"):
        deliver_publication(publication, ORIGIN,
                            access_client_id="example-client", access_client_secret="example-not-a-secret")
    assert len(requests) == 1


def run_publisher(monkeypatch, tmp_path, experiments):
    ci = publisher()
    inputs, output = tmp_path / "experiments", tmp_path / "output"
    inputs.mkdir()
    for position, experiment in enumerate(experiments):
        (inputs / f"example-{position}.json").write_text(json.dumps(experiment))
    monkeypatch.setenv("BENCH_CORE_IMAGES", "{}")
    monkeypatch.setattr(sys, "argv", ["ci.py", "--repository", IMAGE.split("@")[0],
                                     "--experiments", str(inputs), "--output", str(output)])
    calls = []
    monkeypatch.setattr(ci, "resolve_or_publish", lambda repository, **kwargs:
                        calls.append(kwargs["version"]) or (kwargs["version"], IMAGE, "reused"))
    return ci, output, calls


@pytest.mark.parametrize("receipt", [{"imported": True}, {"imported": "yes", "runId": None},
                                    {"imported": True, "runId": "example-arbitrary-response"}])
def test_delivery_rejects_unconfirmed_acknowledgements(monkeypatch, publication, receipt):
    original_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(202, json=receipt)), **kwargs))
    with pytest.raises(BenchError, match="publication_(acknowledgement_invalid|delivery_unconfirmed)"):
        deliver_publication(publication, ORIGIN)


def test_publisher_keeps_each_experiment_version_and_delivers_newest_first(
        monkeypatch, tmp_path, publication, store):
    original = publication.definition.model_dump()
    newest = copy.deepcopy(original)
    newest.update(revision="2", generation=2, enhancerVersion="0.2.0")
    ci, output, calls = run_publisher(monkeypatch, tmp_path, [original, newest])
    ci.main()
    envelopes = [json.loads(path.read_text()) for path in sorted(output.glob("*.json"))]
    assert calls == ["0.1.0", "0.2.0"]
    assert [e["definition"]["revision"] for e in envelopes] == ["2", "1"]
    from enhancement_bench.definitions import Publication

    for envelope in envelopes:
        store.import_publication(Publication.model_validate(envelope))
    assert len(store.runs()) == 1 and store.runs()[0]["revision"] == "2"


def test_duplicate_experiment_revision_fails_before_image_resolution(monkeypatch, tmp_path, publication):
    experiment = publication.definition.model_dump()
    ci, _, calls = run_publisher(monkeypatch, tmp_path, [experiment, experiment])
    with pytest.raises(SystemExit, match="bench_publication_failed"):
        ci.main()
    assert calls == []


def test_registered_image_reuse_is_pinned_and_does_not_hide_changed_current_source(monkeypatch):
    ci = publisher()
    entry = {"image": IMAGE, "variant": "default", "buildInputSha256": "b" * 64}
    monkeypatch.setattr(ci, "core_version", lambda: "0.2.0")
    assert ci.configured_image("0.1.0", "default", {"0.1.0": entry}) == ("0.1.0", IMAGE, "registered")
    with pytest.raises(BenchError, match="registered_core_image_invalid"):
        ci.configured_image("0.1.0", "models", {"0.1.0": entry})
    monkeypatch.setattr(ci, "core_version", lambda: "0.1.0")
    monkeypatch.setattr(ci, "build_hash", lambda **kwargs: "c" * 64)
    with pytest.raises(BenchError, match="core_version_reused_for_changed_code"):
        ci.configured_image("0.1.0", "default", {"0.1.0": entry})


def test_retained_artifact_keeps_unknown_build_inputs_unknown(monkeypatch):
    ci = publisher()
    entry = {"image": IMAGE, "variant": "default"}
    monkeypatch.setattr(ci, "core_version", lambda: "0.2.0")
    assert ci.configured_image("0.1.0", "default", {"0.1.0": entry}) == ("0.1.0", IMAGE, "registered")
    monkeypatch.setattr(ci, "core_version", lambda: "0.1.0")
    with pytest.raises(BenchError, match="core_version_reused_for_changed_code"):
        ci.configured_image("0.1.0", "default", {"0.1.0": entry})


def test_historical_version_cannot_be_built_from_current_source(monkeypatch):
    ci = publisher()
    monkeypatch.setattr(ci, "core_version", lambda: "0.2.0")
    monkeypatch.setattr(ci, "existing_tag", lambda tag: False)
    monkeypatch.setattr(ci, "command", lambda *args, **kwargs: pytest.fail("must not build wrong source"))
    with pytest.raises(BenchError, match="requested_core_version_not_published"):
        ci.resolve_or_publish("registry.example.com/example/enhancer", version="0.1.0", allow_publish=True)


def test_json_push_triggers_publication_only_on_operator_selected_branch():
    workflow = yaml.safe_load((ROOT / ".github/workflows/bench-publish.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    assert triggers["push"]["paths"] == ["experiments/**/*.json"]
    job = workflow["jobs"]["publish"]
    assert "vars.BENCH_PUBLICATION_BRANCH" in job["if"]
    assert "github.event.repository.default_branch" in job["if"]
    assert job["environment"] == "bench-publication"
    assert workflow["concurrency"]["cancel-in-progress"] is False
