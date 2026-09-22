"""Pure launcher source/build-command contracts, not native execution proof."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import os
import hashlib

import pytest


@pytest.fixture
def helper(monkeypatch):
    from prompt_enhancer.application import owned_process
    monkeypatch.setattr(owned_process, "run_owned_process", lambda *a, **k: pytest.fail("no native launch"))
    spec = importlib.util.spec_from_file_location("synthetic_launcher_builder", Path(__file__).parents[1] / "scripts" / "prepare_windows_launchers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fixed_gui_commands_and_mitigations(helper):
    compile_command, link = helper.commands(Path("toolchain"), Path("build"), False)
    assert "-nostdinc" in compile_command
    assert "-fno-stack-protector" not in compile_command
    for option in ("--no-insert-timestamp", "--dynamicbase", "--nxcompat", "--high-entropy-va"):
        assert option in link
    assert link[link.index("--subsystem") + 1] == "windows"
    assert link[link.index("--entry") + 1] == "launcher_entry"
    assert "-DMETRICS_ENTRY=1" in helper.commands(Path("toolchain"), Path("build"), True)[0]


def test_fixed_entrypoints_no_subprocess_and_no_console(helper):
    source = helper.SOURCE.read_text()
    assert "Py_Main" in source and "Py_GetVersion" in source
    assert "agent_desktop_main" in source and "desktop_main" in source
    assert "no_arguments()" in source
    assert "LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32" in source
    assert "FILE_FLAG_OPEN_REPARSE_POINT" in source
    assert "static WCHAR executable[CAPACITY]" in source
    assert '"3.13."' in source and '"3.13.0 "' not in source
    for forbidden in ("CreateProcess", "ShellExecute", "AllocConsole", "system("):
        assert forbidden not in source
    assert "if (result == 70) result = fail();" in source
    assert "if (result != 0)" not in source
    assert "raise SystemExit(entry())" in source


@pytest.mark.parametrize("data", [b"", b"MZ", b"x" * 1024, b"MZ" + b"\0" * 1022])
def test_invalid_pe_refused(helper, data):
    with pytest.raises((ValueError, __import__("struct").error)):
        helper.pe_imports(data)


def test_invalid_cli_is_content_free(helper, capsys):
    assert helper.main([]) == 1
    captured = capsys.readouterr()
    assert not captured.err
    assert "launcher_preparation_failed" in captured.out


def test_inventory_refuses_budget_before_read(helper, tmp_path, monkeypatch):
    (tmp_path / "first.exe").write_bytes(b"1234")
    (tmp_path / "second.exe").write_bytes(b"12345")
    monkeypatch.setattr(helper, "TOOLS", {"first": "first.exe", "second": "second.exe"})
    monkeypatch.setattr(helper, "MAX_INVENTORY_BYTES", 8)
    calls = []
    original = helper.read
    def observed(path, maximum):
        calls.append(path.name)
        return original(path, maximum)
    monkeypatch.setattr(helper, "read", observed)
    with pytest.raises(ValueError):
        helper.inventory(tmp_path)
    assert calls == ["first.exe"]


def test_read_refuses_opened_replacement_even_if_path_unchanged(helper, tmp_path, monkeypatch):
    target, replacement = tmp_path / "synthetic.dat", tmp_path / "replacement.dat"
    target.write_bytes(b"same-size")
    replacement.write_bytes(b"different")
    original = Path.open
    def swapped(path, *args, **kwargs):
        return original(replacement if path == target else path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", swapped)
    with pytest.raises(ValueError):
        helper.read(target)


@pytest.mark.parametrize("field,value", [("st_ctime_ns", 7), ("st_ino", 0), ("st_file_attributes", 0x400),
                                         ("st_size", 999), ("st_birthtime_ns", 7), ("st_nlink", 2), ("st_mode", 0o100777)])
def test_read_refuses_descriptor_mutation(helper, tmp_path, monkeypatch, field, value):
    target = tmp_path / "synthetic.dat"
    target.write_bytes(b"synthetic")
    original = os.fstat
    calls = 0
    def changed(fd):
        nonlocal calls
        result = original(fd)
        calls += 1
        if calls != 2:
            return result
        fields = {key: getattr(result, key) for key in dir(result) if key.startswith("st_")}
        fields[field] = value
        return SimpleNamespace(**fields)
    monkeypatch.setattr(os, "fstat", changed)
    with pytest.raises(ValueError):
        helper.read(target)


def test_windows_birthtime_semantics_and_posix_strictness(helper, monkeypatch):
    fields = dict(st_dev=1, st_ino=2, st_mode=0o100600, st_nlink=1, st_size=9,
                  st_mtime_ns=10, st_ctime_ns=20, st_birthtime_ns=20)
    path = SimpleNamespace(**fields)
    descriptor = SimpleNamespace(**{**fields, "st_ctime_ns": 30})
    monkeypatch.setattr(helper, "os", SimpleNamespace(name="nt"))
    assert helper.same_open_file(path, descriptor)
    monkeypatch.setattr(helper, "os", SimpleNamespace(name="posix"))
    assert not helper.same_open_file(path, descriptor)


def test_python_dll_teardown_is_process_owned(helper):
    source = helper.SOURCE.read_text()
    assert "FreeLibrary(python)" not in source
    assert source.count("static wchar_t code[]") == 2


def test_closed_phase_error_does_not_emit_message(helper, monkeypatch, capsys):
    def failed(*args):
        raise helper.PreparationError("compiler_failed")
    monkeypatch.setattr(helper, "prepare", failed)
    assert helper.main(["--toolchain-root", "synthetic", "--output", "synthetic"]) == 1
    assert '"error_code":"compiler_failed"' in capsys.readouterr().out


@pytest.mark.parametrize("suffix", [".exe", ".EXE", ".bat", ".cmd", ".com"])
def test_windows_filename_execute_heuristic_is_narrow(helper, monkeypatch, suffix):
    fields = dict(st_dev=1, st_ino=2, st_mode=0o100666, st_nlink=1, st_size=9,
                  st_mtime_ns=10, st_ctime_ns=20)
    descriptor = SimpleNamespace(**fields)
    path = SimpleNamespace(**{**fields, "st_mode": 0o100777})
    monkeypatch.setattr(helper, "os", SimpleNamespace(name="nt"))
    assert helper.same_open_file(path, descriptor, suffix)
    assert not helper.same_open_file(path, descriptor, ".dat")
    assert not helper.same_open_file(SimpleNamespace(**{**fields, "st_mode": 0o100577}), descriptor, suffix)
    monkeypatch.setattr(helper, "os", SimpleNamespace(name="posix"))
    assert not helper.same_open_file(path, descriptor, suffix)


def test_actual_synthetic_executable_read(helper, tmp_path):
    target = tmp_path / "synthetic.exe"
    target.write_bytes(b"synthetic executable bytes, never launched")
    assert helper.read(target) == b"synthetic executable bytes, never launched"


@pytest.mark.parametrize("case", ["correct", "wrong_size", "wrong_hash", "unknown"])
def test_exact_oversized_header_allowance(helper, tmp_path, monkeypatch, case):
    directory = tmp_path / "headers"
    directory.mkdir()
    payload = b"s" * (4 * 1024 * 1024 + 1)
    (directory / "synthetic.h").write_bytes(payload)
    monkeypatch.setattr(helper, "TOOLS", {})
    monkeypatch.setattr(helper, "LIBRARIES", ())
    monkeypatch.setattr(helper, "HEADERS", ("headers",))
    size = len(payload) + (1 if case == "wrong_size" else 0)
    sha = "0" * 64 if case == "wrong_hash" else hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(helper, "OVERSIZED_HEADERS", {} if case == "unknown" else {"headers/synthetic.h": (size, sha)})
    observed = []
    original = helper.read
    def read(path, maximum):
        observed.append(path.name)
        return original(path, maximum)
    monkeypatch.setattr(helper, "read", read)
    if case == "correct":
        assert helper.inventory(tmp_path)["files"]["headers/synthetic.h"] == {"size": len(payload), "sha256": sha}
    else:
        with pytest.raises(ValueError):
            helper.inventory(tmp_path)
        if case == "wrong_size":
            assert not observed
