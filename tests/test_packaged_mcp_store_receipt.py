from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "tests" / "support"
sys.path.insert(0, str(SUPPORT))
SPEC = importlib.util.spec_from_file_location("packaged_mcp_store_runner", SUPPORT / "packaged_mcp_store_runner.py")
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def browser_value(phase: str = "live") -> dict[str, object]:
    value = {
        "contract":"packaged-mcp-store-browser-probe.v2", **dict.fromkeys(runner._FLAGS, True),
        "initial_tiles":2,"searched_tiles":1,"catalog_response_events":2,"review_response_events":1,
        "forbidden_mutations":0,"external_requests":0,"page_errors":0,"server_failures":0,
        "managed_lifecycle_mutations":0,"model_mutations":0,"native_confirmation_mutations":0,
        "settings_locator_count":1,"agent_navigation_status":200,
        "initial_catalog_status":200,"search_catalog_status":200,
        "review_status":200,"uncached_catalog_status":None,
        "expected_outage_responses":0,"journey_phase":phase,
        "error_code":None,"exception_kind":None,
    }
    if phase == "live":
        for key in ("cached_delivery_verified", "cached_age_visible",
                    "exact_review_unavailable", "uncached_query_refused"):
            value[key] = False
    else:
        for key in ("live_review_rendered", "provenance_visible", "review_boundary_visible"):
            value[key] = False
        value.update(review_status=503, uncached_catalog_status=503,
                     expected_outage_responses=2)
    return value


def encoded(value: dict[str, object]) -> bytes:
    return runner._PREFIX + json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def test_browser_receipt_accepts_exact_read_only_success() -> None:
    value = browser_value()
    assert runner._browser_receipt(encoded(value)) == value
    assert runner._browser_passed(value)
    cached = browser_value("cached")
    assert runner._browser_receipt(encoded(cached)) == cached
    assert runner._browser_passed(cached)


@pytest.mark.parametrize(("key", "replacement"), [
    ("setup_plan_disabled", False), ("initial_tiles", 1), ("searched_tiles", 2),
    ("settings_locator_count", 0), ("agent_navigation_status", 404),
    ("catalog_response_events", 1), ("review_response_events", 0),
    ("forbidden_mutations", 1), ("external_requests", 1),
    ("managed_lifecycle_mutations", 1), ("model_mutations", 1),
    ("native_confirmation_mutations", 1), ("review_status", 503),
])
def test_browser_receipt_rejects_false_success(key: str, replacement: object) -> None:
    value = browser_value(); value[key] = replacement
    assert runner._browser_receipt(encoded(value)) is None


def test_browser_receipt_rejects_unknown_duplicate_raw_and_unbounded() -> None:
    value = browser_value(); value["raw_registry_body"] = "fictional"
    assert runner._browser_receipt(encoded(value)) is None


@pytest.mark.parametrize(("key", "replacement"), [
    ("cached_delivery_verified", False), ("cached_age_visible", False),
    ("exact_review_unavailable", False), ("uncached_query_refused", False),
    ("expected_outage_responses", 1), ("review_status", 200),
    ("uncached_catalog_status", 200), ("journey_phase", "live"),
])
def test_cached_browser_receipt_rejects_cross_phase_or_incomplete_evidence(
    key: str, replacement: object,
) -> None:
    value = browser_value("cached"); value[key] = replacement
    assert runner._browser_receipt(encoded(value)) is None
    duplicate = encoded(browser_value()).replace(b'"contract":"packaged-mcp-store-browser-probe.v2"',
        b'"contract":"packaged-mcp-store-browser-probe.v2","contract":"forged"')
    assert runner._browser_receipt(duplicate) is None
    value = browser_value(); value["initial_tiles"] = True
    assert runner._browser_receipt(encoded(value)) is None
    value["initial_tiles"] = 101
    assert runner._browser_receipt(encoded(value)) is None


