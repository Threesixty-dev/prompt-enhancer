"""Pure protocol-driver boundaries, without compilation, sockets or processes."""
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def helper(monkeypatch):
    from prompt_enhancer.application import owned_process

    def forbidden(*args, **kwargs):
        pytest.fail("pure protocol tests must not launch")

    monkeypatch.setattr(owned_process, "start_owned_process", forbidden)
    monkeypatch.setattr(owned_process, "run_owned_process", forbidden)
    support = Path(__file__).parent / "support"
    monkeypatch.syspath_prepend(str(support))
    spec = importlib.util.spec_from_file_location("synthetic_protocol_helper", support / "probe_synthetic_llama_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_production_cpu_command(helper):
    assert helper.arguments(Path("fixture.exe"), Path("synthetic-fixture.gguf"), 23456) == [
        "fixture.exe", "-m", "synthetic-fixture.gguf", "--host", "127.0.0.1",
        "--port", "23456", "-ngl", "0", "-c", "4096", "--no-webui",
    ]


@pytest.mark.parametrize("port", [8765, 8766, 0, 1023, 65536, True, "23456"])
def test_forbidden_ports(helper, port):
    with pytest.raises(helper.ProbeFailure):
        helper.arguments(Path("fixture.exe"), Path("synthetic-fixture.gguf"), port)


@pytest.mark.parametrize("payload", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b"x" * 16385])
def test_json_rejection(helper, payload):
    with pytest.raises((helper.ProbeFailure, ValueError)):
        helper.decode(payload)


def test_synthetic_body_only(helper):
    assert json.loads(helper.body()) == {
        "model": "synthetic-fixture", "messages": [{"role": "user", "content": "Synthetic streaming acceptance."}],
        "stream": False,
    }


def test_invalid_arguments_are_content_free(helper, capsys):
    assert helper.main(["--unknown", "fictional-value"]) == 1
    captured = capsys.readouterr()
    assert not captured.err
    assert json.loads(captured.out.split("=", 1)[1]) == {
        "contract": helper.CONTRACT, "passed": False, "error_code": "invalid_arguments",
    }


def test_bad_manifest_hash_rejected_before_launch(helper):
    with pytest.raises(helper.ProbeFailure):
        helper.verify_fixture(Path("fictional"), "not-a-hash")
