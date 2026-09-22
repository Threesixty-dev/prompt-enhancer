import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest

spec = importlib.util.spec_from_file_location("npm_distribution_fixture", Path(__file__).resolve().parents[1] / "scripts/prepare_npm_distribution.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def archive(extra=()):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz", format=tarfile.USTAR_FORMAT) as tar:
        for name, value in [("package/package.json", b'{"name":"npm","version":"11.6.2"}'),
                            ("package/bin/npm-cli.js", b"// synthetic only")]:
            item = tarfile.TarInfo(name); item.size = len(value)
            tar.addfile(item, io.BytesIO(value))
        for item in extra:
            tar.addfile(item, io.BytesIO(bytes(item.size)) if item.isreg() else None)
    return out.getvalue()


def test_fresh_extraction_binds_exact_bytes_without_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "unused-home"))
    source = tmp_path / "npm.tgz"; source.write_bytes(archive())
    args = dict(archive_path=source, archive_size=source.stat().st_size, archive_sha256=p.digest(source.read_bytes()),
                npm_version="11.6.2", destination=tmp_path / "prepared")
    result = p.prepare(**args)
    assert result["files"] == 2 and not result["executed"]
    assert p.digest((args["destination"] / "manifest.json").read_bytes()) == result["manifest_sha256"]
    assert p.digest(source.read_bytes()) == args["archive_sha256"]
    assert str(tmp_path) not in json.dumps(result)
    with pytest.raises(p.FrontendDependencyPreparationError): p.prepare(**args)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "other/file", "package/../outside", "package/file:ads", "package/CON", "package/package.json", "package/PACKAGE.JSON"])
def test_unsafe_names_and_collisions_refused(name):
    item = tarfile.TarInfo(name)
    with tarfile.open(fileobj=io.BytesIO(archive([item])), mode="r:gz") as tar:
        with pytest.raises((p.FrontendDependencyPreparationError, ValueError)): p.members(tar)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE])
def test_links_and_special_members_refused(kind):
    item = tarfile.TarInfo("package/special"); item.type = kind
    if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE): item.linkname = "package/package.json"
    with tarfile.open(fileobj=io.BytesIO(archive([item])), mode="r:gz") as tar:
        with pytest.raises(p.FrontendDependencyPreparationError): p.members(tar)


def test_bounds_and_file_ancestor_refused(monkeypatch):
    item = tarfile.TarInfo("package/package.json/child")
    with tarfile.open(fileobj=io.BytesIO(archive([item])), mode="r:gz") as tar:
        with pytest.raises(p.FrontendDependencyPreparationError): p.members(tar)
    monkeypatch.setattr(p, "MAX_ENTRIES", 1)
    with tarfile.open(fileobj=io.BytesIO(archive()), mode="r:gz") as tar:
        with pytest.raises(p.FrontendDependencyPreparationError): p.members(tar)


@pytest.mark.parametrize("kind", ["version", "pin", "truncated", "extra", "manifest"])
def test_invalid_inputs_or_late_tamper_never_publish(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "unused-home"))
    data = archive()
    if kind == "truncated": data = data[:len(data) // 2]
    source = tmp_path / "npm.tgz"; source.write_bytes(data)
    args = dict(archive_path=source, archive_size=len(data), archive_sha256=p.digest(data),
                npm_version="11.6.2", destination=tmp_path / "prepared")
    if kind == "version": args["npm_version"] = "arbitrary receipt text"
    if kind == "pin": args["archive_sha256"] = "0" * 64
    original = p.pinned
    calls = 0
    def altered(*a, **kw):
        nonlocal calls
        result = original(*a, **kw); calls += 1
        if calls == 2 and kind in {"extra", "manifest"}:
            work = next(tmp_path.glob(".npm-distribution-*"))
            (work / ("extra.txt" if kind == "extra" else "manifest.json")).write_bytes(b"synthetic tamper")
        return result
    monkeypatch.setattr(p, "pinned", altered)
    with pytest.raises(p.FrontendDependencyPreparationError): p.prepare(**args)
    assert not args["destination"].exists()


@pytest.mark.parametrize("bound", ["MAX_FILE", "MAX_TOTAL"])
def test_file_and_aggregate_bounds_before_copy(monkeypatch, bound):
    monkeypatch.setattr(p, bound, 1)
    with tarfile.open(fileobj=io.BytesIO(archive()), mode="r:gz") as tar:
        with pytest.raises(p.FrontendDependencyPreparationError): p.members(tar)
