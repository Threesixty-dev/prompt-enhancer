"""Pure build-boundary tests; these are not compiled protocol acceptance."""
import importlib.util
import json
from pathlib import Path
import struct

import pytest


@pytest.fixture
def helper(monkeypatch):
    from prompt_enhancer.application import owned_process

    def forbidden(*args, **kwargs):
        pytest.fail("pure fixture tests cannot launch a process")

    monkeypatch.setattr(owned_process, "run_owned_process", forbidden)
    source = Path(__file__).parent / "support" / "prepare_synthetic_llama_fixture.py"
    spec = importlib.util.spec_from_file_location("synthetic_fixture_helper", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_metadata_only_model(helper):
    payload = helper.gguf_payload()
    assert len(payload) == 24
    assert struct.unpack("<4sIQQ", payload) == (b"GGUF", 3, 0, 0)


def test_compiler_command_is_explicit_offline(helper):
    compiler, source, output = map(Path, ("compiler.exe", "fixture.cs", "fixture.exe"))
    references = [Path("mscorlib.dll"), Path("System.dll"), Path("System.Web.Extensions.dll")]
    assert helper.compiler_arguments(compiler, source, output, references) == [
        "compiler.exe", "/nologo", "/noconfig", "/nostdlib+", "/target:exe",
        "/platform:anycpu", "/optimize+", "/langversion:5", "/out:fixture.exe",
        "/reference:mscorlib.dll", "/reference:System.dll",
        "/reference:System.Web.Extensions.dll", "fixture.cs",
    ]


@pytest.mark.parametrize("arguments", [[], ["--unknown"], ["--compiler", "fictional", "--artifact-root", "fictional"]])
def test_invalid_inputs_never_launch_or_disclose(helper, capsys, arguments):
    assert helper.main(arguments) == 1
    output = capsys.readouterr()
    assert not output.err
    prefix = "SYNTHETIC_LLAMA_FIXTURE_BUILD="
    assert output.out.startswith(prefix)
    assert json.loads(output.out[len(prefix):]) == {
        "contract": helper.CONTRACT, "passed": False,
        "error_code": "fixture_build_failed", "owned_cleanup_confirmed": False,
    }


def test_path_type_checks(helper, tmp_path):
    file = tmp_path / "synthetic.txt"
    file.write_bytes(b"synthetic")
    assert helper.checked_path(file, directory=False) == file.resolve()
    with pytest.raises(helper.InvalidInput):
        helper.checked_path(file, directory=True)
    with pytest.raises(helper.InvalidInput):
        helper.checked_path(Path("relative"), directory=False)


def test_fingerprint_contains_no_path(helper, tmp_path):
    file = tmp_path / "synthetic.txt"
    file.write_bytes(b"synthetic")
    result = helper.fingerprint(file)
    assert set(result) == {"sha256", "size"}
    assert result["size"] == 9
    assert len(result["sha256"]) == 64


def test_source_declares_production_cpu_flags_and_transport_bounds(helper):
    # Static contract only. Actual flag/protocol behavior needs the reviewed compiler run.
    source = helper.SOURCE.read_text(encoding="utf-8")
    for flag in ('"-m"', '"--host"', '"--port"', '"-ngl"', '"-c"', '"--no-webui"'):
        assert flag in source
    assert 'host == "127.0.0.1"' in source
    assert 'layers == "0"' in source
    assert "LifetimeSeconds = 120" in source
    assert "MaxRequests = 64" in source
    assert "MaxBody = 262144" in source
    assert "Clients.Count >= 4" in source
    assert "TcpListener(IPAddress.Loopback, port)" in source
    assert "HttpListener" not in source


def test_compiler_diagnostics_only_return_unique_codes(helper):
    capture = b"fictional.cs(17,2): error CS0165: private-looking text\r\nwarning CS0219: hidden\nerror CS0165: duplicate"
    assert helper.compiler_diagnostic_codes(capture, b"error CS1002: hidden") == ["CS0165", "CS0219", "CS1002"]


@pytest.mark.parametrize("capture", [
    b"CS1234", b"error CS12345", b"error CS1234_secret", b"xerror CS1234",
    b"error CS12\n34", b"error CS\xff1234", b"error CS1234X", b"error cs1234",
])
def test_compiler_diagnostics_reject_non_codes(helper, capture):
    assert helper.compiler_diagnostic_codes(capture, b"") == []


def test_compiler_diagnostics_hard_bounds(helper):
    capture = b"\n".join(("error CS%04d: hidden" % number).encode() for number in range(20))
    assert helper.compiler_diagnostic_codes(capture, b"") == ["CS%04d" % number for number in range(8)]
    assert helper.compiler_diagnostic_codes(b"x" * 65536 + b" error CS1234", b"") == []
    assert helper.compiler_diagnostic_codes("error CS1234", b"") == []


def test_compiler_failure_categories_are_closed_and_content_free(helper):
    result = helper.compiler_failure_categories(
        b"fictional-path: Access is denied; cvtres.exe; private-looking arbitrary content",
        b"0x80070020; not enough quota; disk is full",
    )
    assert result == ["access_denied", "sharing_violation", "resource_compiler", "resource_quota", "disk_full"]
    assert helper.compiler_failure_categories(b"arbitrary unrecognized failure", b"") == []
    assert helper.compiler_failure_categories(b"x" * 65536 + b" access is denied", b"") == []


def test_compiler_dependency_closure_is_exact_and_bounded(helper):
    import inspect

    assert helper.COMPILER_PROCESS_LIMIT == 2
    implementation = inspect.getsource(helper.prepare)
    assert 'checked_path(compiler.parent / "cvtres.exe", directory=False)' in implementation
    assert "inputs = [compiler, SOURCE.absolute(), *references, resource_compiler]" in implementation
    assert "before != [fingerprint(item) for item in inputs]" in implementation
    assert "maximum_active_processes=COMPILER_PROCESS_LIMIT" in implementation
    assert '"resource_compiler": before[5]' in implementation
    assert "timeout=30" in implementation


def test_malformed_scenario_has_fixed_refusal_boundary(helper):
    source = helper.SOURCE.read_text(encoding="utf-8")
    assert "try { scenario = Scenario(body, out streaming); }" in source
    for kind in ("ArgumentException", "InvalidOperationException", "InvalidCastException"):
        assert "catch (" + kind + ") { scenario = null; streaming = false; }" in source
    # Transport writes stay outside the parser catch and use the existing cleanup.
    assert source.index("catch (InvalidCastException)") < source.index("if (scenario == null)")
