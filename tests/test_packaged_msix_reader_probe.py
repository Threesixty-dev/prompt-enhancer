"""Pure closed receipt validation; no staged interpreter launched."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def helper(monkeypatch):
    from prompt_enhancer.application import owned_process
    monkeypatch.setattr(owned_process, "run_owned_process", lambda *a, **k: pytest.fail("no process launch"))
    support = Path(__file__).parent / "support"
    monkeypatch.syspath_prepend(str(support))
    spec = importlib.util.spec_from_file_location("synthetic_msix_probe", support / "packaged_msix_reader_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def success(helper):
    return {"contract": helper.CONTRACT, "passed": True, "error_code": None, "python_version": "3.13.0",
            **{key: True for key in helper.FLAGS}}


def encode(value):
    return b"PACKAGED_SOURCE_MSIX_READER=" + json.dumps(value).encode() + b"\n"


def test_success_and_inline_code_compile(helper):
    assert helper.parse_receipt(encode(success(helper))) == success(helper)
    compile(helper.CODE, "synthetic-inline", "exec")


@pytest.mark.parametrize("field,value", [("passed", 1), ("python_version", "3.11.0"), ("error_code", "raw error"), ("extra", True)])
def test_closed_schema(helper, field, value):
    assert helper.parse_receipt(encode({**success(helper), field: value})) is None


def test_false_inconsistent_flag_rejected(helper):
    for key in helper.FLAGS:
        assert helper.parse_receipt(encode({**success(helper), key: False})) is None
        assert helper.parse_receipt(encode({**success(helper), key: 1})) is None


def test_duplicate_multiline_and_oversize_rejected(helper):
    raw = encode(success(helper))
    assert helper.parse_receipt(raw.replace(b'"passed": true', b'"passed": true,"passed":true')) is None
    assert helper.parse_receipt(raw + b"arbitrary\n") is None
    assert helper.parse_receipt(b"x" * 4097) is None


def test_invalid_cli_content_free(helper, capsys):
    assert helper.main([]) == 1
    captured = capsys.readouterr()
    assert not captured.err
    assert json.loads(captured.out.split("=", 1)[1])["error_code"] == "invalid_arguments"
