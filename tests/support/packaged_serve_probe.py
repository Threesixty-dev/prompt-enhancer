"""Bounded isolated-runtime smoke for packaged ``serve`` startup.

This driver is intended for an explicitly reviewed staged-runtime run. It uses
the installed module entrypoint, a sterile temporary home, public loopback
routes only, and owned process-tree cleanup. It does not read the new app token,
provider sessions, provider credentials, model caches, or user configuration.
"""

from __future__ import annotations

import http.client
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import stat
import tempfile
import threading
import time
from typing import BinaryIO
from urllib.parse import urlsplit

from prompt_enhancer.application.owned_process import (
    process_tree_exited,
    start_owned_process,
    terminate_owned_process,
)


_STARTUP_TIMEOUT_SECONDS = 30.0
_HTTP_TIMEOUT_SECONDS = 0.75
_MAX_CAPTURE_BYTES = 64 * 1024
_MAX_HTTP_BYTES = 256 * 1024
_MAX_SINGLE_ASSET_BYTES = 2 * 1024 * 1024
_MAX_TOTAL_ASSET_BYTES = 8 * 1024 * 1024
_MAX_ASSET_REFERENCES = 32
_RELEASE_TIMEOUT_SECONDS = 5.0
_MODULE_IDENTIFIER = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*",
    flags=re.ASCII,
)
_STATIC_ASSET_PATH = re.compile(
    r"/assets/[A-Za-z0-9][A-Za-z0-9._-]{0,95}-[A-Za-z0-9_-]{8,64}"
    r"\.(?:js|mjs|css)",
    flags=re.ASCII,
)


def _read_bounded(
    stream: BinaryIO,
    destination: bytearray,
    overflow: threading.Event,
) -> None:
    while True:
        try:
            chunk = stream.read(4096)
        except (OSError, ValueError):
            return
        if not chunk:
            return
        remaining = _MAX_CAPTURE_BYTES - len(destination)
        if remaining > 0:
            destination.extend(chunk[:remaining])
        if len(chunk) > remaining:
            overflow.set()
            return


def _capture_threads(
    process,
) -> tuple[list[threading.Thread], list[bytearray], list[threading.Event]]:
    streams = (process.stdout, process.stderr)
    buffers = [bytearray(), bytearray()]
    overflows = [threading.Event(), threading.Event()]
    threads: list[threading.Thread] = []
    for stream, buffer, overflow, name in zip(
        streams,
        buffers,
        overflows,
        ("stdout", "stderr"),
        strict=True,
    ):
        if stream is None:
            continue
        thread = threading.Thread(
            target=_read_bounded,
            args=(stream, buffer, overflow),
            name=f"packaged-serve-{name}",
            daemon=True,
        )
        thread.start()
        threads.append(thread)
    return threads, buffers, overflows


class _DashboardAssetReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paths: set[str] = set()
        self.invalid_reference = False

    def _record(self, value: str | None) -> None:
        if value is None:
            self.invalid_reference = True
            return
        parsed = urlsplit(value)
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.path != value
            or len(value) > 180
            or _STATIC_ASSET_PATH.fullmatch(value) is None
        ):
            self.invalid_reference = True
            return
        self.paths.add(value)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag.casefold() == "script" and attributes.get("src") is not None:
            self._record(attributes.get("src"))
            return
        if tag.casefold() != "link":
            return
        rel = set((attributes.get("rel") or "").casefold().split())
        if "stylesheet" in rel or "modulepreload" in rel:
            self._record(attributes.get("href"))


def _read_staged_file(path: Path, *, maximum_bytes: int) -> bytes | None:
    try:
        metadata = path.lstat()
        reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if (
            getattr(metadata, "st_file_attributes", 0) & reparse_attribute
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_size > maximum_bytes
        ):
            return None
        with path.open("rb") as stream:
            content = stream.read(maximum_bytes + 1)
        if len(content) != metadata.st_size or len(content) > maximum_bytes:
            return None
        return content
    except OSError:
        return None


def _is_directory_not_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return (
        stat.S_ISDIR(metadata.st_mode)
        and not getattr(metadata, "st_file_attributes", 0) & reparse_attribute
    )


