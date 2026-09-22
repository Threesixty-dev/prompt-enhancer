"""Synthetic planning tests: no candidate assembly or executable launch."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest


@pytest.fixture
def helper(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("candidate_helper", scripts / "prepare_msix_candidate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "stage_windows_release", lambda **kwargs: pytest.fail("no real staging"))
    return module


def inputs(helper):
    stage = {"artifacts": 43, "stage": {"files": [[f"synthetic/file-{i}.txt", 1, "a" * 64] for i in range(2578)]}}
    launchers = {"contract": "windows-native-launchers.v1", "files": copy.deepcopy(helper.LAUNCHERS),
                 "build_performed": True, "owned_cleanup_confirmed": True, "two_builds_identical": True}
    return stage, launchers


def plan(helper, stage, launchers):
    return helper.make_plan(stage, launchers, "b" * 40, "c" * 64, "d" * 64)


def test_exact_explicit_plan(helper):
    result = plan(helper, *inputs(helper))
    assert len(result.files) == 2584
    assert result.distributable is False
    assert {item.destination_relative_path for item in result.files} >= set(helper.LAUNCHERS)
    assert all(not item.source_relative_path.startswith("/") for item in result.files)


def test_explicit_stage_pin_propagates_to_all_stage_sources(helper):
    stage, launchers = inputs(helper)
    group = "windows-application-stage-43-python31315-review2"
    digest = "e" * 64
    result = helper.make_plan(
        stage, launchers, "b" * 40, digest, "d" * 64, stage_group=group
    )
    stage_files = result.files[:2578]
    assert all(item.source_relative_path.startswith(f"{group}/stage/") for item in stage_files)
    assert {item.name: item.sha256 for item in result.lockfile_hashes}["stage-input-manifest"] == digest


@pytest.mark.parametrize("group", (
    "../stage", "nested/stage", "nested\\stage", "C:stage", "NUL", "trailing.", "",
))
def test_stage_group_override_rejects_unsafe_components_before_io(helper, monkeypatch, group):
    monkeypatch.setattr(helper, "external", lambda *_args: pytest.fail("filesystem boundary must not run"))
    with pytest.raises(ValueError):
        helper.stage_pin(group, "e" * 64)


@pytest.mark.parametrize("group,digest", (
    ("review2", None), (None, "e" * 64), ("review2", "bad"),
    ("review2", "E" * 64), (True, "e" * 64),
))
def test_stage_override_requires_complete_well_formed_pin_before_io(helper, monkeypatch, group, digest):
    monkeypatch.setattr(helper, "external", lambda *_args: pytest.fail("filesystem boundary must not run"))
    with pytest.raises(ValueError):
        helper.stage_pin(group, digest)


def test_historical_stage_pin_defaults_are_preserved(helper):
    assert helper.stage_pin(None, None) == (helper.STAGE_GROUP, helper.STAGE_SHA)


def test_cli_stage_override_reaches_assembly(helper, monkeypatch, capsys):
    observed = {}
    def fake_assemble(arguments):
        observed["group"] = arguments.stage_group
        observed["sha256"] = arguments.stage_manifest_sha256
        observed["count"] = arguments.stage_file_count
        return {"passed": True}
    monkeypatch.setattr(helper, "assemble", fake_assemble)
    group = "windows-application-stage-43-python31315-review2"
    digest = "e" * 64
    args = [
        "--source-root", "synthetic", "--destination", "synthetic",
        "--manifest-output", "synthetic", "--stage-manifest-size", "1",
        "--launcher-manifest-size", "1", "--launcher-manifest-sha256", "a" * 64,
        "--git-revision", "b" * 40, "--stage-group", group,
        "--stage-manifest-sha256", digest, "--stage-file-count", "2582",
    ]
    assert helper.main(args) == 0
    assert observed == {"group": group, "sha256": digest, "count": 2582}
    assert json.loads(capsys.readouterr().out) == {"passed": True}


@pytest.mark.parametrize("name", ["../escape", "C:/escape", "bad\\name", "PromptEnhancer.exe", "AppxManifest.xml", "synthetic/file-1.txt", "synthetic"])
def test_invalid_paths_and_collisions(helper, name):
    stage, launchers = inputs(helper)
    stage["stage"]["files"][0][0] = name
    with pytest.raises(ValueError):
        plan(helper, stage, launchers)


@pytest.mark.parametrize("value", [True, -1, "1"])
def test_invalid_size(helper, value):
    stage, launchers = inputs(helper)
    stage["stage"]["files"][0][1] = value
    with pytest.raises(ValueError):
        plan(helper, stage, launchers)


def test_count_and_launcher_mismatch(helper):
    stage, launchers = inputs(helper)
    stage["stage"]["files"].pop()
    with pytest.raises(ValueError):
        plan(helper, stage, launchers)
    stage, launchers = inputs(helper)
    launchers["files"]["extra.exe"] = {"size": 1, "sha256": "a" * 64}
    with pytest.raises(ValueError):
        plan(helper, stage, launchers)


@pytest.mark.parametrize('count',[True,False,0,-1,50000,49995,'2582'])
def test_invalid_count_pin(helper,count):
    with pytest.raises(ValueError):helper.stage_count(count)


def test_custom_exact_count_and_mismatch(helper):
    stage,launchers=inputs(helper)
    stage['stage']['files'].extend([[f'synthetic/new-{i}.txt',1,'a'*64] for i in range(4)])
    result=helper.make_plan(stage,launchers,'b'*40,'c'*64,'d'*64,stage_group='review3',stage_file_count=2582)
    assert len(result.files)==2588
    with pytest.raises(ValueError):
        helper.make_plan(stage,launchers,'b'*40,'c'*64,'d'*64,stage_group='review3',stage_file_count=2581)
    assert helper.stage_count(helper.MAX_STAGED_FILES-6)==49994


@pytest.mark.parametrize('group,digest',[(None,None),('review3',None),(None,'a'*64)])
def test_custom_count_requires_explicit_complete_stage_pin_before_io(helper,monkeypatch,group,digest):
    from types import SimpleNamespace
    monkeypatch.setattr(helper,'external',lambda *args:pytest.fail('filesystem touched'))
    with pytest.raises(ValueError):
        helper.assemble(SimpleNamespace(stage_file_count=2582,stage_group=group,stage_manifest_sha256=digest))


@pytest.mark.parametrize("payload", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_bad_json(helper, tmp_path, payload):
    path = tmp_path / "synthetic.json"
    path.write_bytes(payload)
    with pytest.raises(ValueError):
        helper.pinned_json(path, len(payload), hashlib.sha256(payload).hexdigest())


def test_manifest_pin_and_bounds(helper, tmp_path):
    path = tmp_path / "synthetic.json"
    data = b'{"synthetic":true}'
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    assert helper.pinned_json(path, len(data), digest) == {"synthetic": True}
    for size, pin in [(len(data) + 1, digest), (len(data), "0" * 64), (True, digest), (helper.MAX_JSON + 1, digest)]:
        with pytest.raises(ValueError):
            helper.pinned_json(path, size, pin)


def test_exact_inventory_refuses_extras(helper, tmp_path):
    (tmp_path / "synthetic.txt").write_bytes(b"synthetic")
    helper.exact_tree(tmp_path, ["synthetic.txt"])
    with pytest.raises(ValueError):
        helper.exact_tree(tmp_path, [])


def test_generated_contract(helper):
    generated = helper.expected_generated()
    assert len(generated) == 4
    assert b'PromptEnhancerMetrics.exe' in generated["AppxManifest.xml"]
    assert b'Example.PromptEnhancer' in generated["AppxManifest.xml"]


def test_closed_argument_error(helper, capsys):
    assert helper.main(["--unknown", "synthetic-sensitive-canary"]) == 2
    output = capsys.readouterr()
    assert "synthetic-sensitive-canary" not in output.out + output.err
    assert json.loads(output.out)["passed"] is False


@pytest.mark.parametrize("raw", [r"\\example.invalid\share\candidate", r"\\?\D:\candidate",
    r"\\.\D:\candidate", r"\??\D:\candidate", r"D:candidate", r"D:\candidate:stream",
    r"D:\synthetic\..\candidate", r"D:\synthetic\NUL", r"D:\synthetic\trailing."])
def test_external_rejects_before_filesystem(helper, monkeypatch, raw):
    def forbidden(*args, **kwargs):
        pytest.fail("filesystem must not be accessed")
    monkeypatch.setattr(Path, "lstat", forbidden)
    monkeypatch.setattr(Path, "home", forbidden)
    with pytest.raises(ValueError):
        helper.external(PureWindowsPath(raw))


def test_external_preserves_posix_absolute(helper, monkeypatch):
    monkeypatch.setattr(helper, "REPOSITORY", PurePosixPath("/synthetic/repository"))
    monkeypatch.setattr(Path, "home", lambda: PurePosixPath("/synthetic/home"))
    path = PurePosixPath("/synthetic/artifacts/candidate")
    assert helper.external(path) == path


def test_closed_staging_phase(helper, monkeypatch, capsys):
    def fail(args):
        raise helper.CandidatePhaseError("arbitrary-sensitive-canary")
    monkeypatch.setattr(helper, "assemble", fail)
    args = ["--source-root", "synthetic", "--destination", "synthetic", "--manifest-output", "synthetic",
            "--stage-manifest-size", "1", "--launcher-manifest-size", "1",
            "--launcher-manifest-sha256", "a" * 64, "--git-revision", "b" * 40]
    assert helper.main(args) == 2
    output = capsys.readouterr()
    assert "arbitrary-sensitive-canary" not in output.out + output.err
    assert json.loads(output.out)["error_code"] == "candidate_staging_failed"
