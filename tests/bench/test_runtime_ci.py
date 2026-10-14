import json
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from enhancement_bench.errors import BenchError
from enhancement_bench.runtime import DockerRuntime, DockerSettings, MODEL_CACHE_PATH, MODEL_CACHE_LABEL, VARIANT_LABEL

ROOT = Path(__file__).resolve().parents[2]


def test_container_command_preserves_loopback_and_ownership(monkeypatch):
    image = "registry.example.com/example/core@sha256:" + "a" * 64
    run_id = str(uuid4())
    calls = []

    def execute(command, **kwargs):
        calls.append((command, kwargs))
        stdout = json.dumps([image]).encode() if command[1:3] == ["image", "inspect"] else b""
        return subprocess.CompletedProcess(command, 0, stdout)

    monkeypatch.setattr(subprocess, "run", execute)
    runtime = DockerRuntime(DockerSettings(("registry.example.com/example/core",)))
    endpoint = runtime.launch({"id": run_id, "image": image, "container_name": "enhancement-bench-" + run_id})
    create, options = next((c, k) for c, k in calls if c[1] == "create")
    assert endpoint.url == "http://127.0.0.1:8787"
    assert "container:enhancement-bench-worker" in create
    assert "--publish" not in create and "0.0.0.0" not in create
    assert "--synthetic-benchmark" in create
    assert "--read-only" in create and "--cap-drop=ALL" in create
    assert endpoint.token not in " ".join(create)
    assert endpoint.token == options["env"]["ENHANCEMENT_API_TOKEN"]
    assert "--mount" not in create
    assert runtime.settings.port == 8787


def test_cleanup_rejects_foreign_container_label(monkeypatch):
    run_id = str(uuid4())
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, b"example-foreign-owner\n")

    monkeypatch.setattr(subprocess, "run", execute)
    runtime = DockerRuntime(DockerSettings(("registry.example.com/example/core",)))
    with pytest.raises(BenchError, match="container_ownership_mismatch"):
        runtime.cleanup(run_id, "enhancement-bench-" + run_id)
    assert not any(c[1] == "rm" for c in calls)


def test_daemon_unavailable_never_counts_as_successful_cleanup(monkeypatch):
    def execute(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, b"")

    monkeypatch.setattr(subprocess, "run", execute)
    runtime = DockerRuntime(DockerSettings(()))
    run_id = str(uuid4())
    with pytest.raises(BenchError, match="container_operation_failed"):
        runtime.cleanup(run_id, "enhancement-bench-" + run_id)


def ci_module():
    from enhancement_bench import core_images
    return core_images


def test_ci_definition_only_changes_reuse_image(monkeypatch):
    ci = ci_module()
    monkeypatch.setattr(ci, "core_version", lambda: "0.1.0")
    monkeypatch.setattr(ci, "build_hash", lambda **kwargs: "example-hash")
    monkeypatch.setattr(ci, "existing_tag", lambda tag: True)
    image = "registry.example.com/example/core@sha256:" + "a" * 64
    calls = []

    def command(args, **kwargs):
        calls.append(args)
        value = [{"RepoDigests": [image], "Config": {"Labels": {"example.enhancement.build-input-sha256": "example-hash", "example.enhancement.build-variant": "default"}}}]
        return subprocess.CompletedProcess(args, 0, json.dumps(value).encode())

    monkeypatch.setattr(ci, "command", command)
    assert ci.resolve_or_publish("registry.example.com/example/core") == ("0.1.0", image, "reused")
    assert not any("--push" in call for call in calls)


def test_ci_changed_code_cannot_overwrite_existing_version(monkeypatch):
    ci = ci_module()
    monkeypatch.setattr(ci, "core_version", lambda: "0.1.0")
    monkeypatch.setattr(ci, "build_hash", lambda **kwargs: "new-code")
    monkeypatch.setattr(ci, "existing_tag", lambda tag: True)
    monkeypatch.setattr(ci, "command", lambda args, **kwargs: subprocess.CompletedProcess(args, 0,
        json.dumps([{"Config": {"Labels": {"example.enhancement.build-input-sha256": "old-code", "example.enhancement.build-variant": "default"}}}]).encode()))
    with pytest.raises(BenchError, match="core_version_reused_for_changed_code"):
        ci.resolve_or_publish("registry.example.com/example/core", allow_publish=True)


def test_registry_network_failure_is_not_absent_tag(monkeypatch):
    ci = ci_module()
    monkeypatch.setattr(ci, "command", lambda args, **kwargs: subprocess.CompletedProcess(args, 1, b"", b"connection refused"))
    with pytest.raises(BenchError, match="registry_tag_state_unconfirmed"):
        ci.existing_tag("registry.example.com/example/core:core-0.1.0")