def _verify_dashboard_assets(
    runtime_root: Path,
    port: int,
    html: bytes,
) -> tuple[int, bool, str | None]:
    parser = _DashboardAssetReferences()
    try:
        parser.feed(html.decode("utf-8", errors="strict"))
        parser.close()
    except (UnicodeDecodeError, ValueError):
        return 0, False, "dashboard_html_invalid"
    paths = sorted(parser.paths)
    if parser.invalid_reference or not paths or len(paths) > _MAX_ASSET_REFERENCES:
        return len(paths), False, "dashboard_asset_reference_invalid"
    if not any(path.endswith((".js", ".mjs")) for path in paths) or not any(
        path.endswith(".css") for path in paths
    ):
        return len(paths), False, "dashboard_asset_reference_incomplete"

    dashboard_root = runtime_root / "prompt_enhancer" / "_resources" / "dashboard"
    asset_directory = dashboard_root / "assets"
    directories = (
        runtime_root,
        runtime_root / "prompt_enhancer",
        runtime_root / "prompt_enhancer" / "_resources",
        dashboard_root,
        asset_directory,
    )
    try:
        if any(not _is_directory_not_reparse(directory) for directory in directories):
            return len(paths), False, "staged_dashboard_assets_unavailable"
    except OSError:
        return len(paths), False, "staged_dashboard_assets_unavailable"
    total_bytes = 0
    for web_path in paths:
        relative_path = web_path.removeprefix("/")
        staged_file = dashboard_root.joinpath(*relative_path.split("/"))
        expected = _read_staged_file(
            staged_file,
            maximum_bytes=_MAX_SINGLE_ASSET_BYTES,
        )
        if expected is None:
            return len(paths), False, "staged_dashboard_asset_unavailable"
        total_bytes += len(expected)
        if total_bytes > _MAX_TOTAL_ASSET_BYTES:
            return len(paths), False, "staged_dashboard_assets_over_budget"
        accept = "text/css" if web_path.endswith(".css") else "text/javascript"
        try:
            status, _content_type, actual = _get(
                port,
                web_path,
                accept,
                maximum_bytes=len(expected),
            )
        except (OSError, http.client.HTTPException):
            return len(paths), False, "dashboard_asset_unavailable"
        if status != 200:
            return len(paths), False, "dashboard_asset_unavailable"
        if hashlib.sha256(actual).digest() != hashlib.sha256(expected).digest():
            return len(paths), False, "dashboard_asset_hash_mismatch"
    return len(paths), True, None


def _startup_diagnostic(buffers: list[bytearray]) -> str:
    """Return a sanitized code; never expose captured output or traceback lines."""
    text = b"\n".join(bytes(buffer) for buffer in buffers).decode(
        "utf-8",
        errors="replace",
    )
    if not text.strip():
        return "startup_output_empty"
    # Fixed semantic categories only: never forward exception messages, paths,
    # source lines or arbitrary identifiers from launcher/app diagnostics.
    for pattern, code in (
        (r"prompt-enhancer: local operation failed safely\.", "application_closed_failure"),
        (r"Fatal Python error:", "python_fatal_initialization"),
        (r"(?i)failed to (?:load|find).*python.*(?:dll|runtime)", "python_runtime_load_failed"),
        (r"(?i)(?:DLL load failed|specified module could not be found)", "native_library_load_failed"),
        (r"(?i)(?:access is denied|permission denied)", "startup_access_denied"),
        (r"(?i)(?:address already in use|only one usage of each socket address)", "loopback_bind_conflict"),
        (r"(?i)(?:not enough memory|out of memory)", "startup_memory_unavailable"),
        (r"(?i)(?:unrecognized arguments|no such option|invalid choice)", "startup_cli_arguments_rejected"),
        (r"(?i)application startup failed", "application_lifespan_failed"),
        (r"(?i)(?:failed to create|unable to create).*process", "launcher_process_creation_failed"),
    ):
        if re.search(pattern, text):
            return code
    missing_import = re.search(
        r"No module named ['\"]([A-Za-z_][A-Za-z0-9_.]*)['\"]",
        text,
    )
    if missing_import:
        module = missing_import.group(1)
        if len(module) <= 80 and _MODULE_IDENTIFIER.fullmatch(module):
            return f"missing_import_module:{module}"
        return "missing_import_other"
    for exception_name in (
        "ModuleNotFoundError",
        "ImportError",
        "OSError",
        "RuntimeError",
        "ValueError",
        "SyntaxError",
        "TypeError",
        "AttributeError",
        "MemoryError",
        "SystemExit",
    ):
        if re.search(rf"\b{exception_name}\b", text):
            return f"startup_{exception_name.casefold()}"
    return "startup_diagnostic_unclassified"


