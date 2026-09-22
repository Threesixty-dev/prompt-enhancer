"""Owned packaged MCP Store UI probe with an injected fictional registry.

The browser uses the packaged production UI and authenticated read-only routes.
Only the registry transport is replaced by a fixed in-process fictional client;
the receipt never represents official-registry or installation acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time

sys.path.insert(0, os.fspath(Path(__file__).resolve().parents[2] / "scripts"))

from pack_msix_candidate import PackError, _manifest, _verify_candidate
from packaged_chat_probe import _ProbeFailure, _await_ready
from packaged_serve_probe import _capture_threads, _environment, _ephemeral_loopback_port, _port_is_released
from packaged_streaming_runner import _checked_file, _safe_external_root, _unique_pairs
from prompt_enhancer.application.mcp_registry_catalog import McpRegistryCacheRecord
from prompt_enhancer.application.owned_process import (
    OwnedProcessRunError, process_tree_exited, run_owned_process,
    start_owned_process, terminate_owned_process,
)

_PREFIX = b"PACKAGED_MCP_STORE_BROWSER_PROBE="
_FLAGS = {
    "passed", "browser_started", "browser_closed", "agent_page_loaded",
    "store_opened", "initial_catalog_verified", "initial_tiles_visible",
    "search_catalog_verified", "search_result_visible", "review_api_verified",
    "provenance_visible", "review_boundary_visible", "setup_plan_disabled",
    "returned_to_catalog", "live_review_rendered", "cached_delivery_verified",
    "cached_age_visible", "exact_review_unavailable", "uncached_query_refused",
}
_COUNTS = {
    "initial_tiles", "searched_tiles", "catalog_response_events",
    "review_response_events", "forbidden_mutations", "external_requests",
    "page_errors", "server_failures", "managed_lifecycle_mutations",
    "model_mutations", "native_confirmation_mutations", "settings_locator_count",
    "expected_outage_responses",
}
_STATUSES = {"agent_navigation_status", "initial_catalog_status", "search_catalog_status",
             "review_status", "uncached_catalog_status"}
_BROWSER_ERRORS = {
    "invalid_environment", "browser_launch_failed", "context_create_failed",
    "page_create_failed", "agent_page_failed", "store_open_failed",
    "catalog_response_failed", "catalog_display_failed", "search_response_failed",
    "search_display_failed", "review_response_failed", "review_display_failed",
    "install_boundary_failed", "return_failed", "request_boundary_failed",
    "cached_delivery_failed", "cached_age_failed", "review_refusal_failed",
    "uncached_query_failed",
    "browser_cleanup_failed", "probe_failed",
}
_RUNNER_FLAGS = {"two_launches_ready", "two_browsers_verified", "registry_injection_explicit",
    "registry_calls_verified", "registry_cache_verified", "cache_persisted_after_restart",
    "cache_unchanged_during_outage", "python_socket_guard_active", "candidate_unchanged",
    "two_launch_cleanup_confirmed", "candidate_ui_entrypoint_verified"}
_RUNNER_ERRORS = {
    "probe_inputs_unavailable", "artifact_root_unsafe", "candidate_invalid",
    "candidate_ui_resource_missing", "unsafe_probe_port", "server_output_limit",
    "server_exited_before_ready", "health_timeout", "browser_failed",
    "server_exited_during_browser", "registry_receipt_invalid",
    "registry_cache_invalid", "cache_changed_during_outage", "candidate_changed", "cleanup_unconfirmed",
    "probe_failed", "invalid_arguments",
}
_DASHBOARD_PREFIX = "prompt_enhancer/_resources/dashboard/"

_SERVER_CODE = r'''
import json, os, socket, sys, threading
from pathlib import Path

stats_path = Path(sys.argv[1])
client_mode = sys.argv[2]
if client_mode not in {"live", "outage"}:
    raise SystemExit(2)
port = int(os.environ["PROMPT_ENHANCER_PORT"])
stats = {"contract":"synthetic-mcp-registry-client.v1","list_calls":0,
         "detail_calls":0,"history_calls":0,"invalid_calls":0,"network_attempts":0,
         "outage_refusals":0,"client_mode":client_mode,
         "startup_phase":"audit_installed","startup_error":None}
lock = threading.Lock()

def publish():
    encoded = json.dumps(stats, sort_keys=True, separators=(",", ":")).encode("ascii")
    temporary = stats_path.with_suffix(".tmp")
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, stats_path)

def audit(event, arguments):
    if event not in {"socket.connect", "socket.bind", "socket.getaddrinfo"}:
        return
    address = arguments[1] if event in {"socket.connect", "socket.bind"} and len(arguments) > 1 else (arguments[0] if arguments else None)
    host = address[0] if isinstance(address, tuple) and address else address
    if host in {"127.0.0.1", "localhost"}:
        return
    with lock:
        stats["network_attempts"] += 1
        publish()
    raise RuntimeError("synthetic_registry_network_denied")

sys.addaudithook(audit)
publish()
if os.environ.get("PE_MCP_AUDIT_SELFTEST") == "1":
    audit("socket.connect", (None, ("127.0.0.1", 4567)))
    audit("socket.bind", (None, ("localhost", 4567)))
    for synthetic in (("socket.connect", (None, ("203.0.113.1", 443))),
                      ("socket.getaddrinfo", ("registry.example",))):
        try:
            audit(*synthetic)
        except RuntimeError:
            pass
        else:
            raise RuntimeError("synthetic_audit_refusal_missing")
    publish()
    sys.stdout.write("SYNTHETIC_MCP_AUDIT_SELFTEST=passed\n")
    raise SystemExit(0)

def startup_phase(value):
    with lock:
        stats["startup_phase"] = value
        publish()

def startup_failure(error):
    if isinstance(error, (ImportError, ModuleNotFoundError)):
        category = "import_error"
    elif isinstance(error, ValueError):
        category = "configuration_error"
    elif isinstance(error, OSError):
        category = "os_error"
    elif isinstance(error, RuntimeError):
        category = "runtime_error"
    else:
        category = "unexpected_error"
    with lock:
        stats["startup_error"] = category
        publish()

def raw_server(name, title, version="1.2.3"):
    return {"server": {
      "$schema":"https://static.modelcontextprotocol.io/schemas/example/server.schema.json",
      "name":name,"title":title,"description":"Fictional public MCP metadata.","version":version,
      "websiteUrl":"https://example.com/mcp", "repository":{"url":"https://github.com/example/mcp","source":"github","id":"example-repository","subfolder":"packages/example"},
      "packages":[{"registryType":"npm","identifier":"@example/synthetic-files","version":version,"runtimeHint":"npx","fileSha256":"a"*64,"transport":{"type":"stdio"}}]},
      "_meta":{"io.modelcontextprotocol.registry/official":{"status":"active","updatedAt":"2040-01-02T10:00:00Z","isLatest":version=="1.2.3"}}}

files = raw_server("com.example/synthetic-files", "Synthetic Files")
browser = raw_server("com.example/synthetic-browser", "Synthetic Browser")

class FixedClient:
    def list_servers(self, *, search, cursor, limit):
        valid_searches = {"", "fictional files"} if client_mode == "live" else {"", "fictional files", "uncached example"}
        valid = cursor is None and limit == 24 and search in valid_searches
        with lock:
            stats["list_calls"] += 1
            if not valid: stats["invalid_calls"] += 1
            if valid and client_mode == "outage": stats["outage_refusals"] += 1
            publish()
        if not valid: raise RuntimeError("synthetic_registry_call_invalid")
        if client_mode == "outage": raise McpRegistryClientError("registry_unavailable")
        rows = [files, browser] if search == "" else [files]
        return {"servers":rows,"metadata":{"count":len(rows),"nextCursor":None}}
    def get_server_version(self, *, name, version):
        valid = name == "com.example/synthetic-files" and version == "1.2.3"
        with lock:
            stats["detail_calls"] += 1
            if not valid: stats["invalid_calls"] += 1
            if valid and client_mode == "outage": stats["outage_refusals"] += 1
            publish()
        if not valid: raise RuntimeError("synthetic_registry_call_invalid")
        if client_mode == "outage": raise McpRegistryClientError("registry_unavailable")
        return files
    def list_server_versions(self, *, name):
        valid = name == "com.example/synthetic-files"
        with lock:
            stats["history_calls"] += 1
            if not valid: stats["invalid_calls"] += 1
            if valid and client_mode == "outage": stats["outage_refusals"] += 1
            publish()
        if not valid: raise RuntimeError("synthetic_registry_call_invalid")
        if client_mode == "outage": raise McpRegistryClientError("registry_unavailable")
        older = raw_server(name, "Synthetic Files", "1.1.0")
        return {"servers":[files, older],"metadata":{"count":2}}
    def fetch_icon(self, source):
        with lock:
            stats["invalid_calls"] += 1
            publish()
        raise RuntimeError("synthetic_registry_icon_refused")

try:
    startup_phase("runtime_bootstrap_import")
    from prompt_enhancer.infrastructure.windows_runtime_bootstrap import bootstrap_current_embedded_windows_runtime
    startup_phase("runtime_bootstrap")
    runtime_bootstrap = bootstrap_current_embedded_windows_runtime()
    startup_phase("application_import")
    from prompt_enhancer.config import AppSettings
    from prompt_enhancer.bootstrap import LocalApplication, bootstrap_local_application
    startup_phase("mcp_import")
    from prompt_enhancer.application.mcp_registry_catalog import McpRegistryCatalogService, McpRegistryClientError
    from prompt_enhancer.infrastructure.mcp_registry import JsonMcpRegistryCache

    class InjectedApplication(LocalApplication):
        def create_mcp_registry_catalog_service(self):
            return McpRegistryCatalogService(FixedClient(), JsonMcpRegistryCache(self.settings.mcp_registry_cache_path))

    startup_phase("settings")
    settings = AppSettings.from_env()
    startup_phase("application_bootstrap")
    base = bootstrap_local_application(settings)
    application = InjectedApplication(base.settings, base.database, base.pseudonymizer)
    startup_phase("app_composition")
    app = application.create_http_app()
    import uvicorn
    startup_phase("server_run")
    uvicorn.run(app, host="127.0.0.1", port=port, access_log=False, log_level="warning")
    startup_phase("server_returned")
except Exception as error:
    startup_failure(error)
    raise SystemExit(1) from None
'''


def _candidate_ui_bound(candidate: object) -> bool:
    try:
        names = {item.relative_path for item in candidate.files}  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        return False
    return (_DASHBOARD_PREFIX + "index.html" in names and any(
        name.startswith(_DASHBOARD_PREFIX + "assets/") and name.endswith(".js")
        for name in names))


def _browser_passed(value: dict[str, object] | None) -> bool:
    common = _FLAGS - {"live_review_rendered", "cached_delivery_verified", "cached_age_visible",
        "exact_review_unavailable", "uncached_query_refused", "provenance_visible", "review_boundary_visible"}
    if not (value and value.get("error_code") is None
        and value.get("exception_kind") is None
        and all(value.get(key) is True for key in common)
        and value.get("initial_tiles") == 2 and value.get("searched_tiles") == 1
        and value.get("settings_locator_count") == 1
        and value.get("agent_navigation_status") == 200
        and value.get("initial_catalog_status") == 200 and value.get("search_catalog_status") == 200
        and 2 <= value.get("catalog_response_events", 0) <= 10
        and 1 <= value.get("review_response_events", 0) <= 5
        and all(value.get(key) == 0 for key in (
            "forbidden_mutations", "external_requests", "page_errors",
            "server_failures", "managed_lifecycle_mutations", "model_mutations",
            "native_confirmation_mutations"))):
        return False
    if value.get("journey_phase") == "live":
        return bool(value.get("review_status") == 200 and value.get("uncached_catalog_status") is None
            and value.get("expected_outage_responses") == 0
            and value.get("live_review_rendered") is True and value.get("provenance_visible") is True
            and value.get("review_boundary_visible") is True
            and all(value.get(key) is False for key in ("cached_delivery_verified", "cached_age_visible",
                "exact_review_unavailable", "uncached_query_refused")))
    if value.get("journey_phase") == "cached":
        return bool(value.get("review_status") == 503 and value.get("uncached_catalog_status") == 503
            and value.get("expected_outage_responses") == 2
            and value.get("live_review_rendered") is False and value.get("provenance_visible") is False
            and value.get("review_boundary_visible") is False
            and all(value.get(key) is True for key in ("cached_delivery_verified", "cached_age_visible",
                "exact_review_unavailable", "uncached_query_refused")))
    return False


def _browser_receipt(output: bytes | bytearray) -> dict[str, object] | None:
    raw = bytes(output)
    try:
        if (len(raw) > 16_384 or not raw.startswith(_PREFIX) or not raw.endswith(b"\n")
                or raw.count(b"\n") != 1 or b"\r" in raw):
            return None
        value = json.loads(raw[len(_PREFIX):-1], object_pairs_hook=_unique_pairs)
        expected = _FLAGS | _COUNTS | _STATUSES | {"contract", "journey_phase", "error_code", "exception_kind"}
        if (not isinstance(value, dict) or set(value) != expected
                or value.get("contract") != "packaged-mcp-store-browser-probe.v2"):
            return None
        if any(type(value[key]) is not bool for key in _FLAGS):
            return None
        if any(type(value[key]) is not int or not 0 <= value[key] <= 100 for key in _COUNTS):
            return None
        if any(value[key] is not None and (type(value[key]) is not int or not 100 <= value[key] <= 599) for key in _STATUSES):
            return None
        if value["error_code"] is not None and (type(value["error_code"]) is not str or value["error_code"] not in _BROWSER_ERRORS):
            return None
        if value["exception_kind"] is not None and value["exception_kind"] not in {"timeout", "target_closed", "playwright_error", "unknown"}:
            return None
        if value["journey_phase"] not in {"live", "cached"}:
            return None
        if value["passed"] != _browser_passed(value):
            return None
        return value
    except (TypeError, ValueError, UnicodeError):
        return None


def _read_closed_json(path: Path, contract: str) -> dict[str, object] | None:
    try:
        metadata = path.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
                or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)
                or metadata.st_nlink != 1 or not 2 <= metadata.st_size <= 4096):
            return None
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if ((opened.st_dev, opened.st_ino, opened.st_size) != (metadata.st_dev, metadata.st_ino, metadata.st_size)
                    or not stat.S_ISREG(opened.st_mode)):
                return None
            raw = os.read(descriptor, 4097)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if ((after.st_dev, after.st_ino, after.st_size) != (metadata.st_dev, metadata.st_ino, metadata.st_size)
                or len(raw) != metadata.st_size):
            return None
        value = json.loads(raw, object_pairs_hook=_unique_pairs)
        expected = {"contract", "list_calls", "detail_calls", "history_calls", "invalid_calls", "network_attempts",
                    "outage_refusals", "client_mode", "startup_phase", "startup_error"}
        if not isinstance(value, dict) or set(value) != expected or value.get("contract") != contract:
            return None
        if any(type(value[key]) is not int or not 0 <= value[key] <= 100 for key in {
                "list_calls", "detail_calls", "history_calls", "invalid_calls", "network_attempts", "outage_refusals"}):
            return None
        if value["client_mode"] not in {"live", "outage"}:
            return None
        if value["startup_phase"] not in {"audit_installed", "runtime_bootstrap_import", "runtime_bootstrap",
                "application_import", "mcp_import", "settings", "application_bootstrap",
                "app_composition", "server_run", "server_returned"}:
            return None
        if value["startup_error"] is not None and value["startup_error"] not in {
                "import_error", "configuration_error", "os_error", "runtime_error", "unexpected_error"}:
            return None
        return value
    except (OSError, ValueError, TypeError, UnicodeError):
        return None


def _cache_valid(path: Path) -> bool:
    try:
        metadata = path.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
                or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)
                or metadata.st_nlink != 1 or not 2 <= metadata.st_size <= 1_048_576):
            return False
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if ((opened.st_dev, opened.st_ino, opened.st_size) != (metadata.st_dev, metadata.st_ino, metadata.st_size)
                    or not stat.S_ISREG(opened.st_mode)):
                return False
            raw = os.read(descriptor, 1_048_577)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if ((after.st_dev, after.st_ino, after.st_size) != (metadata.st_dev, metadata.st_ino, metadata.st_size)
                or len(raw) != metadata.st_size):
            return False
        payload = json.loads(raw, object_pairs_hook=_unique_pairs)
        entries = payload.get("entries") if isinstance(payload, dict) else None
        def key(search: str) -> str:
            return hashlib.sha256(f"v1\x00{search}\x00\x0024".encode("utf-8")).hexdigest()
        if (set(payload) != {"format_version", "entries"} or payload.get("format_version") != 2
                or not isinstance(entries, dict) or set(entries) != {key(""), key("fictional files")}):
            return False
        blank = McpRegistryCacheRecord.model_validate(entries[key("")])
        searched = McpRegistryCacheRecord.model_validate(entries[key("fictional files")])
        blank_identities = {(server.name, server.title, server.version) for server in blank.servers}
        searched_identities = {(server.name, server.title, server.version) for server in searched.servers}
        return (blank.search == "" and blank.cursor is None and blank.limit == 24
            and blank.next_cursor is None and blank.partial is False
            and len(blank.servers) == 2
            and blank_identities == {
                ("com.example/synthetic-files", "Synthetic Files", "1.2.3"),
                ("com.example/synthetic-browser", "Synthetic Browser", "1.2.3")}
            and searched.search == "fictional files" and searched.cursor is None and searched.limit == 24
            and searched.next_cursor is None and searched.partial is False
            and len(searched.servers) == 1
            and searched_identities == {("com.example/synthetic-files", "Synthetic Files", "1.2.3")})
    except (OSError, ValueError, TypeError, UnicodeError):
        return False


def _audit_selftest(root: Path) -> bool:
    receipt = root / "audit-receipt.json"
    executable = Path(getattr(sys, "_base_executable", sys.executable))
    if _checked_file(executable) is None:
        return False
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR")
    path_entries = [os.fspath(executable.parent)]
    if system_root:
        path_entries.append(os.fspath(Path(system_root) / "System32"))
    environment = {"PATH": os.pathsep.join(path_entries), "SYSTEMROOT": system_root or "",
                   "WINDIR": system_root or ""}
    environment.update(TEMP=os.fspath(root), TMP=os.fspath(root), PYTHONIOENCODING="utf-8",
                       PE_MCP_AUDIT_SELFTEST="1", PROMPT_ENHANCER_PORT="4567")
    try:
        result = run_owned_process((os.fspath(executable), "-I", "-B", "-c", _SERVER_CODE, os.fspath(receipt), "live"),
            cwd=root, env=environment, stdout_limit=256, stderr_limit=256,
            timeout=10, maximum_active_processes=1)
    except OwnedProcessRunError:
        return False
    value = _read_closed_json(receipt, "synthetic-mcp-registry-client.v1")
    return (result.returncode == 0 and result.stderr == b""
            and result.stdout.splitlines() == [b"SYNTHETIC_MCP_AUDIT_SELFTEST=passed"]
            and value is not None and value["network_attempts"] == 2
            and value["client_mode"] == "live" and value["outage_refusals"] == 0
            and value["startup_phase"] == "audit_installed" and value["startup_error"] is None
            and value["list_calls"] == value["detail_calls"] == value["history_calls"] == 0)


def _cache_snapshot(path: Path) -> tuple[int, int, int, int, str] | None:
    try:
        metadata = path.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode)
                or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)
                or metadata.st_nlink != 1 or not 2 <= metadata.st_size <= 1_048_576):
            return None
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if ((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_nlink)
                    != (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, metadata.st_nlink)
                    or not stat.S_ISREG(opened.st_mode)):
                return None
            raw = os.read(descriptor, 1_048_577)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        path_after = path.lstat()
        expected = (metadata.st_dev, metadata.st_ino, metadata.st_size,
                    metadata.st_mtime_ns, metadata.st_nlink)
        if ((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink) != expected
                or (path_after.st_dev, path_after.st_ino, path_after.st_size,
                    path_after.st_mtime_ns, path_after.st_nlink) != expected
                or not stat.S_ISREG(path_after.st_mode) or stat.S_ISLNK(path_after.st_mode)
                or bool(getattr(path_after, "st_file_attributes", 0) & 0x400)
                or len(raw) != metadata.st_size):
            return None
        return (metadata.st_dev, metadata.st_ino, metadata.st_size,
                metadata.st_mtime_ns, hashlib.sha256(raw).hexdigest())
    except OSError:
        return None


def _run_browser(node: Path, script: Path, executable: Path, environment: dict[str, str],
                 root: Path, port: int, phase: str, report: dict[str, object]) -> dict[str, object]:
    child = dict(environment)
    child.update(PE_PACKAGED_BASE_URL=f"http://127.0.0.1:{port}",
                 PE_PACKAGED_BROWSER_EXECUTABLE=os.fspath(executable),
                 PE_PACKAGED_MCP_STORE_PHASE=phase)
    try:
        result = run_owned_process((os.fspath(node), os.fspath(script)), cwd=root, env=child,
            stdout_limit=16_384, stderr_limit=16_384, timeout=90, maximum_active_processes=8)
        report["browser_cleanups_confirmed"] += 1
    except OwnedProcessRunError as error:
        if error.code in {"owned_process_timeout", "owned_process_stdout_limit", "owned_process_stderr_limit"}:
            report["browser_cleanups_confirmed"] += 1
        raise _ProbeFailure("browser_failed") from None
    receipt = _browser_receipt(result.stdout)
    report["browser_receipts"].append(receipt)
    if result.returncode == 0:
        report["browser_zero_exits"] += 1
    if not result.stderr:
        report["browser_stderr_empty_runs"] += 1
    if (result.returncode != 0 or result.stderr or not _browser_passed(receipt)
            or receipt.get("journey_phase") != phase):
        raise _ProbeFailure("browser_failed")
    return receipt  # type: ignore[return-value]


def _complete(report: dict[str, object]) -> bool:
    return report.get("error_code") is None and all(report.get(key) is True for key in _RUNNER_FLAGS)


def _record_cleanup_error(report: dict[str, object], code: str, primary_failure: bool) -> None:
    """Record cleanup/output failure without replacing the phase's primary failure."""
    if not primary_failure and report.get("error_code") is None:
        report["error_code"] = code


