"""Real core/bench container smoke. The loopback inference provider is simulated.

This deliberately does not claim live OpenHands/Codex or genuine-model acceptance.
Only this test's labelled containers are removed; no image is published.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid


def docker(args, *, capture=False, input=None):
    result = subprocess.run(["docker", *args], input=input, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                            stderr=subprocess.PIPE, timeout=180)
    if result.returncode:
        # Only the inner test's fixed diagnostics can be reported, never container logs.
        if args[:1] == ["exec"] and result.stdout:
            print(result.stdout.decode()[:2000])
        raise RuntimeError("smoke_docker_command_failed")
    return result.stdout


def inner():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from enhancement_bench.definitions import Publication, Overrides
    from enhancement_bench.protocol import Contracts
    from enhancement_bench.runtime import DockerRuntime, DockerSettings, MODEL_CACHE_PATH
    from enhancement_bench.store import Store
    from enhancement_bench.worker import Worker
    from enhancement_bench.protocol import IDENTITY
    from jsonschema import Draft202012Validator

    generation_validator = Draft202012Validator(json.loads(
        (Path(os.environ["BENCH_CONTRACTS"]) / "generation-context.schema.json").read_text()))
    deliveries = {}
    provider_failures = []
    model_runtime = os.environ.get("SMOKE_MODEL_RUNTIME") == "1"
    model_launches = []

    class SmokeRuntime(DockerRuntime):
        def launch(self, run):
            endpoint = super().launch(run)
            if model_runtime:
                name = run["container_name"]
                mounts = json.loads(self._command(["inspect", "--format", "{{json .Mounts}}", name], capture=True).stdout)
                cache = next(m for m in mounts if m["Destination"] == MODEL_CACHE_PATH)
                assert cache["Type"] == "volume" and not cache["RW"]
                resources = self._command(["inspect", "--format", "{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}", name], capture=True).stdout
                assert resources.strip() == b"4294967296 2000000000"
                probe = """import errno, pathlib, torch, transformers
from prompt_enhancer.infrastructure.text_models.loader import (validate_model_cache_root,
    isolated_hugging_face_environment, transformers_network_closed, prepare_model_snapshot,
    ModelSnapshotUnavailableError)
from prompt_enhancer.infrastructure.text_models.manifests import TEXT_MODEL_MANIFESTS
cache = pathlib.Path('/opt/enhancement/runtime/model-eval')
root = pathlib.Path('/opt/enhancement')
assert validate_model_cache_root(cache, repo_root=root) == cache
assert (cache / 'example-fixture.txt').read_text() == 'synthetic-cache-fixture'
with isolated_hugging_face_environment(cache, repo_root=root), transformers_network_closed():
    try:
        prepare_model_snapshot(TEXT_MODEL_MANIFESTS['multilingual_e5_small'], cache_root=cache, repo_root=root, allow_download=False)
    except ModelSnapshotUnavailableError:
        pass
    else:
        raise AssertionError('missing_snapshot_not_rejected')
try:
    (cache / 'write-probe.txt').write_text('must-not-write')
except OSError as error:
    assert error.errno == errno.EROFS
else:
    raise AssertionError('cache_not_read_only')
