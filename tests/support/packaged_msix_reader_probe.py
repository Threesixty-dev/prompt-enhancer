"""Run the reviewed SOURCE release reader under staged Python; not signer proof."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile

from prompt_enhancer.application.owned_process import run_owned_process
from prepare_synthetic_llama_fixture import QuietParser, checked_path, fingerprint
from packaged_streaming_runner import _safe_external_root
from packaged_serve_probe import _environment

CONTRACT = "packaged-source-msix-reader-probe.v1"
SOURCE = Path(__file__).absolute().parents[2] / "scripts" / "verify_msix_package.py"
FLAGS = {"source_hash_verified", "ctime_split_observed", "birthtime_equal", "identity_equal",
         "exact_read_verified", "wrong_length_refused", "over_budget_refused"}

CODE = r'''
import hashlib, importlib.util, json, os, pathlib, sys, time
def audit(event, args):
    if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn"}:
        raise RuntimeError("external_operation_forbidden")
sys.addaudithook(audit)
keys = ("source_hash_verified", "ctime_split_observed", "birthtime_equal", "identity_equal", "exact_read_verified", "wrong_length_refused", "over_budget_refused")
receipt = {"contract":"packaged-source-msix-reader-probe.v1", "passed":False, "error_code":None, "python_version":".".join(map(str,sys.version_info[:3])), **dict.fromkeys(keys,False)}
try:
    source, expected, directory = pathlib.Path(sys.argv[1]), sys.argv[2], pathlib.Path(sys.argv[3])
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise ValueError()
    spec = importlib.util.spec_from_file_location("reviewed_source_msix_reader", source)
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    receipt["source_hash_verified"] = hashlib.sha256(source.read_bytes()).hexdigest() == expected
    fixture = directory / "synthetic.manifest"
    payload = b"Synthetic release manifest.\n"
    with fixture.open("xb") as stream:
        stream.write(b"Synthetic initial content.\n")
    for attempt in range(10):
        time.sleep(0.01)
        with fixture.open("wb") as stream:
            stream.write(payload)
        path_stat = fixture.lstat()
        with fixture.open("rb") as stream:
            fd_stat = os.fstat(stream.fileno())
        if path_stat.st_ctime_ns != fd_stat.st_ctime_ns:
            break
    receipt["ctime_split_observed"] = path_stat.st_ctime_ns != fd_stat.st_ctime_ns
    receipt["birthtime_equal"] = (hasattr(path_stat,"st_birthtime_ns") and hasattr(fd_stat,"st_birthtime_ns") and path_stat.st_birthtime_ns == fd_stat.st_birthtime_ns)
    receipt["identity_equal"] = bool(path_stat.st_ino and path_stat.st_dev == fd_stat.st_dev and path_stat.st_ino == fd_stat.st_ino)
    receipt["exact_read_verified"] = reader._read_regular(fixture, maximum=len(payload), exact=len(payload)) == payload
    receipt["wrong_length_refused"] = reader._read_regular(fixture, maximum=128, exact=len(payload)+1) is None
    receipt["over_budget_refused"] = reader._read_regular(fixture, maximum=len(payload)-1) is None
    receipt["passed"] = all(receipt[key] is True for key in keys)
    if not receipt["passed"]:
        receipt["error_code"] = "reader_contract_unconfirmed"
except Exception:
    receipt["error_code"] = "reader_probe_failed"
print("PACKAGED_SOURCE_MSIX_READER="+json.dumps(receipt,sort_keys=True,separators=(",",":")))
sys.exit(0 if receipt["passed"] else 1)
'''


def parse_receipt(raw: bytes) -> dict | None:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    prefix = b"PACKAGED_SOURCE_MSIX_READER="
    if not isinstance(raw, bytes) or len(raw) > 4096:
        return None
    raw = raw.removesuffix(b"\r\n").removesuffix(b"\n")
    if not raw.startswith(prefix) or b"\r" in raw or b"\n" in raw:
        return None
    try:
        value = json.loads(raw[len(prefix):], object_pairs_hook=unique)
        if (not isinstance(value, dict) or set(value) != FLAGS | {"contract", "passed", "error_code", "python_version"}
                or value["contract"] != CONTRACT or type(value["passed"]) is not bool
                or any(type(value[key]) is not bool for key in FLAGS)
                or not isinstance(value["python_version"], str) or re.fullmatch(r"3\.13\.[0-9]{1,3}", value["python_version"]) is None
                or value["error_code"] not in (None, "reader_contract_unconfirmed", "reader_probe_failed")
                or value["passed"] != (value["error_code"] is None and all(value[key] for key in FLAGS))):
            return None
        return value
    except (ValueError, UnicodeError):
        return None


def probe(runtime: Path, source_hash: str, artifact_root: Path) -> dict:
    report = {"contract": CONTRACT, "passed": False, "error_code": "probe_failed", "owned_cleanup_confirmed": False}
    try:
        root = _safe_external_root(artifact_root)
        if os.name != "nt" or root is None or re.fullmatch(r"[0-9a-f]{64}", source_hash) is None:
            return report
        executable = checked_path(runtime / "python.exe", directory=False)
        source = checked_path(SOURCE, directory=False)
        source_before, python_before = fingerprint(source), fingerprint(executable)
        if source_before["sha256"] != source_hash:
            return report
        directory = Path(tempfile.mkdtemp(prefix="source-msix-reader-", dir=root))
        for name in ("temp", "empty-profile", "private-home", "empty-claude", "empty-codex", "empty-model-cache"):
            (directory / name).mkdir()
        result = run_owned_process(
            [str(executable), "-I", "-B", "-c", CODE, str(source), source_hash, str(directory)],
            cwd=directory, env=_environment(runtime, directory, 0), timeout=15,
            stdout_limit=4096, stderr_limit=4096, maximum_active_processes=1,
        )
        report["owned_cleanup_confirmed"] = True
        receipt = parse_receipt(result.stdout)
        valid = receipt is not None and not result.stderr and result.returncode == (0 if receipt["passed"] else 1)
        del result
        if not valid or source_before != fingerprint(source) or python_before != fingerprint(executable):
            return report
        report.update(receipt)
        report.update(source=source_before, runtime_python=python_before)
    except Exception:
        pass
    return report


def main(argv=None):
    try:
        parser = QuietParser(description=__doc__)
        parser.add_argument("--runtime", required=True, type=Path)
        parser.add_argument("--source-sha256", required=True)
        parser.add_argument("--artifact-root", required=True, type=Path)
        args = parser.parse_args(argv)
        report = probe(args.runtime, args.source_sha256, args.artifact_root)
    except Exception:
        report = {"contract": CONTRACT, "passed": False, "error_code": "invalid_arguments"}
    print("PACKAGED_SOURCE_MSIX_READER_PROBE=" + json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