def _startup_exit_diagnostic(returncode: int | None) -> str:
    """Classify known Windows statuses without guessing an unknown failure."""
    if returncode is None:
        return "process_still_running"
    status = returncode & 0xFFFFFFFF
    return {
        0: "process_exit_success",
        1: "process_exit_general_failure",
        2: "process_exit_arguments_or_launcher_failure",
        0xC0000005: "windows_access_violation",
        0xC0000017: "windows_no_memory",
        0xC000007B: "windows_invalid_image_format",
        0xC0000135: "windows_dll_not_found",
        0xC0000142: "windows_dll_initialization_failed",
        0xC0000409: "windows_fail_fast",
    }.get(status, "process_exit_unclassified")


def _ephemeral_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_EXCLUSIVEADDRUSE,
                1,
            )
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _get(
    port: int,
    path: str,
    accept: str,
    *,
    maximum_bytes: int = _MAX_HTTP_BYTES,
) -> tuple[int, str, bytes]:
    connection = http.client.HTTPConnection(
        "127.0.0.1",
        port,
        timeout=_HTTP_TIMEOUT_SECONDS,
    )
    try:
        connection.request("GET", path, headers={"Accept": accept})
        response = connection.getresponse()
        content_type = response.getheader("Content-Type", "")
        payload = response.read(maximum_bytes + 1)
        if len(payload) > maximum_bytes:
            return response.status, content_type, b""
        return response.status, content_type, payload
    finally:
        connection.close()


def _environment(runtime_root: Path, root: Path, port: int) -> dict[str, str]:
    home = root / "private-home"
    profile = root / "empty-profile"
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR")
    path_entries = [os.fspath(runtime_root)]
    if system_root:
        path_entries.append(os.fspath(Path(system_root) / "System32"))
    return {
        "PATH": os.pathsep.join(path_entries),
        "SYSTEMROOT": system_root or "",
        "WINDIR": system_root or "",
        "TEMP": os.fspath(root / "temp"),
        "TMP": os.fspath(root / "temp"),
        "USERPROFILE": os.fspath(profile),
        "HOME": os.fspath(profile),
        "APPDATA": os.fspath(profile / "AppData" / "Roaming"),
        "LOCALAPPDATA": os.fspath(profile / "AppData" / "Local"),
        "PROMPT_ENHANCER_HOME": os.fspath(home),
        "PROMPT_ENHANCER_SESSION_READER": "disabled",
        "PROMPT_ENHANCER_HOST": "127.0.0.1",
        "PROMPT_ENHANCER_PORT": str(port),
        "PROMPT_ENHANCER_CLAUDE_HOME": os.fspath(root / "empty-claude"),
        "CODEX_HOME": os.fspath(root / "empty-codex"),
        "HF_HOME": os.fspath(root / "empty-model-cache"),
        "PYTHONIOENCODING": "utf-8",
    }