def test_closed_registry_receipt_rejects_extra_duplicate_and_invalid_counts(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    valid = {"contract":"synthetic-mcp-registry-client.v1","list_calls":2,"detail_calls":1,
             "history_calls":1,"invalid_calls":0,"network_attempts":0,
             "outage_refusals":0,"client_mode":"live",
             "startup_phase":"server_run","startup_error":None}
    path.write_text(json.dumps(valid), encoding="utf-8")
    assert runner._read_closed_json(path, "synthetic-mcp-registry-client.v1") == valid
    path.write_text('{"contract":"synthetic-mcp-registry-client.v1","contract":"forged","list_calls":2,"detail_calls":1,"history_calls":1,"invalid_calls":0,"network_attempts":0}', encoding="utf-8")
    assert runner._read_closed_json(path, "synthetic-mcp-registry-client.v1") is None
    valid["path"] = "C:/private"
    path.write_text(json.dumps(valid), encoding="utf-8")
    assert runner._read_closed_json(path, "synthetic-mcp-registry-client.v1") is None


def test_closed_receipt_rejects_reparse_and_post_open_identity_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps({"contract":"synthetic-mcp-registry-client.v1","list_calls":2,
        "detail_calls":1,"history_calls":1,"invalid_calls":0,"network_attempts":0,
        "outage_refusals":0,"client_mode":"live",
        "startup_phase":"server_run","startup_error":None}), encoding="utf-8")
    real_lstat = Path.lstat
    metadata = real_lstat(path)
    reparse = SimpleNamespace(**{name: getattr(metadata, name) for name in (
        "st_mode", "st_nlink", "st_size", "st_dev", "st_ino")}, st_file_attributes=0x400)
    monkeypatch.setattr(Path, "lstat", lambda self: reparse if self == path else real_lstat(self))
    assert runner._read_closed_json(path, "synthetic-mcp-registry-client.v1") is None
    monkeypatch.undo()

    real_fstat = runner.os.fstat
    calls = 0
    def changed(descriptor: int):
        nonlocal calls
        calls += 1
        value = real_fstat(descriptor)
        if calls == 2:
            return SimpleNamespace(st_dev=value.st_dev, st_ino=value.st_ino,
                st_size=value.st_size + 1, st_mode=value.st_mode)
        return value
    monkeypatch.setattr(runner.os, "fstat", changed)
    assert runner._read_closed_json(path, "synthetic-mcp-registry-client.v1") is None


