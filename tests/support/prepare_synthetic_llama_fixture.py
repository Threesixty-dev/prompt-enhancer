"""Build an offline test transport; never launch it or claim model inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import tempfile

from prompt_enhancer.application.owned_process import run_owned_process

CONTRACT = "synthetic-llama-fixture-build.v1"
REPOSITORY = Path(__file__).absolute().parents[2]
SOURCE = Path(__file__).with_name("synthetic_llama_server.cs")
# Compiler-only closure: csc plus its adjacent resource converter; not a runtime budget.
COMPILER_PROCESS_LIMIT = 2


class InvalidInput(ValueError):
    pass


class QuietParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InvalidInput("invalid_arguments")


def checked_path(path: Path, *, directory: bool) -> Path:
    """Reject redirected paths before resolution, including ancestor junctions."""
    if not path.is_absolute() or ".." in path.parts:
        raise InvalidInput("invalid_path")
    for item in (path, *path.parents):
        metadata = item.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise InvalidInput("redirected_path")
    metadata = path.lstat()
    if not (stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)):
        raise InvalidInput("invalid_path_type")
    return path.resolve(strict=True)


def validate_inputs(compiler: Path, artifact_root: Path) -> tuple[Path, Path, list[Path]]:
    if os.name != "nt":
        raise InvalidInput("windows_required")
    system_root = checked_path(Path(os.environ.get("SystemRoot", "")), directory=True)
    expected = system_root / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    compiler = checked_path(compiler, directory=False)
    if compiler != checked_path(expected, directory=False):
        raise InvalidInput("untrusted_compiler")
    artifact_root = checked_path(artifact_root, directory=True)
    repository = REPOSITORY.resolve(strict=True)
    home = Path.home().resolve(strict=True)
    if (artifact_root == Path(artifact_root.anchor)
            or artifact_root.is_relative_to(repository) or repository.is_relative_to(artifact_root)
            or artifact_root.is_relative_to(home) or home.is_relative_to(artifact_root)):
        raise InvalidInput("external_artifact_root_required")
    references = [checked_path(compiler.parent / name, directory=False) for name in
                  ("mscorlib.dll", "System.dll", "System.Web.Extensions.dll")]
    checked_path(SOURCE.absolute(), directory=False)
    return compiler, artifact_root, references


def fingerprint(path: Path) -> dict[str, str | int]:
    checked_path(path, directory=False)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns
    ):
        raise InvalidInput("input_changed")
    return {"sha256": digest.hexdigest(), "size": before.st_size}


def compiler_arguments(compiler: Path, source: Path, output: Path, references: list[Path]) -> list[str]:
    return [str(compiler), "/nologo", "/noconfig", "/nostdlib+", "/target:exe",
            "/platform:anycpu", "/optimize+", "/langversion:5", "/out:" + str(output),
            *["/reference:" + str(item) for item in references], str(source)]


def gguf_payload() -> bytes:
    # Metadata-only fixture, deliberately no tensors, tokenizer or model weights.
    return struct.pack("<4sIQQ", b"GGUF", 3, 0, 0)


def compiler_diagnostic_codes(stdout: bytes, stderr: bytes) -> list[str]:
    """Return only bounded compiler identifiers, never decoded diagnostics."""
    if not isinstance(stdout, bytes) or not isinstance(stderr, bytes):
        return []
    codes: list[str] = []
    for capture in (stdout[:65536], stderr[:65536]):
        for match in re.finditer(rb"(?<![A-Za-z0-9_])(?:error|warning) (CS[0-9]{4})(?![A-Za-z0-9_])", capture):
            code = match.group(1).decode("ascii")
            if code not in codes:
                codes.append(code)
                if len(codes) == 8:
                    return codes
    return codes


def compiler_failure_categories(stdout: bytes, stderr: bytes) -> list[str]:
    """Classify known English compiler/native failures without forwarding text."""
    capture = (stdout[:65536] + b"\n" + stderr[:65536]).lower()
    patterns = (
        ("access_denied", (b"access is denied", b"access to the path", b"0x80070005")),
        ("sharing_violation", (b"being used by another process", b"0x80070020")),
        ("file_not_found", (b"cannot find the file", b"0x80070002")),
        ("path_not_found", (b"cannot find the path", b"0x80070003")),
        ("resource_compiler", (b"cvtres.exe", b"win32 resource", b"win32resource")),
        ("resource_quota", (b"not enough quota", b"insufficient system resources", b"0x80070718")),
        ("disk_full", (b"not enough space on the disk", b"disk is full", b"0x80070070")),
    )
    return [label for label, needles in patterns if any(needle in capture for needle in needles)]


def prepare(compiler: Path, artifact_root: Path) -> dict:
    compiler, artifact_root, references = validate_inputs(compiler, artifact_root)
    resource_compiler = checked_path(compiler.parent / "cvtres.exe", directory=False)
    inputs = [compiler, SOURCE.absolute(), *references, resource_compiler]
    before = [fingerprint(item) for item in inputs]
    output_root = Path(tempfile.mkdtemp(prefix="synthetic-llama-", dir=artifact_root))
    checked_path(output_root, directory=True)
    for name in ("home", "temp", "local", "roaming"):
        (output_root / name).mkdir()
    system_root = str(Path(os.environ["SystemRoot"]).resolve(strict=True))
    environment = {
        "SystemRoot": system_root, "WINDIR": system_root,
        "PATH": str(compiler.parent) + os.pathsep + str(Path(system_root) / "System32"),
        "TEMP": str(output_root / "temp"), "TMP": str(output_root / "temp"),
        "HOME": str(output_root / "home"), "USERPROFILE": str(output_root / "home"),
        "LOCALAPPDATA": str(output_root / "local"), "APPDATA": str(output_root / "roaming"),
    }
    output = output_root / "synthetic-llama-server.exe"
    result = run_owned_process(
        compiler_arguments(compiler, SOURCE.absolute(), output, references),
        cwd=output_root, env=environment, timeout=30, maximum_active_processes=COMPILER_PROCESS_LIMIT,
        stdout_limit=65536, stderr_limit=65536,
    )
    # Never expose compiler diagnostics, even for a failed compilation.
    exit_code = result.returncode
    diagnostic_codes = compiler_diagnostic_codes(result.stdout, result.stderr)
    failure_categories = compiler_failure_categories(result.stdout, result.stderr)
    del result
    if before != [fingerprint(item) for item in inputs]:
        raise InvalidInput("input_changed")
    if exit_code != 0:
        return {"contract": CONTRACT, "passed": False, "error_code": "compiler_failed",
                "compiler_exit_code": exit_code, "owned_cleanup_confirmed": True,
                "artifact_id": output_root.name, "compiler_diagnostic_codes": diagnostic_codes,
                "compiler_failure_categories": failure_categories,
                "resource_compiler": before[5], "compiler_process_limit": COMPILER_PROCESS_LIMIT}
    executable = fingerprint(output)
    model = output_root / "synthetic-fixture.gguf"
    with model.open("xb") as stream:
        stream.write(gguf_payload())
    receipt = {
        "contract": CONTRACT, "passed": True, "error_code": None,
        "compiler_exit_code": 0, "owned_cleanup_confirmed": True,
        "artifact_id": output_root.name, "compiler": before[0], "source": before[1],
        "references": before[2:5], "resource_compiler": before[5],
        "compiler_process_limit": COMPILER_PROCESS_LIMIT,
        "executable": executable, "model": fingerprint(model),
        "lifetime_seconds": 120, "request_limit": 64, "concurrency_limit": 4,
        "request_body_limit": 262144, "inference_capable": False,
    }
    with (output_root / "fixture-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True)
        stream.write("\n")
    return receipt


def main(argv: list[str] | None = None) -> int:
    try:
        parser = QuietParser(description=__doc__)
        parser.add_argument("--compiler", type=Path, required=True)
        parser.add_argument("--artifact-root", type=Path, required=True)
        args = parser.parse_args(argv)
        receipt = prepare(args.compiler, args.artifact_root)
    except Exception:
        # Failure does not imply cleanup confirmation: owned-runner errors fail closed.
        receipt = {"contract": CONTRACT, "passed": False, "error_code": "fixture_build_failed",
                   "owned_cleanup_confirmed": False}
    print("SYNTHETIC_LLAMA_FIXTURE_BUILD=" + json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
