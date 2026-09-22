import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from prompt_enhancer.infrastructure.windows_dependency_preparation import WindowsDependencyPreparationReport
from prompt_enhancer.infrastructure.windows_wheel_acquisition import WindowsWheelAcquisitionError, acquire_windows_wheels
from prompt_enhancer.infrastructure.windows_wheel_inventory import WindowsWheelArtifact, WindowsWheelInventory, WindowsWheelTarget


class _Response:
    def __init__(self, url: str, data: bytes, status: int = 200): self.url, self.data, self.status, self.position = url, data, status, 0
    def read_chunk(self, size: int, timeout_seconds: float) -> bytes:
        value = self.data[self.position:self.position + size]; self.position += len(value); return value
    def close(self) -> None: pass


def _plan(tmp_path: Path, *, url: str = "https://files.pythonhosted.org/packages/a/b/demo-1.0-py3-none-any.whl", data: bytes = b"wheel"):
    digest = hashlib.sha256(data).hexdigest(); artifact = WindowsWheelArtifact("demo", "1.0", "demo-1.0-py3-none-any.whl", digest, len(data))
    lock = tmp_path / "uv.lock"; lock.write_text(f'''version = 1\n[[package]]\nname = "demo"\nversion = "1.0"\nwheels = [{{ url = "{url}", hash = "sha256:{digest}", size = {len(data)} }}]\n''')
    lock_hash = hashlib.sha256(lock.read_bytes()).hexdigest(); target = WindowsWheelTarget("3.13.0", "amd64")
    inventory = WindowsWheelInventory(target, (artifact,), "export", lock_hash, "p" * 64)
    report = WindowsDependencyPreparationReport(target, (artifact,), (), (), "p" * 64, lock_hash, "all", "export", (), False, False)
    return report, inventory, lock, artifact, data


def test_acquires_only_exact_lock_bound_bytes(tmp_path: Path):
    report, inventory, lock, artifact, data = _plan(tmp_path)
    result = acquire_windows_wheels(report=report, inventory=inventory, lockfile=lock, destination=tmp_path / "wheels", transport=lambda url, timeout: _Response(url, data))
    assert (tmp_path / "wheels" / artifact.filename).read_bytes() == data
    assert result.complete is False and result.release_accepted is False


@pytest.mark.parametrize("url", ["http://files.pythonhosted.org/packages/a/b/demo-1.0-py3-none-any.whl", "https://evil.example/packages/a/b/demo-1.0-py3-none-any.whl", "https://files.pythonhosted.org:444/packages/a/b/demo-1.0-py3-none-any.whl"])
def test_wrong_host_and_tampered_lock_are_rejected_before_network(tmp_path: Path, url: str):
    report, inventory, lock, _artifact, data = _plan(tmp_path, url=url)
    with pytest.raises(WindowsWheelAcquisitionError): acquire_windows_wheels(report=report, inventory=inventory, lockfile=lock, destination=tmp_path / "wheels", transport=lambda _url, _timeout: _Response("", data))


@pytest.mark.parametrize("response", [lambda url, data: _Response("https://files.pythonhosted.org/other", data), lambda url, data: _Response(url, b"bad"), lambda url, data: _Response(url, data + b"more")])
def test_redirect_hash_truncation_and_oversize_are_rejected(tmp_path: Path, response):
    report, inventory, lock, _artifact, _data = _plan(tmp_path)
    with pytest.raises(WindowsWheelAcquisitionError): acquire_windows_wheels(report=report, inventory=inventory, lockfile=lock, destination=tmp_path / "wheels", transport=lambda url, timeout: response(url, data))
    assert not (tmp_path / "wheels").exists() and not list(tmp_path.glob(".wheel-acquisition-incomplete-*"))