def _port_is_released(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_EXCLUSIVEADDRUSE,
                    1,
                )
            listener.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def probe(runtime_root: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "contract": "packaged-serve-probe.v1",
        "runtime_python_present": False,
        "process_started": False,
        "health_ok": False,
        "agent_static_ok": False,
        "dashboard_assets_checked": 0,
        "dashboard_asset_hashes_match": False,
        "owned_tree_stopped": False,
        "process_handles_closed": False,
        "port_released": False,
        "shutdown_kind": "owned_process_termination",
        "error_code": None,
    }
    executable = runtime_root / "python.exe"
    if sys.platform != "win32" or not executable.is_file():
        report["error_code"] = "runtime_unavailable"
        return report
    report["runtime_python_present"] = True

    process = None
    threads: list[threading.Thread] = []
    buffers: list[bytearray] = []
    overflows: list[threading.Event] = []
    port = _ephemeral_loopback_port()
    artifact_root = Path(__file__).resolve().parents[2] / "test-results"
    artifact_root.mkdir(parents=True, exist_ok=True)
    # Keep the isolated app database and logs' containing directory for review;
    # never print this path and never recursively remove it from the probe.
    root = Path(
        tempfile.mkdtemp(prefix="packaged-serve-smoke-", dir=artifact_root)
    )
    try:
        (root / "temp").mkdir()
        (root / "empty-profile").mkdir()
        env = _environment(runtime_root, root, port)
        process = start_owned_process(
            (
                os.fspath(executable),
                "-I",
                "-B",
                "-m",
                "prompt_enhancer",
                "serve",
            ),
            cwd=root,
            env=env,
            capture_stdout=True,
            capture_stderr=True,
            maximum_active_processes=4,
        )
        threads, buffers, overflows = _capture_threads(process)
        report["process_started"] = True

        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        failure: str | None = None
        while time.monotonic() < deadline:
            if any(item.is_set() for item in overflows):
                failure = "server_output_limit"
                break
            try:
                status, content_type, payload = _get(
                    port,
                    "/health",
                    "application/json",
                )
                if status == 200:
                    health = json.loads(payload)
                    if health != {
                        "status": "ok",
                        "cost_mode": "offline_only",
                        "data_tier": "metadata",
                    }:
                        failure = "health_contract_mismatch"
                        break
                    report["health_ok"] = True
                    break
            except (OSError, http.client.HTTPException, ValueError):
                pass
            if process_tree_exited(process):
                failure = "server_exited_before_ready"
                break
            time.sleep(0.1)
        if not report["health_ok"] and failure is None:
            failure = "health_timeout"

        if report["health_ok"] and failure is None:
            try:
                status, content_type, payload = _get(
                    port,
                    "/agent",
                    "text/html",
                )
                report["agent_static_ok"] = (
                    status == 200
                    and "text/html" in content_type.casefold()
                    and payload.lower().startswith(b"<!doctype html")
                )
                if not report["agent_static_ok"]:
                    failure = "agent_static_unavailable"
                else:
                    (
                        report["dashboard_assets_checked"],
                        report["dashboard_asset_hashes_match"],
                        failure,
                    ) = _verify_dashboard_assets(runtime_root, port, payload)
            except (OSError, http.client.HTTPException):
                failure = "agent_static_unavailable"
        if failure in {"server_exited_before_ready", "health_timeout"}:
            for thread in threads:
                thread.join(timeout=0.25)
            report["startup_diagnostic"] = _startup_diagnostic(buffers)
            report["startup_exit_code"] = process.poll()
            report["startup_exit_category"] = _startup_exit_diagnostic(process.poll())
            report["startup_stdout_bytes"] = len(buffers[0])
            report["startup_stderr_bytes"] = len(buffers[1])
        report["error_code"] = failure
    except Exception:
        report["error_code"] = "serve_probe_failed"
    finally:
        # Stop the complete owned process tree before closing handles or doing
        # anything that could affect its working directory/state.
        if process is not None:
            report["owned_tree_stopped"] = terminate_owned_process(
                process,
                graceful_timeout=0.1,
                forced_timeout=2.0,
            )
            try:
                report["process_handles_closed"] = bool(
                    process.close(close_streams=True)
                )
            except Exception:
                report["process_handles_closed"] = False
            for thread in threads:
                thread.join(timeout=1.0)
        release_deadline = time.monotonic() + _RELEASE_TIMEOUT_SECONDS
        while time.monotonic() < release_deadline:
            if _port_is_released(port):
                report["port_released"] = True
                break
            time.sleep(0.05)
        if report["error_code"] is None and not all(
            report[key]
            for key in (
                "health_ok",
                "agent_static_ok",
                "dashboard_asset_hashes_match",
                "owned_tree_stopped",
                "process_handles_closed",
                "port_released",
            )
        ):
            report["error_code"] = "serve_cleanup_unconfirmed"
    return report


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("PACKAGED_SERVE_PROBE={\"error_code\":\"invalid_arguments\"}")
        return 2
    report = probe(Path(arguments[0]))
    print(
        "PACKAGED_SERVE_PROBE="
        + json.dumps(report, sort_keys=True, separators=(",", ":")),
        flush=True,
    )
    passed = (
        report.get("runtime_python_present") is True
        and report.get("process_started") is True
        and report.get("health_ok") is True
        and report.get("agent_static_ok") is True
        and report.get("dashboard_asset_hashes_match") is True
        and report.get("owned_tree_stopped") is True
        and report.get("process_handles_closed") is True
        and report.get("port_released") is True
        and report.get("error_code") is None
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