def probe(runtime: Path, candidate_manifest: Path, candidate_manifest_sha256: str,
          node: Path, script: Path, browser_executable: Path, artifact_root: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "contract": "packaged-mcp-store-runner.v2", "passed": False, "error_code": None,
        **dict.fromkeys(_RUNNER_FLAGS, False), "registry_client": "injected_synthetic",
        "network_isolation_proven": False, "registry_list_calls": [0, 0],
        "registry_detail_calls": [0, 0], "registry_history_calls": [0, 0],
        "registry_outage_refusals": [0, 0], "registry_invalid_calls": [0, 0],
        "server_network_attempts": [0, 0], "server_startup_phases": [None, None],
        "server_startup_errors": [None, None], "shutdown_kind": "owned_process_termination",
        "browser_receipts": [], "browser_zero_exits": 0, "browser_stderr_empty_runs": 0,
        "browser_cleanups_confirmed": 0, "server_launches_ready": 0,
        "server_trees_stopped": 0, "server_handles_closed": 0,
        "server_readers_stopped": 0, "ports_released": 0,
    }
    if (sys.platform != "win32" or any(_checked_file(path) is None for path in (
            runtime / "python.exe", candidate_manifest, node, script, browser_executable))):
        report["error_code"] = "probe_inputs_unavailable"; return report
    if _safe_external_root(artifact_root) is None:
        report["error_code"] = "artifact_root_unsafe"; return report
    try:
        candidate, canonical = _manifest(candidate_manifest, candidate_manifest_sha256)
        _verify_candidate(runtime, candidate, canonical)
    except (PackError, OSError, ValueError):
        report["error_code"] = "candidate_invalid"; return report
    if not _candidate_ui_bound(candidate):
        report["error_code"] = "candidate_ui_resource_missing"; return report
    root = Path(tempfile.mkdtemp(prefix="packaged-mcp-store-", dir=artifact_root))
    cache_path = root / "private-home" / "mcp-registry-cache.json"
    live_cache_snapshot = None
    try:
        for name in ("temp", "empty-profile", "empty-codex", "empty-claude", "empty-model-cache"):
            (root / name).mkdir()
        report["registry_injection_explicit"] = True
        for index, phase in enumerate(("live", "outage")):
            port = _ephemeral_loopback_port()
            if port in {8765, 8766} or not 1024 <= port <= 65535:
                raise _ProbeFailure("unsafe_probe_port")
            environment = _environment(runtime, root, port)
            stats_path = root / f"registry-receipt-{index + 1}.json"
            server = capture = None
            original_failure = False
            cleanup_failed = False
            try:
                server = start_owned_process((os.fspath(runtime / "python.exe"), "-I", "-B", "-c",
                    _SERVER_CODE, os.fspath(stats_path), phase), cwd=root, env=environment,
                    capture_stdout=True, capture_stderr=True, maximum_active_processes=4)
                capture = _capture_threads(server)
                _await_ready(server, port, capture[2])
                report["server_launches_ready"] += 1
                if index == 1:
                    current = _cache_snapshot(cache_path)
                    if live_cache_snapshot is None or current != live_cache_snapshot:
                        raise _ProbeFailure("cache_changed_during_outage")
                    report["cache_persisted_after_restart"] = True
                _run_browser(node, script, browser_executable, environment, root, port,
                             "live" if index == 0 else "cached", report)
                if process_tree_exited(server):
                    raise _ProbeFailure("server_exited_during_browser")
                stats = _read_closed_json(stats_path, "synthetic-mcp-registry-client.v1")
                expected = ((2, 1, 1, 0), (3, 1, 0, 4))[index]
                if (stats is None or stats["client_mode"] != phase
                        or (stats["list_calls"], stats["detail_calls"], stats["history_calls"],
                            stats["outage_refusals"]) != expected
                        or stats["invalid_calls"] != 0 or stats["network_attempts"] != 0
                        or stats["startup_phase"] != "server_run" or stats["startup_error"] is not None):
                    raise _ProbeFailure("registry_receipt_invalid")
                for key, report_key in (("list_calls", "registry_list_calls"),
                        ("detail_calls", "registry_detail_calls"), ("history_calls", "registry_history_calls"),
                        ("outage_refusals", "registry_outage_refusals"), ("invalid_calls", "registry_invalid_calls"),
                        ("network_attempts", "server_network_attempts")):
                    report[report_key][index] = stats[key]
                report["server_startup_phases"][index] = stats["startup_phase"]
                report["server_startup_errors"][index] = stats["startup_error"]
                report["python_socket_guard_active"] = True
                if index == 0:
                    if not _cache_valid(cache_path):
                        raise _ProbeFailure("registry_cache_invalid")
                    live_cache_snapshot = _cache_snapshot(cache_path)
                    if live_cache_snapshot is None:
                        raise _ProbeFailure("registry_cache_invalid")
                    report["registry_cache_verified"] = True
                else:
                    if _cache_snapshot(cache_path) != live_cache_snapshot:
                        raise _ProbeFailure("cache_changed_during_outage")
                    report["cache_unchanged_during_outage"] = True
            except _ProbeFailure:
                original_failure = True
                raise
            except Exception:
                original_failure = True
                raise
            finally:
                if server is not None:
                    try:
                        if terminate_owned_process(server, graceful_timeout=.1, forced_timeout=3):
                            report["server_trees_stopped"] += 1
                    except Exception:
                        pass
                    try:
                        if server.close(close_streams=True):
                            report["server_handles_closed"] += 1
                    except Exception:
                        pass
                if capture is not None:
                    for thread in capture[0]: thread.join(timeout=1)
                    if all(not thread.is_alive() for thread in capture[0]):
                        report["server_readers_stopped"] += 1
                    if any(event.is_set() for event in capture[2]):
                        cleanup_failed = True
                        _record_cleanup_error(report, "server_output_limit", original_failure)
                    for buffer in capture[1]: buffer.clear()
                stats = _read_closed_json(stats_path, "synthetic-mcp-registry-client.v1")
                if stats is not None:
                    report["server_startup_phases"][index] = stats["startup_phase"]
                    report["server_startup_errors"][index] = stats["startup_error"]
                    report["python_socket_guard_active"] = True
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if _port_is_released(port):
                        report["ports_released"] += 1
                        break
                    time.sleep(.05)
                if (report["server_trees_stopped"] < index + 1
                        or report["server_handles_closed"] < index + 1
                        or report["server_readers_stopped"] < index + 1
                        or report["ports_released"] < index + 1):
                    cleanup_failed = True
                if cleanup_failed:
                    _record_cleanup_error(report, "cleanup_unconfirmed", original_failure)
            if report["error_code"] is not None:
                break
        report["two_launches_ready"] = report["server_launches_ready"] == 2
        report["two_browsers_verified"] = (len(report["browser_receipts"]) == 2
            and [value.get("journey_phase") if value else None for value in report["browser_receipts"]]
                == ["live", "cached"]
            and all(_browser_passed(value) for value in report["browser_receipts"]))
        report["registry_calls_verified"] = (report["registry_list_calls"] == [2, 3]
            and report["registry_detail_calls"] == [1, 1]
            and report["registry_history_calls"] == [1, 0]
            and report["registry_outage_refusals"] == [0, 4]
            and report["registry_invalid_calls"] == [0, 0]
            and report["server_network_attempts"] == [0, 0])
        report["two_launch_cleanup_confirmed"] = all(report[key] == 2 for key in (
            "browser_cleanups_confirmed", "server_trees_stopped", "server_handles_closed",
            "server_readers_stopped", "ports_released"))
        report["candidate_ui_entrypoint_verified"] = True
    except _ProbeFailure as error:
        if report["error_code"] is None:
            report["error_code"] = error.code if error.code in _RUNNER_ERRORS else "probe_failed"
    except Exception:
        if report["error_code"] is None: report["error_code"] = "probe_failed"
    finally:
        try:
            _verify_candidate(runtime, candidate, canonical)
            report["candidate_unchanged"] = True
        except Exception:
            if report["error_code"] is None: report["error_code"] = "candidate_changed"
        if report["error_code"] is None and not _complete(report): report["error_code"] = "cleanup_unconfirmed"
    report["passed"] = (_complete(report) and report["registry_client"] == "injected_synthetic"
        and report["network_isolation_proven"] is False
        and report["server_startup_phases"] == ["server_run", "server_run"]
        and report["server_startup_errors"] == [None, None]
        and report["browser_zero_exits"] == 2 and report["browser_stderr_empty_runs"] == 2)
    return report


def main(argv: list[str] | None = None) -> int:
    class Parser(argparse.ArgumentParser):
        def error(self, message): raise ValueError() from None
    parser = Parser(description=__doc__)
    for name in ("runtime", "candidate-manifest", "node", "script", "browser-executable", "artifact-root"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--candidate-manifest-sha256", required=True)
    try:
        args = parser.parse_args(argv)
        report = probe(args.runtime, args.candidate_manifest, args.candidate_manifest_sha256,
                       args.node, args.script, args.browser_executable, args.artifact_root)
    except Exception:
        report = {"contract":"packaged-mcp-store-runner.v2","passed":False,"error_code":"invalid_arguments"}
    print("PACKAGED_MCP_STORE_RUNNER=" + json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if report.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