def test_cache_validation_is_bounded_and_requires_two_queries(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    def key(search: str) -> str:
        import hashlib
        return hashlib.sha256(f"v1\x00{search}\x00\x0024".encode()).hexdigest()
    from datetime import UTC, datetime
    from prompt_enhancer.application.mcp_registry_catalog import (
        McpRegistryCacheRecord, McpRegistryServer, _catalog_id, _presentation_revision,
    )
    def record(search: str, servers: tuple[McpRegistryServer, ...]) -> dict[str, object]:
        return McpRegistryCacheRecord(fetched_at=datetime(2040, 1, 2, tzinfo=UTC), search=search,
            cursor=None, limit=24, servers=servers, next_cursor=None, partial=False,
            icon_sources={}).model_dump(mode="json")
    def server(name: str, title: str) -> McpRegistryServer:
        updated = datetime(2040, 1, 2, tzinfo=UTC)
        revision = _presentation_revision(name=name, version="1.2.3", title=title,
            description="Fictional public metadata.", status="active", updated_at=updated,
            repository_url=None, website_url=None, icon=None)
        return McpRegistryServer(catalog_id=_catalog_id(name, "1.2.3"), name=name, title=title,
            description="Fictional public metadata.", version="1.2.3", publisher="com.example",
            status="active", updated_at=updated, website_url=None, repository_url=None,
            presentation_revision=revision, packages=(), remotes=(), supports_local=False,
            supports_remote=False, icon=None)
    files = server("com.example/synthetic-files", "Synthetic Files")
    browser = server("com.example/synthetic-browser", "Synthetic Browser")
    entries = {key(""): record("", (files, browser)),
               key("fictional files"): record("fictional files", (files,))}
    path.write_text(json.dumps({"format_version":2,"entries":entries}), encoding="utf-8")
    assert runner._cache_valid(path)

    duplicate_record = json.loads(json.dumps(entries[key("")]))
    duplicate_record["servers"].append(duplicate_record["servers"][0])
    entries[key("")] = duplicate_record
    path.write_text(json.dumps({"format_version":2,"entries":entries}), encoding="utf-8")
    assert not runner._cache_valid(path)

    entries[key("")] = record("", (files, browser))
    entries[key("fictional files")] = record("fictional files", (browser,))
    path.write_text(json.dumps({"format_version":2,"entries":entries}), encoding="utf-8")
    assert not runner._cache_valid(path)

    entries[key("fictional files")] = record("fictional files", (files,))
    entries.pop(key("fictional files"))
    path.write_text(json.dumps({"format_version":2,"entries":entries}), encoding="utf-8")
    assert not runner._cache_valid(path)


def test_cache_validation_rejects_malformed_or_wrong_identity(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({"format_version":2,"entries":{}}), encoding="utf-8")
    assert not runner._cache_valid(path)
    path.write_text(json.dumps({"format_version":2,"entries":{"a" * 64:{"servers":[{}]}}}), encoding="utf-8")
    assert not runner._cache_valid(path)


def test_cache_snapshot_rejects_reparse_and_post_read_identity_or_mtime_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "cache.json"
    path.write_text('{"fixture":true}', encoding="utf-8")
    original = runner._cache_snapshot(path)
    assert original is not None

    real_lstat = Path.lstat
    metadata = real_lstat(path)
    fields = {name: getattr(metadata, name) for name in (
        "st_mode", "st_nlink", "st_size", "st_dev", "st_ino", "st_mtime_ns")}
    reparse = SimpleNamespace(**fields, st_file_attributes=0x400)
    monkeypatch.setattr(Path, "lstat", lambda self: reparse if self == path else real_lstat(self))
    assert runner._cache_snapshot(path) is None
    monkeypatch.undo()

    calls = 0
    changed_path = SimpleNamespace(**{**fields, "st_ino": metadata.st_ino + 1}, st_file_attributes=0)
    def changed_lstat(self: Path):
        nonlocal calls
        if self != path:
            return real_lstat(self)
        calls += 1
        return metadata if calls == 1 else changed_path
    monkeypatch.setattr(Path, "lstat", changed_lstat)
    assert runner._cache_snapshot(path) is None
    monkeypatch.undo()

    real_fstat = runner.os.fstat
    calls = 0
    def changed_fstat(descriptor: int):
        nonlocal calls
        calls += 1
        value = real_fstat(descriptor)
        if calls == 2:
            return SimpleNamespace(st_dev=value.st_dev, st_ino=value.st_ino,
                st_size=value.st_size, st_mtime_ns=value.st_mtime_ns + 1,
                st_nlink=value.st_nlink, st_mode=value.st_mode)
        return value
    monkeypatch.setattr(runner.os, "fstat", changed_fstat)
    assert runner._cache_snapshot(path) is None


def test_primary_failure_is_not_masked_by_cleanup_failure() -> None:
    report: dict[str, object] = {"error_code": None}
    runner._record_cleanup_error(report, "cleanup_unconfirmed", True)
    assert report["error_code"] is None
    report["error_code"] = "browser_failed"
    runner._record_cleanup_error(report, "cleanup_unconfirmed", True)
    assert report["error_code"] == "browser_failed"
    report["error_code"] = None
    runner._record_cleanup_error(report, "cleanup_unconfirmed", False)
    assert report["error_code"] == "cleanup_unconfirmed"


def test_server_audit_hook_allows_synthetic_loopback_and_refuses_external(tmp_path: Path) -> None:
    assert runner._audit_selftest(tmp_path)


@pytest.mark.parametrize(("field", "value"), [
    ("startup_phase", "private-module-name"),
    ("startup_error", "arbitrary-lowercase-error"),
])
def test_startup_diagnostic_rejects_unclosed_values(tmp_path: Path, field: str, value: str) -> None:
    receipt = {"contract":"synthetic-mcp-registry-client.v1","list_calls":0,"detail_calls":0,
        "history_calls":0,"invalid_calls":0,"network_attempts":0,
        "outage_refusals":0,"client_mode":"live",
        "startup_phase":"application_import","startup_error":None}
    receipt[field] = value
    path = tmp_path / "startup.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    assert runner._read_closed_json(path, "synthetic-mcp-registry-client.v1") is None


def test_candidate_requires_canonical_packaged_dashboard() -> None:
    valid = SimpleNamespace(files=(SimpleNamespace(relative_path="prompt_enhancer/_resources/dashboard/index.html"), SimpleNamespace(relative_path="prompt_enhancer/_resources/dashboard/assets/app.js")))
    root_only = SimpleNamespace(files=(SimpleNamespace(relative_path="index.html"), SimpleNamespace(relative_path="assets/app.js")))
    assert runner._candidate_ui_bound(valid)
    assert not runner._candidate_ui_bound(root_only)


def test_browser_source_uses_real_read_only_routes_and_no_install() -> None:
    source = (ROOT / "frontend" / "e2e" / "packaged-mcp-store-probe.mjs").read_text(encoding="utf-8")
    assert '![' + '"GET", "HEAD", "OPTIONS"' + '].includes(request.method())' in source
    assert 'page.goto(`${origin}/agent`' in source
    assert 'name: /^Agent settings(?:\\s|$)/u' in source and 'name: "MCP Store"' in source
    assert 'getAttribute("aria-controls") === "agent-settings-drawer"' in source
    assert 'name: "Close new chat setup"' in source
    assert "/v1/integrations/mcp-store/catalog" in source
    assert "Review Synthetic Files" in source
    assert "Save setup plan" in source and "isDisabled" in source
    assert "page.screenshot" not in source and "response.json()" not in source


def test_runner_injects_fixed_client_and_denies_server_network() -> None:
    source = (SUPPORT / "packaged_mcp_store_runner.py").read_text(encoding="utf-8")
    assert "class FixedClient" in source and "class InjectedApplication" in source
    assert "bootstrap_current_embedded_windows_runtime()" in source
    bootstrap_call = runner._SERVER_CODE.index("runtime_bootstrap = bootstrap_current_embedded_windows_runtime()")
    assert bootstrap_call < runner._SERVER_CODE.index("from prompt_enhancer.config import AppSettings")
    assert bootstrap_call < runner._SERVER_CODE.index("from prompt_enhancer.application.mcp_registry_catalog import McpRegistryCatalogService")
    assert 'startup_phase("mcp_import")' in runner._SERVER_CODE
    assert 'McpRegistryClientError("registry_unavailable")' in runner._SERVER_CODE
    assert "sys.addaudithook(audit)" in source
    assert '"socket.connect", "socket.bind", "socket.getaddrinfo"' in source
    assert "OfficialMcpRegistryHttpClient" not in source
    assert '"network_isolation_proven": False' in source
    assert "maximum_active_processes=4" in source and "maximum_active_processes=8" in source
    assert "timeout=90" in source and "8765, 8766" in source
    assert source.count("_verify_candidate(runtime, candidate, canonical)") == 2
    compile(runner._SERVER_CODE, "<synthetic-mcp-store-server>", "exec")


def test_restart_wiring_binds_ordered_phases_and_exact_outage_requests() -> None:
    runner_source = (SUPPORT / "packaged_mcp_store_runner.py").read_text(encoding="utf-8")
    browser_source = (ROOT / "frontend" / "e2e" / "packaged-mcp-store-probe.mjs").read_text(encoding="utf-8")
    assert 'for index, phase in enumerate(("live", "outage"))' in runner_source
    assert '== ["live", "cached"]' in runner_source
    assert 'receipt.get("journey_phase") != phase' in runner_source
    assert 'set(entries) != {key(""), key("fictional files")}' in runner_source
    assert 'selectedPresentationRevision' in browser_source and 'selectedCatalogId' in browser_source
    assert '=== "name,presentation_revision,version"' in browser_source
    assert '=== "limit,search"' in browser_source
    assert 'Offline fallback · ${searchPayload.source.cache_age_seconds}s old' in browser_source


def test_main_has_closed_invalid_argument_receipt(capsys: pytest.CaptureFixture[str]) -> None:
    assert runner.main(["--unknown", "private-canary"]) == 1
    output = capsys.readouterr()
    assert output.err == "" and "private-canary" not in output.out
    assert json.loads(output.out.removeprefix("PACKAGED_MCP_STORE_RUNNER=")) == {
        "contract":"packaged-mcp-store-runner.v2","passed":False,"error_code":"invalid_arguments"}