def test_network_failure_and_nooverwrite_are_rejected(tmp_path: Path):
    report, inventory, lock, _artifact, _data = _plan(tmp_path)
    with pytest.raises(WindowsWheelAcquisitionError): acquire_windows_wheels(report=report, inventory=inventory, lockfile=lock, destination=tmp_path / "wheels", transport=lambda url, timeout: (_ for _ in ()).throw(OSError()))
    (tmp_path / "wheels").mkdir()
    with pytest.raises(WindowsWheelAcquisitionError): acquire_windows_wheels(report=report, inventory=inventory, lockfile=lock, destination=tmp_path / "wheels", transport=lambda url, timeout: _Response(url, b""))


def test_late_eof_cannot_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    report, inventory, lock, _artifact, data = _plan(tmp_path)
    clock = iter((0.0, 0.0, 0.0, 1.0))
    monkeypatch.setattr("prompt_enhancer.infrastructure.windows_wheel_acquisition.time.monotonic", lambda: next(clock))
    with pytest.raises(WindowsWheelAcquisitionError): acquire_windows_wheels(report=report, inventory=inventory, lockfile=lock, destination=tmp_path / "wheels", transport=lambda url, timeout: _Response(url, b""), timeout_seconds=0.5)
    assert not (tmp_path / "wheels").exists()


def test_slow_read_receives_remaining_deadline_and_cannot_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    report, inventory, lock, _artifact, data = _plan(tmp_path)
    observed: list[float] = []
    class Slow(_Response):
        def read_chunk(self, size: int, timeout_seconds: float) -> bytes:
            observed.append(timeout_seconds); return super().read_chunk(size, timeout_seconds)
    clock = iter((0.0, 0.0, 0.0, 1.0))
    monkeypatch.setattr("prompt_enhancer.infrastructure.windows_wheel_acquisition.time.monotonic", lambda: next(clock))
    with pytest.raises(WindowsWheelAcquisitionError): acquire_windows_wheels(report=report, inventory=inventory, lockfile=lock, destination=tmp_path / "wheels", transport=lambda url, timeout: Slow(url, data), timeout_seconds=0.5)
    assert observed and 0 < observed[0] <= 0.5 and not (tmp_path / "wheels").exists()


def test_cli_rejects_target_mismatch_without_calling_acquirer(tmp_path: Path):
    report, inventory, lock, artifact, _data = _plan(tmp_path)
    report_path, inventory_path = tmp_path / "report.json", tmp_path / "inventory.json"
    report_path.write_text(json.dumps({"target": {"python_full_version": "3.12.0", "architecture": "amd64"}, "registry_wheels": [{"package": artifact.package, "version": artifact.version, "filename": artifact.filename, "sha256": artifact.sha256, "size_bytes": artifact.size_bytes}], "source_build_requirements": [], "prepared_source_wheels": [], "pyproject_sha256": report.pyproject_sha256, "lockfile_sha256": report.lockfile_sha256, "export_fingerprint": report.export_fingerprint, "registry_export_fingerprint": report.registry_export_fingerprint, "unresolved_blockers": [], "complete": False, "release_accepted": False}))
    inventory_path.write_text(json.dumps({"target": {"python_full_version": "3.13.0", "architecture": "amd64"}, "artifacts": [{"package": artifact.package, "version": artifact.version, "filename": artifact.filename, "sha256": artifact.sha256, "size_bytes": artifact.size_bytes}], "export_fingerprint": inventory.export_fingerprint, "lockfile_sha256": inventory.lockfile_sha256, "pyproject_sha256": inventory.pyproject_sha256, "complete": True}))
    spec = importlib.util.spec_from_file_location("acquire_windows_wheels_cli", Path(__file__).parents[1] / "scripts" / "acquire_windows_wheels.py")
    assert spec and spec.loader; module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    called = False
    def acquire(**kwargs):
        nonlocal called; called = True; raise AssertionError
    assert module.main(["--report", str(report_path), "--inventory", str(inventory_path), "--lockfile", str(lock), "--destination", str(tmp_path / "out")], acquire=acquire) == 2
    assert called is False
