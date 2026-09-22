"""Pure native-probe receipt tests; launchers are never executed here."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def helper(monkeypatch):
    from prompt_enhancer.application import owned_process
    monkeypatch.setattr(owned_process, "run_owned_process", lambda *a, **k: pytest.fail("no launcher execution"))
    support = Path(__file__).parent / "support"
    monkeypatch.syspath_prepend(str(support))
    spec = importlib.util.spec_from_file_location("synthetic_native_probe", support / "native_launcher_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receipt(helper):
    return {"contract": "native-launcher-entry.v1", "entry": "agent", "python_version": "3.13.15",
            **{key: True for key in helper.ENTRY_FLAGS}}


def test_valid_receipt_and_stub_compiles(helper):
    assert helper.entry_receipt(json.dumps(receipt(helper)).encode(), "agent")
    compile(helper.STUB, "synthetic-stub", "exec")


@pytest.mark.parametrize("field,value", [("python_version", "3.13.0"), ("entry", "metrics"),
                                         ("runtime_origin", False), ("isolated", 1), ("extra", "arbitrary")])
def test_invalid_receipt(helper, field, value):
    assert not helper.entry_receipt(json.dumps({**receipt(helper), field: value}).encode(), "agent")


def test_duplicate_oversize_and_multiline(helper):
    data = json.dumps(receipt(helper)).encode()
    assert not helper.entry_receipt(data.replace(b'"entry": "agent"', b'"entry":"agent","entry":"agent"'), "agent")
    assert not helper.entry_receipt(data + b"\n", "agent")
    assert not helper.entry_receipt(b"x" * 2049, "agent")


def test_pinned_archive_and_two_fixed_launchers(helper):
    assert helper.ARCHIVE_SIZE == 11009825
    assert len(helper.ARCHIVE_SHA) == 64
    assert {value[3] for value in helper.LAUNCHERS.values()} == {17, 19}
    assert set(helper.LAUNCHERS) == {"PromptEnhancer.exe", "PromptEnhancerMetrics.exe"}


def test_bad_arguments_do_not_launch(helper, capsys):
    assert helper.main([]) == 1
    captured = capsys.readouterr()
    assert not captured.err
    assert json.loads(captured.out.split("=", 1)[1])["error_code"] == "invalid_arguments"
