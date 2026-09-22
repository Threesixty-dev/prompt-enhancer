"""Reviewed staged bootstrap diagnostic: no listener, content-free phases only."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

from packaged_serve_probe import _environment, _ephemeral_loopback_port, _port_is_released
from prompt_enhancer.application.owned_process import run_owned_process


_PHASES = {"imports", "embedded_bootstrap", "settings", "initialize", "resource", "static_revision", "create_http_app", "complete"}
_ERRORS = {"none", "OSError", "RuntimeError", "ValueError", "ImportError", "ModuleNotFoundError", "TypeError", "AttributeError", "WindowsRuntimeBootstrapError", "other"}
_DETAILS = {"none", "dashboard_unavailable", "network_denied", "bootstrap_unsafe", "bootstrap_unavailable", "bootstrap_failed", "bootstrap_cleanup_unconfirmed", "other"}
_PTH_FLAGS = {
    "inspection_ok", "regular", "noreparse", "size_bounded", "size_equal",
    "mtime_equal", "ctime_equal", "lstat_after_equal", "active_lines_expected",
    "birthtime_available", "birthtime_equal",
    "dev_equal", "ino_equal", "ino_nonzero",
}
_CODE = r'''
import json, sys
phase = "imports"
error_kind = "none"
detail = "none"
bootstrap = None
closed = True
pth_metadata = None
def prohibit_network(event, arguments):
    if event in {"socket.connect", "socket.bind", "socket.getaddrinfo"}:
        raise RuntimeError("synthetic_probe_network_denied")
sys.addaudithook(prohibit_network)
try:
    from prompt_enhancer.cli import _initialize
    from prompt_enhancer.config import AppSettings
    from prompt_enhancer.infrastructure.windows_runtime_bootstrap import bootstrap_current_embedded_windows_runtime
    phase = "embedded_bootstrap"
    bootstrap = bootstrap_current_embedded_windows_runtime()
    phase = "settings"
    settings = AppSettings.from_env()
    phase = "initialize"
    application = _initialize(settings)
    phase = "resource"
    from prompt_enhancer.infrastructure.resources.packaged import default_packaged_resource_resolver
    from prompt_enhancer.application.resources import ResourceKind
    from prompt_enhancer.api import _static_app_revision
    resource = default_packaged_resource_resolver().resolve(ResourceKind.DASHBOARD_STATIC)
    phase = "static_revision"
    if resource.path is None:
        raise ValueError("integrated dashboard build is unavailable or unsafe")
    _static_app_revision(resource.path)
    phase = "create_http_app"
    app = application.create_http_app()
    phase = "complete"
except Exception as error:
    candidate = type(error).__name__
    error_kind = candidate if candidate in {"OSError", "RuntimeError", "ValueError", "ImportError", "ModuleNotFoundError", "TypeError", "AttributeError", "WindowsRuntimeBootstrapError"} else "other"
    detail = {
        "integrated dashboard build is unavailable or unsafe": "dashboard_unavailable",
        "synthetic_probe_network_denied": "network_denied",
        "windows runtime bootstrap path is unsafe": "bootstrap_unsafe",
        "windows runtime bootstrap path is unavailable": "bootstrap_unavailable",
        "windows runtime bootstrap is unavailable": "bootstrap_unavailable",
        "windows runtime bootstrap failed": "bootstrap_failed",
        "windows runtime bootstrap cleanup unconfirmed": "bootstrap_cleanup_unconfirmed",
    }.get(str(error), "other")
    if phase == "embedded_bootstrap" and detail == "bootstrap_unsafe":
        pth_metadata = {key:False for key in (
            "inspection_ok", "regular", "noreparse", "size_bounded", "size_equal",
            "mtime_equal", "ctime_equal", "lstat_after_equal", "active_lines_expected",
            "birthtime_available", "birthtime_equal",
            "dev_equal", "ino_equal", "ino_nonzero",
        )}
        try:
            import os, stat
            from pathlib import Path
            marker = Path(sys.executable).parent / "python313._pth"
            before = marker.lstat()
            pth_metadata["regular"] = stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode)
            pth_metadata["noreparse"] = not bool(getattr(before,"st_file_attributes",0) & 0x400)
            pth_metadata["size_bounded"] = 0 < before.st_size <= 4096
            if pth_metadata["regular"] and pth_metadata["noreparse"] and pth_metadata["size_bounded"]:
                with marker.open("rb") as stream:
                    opened = os.fstat(stream.fileno())
                    data = stream.read(4097)
                after = marker.lstat()
                pth_metadata["size_equal"] = before.st_size == opened.st_size == len(data)
                pth_metadata["mtime_equal"] = before.st_mtime_ns == opened.st_mtime_ns
                pth_metadata["ctime_equal"] = before.st_ctime_ns == opened.st_ctime_ns
                pth_metadata["dev_equal"] = before.st_dev == opened.st_dev
                pth_metadata["ino_equal"] = before.st_ino == opened.st_ino
                pth_metadata["ino_nonzero"] = bool(before.st_ino and opened.st_ino)
                pth_metadata["lstat_after_equal"] = (before.st_size,before.st_mtime_ns,before.st_ctime_ns) == (after.st_size,after.st_mtime_ns,after.st_ctime_ns)
                pth_metadata["birthtime_available"] = all(hasattr(item,"st_birthtime_ns") for item in (before,opened,after))
                pth_metadata["birthtime_equal"] = pth_metadata["birthtime_available"] and before.st_birthtime_ns == opened.st_birthtime_ns == after.st_birthtime_ns
                active = [line.strip() for line in data.decode("utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
                pth_metadata["active_lines_expected"] = active == ["python313.zip", "."]
                pth_metadata["inspection_ok"] = True
        except Exception:
            pass
finally:
    if bootstrap is not None:
        try:
            bootstrap.close()
        except Exception:
            closed = False
print("PACKAGED_BOOTSTRAP_CHILD=" + json.dumps({"phase":phase,"exception_kind":error_kind,"detail":detail,"bootstrap_closed":closed,"pth_metadata":pth_metadata},separators=(",",":")))
'''


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    report: dict[str, object] = {"contract": "packaged-bootstrap-probe.v1", "error_code": None}
    if len(arguments) != 1:
        report["error_code"] = "invalid_arguments"
    else:
        runtime = Path(arguments[0])
        port = _ephemeral_loopback_port()
        executable = runtime / "python.exe"
        if sys.platform != "win32" or not executable.is_absolute() or not executable.is_file() or port == 8765:
            report["error_code"] = "runtime_unavailable"
        else:
            try:
                results = Path(__file__).resolve().parents[2] / "test-results"
                results.mkdir(exist_ok=True)
                root = Path(tempfile.mkdtemp(prefix="packaged-bootstrap-", dir=results))
                (root / "temp").mkdir()
                (root / "empty-profile").mkdir()
                result = run_owned_process(
                    (os.fspath(executable), "-I", "-B", "-c", _CODE), cwd=root,
                    env=_environment(runtime, root, port), timeout=30,
                    stdout_limit=16384, stderr_limit=16384, maximum_active_processes=4,
                )
                report["exit_code"] = result.returncode
                # run_owned_process returns only after tree exit, reader joins,
                # and successful handle closure; otherwise it raises.
                report["owned_cleanup_confirmed"] = True
                report["stdout_bytes"] = len(result.stdout)
                report["stderr_bytes"] = len(result.stderr)
                raw = result.stdout.strip()
                prefix = b"PACKAGED_BOOTSTRAP_CHILD="
                def unique_pairs(pairs):
                    parsed = {}
                    for key, value in pairs:
                        if key in parsed:
                            raise ValueError("duplicate_field")
                        parsed[key] = value
                    return parsed

                receipt = json.loads(raw[len(prefix):], object_pairs_hook=unique_pairs) if raw.startswith(prefix) and b"\n" not in raw and b"\r" not in raw else None
                if (
                    not isinstance(receipt, dict)
                    or set(receipt) != {"phase", "exception_kind", "detail", "bootstrap_closed", "pth_metadata"}
                    or receipt["phase"] not in _PHASES
                    or receipt["exception_kind"] not in _ERRORS
                    or receipt["detail"] not in _DETAILS
                    or type(receipt["bootstrap_closed"]) is not bool
                    or (receipt["pth_metadata"] is not None and (
                        receipt["phase"] != "embedded_bootstrap"
                        or receipt["detail"] != "bootstrap_unsafe"
                        or not isinstance(receipt["pth_metadata"], dict)
                        or set(receipt["pth_metadata"]) != _PTH_FLAGS
                        or any(type(value) is not bool for value in receipt["pth_metadata"].values())
                    ))
                ):
                    report["error_code"] = "invalid_child_receipt"
                else:
                    report["diagnostic"] = receipt
                    if result.returncode != 0 or not receipt["bootstrap_closed"]:
                        report["error_code"] = "diagnostic_completion_unconfirmed"
            except Exception:
                report["error_code"] = "bootstrap_probe_failed"
            report["port_released"] = _port_is_released(port)
    print("PACKAGED_BOOTSTRAP_PROBE=" + json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if report["error_code"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