"""
                self._command(["exec", name, "python", "-c", probe], timeout=60)
                model_launches.append(run["id"])
            return endpoint

        def _command(self, args, **kwargs):
            if args[:1] == ["create"]:
                # Trust only this fixture's ephemeral CA; TLS verification remains on.
                args = args[:1] + ["--mount", "type=bind,src=" + os.environ["SMOKE_CA_SOURCE"]
                        + ",dst=/etc/ssl/certs/ca-certificates.crt,readonly"] + args[1:]
            return super()._command(args, **kwargs)

        def cleanup(self, run_id, name):
            state = self._command(["inspect", "--format", "{{.State.Status}} {{.State.ExitCode}}", name], capture=True, allow_failure=True)
            if state.returncode == 0 and not state.stdout.startswith(b"running"):
                print("synthetic_core_state=" + state.stdout.decode().strip())
                logs = self._command(["logs", "--tail", "8", name], capture=True, allow_failure=True)
                # Core diagnostics are fixed codes; do not emit arbitrary runtime text.
                for code in (b"core_configuration_invalid", b"api_token_too_short", b"ModuleNotFoundError", b"PermissionError"):
                    if code in logs.stdout:
                        print("synthetic_core_startup=" + code.decode())
            return super().cleanup(run_id, name)

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            if length > 320000:
                self.send_error(413)
                return
            try:
                value = json.loads(self.rfile.read(length))
                assert value["model"] == "example-qualified-model"
                messages = [item for item in value["messages"] if item["role"] == "user"]
                assert len(messages) == 1
                payload = json.loads(messages[0]["content"])
                assert set(payload) == {"subject", "generation_context"}
                measured = payload["generation_context"]
                assert generation_validator.is_valid(measured)
                assert measured["before"] and all(e["metrics"] and e["provenance"] for e in measured["before"])
                metrics = [m for e in measured["before"] for m in e["metrics"]]
                assert all(m["state"] and m["reason"] for m in metrics)
                assert all(m["value"] is None and m["label"] is None for m in metrics if m["state"] != "known")
                assert measured["attempt_id"] not in deliveries
                deliveries[measured["attempt_id"]] = payload
            except (AssertionError, KeyError, TypeError, ValueError):
                provider_failures.append("generation_payload_invalid")
                self.send_error(422)
                return
            candidate = json.dumps({"enhanced_prompt": "Add a parser for the fictional example widget. Return a patch and passing unit tests. Preserve existing public interfaces. Clarify missing input and output formats."})
            body = json.dumps({"model": "example-qualified-model", "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": candidate}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 4000), Provider)
    import ssl
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain("/tmp/provider.crt", "/tmp/provider.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    run_ids = []
    try:
        definition = json.loads(Path("/tmp/definition.json").read_text())
        definition["consumerBinding"]["provider"] = "inference"
        image = os.environ["SMOKE_CORE_IMAGE"]
        publication = Publication.model_validate({"schemaVersion": "bench-publication/v1", "definition": definition,
                                                  "image": image, "coreVersion": definition["enhancerVersion"]})
        store = Store(Path("/data/smoke.sqlite3"))
        model_settings = dict(core_variant="models", model_cache_volume=os.environ["SMOKE_MODEL_CACHE_VOLUME"],
            config_path=Path("/tmp/model-config.json"), memory="4g", cpus="2") if model_runtime else {}
        runtime = SmokeRuntime(DockerSettings((image.split("@")[0],),
            network_namespace=os.environ["SMOKE_NAMESPACE"], config_source=os.environ["SMOKE_CONFIG_SOURCE"],
            environment_keys=("ENHANCEMENT_CONSUMER_TOKEN",), **model_settings))
        contracts = Contracts(Path(os.environ["BENCH_CONTRACTS"]))

        def verify_delivery(run):
            attempt = next(a for a in run["attempts"] if a["unit_id"] == "consumer")
            payload = deliveries[attempt["id"]]
            measured, result = payload["generation_context"], attempt["result"]
            request = contracts.request(run, attempt)
            assert payload["subject"] == request["subject"]
            assert all(measured[key] == result[key] == request[key] for key in IDENTITY)
            assert measured["before"] == result["before"]
            assert measured["evaluation_profile"] == result["evaluation_profile"]
            assert measured["objective"] == result["effective_objective"] == request["objective"]
            assert measured["steering"] == result["effective_steering"] == request["steering"]
            assert measured["protocol_version"] == result["generation_context_version"]
            assert measured["prompt_version"] == result["generation_prompt_version"]
            return measured

        worker = Worker(store, contracts, runtime, run_seconds=120)
        run_id = store.import_publication(publication)["runId"]
        run_ids.append(run_id)
        assert store.import_publication(publication)["runId"] == run_id
        worker.step()
        result = store.run(run_id)
        if result["status"] != "succeeded":
            print(json.dumps({"status": result["status"], "error": result["error_code"],
                              "attempts": [{"state": a["status"], "error": a["error_code"],
                                            "core_errors": a["result"]["errors"] if a["result"] else None} for a in result["attempts"]]}))
            raise AssertionError("real_core_smoke_failed")
        assert len(result["attempts"]) == 2 and not result["cleanup_pending"]
        assert all(a["result"]["before"] and a["result"]["after"] for a in result["attempts"])
        assert result["attempts"][0]["result"]["evaluation_profile"] == result["attempts"][1]["result"]["evaluation_profile"]
        assert result["attempts"][1]["result"]["consumer_provenance"]["provider"] == "inference"
        original_context = verify_delivery(result)
        reopened = Store(store.path)
        assert reopened.run(run_id)["attempts"] == result["attempts"]
        overrides = Overrides(parameters={"timeout_seconds": 60},
            unitObjectives={"consumer": {"revision": "2", "targets": [{"kind": "numeric", "evaluator_id": "prompt",
                "metric_key": "prompt.acceptance_testability", "direction": "increase", "desired_value": 0.9}]}},
            unitSteering={"consumer": {"style": "concise", "focus": ["acceptance"]}})
        manual = reopened.enqueue_ui(definition["stableId"], definition["revision"], overrides, str(uuid.uuid4()), run_id)
        run_ids.append(manual)
        Worker(reopened, contracts, runtime, run_seconds=120).step()
        assert reopened.run(manual)["status"] == "succeeded"
        assert reopened.run(manual)["effective"]["units"][0]["parameters"]["timeout_seconds"] == 60
        changed_context = verify_delivery(reopened.run(manual))
        assert changed_context["objective"] != original_context["objective"]
        assert changed_context["steering"] != original_context["steering"]
        assert changed_context["before"] == original_context["before"]
        assert changed_context["evaluation_profile"] == original_context["evaluation_profile"]
        assert len(deliveries) == 2 and not provider_failures
        assert len(model_launches) == (2 if model_runtime else 0)
        assert not reopened.pending_cleanup()
        print(json.dumps({"scope": "real_core_containers_with_simulated_inference", "runs": 2, "attempts": 4,
                          "same_evaluator_profile": True, "duplicates_suppressed": True, "restart_persistence": True,
                          "measured_generation_payload_verified": True, "objective_steering_overrides_verified": True,
                          "model_cache_resources_verified": model_runtime, "missing_snapshot_rejected": model_runtime,
                          "weights_loaded": False, "gpu_qualified": False,
                          "cleanup_confirmed": True, "live_consumer_qualified": False}))
    finally:
        for run_id in run_ids:
            try:
                runtime.cleanup(run_id, f"enhancement-bench-{run_id}")
            except Exception:
                pass
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inner", action="store_true")
    parser.add_argument("--core-image", default="local/enhancement-core:bench-validation")
    parser.add_argument("--bench-image", default="local/enhancement-bench:validation")
    parser.add_argument("--model-runtime", action="store_true")
    args = parser.parse_args()
    if args.inner:
        inner()
        return
    root = Path(__file__).resolve().parents[2]
    digests = json.loads(docker(["image", "inspect", args.core_image, "--format", "{{json .RepoDigests}}"], capture=True))
    if not digests or not all(isinstance(value, str) and "@sha256:" in value for value in digests):
        raise SystemExit("local_registry_manifest_digest_unavailable_no_image_id_substitution")
    image = digests[0]
    namespace = "enhancement-bench-smoke-" + uuid.uuid4().hex[:12]
    cache_volume = "enhancement-bench-models-smoke-" + uuid.uuid4().hex[:12]
    cache_created = False
    with tempfile.TemporaryDirectory(prefix="bench-docker-smoke-") as directory:
        cert, key = Path(directory).resolve() / "provider.crt", Path(directory).resolve() / "provider.key"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
                        "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=True)
        config = Path(directory).resolve() / "core.json"
        core_config = {"consumers": [{"binding_id": "example-consumer", "provider": "inference",
            "endpoint": "https://127.0.0.1:4000", "credential_env": "ENHANCEMENT_CONSUMER_TOKEN",
            "model": "example-qualified-model", "model_revision": "example-revision", "model_license": "example-license"}],
            "evaluators": [], "max_active": 1, "max_retained": 8}
        if args.model_runtime:
            core_config["evaluators"] = [{"binding_id": "example-embedding", "kind": "embedding",
                "manifest_key": "multilingual_e5_small", "cache_root": "/opt/enhancement/runtime/model-eval", "device": "cpu"}]
        config.write_text(json.dumps(core_config))
        try:
            if args.model_runtime:
                docker(["volume", "create", "--label", "enhancement-bench.model-cache=reviewed-v1",
                        "--label", "enhancement-bench.test=model-runtime", cache_volume])
                cache_created = True
                docker(["run", "--rm", "--network", "none", "--user", "0:0", "--read-only", "--cap-drop=ALL",
                        "--label", "enhancement-bench.test=model-runtime", "--mount", f"type=volume,src={cache_volume},dst=/fixture,volume-nocopy",
                        "--entrypoint", "python", args.bench_image, "-c",
                        "import pathlib,os; p=pathlib.Path('/fixture'); os.chmod(p,0o777); (p/'example-fixture.txt').write_text('synthetic-cache-fixture')"])
            docker(["run", "-d", "--name", namespace, "--label", "enhancement-bench.test=synthetic-smoke",
                    "--network", "none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                    "--group-add", "0", "--tmpfs", "/tmp:rw,nosuid,size=32m,mode=1777", "--tmpfs", "/data:rw,nosuid,size=32m,mode=1777",
                    "--mount", "type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock",
                    "--env", "SMOKE_CORE_IMAGE=" + image, "--env", "SMOKE_NAMESPACE=" + namespace,
                    "--env", "SMOKE_CONFIG_SOURCE=" + str(config),
                    "--env", "SMOKE_CA_SOURCE=" + str(cert),
                    "--env", "SMOKE_MODEL_RUNTIME=" + ("1" if args.model_runtime else "0"),
                    "--env", "SMOKE_MODEL_CACHE_VOLUME=" + cache_volume,
                    "--env", "ENHANCEMENT_CONSUMER_TOKEN=example-synthetic-token-not-a-secret",
                    "--entrypoint", "sleep", args.bench_image, "300"])
            for source, destination in ((Path(__file__).resolve(), "/tmp/docker_smoke.py"),
                    (root / "bench/definitions/example-widget.json", "/tmp/definition.json"),
                    (config, "/tmp/model-config.json"),
                    (cert, "/tmp/provider.crt"), (key, "/tmp/provider.key")):
                docker(["exec", "-i", namespace, "python", "-c",
                        "import pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())", destination],
                       input=source.read_bytes())
            output = docker(["exec", namespace, "python", "/tmp/docker_smoke.py", "--inner"], capture=True)
            print(output.decode().strip())
        finally:
            try:
                docker(["rm", "--force", namespace])
            finally:
                if cache_created:
                    docker(["volume", "rm", cache_volume])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("docker_smoke_failed") from None
