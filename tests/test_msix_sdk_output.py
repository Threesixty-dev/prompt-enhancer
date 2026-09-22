"""Synthetic exact SDK-output protocol tests, without process execution."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from msix_sdk_output import OutputPolicy, OutputError, UnpackPolicy


def policy(count=2):
    return OutputPolicy("D:/synthetic/candidate", "D:/synthetic/output/package.msix",
                        ["AppxManifest.xml"] + [f"files/synthetic-{i}.txt" for i in range(count)])


def transcript(value):
    selected = {}
    for line, key in value.lines.items():
        if key != "success":
            selected.setdefault(key, line)
    return ("\r\n".join(selected.values()) + "\r\nPackage creation succeeded.\r\n").encode()


def test_valid_and_input_derived_scaling():
    small, large = policy(2), policy(100)
    assert small.byte_limit < large.byte_limit
    assert small.line_limit < large.line_limit
    assert small.validate(transcript(small))["sdk_stdout_payload_files"] == 2
    assert large.validate(transcript(large))["sdk_stdout_payload_files"] == 100


@pytest.mark.parametrize("kind", ["unknown", "error", "warning", "duplicate", "truncated", "encoding", "byte_overflow", "blank_overflow", "missing_payload", "missing_success"])
def test_invalid_output(kind):
    value = policy()
    data = transcript(value)
    if kind in {"unknown", "error", "warning"}:
        data = {"unknown": b"arbitrary-private-canary", "error": b"MakeAppx : error: synthetic", "warning": b"MakeAppx : warning: synthetic"}[kind] + b"\r\n" + data
    elif kind == "duplicate":
        data = b"Microsoft (R) MakeAppx Tool\r\n" + data
    elif kind == "truncated":
        data = data[:-4]
    elif kind == "encoding":
        data = b"\xff\n"
    elif kind == "byte_overflow":
        data = b"a" * (value.byte_limit + 1)
    elif kind == "blank_overflow":
        data = b"\n" * (value.blank_limit + 1) + data
    elif kind == "missing_payload":
        data = b"\r\n".join(line for line in data.split(b"\r\n") if not line.startswith((b"Adding ", b"Processing ")))
    else:
        data = data.replace(b"Package creation succeeded.\r\n", b"")
    with pytest.raises(OutputError) as caught:
        value.validate(data)
    assert "arbitrary-private-canary" not in str(caught.value)


def test_count_guard_before_expansion():
    with pytest.raises(OutputError):
        policy(9998)


@pytest.mark.parametrize("ending", [b"\r\r\n", b"\r\n", b"\n", b""])
def test_complete_footer_with_or_without_final_newline(ending):
    value = policy()
    data = transcript(value)[:-2] + ending
    assert value.validate(data)["sdk_stdout_payload_files"] == 2


@pytest.mark.parametrize("ending", [b"\r", b"\rX", b"\r\r\r\n", b"\rinline\n"])
def test_lone_carriage_return_refused(ending):
    value = policy()
    with pytest.raises(OutputError, match="sdk_stdout_truncated"):
        value.validate(transcript(value)[:-2] + ending)


def test_failure_diagnostics_are_content_free():
    value = policy()
    with pytest.raises(OutputError) as caught:
        value.validate(b"synthetic-private-canary\r\r\n")
    assert caught.value.diagnostics == {"ends_lf": True, "crlf_count": 1, "crcrlf_count": 1, "lone_cr_count": 0,
                                        "max_line_bytes": 24, "unknown_line_count": 1,
                                        "template_counts": {"blank": 1, "unknown": 1}}
    assert "synthetic-private-canary" not in str(caught.value.diagnostics)


def test_full_crcrlf_transcript_and_derived_budget():
    value = policy()
    data = transcript(value).replace(b"\r\n", b"\r\r\n")
    assert value.validate(data)["sdk_stdout_payload_files"] == 2
    assert len(data) <= value.byte_limit


def test_observed_extended_processing_and_memory_shape():
    value = policy()
    selected = {}
    for line, key in value.lines.items():
        if key == "success" or isinstance(key, tuple) and key[0] == "adding":
            continue
        selected[key] = line
    data = ("\r\r\n".join(selected.values()) + "\r\r\nMemory limit defaulting to 123456 bytes.\r\r\nPackage creation succeeded.\r\r\n").encode()
    assert b"\\\\?\\" in data
    assert value.validate(data)["sdk_stdout_payload_files"] == 2


@pytest.mark.parametrize("number", ["-1", "18446744073709551616", "1" * 21, "1.5", "01", "00"])
def test_memory_unsigned64_refusal(number):
    value = policy()
    with pytest.raises(OutputError):
        value.validate(f"Memory limit defaulting to {number} bytes.\n".encode() + transcript(value))


def test_content_directory_exact_identity_and_shared_slot():
    value = policy()
    variants = [line for line, key in value.lines.items() if key == "content_path"]
    assert len(variants) == 2
    data = transcript(value)
    with pytest.raises(OutputError, match="sdk_stdout_duplicate"):
        value.validate(variants[1].encode() + b"\n" + data)
    with pytest.raises(OutputError, match="sdk_stdout_unknown"):
        value.validate(data.replace(variants[0].encode(), variants[0].replace("candidate", "unrelated").encode()))


def test_explicit_sha256_and_shared_hash_slot():
    value = policy()
    data = transcript(value)
    default = b"Using default hash method: SHA256."
    explicit = b"Option /h specified, using custom hash method: SHA256."
    assert value.validate(data.replace(default, explicit))["sdk_stdout_payload_files"] == 2
    with pytest.raises(OutputError, match="sdk_stdout_duplicate"):
        value.validate(explicit + b"\n" + data)
    for other in (b"SHA384", b"SHA512", b"MD5"):
        with pytest.raises(OutputError, match="sdk_stdout_unknown"):
            value.validate(data.replace(default, explicit.replace(b"SHA256", other)))


def unpack_transcript(value):
    selected = {}
    for line, key in value.lines.items():
        if key != "success":
            selected[key] = line
    return ("\r\r\n".join(selected.values()) + "\r\r\n" + value.footer).encode()


def test_observed_unpack_coverage_thirteen_entries():
    names = [f"files/synthetic-{i}.txt" for i in range(12)] + ["AppxBlockMap.xml"]
    value = UnpackPolicy("D:/synthetic/package.msix", "D:/synthetic/extracted", names)
    result = value.validate(unpack_transcript(value))
    assert result["sdk_stdout_extracted_files"] == 13
    assert "sdk_stdout_payload_files" not in result


@pytest.mark.parametrize("kind", ["duplicate", "missing", "otherpath", "othername"])
def test_unpack_exact_extraction_rejections(kind):
    value = UnpackPolicy("D:/synthetic/package.msix", "D:/synthetic/extracted", ["synthetic.txt"])
    data = unpack_transcript(value)
    line = next(line for line in data.split(b"\r\r\n") if line.startswith(b"Extracting file "))
    if kind == "duplicate":
        data = line + b"\n" + data
    elif kind == "missing":
        data = data.replace(line + b"\r\r\n", b"")
    elif kind == "otherpath":
        data = data.replace(line, line.replace(b"extracted", b"unrelated"))
    else:
        data = data.replace(line, line.replace(b"synthetic.txt", b"unlisted.txt"))
    with pytest.raises(OutputError):
        value.validate(data)