def test_static_consumer_has_no_container_launcher_or_bench_secrets():
    config = (ROOT / "deployment/bench/compose.yaml").read_text()
    consumer = config.split("\n  consumer:\n", 1)[1].split("\n  consumer-relay:\n", 1)[0]
    assert "docker.sock" not in consumer
    assert "BENCH_OPERATOR_TOKEN" not in consumer
    assert "network_mode: none" in consumer
    assert "BENCH_GATEWAY_BRIDGE" in consumer
    relay = config.split("\n  consumer-relay:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    assert "network_mode: service:bench-worker" in relay
    assert "TOKEN" not in relay and "docker.sock" not in relay and "ports:" not in relay
    assert "ports:" not in consumer
    assert 'ports: ["127.0.0.1:8088:8088"]' in config


def model_settings(tmp_path, **changes):
    device = changes.get("model_device", "cpu")
    config = tmp_path / "core.json"
    config.write_text(json.dumps({"evaluators": [{"cache_root": MODEL_CACHE_PATH, "device": device}]}))
    values = dict(core_variant="models", model_cache_volume="enhancement-bench-models-example",
                  config_source="/srv/example/bench/core.json", config_path=config, memory="4g", cpus="2.5")
    return DockerSettings(("registry.example.com/example/core",), **(values | changes))


def model_commands(monkeypatch, settings, *, variant="models", volume_changes=None):
    image = "registry.example.com/example/core@sha256:" + "a" * 64
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        if command[1:3] == ["volume", "inspect"]:
            stdout = json.dumps({"Name": settings.model_cache_volume, "Driver": "local", "Options": None,
                                 "Labels": {MODEL_CACHE_LABEL: "reviewed-v1"}} | (volume_changes or {})).encode()
        elif command[1:3] == ["image", "inspect"]:
            stdout = json.dumps([image]).encode() if "RepoDigests" in command[4] else variant.encode()
        else:
            stdout = b""
        return subprocess.CompletedProcess(command, 0, stdout)

    monkeypatch.setattr(subprocess, "run", execute)
    run_id = str(uuid4())
    return calls, {"id": run_id, "image": image, "container_name": "enhancement-bench-" + run_id,
                   "memory": "999g", "docker_args": ["--privileged"]}


@pytest.mark.parametrize("device,gpu", [("cpu", None), ("cuda", "0")])
def test_model_cache_resources_and_single_gpu_are_operator_owned(monkeypatch, tmp_path, device, gpu):
    settings = model_settings(tmp_path, model_device=device, gpu_device=gpu)
    calls, run = model_commands(monkeypatch, settings)
    DockerRuntime(settings).launch(run)
    create = next(c for c in calls if c[1] == "create")
    assert f"type=volume,src={settings.model_cache_volume},dst={MODEL_CACHE_PATH},readonly,volume-nocopy" in create
    assert create[create.index("--memory") + 1] == "4g"
    assert create[create.index("--cpus") + 1] == "2.5"
    assert "--privileged" not in create and "999g" not in create
    assert ("--gpus" in create) == (device == "cuda")
    if gpu:
        assert create[create.index("--gpus") + 1] == "device=0"


@pytest.mark.parametrize("changes", [
    {"memory": "0g"}, {"memory": "129g"}, {"memory": "1g,privileged"},
    {"cpus": "NaN"}, {"cpus": "0"}, {"cpus": "65"},
    {"model_device": "mps"}, {"model_device": "cuda"},
    {"model_device": "cuda", "gpu_device": "all"}, {"gpu_device": "0"},
    {"model_cache_volume": "/srv/example/private"}, {"model_cache_volume": "enhancement-bench-models-example,volume-opt=device=/"},
    {"core_variant": "default"},
])
def test_invalid_model_runtime_settings_reject_before_docker(tmp_path, changes):
    with pytest.raises(BenchError):
        model_settings(tmp_path, **changes)


@pytest.mark.parametrize("volume_changes", [
    {"Options": {"type": "none", "device": "/", "o": "bind"}},
    {"Driver": "example-network-driver"}, {"Labels": {}}, {"Name": "example-other"},
])
def test_model_mount_rejects_unreviewed_or_host_backed_volumes(monkeypatch, tmp_path, volume_changes):
    settings = model_settings(tmp_path)
    calls, run = model_commands(monkeypatch, settings, volume_changes=volume_changes)
    with pytest.raises(BenchError, match="model_cache_volume_unconfirmed"):
        DockerRuntime(settings).launch(run)
    assert not any(c[1] == "create" for c in calls)


def test_model_config_and_variant_must_match_runtime(monkeypatch, tmp_path):
    settings = model_settings(tmp_path)
    calls, run = model_commands(monkeypatch, settings, variant="default")
    with pytest.raises(BenchError, match="model_image_variant_unconfirmed"):
        DockerRuntime(settings).launch(run)
    settings.config_path.write_text(json.dumps({"evaluators": [{"cache_root": "/tmp/example-cache", "device": "cpu"}]}))
    with pytest.raises(BenchError, match="model_config_runtime_mismatch"):
        DockerRuntime(settings).launch(run)
    settings.config_path.write_text(json.dumps({"evaluators": [{"cache_root": MODEL_CACHE_PATH, "device": "cuda"}]}))
    with pytest.raises(BenchError, match="model_config_runtime_mismatch"):
        DockerRuntime(settings).launch(run)
    assert not any(c[1] == "create" for c in calls)


def test_runtime_environment_defaults_and_explicit_models(tmp_path):
    default = DockerSettings.from_environment((), {})
    assert (default.core_variant, default.memory, default.cpus, default.model_device) == ("default", "1g", "1", "cpu")
    assert default.model_cache_volume is None and default.gpu_device is None
    configured = DockerSettings.from_environment((), {
        "BENCH_CORE_VARIANT": "models", "BENCH_MODEL_CACHE_VOLUME": "enhancement-bench-models-example",
        "BENCH_CORE_CONFIG_PATH": str(tmp_path / "core.json"), "BENCH_CORE_CONFIG_SOURCE": "/srv/example/bench/core.json",
        "BENCH_CORE_MEMORY": "4g", "BENCH_CORE_CPUS": "2", "BENCH_MODEL_DEVICE": "cuda", "BENCH_GPU_DEVICE": "0"})
    assert configured.core_variant == "models" and configured.model_device == "cuda" and configured.gpu_device == "0"


def test_build_variants_have_distinct_fingerprints(tmp_path):
    ci = ci_module()
    for name in ("pyproject.toml", "uv.lock", "README.md"):
        (tmp_path / name).write_text("example-build-input")
    assert ci.build_hash(tmp_path, variant="default") != ci.build_hash(tmp_path, variant="models")
    with pytest.raises(BenchError, match="unsupported_build_variant"):
        ci.build_hash(tmp_path, variant="unreviewed")


def test_build_fingerprint_ignores_generated_metadata_but_tracks_source(tmp_path):
    ci = ci_module()
    for name in ("pyproject.toml", "uv.lock", "README.md"):
        (tmp_path / name).write_text("example-build-input")
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir()
    source.write_text("EXAMPLE = 1\n")
    before = ci.build_hash(tmp_path)
    for directory in ("example.egg-info", "example.dist-info", "__pycache__"):
        metadata = source.parent / directory
        metadata.mkdir()
        (metadata / "example.txt").write_text("example generated metadata")
    assert ci.build_hash(tmp_path) == before
    source.write_text("EXAMPLE = 2\n")
    assert ci.build_hash(tmp_path) != before


def test_models_variant_uses_separate_tag_build_arg_and_label(monkeypatch):
    ci = ci_module()
    monkeypatch.setattr(ci, "core_version", lambda: "0.1.0")
    variants, tags, calls = [], [], []
    monkeypatch.setattr(ci, "build_hash", lambda **kwargs: variants.append(kwargs["variant"]) or "example-models-hash")
    monkeypatch.setattr(ci, "existing_tag", lambda tag: tags.append(tag) or False)

    def command(args, **kwargs):
        calls.append(args)
        Path(args[args.index("--metadata-file") + 1]).write_text(json.dumps({"containerimage.digest": "sha256:" + "a" * 64}))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(ci, "command", command)
    version, image, action = ci.resolve_or_publish("registry.example.com/example/core", variant="models", allow_publish=True)
    assert variants == ["models"] and tags == ["registry.example.com/example/core:core-0.1.0-models"]
    assert "ENHANCEMENT_WITH_MODELS=1" in calls[0] and f"{VARIANT_LABEL}=models" in calls[0]
    assert action == "built" and image.endswith("@sha256:" + "a" * 64)


def test_reuse_rejects_different_build_variant(monkeypatch):
    ci = ci_module()
    monkeypatch.setattr(ci, "core_version", lambda: "0.1.0")
    monkeypatch.setattr(ci, "build_hash", lambda **kwargs: "example-hash")
    monkeypatch.setattr(ci, "existing_tag", lambda tag: True)
    monkeypatch.setattr(ci, "command", lambda args, **kwargs: subprocess.CompletedProcess(args, 0,
        json.dumps([{"Config": {"Labels": {VARIANT_LABEL: "default", "example.enhancement.build-input-sha256": "example-hash"}}}]).encode()))
    with pytest.raises(BenchError, match="core_image_variant_mismatch"):
        ci.resolve_or_publish("registry.example.com/example/core", variant="models", allow_publish=True)
