import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from enhancement_bench import core_images
from enhancement_bench.errors import BenchError

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "registry.example.com/example/core"
IMAGE = REPOSITORY + "@sha256:" + "a" * 64
REVISION = "b" * 40


@pytest.fixture
def release_module(monkeypatch):
    spec = importlib.util.spec_from_file_location("core_release", ROOT / "bench/core_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(core_images, "core_version", lambda: "0.1.0")
    monkeypatch.setattr(core_images, "build_hash", lambda **kwargs: "c" * 64)
    return module


@pytest.mark.parametrize("version", ["0.1.0", "0.2.0"])
def test_experiment_resolution_never_builds_a_missing_version(monkeypatch, version):
    monkeypatch.setattr(core_images, "core_version", lambda: "0.1.0")
    monkeypatch.setattr(core_images, "build_hash", lambda **kwargs: "c" * 64)
    monkeypatch.setattr(core_images, "existing_tag", lambda tag: False)
    monkeypatch.setattr(core_images, "command", lambda *args, **kwargs: pytest.fail("must not build or push"))
    with pytest.raises(BenchError, match="core_release_required"):
        core_images.resolve_existing(REPOSITORY, version=version)


def test_release_validates_source_then_publishes_and_verifies_without_definitions(release_module, monkeypatch):
    events = []
    monkeypatch.setattr(core_images, "command", lambda args, **kwargs:
                        subprocess.CompletedProcess(args, 0, REVISION.encode()))

    def publish(repository, **kwargs):
        events.append(("publish", repository, kwargs))
        return "0.1.0", IMAGE, "built"

    monkeypatch.setattr(core_images, "resolve_or_publish", publish)
    monkeypatch.setattr(release_module, "verify_runtime", lambda *args: events.append(("verify", *args)))
    receipt = release_module.release(REPOSITORY, "0.1.0", REVISION, "models")
    assert events == [
        ("publish", REPOSITORY, {"version": "0.1.0", "variant": "models", "allow_publish": True}),
        ("verify", IMAGE, "0.1.0", "models"),
    ]
    assert receipt == {
        "schemaVersion": "core-release/v1", "coreVersion": "0.1.0", "variant": "models",
        "image": IMAGE, "buildInputSha256": "c" * 64, "validatedSourceRevision": REVISION,
        "action": "built", "runtimeVerified": True,
    }


@pytest.mark.parametrize("changes,code", [
    ({"version": "0.2.0"}, "release_version_must_match_source"),
    ({"repository": "example.invalid/repo:latest"}, "invalid_image_repository"),
    ({"source_revision": "example-ref"}, "release_source_revision_invalid"),
    ({"source_revision": "d" * 40}, "release_source_revision_mismatch"),
    ({"variant": "unreviewed"}, "unsupported_build_variant"),
])
def test_release_rejects_wrong_identity_before_registry_access(release_module, monkeypatch, changes, code):
    monkeypatch.setattr(core_images, "command", lambda args, **kwargs:
                        subprocess.CompletedProcess(args, 0, REVISION.encode()))
    monkeypatch.setattr(core_images, "resolve_or_publish", lambda *args, **kwargs: pytest.fail("registry must not be reached"))
    values = dict(repository=REPOSITORY, version="0.1.0", source_revision=REVISION, variant="default")
    with pytest.raises(BenchError, match=code):
        release_module.release(**(values | changes))


@pytest.mark.parametrize("variant", ["default", "models"])
def test_runtime_probe_is_offline_bounded_and_cleans_only_its_container(release_module, monkeypatch, variant):
    calls = []

    def command(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, b"")

    monkeypatch.setattr(core_images, "command", command)
    release_module.verify_runtime(IMAGE, "0.1.0", variant)
    run, options = calls[0]
    name = run[run.index("--name") + 1]
    assert name.startswith("enhancement-core-release-")
    assert run[run.index("--network") + 1] == "none"
    assert "--read-only" in run and "--cap-drop=ALL" in run
    assert "--volume" not in run and "--mount" not in run and "--env" not in run
    assert run[-2:] == ["0.1.0", variant] and options["timeout"] == 60
    assert calls[1][0] == ["docker", "rm", "--force", name]
    assert calls[2][0][3:5] == ["--filter", "name=^/" + name + "$"]


def test_failed_runtime_probe_still_checks_cleanup(release_module, monkeypatch):
    calls = []

    def command(args, **kwargs):
        calls.append(args)
        if args[:2] == ["docker", "run"]:
            raise BenchError("publication_command_unconfirmed")
        return subprocess.CompletedProcess(args, 0, b"")

    monkeypatch.setattr(core_images, "command", command)
    with pytest.raises(BenchError, match="publication_command_unconfirmed"):
        release_module.verify_runtime(IMAGE, "0.1.0", "default")
    assert [args[1] for args in calls] == ["run", "rm", "ps"]


def test_unconfirmed_cleanup_fails_the_release_probe(release_module, monkeypatch):
    monkeypatch.setattr(core_images, "command", lambda args, **kwargs:
        subprocess.CompletedProcess(args, 0, b"example-container" if args[1] == "ps" else b""))
    with pytest.raises(BenchError, match="release_probe_cleanup_unconfirmed"):
        release_module.verify_runtime(IMAGE, "0.1.0", "default")


def test_release_cli_check_mode_has_no_publication_effects(release_module, monkeypatch, capsys):
    monkeypatch.setattr(core_images, "command", lambda args, **kwargs:
                        subprocess.CompletedProcess(args, 0, REVISION.encode()))
    monkeypatch.setattr(release_module, "release", lambda *args: pytest.fail("check must not publish"))
    monkeypatch.setattr(sys, "argv", ["core_release.py", "--check", "--repository", REPOSITORY,
                                     "--version", "0.1.0", "--source-revision", REVISION])
    release_module.main()
    assert "no image published" in capsys.readouterr().out


def test_failed_verification_writes_no_success_receipt(release_module, monkeypatch, tmp_path, capsys):
    output = tmp_path / "receipt.json"
    monkeypatch.setattr(core_images, "command", lambda args, **kwargs:
                        subprocess.CompletedProcess(args, 0, REVISION.encode()))
    monkeypatch.setattr(core_images, "resolve_or_publish", lambda *args, **kwargs: ("0.1.0", IMAGE, "built"))
    monkeypatch.setattr(release_module, "verify_runtime", lambda *args:
                        (_ for _ in ()).throw(BenchError("example_probe_failed")))
    monkeypatch.setattr(sys, "argv", ["core_release.py", "--allow-publish", "--repository", REPOSITORY,
                                     "--version", "0.1.0", "--source-revision", REVISION, "--output", str(output)])
    with pytest.raises(SystemExit, match="core_release_failed"):
        release_module.main()
    assert not output.exists() and not capsys.readouterr().out


def test_workflows_separate_manual_core_publication_from_experiment_delivery():
    core = yaml.safe_load((ROOT / ".github/workflows/bench-core-publish.yml").read_text())
    experiment = yaml.safe_load((ROOT / ".github/workflows/bench-publish.yml").read_text())
    assert set(core.get("on", core.get(True))) == {"workflow_dispatch"}
    job = core["jobs"]["publish"]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert job["env"]["CORE_SOURCE_REVISION"] == "${{ inputs.source_revision }}"
    assert core.get("on", core.get(True))["workflow_dispatch"]["inputs"]["source_revision"]["required"] is True
    assert job["permissions"]["packages"] == "write"
    assert core["concurrency"]["cancel-in-progress"] is False
    core_commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "bench/core_release.py --allow-publish" in core_commands
    assert "bench/ci.py" not in core_commands and "enhancement_bench.cli deliver" not in core_commands
    assert "BENCH_DELIVERY_URL" not in json.dumps(core) and "BENCH_CF_ACCESS" not in json.dumps(core)
    assert experiment["jobs"]["publish"]["permissions"]["packages"] == "read"
    experiment_commands = "\n".join(step.get("run", "") for step in experiment["jobs"]["publish"]["steps"])
    assert "--allow-publish" not in experiment_commands and "core_release.py" not in experiment_commands
    assert "enhancement_bench.cli deliver" in experiment_commands
