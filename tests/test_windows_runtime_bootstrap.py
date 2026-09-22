from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from prompt_enhancer.infrastructure import windows_runtime_bootstrap as runtime_bootstrap

from prompt_enhancer.infrastructure.windows_runtime_bootstrap import WindowsRuntimeBootstrapError, bootstrap_current_embedded_windows_runtime, bootstrap_windows_runtime


class _Handle:
    def __init__(self): self.closed = False
    def close(self): self.closed = True


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "staged"; root.mkdir()
    for name in ("win32", "win32/lib", "pythonwin", "pywin32_system32"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def test_explicit_app_local_paths_and_dll_handle_lifetime(tmp_path: Path):
    root = _root(tmp_path); paths = ["base"]; calls: list[str] = []; handle = _Handle()
    value = bootstrap_windows_runtime(staged_root=root, path_list=paths, add_dll_directory=lambda path: calls.append(path) or handle)
    assert [path.relative_to(root).as_posix() for path in value.import_paths] == ["win32", "win32/lib", "pythonwin"]
    assert calls == [str(root / "pywin32_system32")] and value.site_enabled_by_bootstrap is False and value.pth_executed_by_bootstrap is False
    assert paths[:3] == [str(root / "win32"), str(root / "win32/lib"), str(root / "pythonwin")]
    value.close(); assert handle.closed is True and paths == ["base"]


def test_missing_paths_never_call_loader(tmp_path: Path):
    root = _root(tmp_path); (root / "pythonwin").rmdir(); calls = []
    with pytest.raises(WindowsRuntimeBootstrapError): bootstrap_windows_runtime(staged_root=root, path_list=[], add_dll_directory=lambda path: calls.append(path))
    assert calls == []


def test_reparse_directory_never_reaches_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = _root(tmp_path); calls = []; original = Path.lstat
    def lstat(path: Path):
        if path == root / "pythonwin": return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original(path)
    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(WindowsRuntimeBootstrapError): bootstrap_windows_runtime(staged_root=root, path_list=[], add_dll_directory=lambda path: calls.append(path))
    assert calls == []


def test_loader_failure_rolls_back_path_and_handles(tmp_path: Path):
    root = _root(tmp_path); paths = []; handle = _Handle()
    def fail(path: str):
        del path; raise OSError("synthetic")
    with pytest.raises(WindowsRuntimeBootstrapError): bootstrap_windows_runtime(staged_root=root, path_list=paths, add_dll_directory=fail)
    assert paths == [] and handle.closed is False


def test_close_is_idempotent_and_preserves_later_equal_path(tmp_path: Path):
    root = _root(tmp_path); paths = []; handle = _Handle()
    value = bootstrap_windows_runtime(staged_root=root, path_list=paths, add_dll_directory=lambda path: handle)
    owned = paths[0]; paths.remove(owned); paths.append(str(root / "win32"))
    value.close(); value.close()
    assert handle.closed is True and paths == [str(root / "win32")]

@pytest.mark.parametrize("content",["python313.zip\n.\n", "python313.zip\nimport site\n", "python313.zip\nunsafe-directory\n"])
def test_current_embedded_detection_requires_exact_isolated_pth(tmp_path: Path,content: str):
    root=_root(tmp_path);executable=root/'python.exe';executable.write_bytes(b'x');(root/'python313._pth').write_text(content);paths=[];handle=_Handle()
    if content=="python313.zip\n.\n":
        value=bootstrap_current_embedded_windows_runtime(platform='nt',executable=str(executable),version=(3,13),add_dll_directory=lambda _:handle,path_list=paths)
        assert value is not None;value.close()
    else:
        with pytest.raises(WindowsRuntimeBootstrapError):bootstrap_current_embedded_windows_runtime(platform='nt',executable=str(executable),version=(3,13),add_dll_directory=lambda _:handle,path_list=paths)
    assert paths==[]

def test_current_embedded_detection_rejects_reparse_marker_before_loader(tmp_path: Path,monkeypatch: pytest.MonkeyPatch):
    root=_root(tmp_path);executable=root/'python.exe';executable.write_bytes(b'x');marker=root/'python313._pth';marker.write_text('python313.zip\n.\n');original=Path.lstat;calls=[]
    def lstat(path: Path):
        if path==marker:return SimpleNamespace(st_mode=stat.S_IFREG,st_file_attributes=0x400,st_size=1,st_mtime_ns=1,st_ctime_ns=1)
        return original(path)
    monkeypatch.setattr(Path,'lstat',lstat)
    with pytest.raises(WindowsRuntimeBootstrapError):bootstrap_current_embedded_windows_runtime(platform='nt',executable=str(executable),version=(3,13),add_dll_directory=lambda _:calls.append(1),path_list=[])
    assert calls==[]

def test_current_embedded_detection_rejects_oversized_marker(tmp_path: Path):
    root=_root(tmp_path);executable=root/'python.exe';executable.write_bytes(b'x');(root/'python313._pth').write_text('x'*4097);calls=[]
    with pytest.raises(WindowsRuntimeBootstrapError):bootstrap_current_embedded_windows_runtime(platform='nt',executable=str(executable),version=(3,13),add_dll_directory=lambda _:calls.append(1),path_list=[])
    assert calls==[]

def test_current_detection_is_noop_without_embedded_marker_or_off_windows(tmp_path: Path):
    root=_root(tmp_path);executable=root/'python.exe';executable.write_bytes(b'x');calls=[]
    assert bootstrap_current_embedded_windows_runtime(platform='nt',executable=str(executable),version=(3,13),add_dll_directory=lambda _:calls.append(1),path_list=[]) is None
    assert bootstrap_current_embedded_windows_runtime(platform='posix',executable=str(executable),version=(3,13),add_dll_directory=lambda _:calls.append(1),path_list=[]) is None
    assert calls==[]


def _marker_snapshots(tmp_path, monkeypatch, *, changed=None, birthtime=True, descriptor_ctime=200):
    root = _root(tmp_path)
    executable = root / "python.exe"
    executable.write_bytes(b"synthetic")
    marker = root / "python313._pth"
    content = b"python313.zip\n.\n"
    marker.write_bytes(content)
    common = dict(
        st_mode=stat.S_IFREG | 0o600, st_file_attributes=0,
        st_dev=11, st_ino=22, st_nlink=1, st_size=len(content), st_mtime_ns=300,
        st_birthtime_ns=100,
    )
    if not birthtime:
        common.pop("st_birthtime_ns")
    snapshots = {
        "before": dict(common, st_ctime_ns=100),
        "opened": dict(common, st_ctime_ns=descriptor_ctime),
        "read_completed": dict(common, st_ctime_ns=descriptor_ctime),
        "after": dict(common, st_ctime_ns=100),
    }
    if changed is not None:
        phase, field, value = changed
        snapshots[phase][field] = value
    path_results = iter(("before", "after"))
    fd_results = iter(("opened", "read_completed"))
    original = Path.lstat

    def lstat(path):
        if path == marker:
            return SimpleNamespace(**snapshots[next(path_results)])
        return original(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(runtime_bootstrap.os, "fstat", lambda _: SimpleNamespace(**snapshots[next(fd_results)]))
    return root, executable


def test_marker_accepts_different_cross_api_ctime_with_equal_birthtime(tmp_path, monkeypatch):
    root, executable = _marker_snapshots(tmp_path, monkeypatch)
    paths = []
    handle = _Handle()
    value = bootstrap_current_embedded_windows_runtime(
        platform="nt", executable=str(executable), version=(3, 13),
        add_dll_directory=lambda _: handle, path_list=paths,
    )
    assert value is not None and len(paths) == 3
    value.close()
    assert paths == [] and handle.closed


@pytest.mark.parametrize("descriptor_ctime", [100, 200])
def test_marker_without_birthtime_requires_cross_api_ctime_equality(tmp_path, monkeypatch, descriptor_ctime):
    root, _ = _marker_snapshots(
        tmp_path, monkeypatch, birthtime=False, descriptor_ctime=descriptor_ctime,
    )
    if descriptor_ctime == 100:
        assert runtime_bootstrap._isolated_pth(root, 3, 13) is True
    else:
        with pytest.raises(WindowsRuntimeBootstrapError, match="path is unsafe"):
            runtime_bootstrap._isolated_pth(root, 3, 13)


@pytest.mark.parametrize(("phase", "field", "value"), [
    ("opened", "st_ino", 23), ("after", "st_ino", 23),
    ("opened", "st_dev", 12), ("after", "st_dev", 12),
    ("opened", "st_ino", 0), ("before", "st_ino", 0),
    ("opened", "st_birthtime_ns", 101), ("after", "st_birthtime_ns", 101),
    ("opened", "st_size", 17), ("read_completed", "st_size", 17),
    ("opened", "st_mtime_ns", 301), ("read_completed", "st_mtime_ns", 301),
    ("after", "st_mtime_ns", 301),
    ("opened", "st_nlink", 2), ("read_completed", "st_nlink", 2), ("after", "st_nlink", 2),
    ("read_completed", "st_ctime_ns", 201), ("after", "st_ctime_ns", 101),
    ("opened", "st_file_attributes", 0x400),
    ("read_completed", "st_file_attributes", 0x400),
    ("after", "st_file_attributes", 0x400),
    ("opened", "st_mode", stat.S_IFLNK | 0o600),
    ("after", "st_mode", stat.S_IFDIR | 0o600),
])
def test_marker_rejects_identity_mutation_reparse_and_snapshot_changes(
    tmp_path, monkeypatch, phase, field, value,
):
    _, executable = _marker_snapshots(tmp_path, monkeypatch, changed=(phase, field, value))
    calls = []
    paths = []
    with pytest.raises(WindowsRuntimeBootstrapError, match="path is unsafe"):
        bootstrap_current_embedded_windows_runtime(
            platform="nt", executable=str(executable), version=(3, 13),
            add_dll_directory=lambda _: calls.append(True), path_list=paths,
        )
    assert not calls and not paths
