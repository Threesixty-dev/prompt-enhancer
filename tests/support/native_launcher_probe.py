"""Run pinned native launchers with a synthetic entry, never the application GUI."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from prepare_windows_launchers import read, safe
from prepare_synthetic_llama_fixture import QuietParser
from packaged_streaming_runner import _safe_external_root
from prompt_enhancer.application.owned_process import run_owned_process
from prompt_enhancer.infrastructure.windows_python_runtime import prepare_windows_python_runtime

ARCHIVE_SHA = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"
ARCHIVE_SIZE = 11009825
LAUNCHERS = {
    "PromptEnhancer.exe": ("9d21817d02d4288e483c657ef42f45549fc285b42c5dc6ebffa2b80335517b62", 13322, "agent", 17),
    "PromptEnhancerMetrics.exe": ("5924cc107d7f00738ee29c48dbd271deb0bbd6f80feb037139155327a757448b", 13322, "metrics", 19),
}
CONTRACT = "native-launcher-synthetic-probe.v1"
ENTRY_FLAGS = {"isolated", "ignore_environment", "no_site", "no_bytecode", "safe_path", "runtime_origin", "executable_matches"}
STUB = r'''
import json, os, pathlib, sys
ORIGIN = 'runtime'
def audit(event, args):
    if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.posix_spawn','os.spawn'}:
        raise RuntimeError('external_operation_forbidden')
sys.addaudithook(audit)
def invoke(entry, code, executable):
    root = pathlib.Path(__file__).resolve().parent.parent
    receipt = {'contract':'native-launcher-entry.v1','entry':entry,'python_version':'.'.join(map(str,sys.version_info[:3])),
               'isolated':sys.flags.isolated == 1,'ignore_environment':sys.flags.ignore_environment == 1,
               'no_site':sys.flags.no_site == 1,'no_bytecode':sys.flags.dont_write_bytecode == 1,
               'safe_path':sys.flags.safe_path is True,'runtime_origin':ORIGIN == 'runtime',
               'executable_matches':pathlib.Path(sys.executable).resolve() == root / executable}
    with (root / (entry + '-receipt.json')).open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,sort_keys=True,separators=(',',':'))
    return code
def agent_desktop_main():
    return invoke('agent',17,'PromptEnhancer.exe')
def desktop_main():
    return invoke('metrics',19,'PromptEnhancerMetrics.exe')
'''


def entry_receipt(data: bytes, expected: str) -> bool:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    if not isinstance(data, bytes) or len(data) > 2048 or b"\n" in data or b"\r" in data:
        return False
    try:
        value = json.loads(data, object_pairs_hook=unique)
        return (isinstance(value, dict) and set(value) == ENTRY_FLAGS | {"contract", "entry", "python_version"}
                and value["contract"] == "native-launcher-entry.v1" and value["entry"] == expected
                and value["python_version"] == "3.13.15" and all(value[key] is True for key in ENTRY_FLAGS))
    except (ValueError, UnicodeError):
        return False


def write_new(path: Path, data: bytes):
    with path.open("xb") as stream:
        stream.write(data)


def probe(archive: Path, launcher_directory: Path, artifact_root: Path) -> dict:
    report = {"contract": CONTRACT, "passed": False, "error_code": None,
              "archive_verified": False, "runtime_files_verified": 0,
              "entries_verified": 0, "exit_codes_verified": 0, "argument_rejections_verified": 0,
              "owned_runs_cleaned": 0, "child_process_limit_enforced": 1,
              "module_injection_refused": False, "runtime_files_unchanged": False,
              "real_application_executed": False, "gui_acceptance_claimed": False}
    phase = "input_invalid"
    try:
        external = _safe_external_root(artifact_root)
        if os.name != "nt" or external is None:
            raise ValueError()
        archive = safe(archive)
        launcher_directory = safe(launcher_directory, directory=True)
        payloads = {}
        for name, (sha, size, _, _) in LAUNCHERS.items():
            data = read(launcher_directory / name, size)
            if len(data) != size or hashlib.sha256(data).hexdigest() != sha:
                raise ValueError()
            payloads[name] = data
        root = Path(tempfile.mkdtemp(prefix="native-launcher-probe-", dir=external))
        runtime = root / "runtime"
        phase = "runtime_preparation_failed"
        prepared = prepare_windows_python_runtime(
            archive=archive, expected_version="3.13.15", expected_architecture="amd64",
            expected_sha256=ARCHIVE_SHA, expected_size_bytes=ARCHIVE_SIZE, destination=runtime)
        report["archive_verified"] = True
        if len(prepared.files) != 34:
            raise ValueError()
        report["runtime_files_verified"] = len(prepared.files)
        for name, data in payloads.items():
            write_new(runtime / name, data)
        for folder, origin in ((runtime, "runtime"), (root / "cwd", "decoy"), (root / "path", "decoy")):
            package = folder / "prompt_enhancer"
            package.mkdir(parents=True)
            write_new(package / "__init__.py", b"# Synthetic native-entry fixture only.\n")
            write_new(package / "desktop_overlay.py", STUB.replace("ORIGIN = 'runtime'", "ORIGIN = '" + origin + "'").encode())
        for name in ("home", "temp", "local", "roaming"):
            (root / name).mkdir()
        system = os.environ["SystemRoot"]
        environment = {"SystemRoot": system, "WINDIR": system,
                       "PATH": str(root / "path") + os.pathsep + str(Path(system) / "System32"),
                       "PYTHONPATH": str(root / "cwd") + os.pathsep + str(root / "path"),
                       "PYTHONHOME": str(root / "path"),
                       "HOME": str(root / "home"), "USERPROFILE": str(root / "home"),
                       "TEMP": str(root / "temp"), "TMP": str(root / "temp"),
                       "APPDATA": str(root / "roaming"), "LOCALAPPDATA": str(root / "local")}
        for name, (_, _, entry, expected_exit) in LAUNCHERS.items():
            receipt_path = runtime / (entry + "-receipt.json")
            phase = "argument_rejection_failed"
            result = run_owned_process([str(runtime / name), "synthetic-extra-argument"], cwd=root / "cwd",
                env=environment, timeout=5, maximum_active_processes=1, stdout_limit=2048, stderr_limit=2048)
            report["owned_runs_cleaned"] += 1
            if result.returncode != 2 or result.stdout or result.stderr or receipt_path.exists():
                raise ValueError()
            del result
            report["argument_rejections_verified"] += 1
            phase = "entry_execution_failed"
            result = run_owned_process([str(runtime / name)], cwd=root / "cwd", env=environment,
                timeout=8, maximum_active_processes=1, stdout_limit=2048, stderr_limit=2048)
            report["owned_runs_cleaned"] += 1
            if result.returncode != expected_exit or result.stdout or result.stderr:
                raise ValueError()
            del result
            report["exit_codes_verified"] += 1
            phase = "entry_receipt_invalid"
            if not entry_receipt(read(receipt_path, 2048), entry):
                raise ValueError()
            report["entries_verified"] += 1
        phase = "module_injection_detected"
        if any((root / folder / (entry + "-receipt.json")).exists()
               for folder in ("cwd", "path") for entry in ("agent", "metrics")):
            raise ValueError()
        report["module_injection_refused"] = True
        phase = "runtime_mutated"
        for item in prepared.files:
            data = read(runtime / item.relative_path, item.size_bytes)
            if len(data) != item.size_bytes or hashlib.sha256(data).hexdigest() != item.sha256:
                raise ValueError()
        for name, data in payloads.items():
            if read(runtime / name, len(data)) != data:
                raise ValueError()
        report["runtime_files_unchanged"] = True
        report["passed"] = True
    except Exception:
        report["error_code"] = phase
    return report


def main(argv=None):
    try:
        parser = QuietParser(description=__doc__)
        parser.add_argument("--archive", type=Path, required=True)
        parser.add_argument("--launcher-directory", type=Path, required=True)
        parser.add_argument("--artifact-root", type=Path, required=True)
        args = parser.parse_args(argv)
        report = probe(args.archive, args.launcher_directory, args.artifact_root)
    except Exception:
        report = {"contract": CONTRACT, "passed": False, "error_code": "invalid_arguments"}
    print("NATIVE_LAUNCHER_PROBE=" + json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
