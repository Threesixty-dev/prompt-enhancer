"""Reviewed-only packaged dashboard probe with sterile state and owned trees.

Never emits child output, paths, authentication material, screenshots or traces.
The separately reviewed browser script must use a fresh nonpersistent context.
No server or browser is launched by importing this module.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

from packaged_serve_probe import (
    _capture_threads,
    _environment,
    _ephemeral_loopback_port,
    _get,
    _port_is_released,
)
from prompt_enhancer.application.owned_process import (
    process_tree_exited,
    start_owned_process,
    terminate_owned_process,
)


_BROWSER_BOOLEANS = {
    "passed", "browser_started", "agent_page_loaded", "retained_chat_verified",
    "draft_cleared_before_reload", "draft_persistence_claimed", "browser_closed",
}
_BROWSER_COUNTS = {
    "projects_created", "chats_created", "composer_drafts_typed", "draft_send_requests",
    "model_dialog_viewports_verified", "model_start_requests", "reloads",
    "catalog_reopens", "external_requests", "page_errors", "server_failures",
}
_BROWSER_ERRORS = {
    "invalid_environment", "browser_launch_failed", "agent_page_unavailable",
    "project_create_ui_failed", "chat_create_ui_failed", "composer_unavailable",
    "model_dialog_failed", "reload_reopen_failed", "browser_cleanup_unconfirmed",
    "browser_probe_failed",
    "context_create_failed", "page_create_failed",
    "model_selection_failed", "model_start_control_failed", "model_dialog_compact_failed",
}
_COMPACT_CHECKS = {
    "panel_720_bounds", "model_720_bounds", "start_720_bounds", "close_720_bounds",
    "model_720_hit", "close_720_hit", "panel_scrolled_bounds", "close_scrolled_bounds",
    "close_scrolled_hit", "panel_480_bounds", "model_480_bounds", "start_480_bounds",
    "close_480_bounds", "model_480_hit", "close_480_hit",
}
_COMPACT_HIT_CLASSES = {
    "agent", "agent__compose", "agent__compose-footer", "agent__head", "agent__layout",
    "agent__layout--session", "agent__layout--window", "agent__main", "agent__workbench",
    "agent-runtime", "agent-runtime--composer", "agent-runtime__composer-actions",
    "agent-runtime__composer-close", "agent-runtime__composer-disclosure",
    "agent-runtime__composer-panel", "agent-runtime__composer-panel-actions",
    "agent-runtime__composer-panel-head", "agent-runtime__head", "app-shell",
    "app-shell--agent-focus", "brand", "brand__mark", "button", "button--ghost",
    "mobile-runtime-marker", "mobile-runtime-marker__icon", "mobile-shell-header",
    "mobile-shell-header__actions", "mobile-shell-header__identity",
    "mobile-shell-header__menu", "primary-nav", "sidebar", "topbar", "ui-dialog",
    "ui-dialog__panel", "ui-dialog__scrim", "workspace",
}
_COMPACT_HIT_TAGS = {
    "aside", "body", "button", "details", "div", "header", "html", "label", "main",
    "nav", "none", "option", "other", "p", "path", "section", "select", "small",
    "span", "strong", "summary", "svg",
}
_POINTER_EVENTS = {"auto", "none", "other", "unavailable"}
_VISIBILITIES = {"visible", "hidden", "collapse", "other", "unavailable"}
_POSITIONS = {"static", "relative", "absolute", "fixed", "sticky", "other", "unavailable"}


def _browser_receipt(output: bytearray) -> dict[str, object] | None:
    """Accept a closed content-free schema; never forward arbitrary child JSON."""
    prefix = b"PACKAGED_AGENT_BROWSER_PROBE="
    raw = bytes(output).strip()
    if not raw.startswith(prefix) or b"\n" in raw or b"\r" in raw:
        return None
    try:
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate field")
                result[key] = value
            return result

        receipt = json.loads(raw[len(prefix):], object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeError):
        return None
    if not isinstance(receipt, dict) or set(receipt) != (
        _BROWSER_BOOLEANS | _BROWSER_COUNTS | {
            "contract", "error_code", "exception_kind", "compact_dialog_bounds", "compact_check", "compact_occluder",
            "compact_hit_classes", "compact_hit_tag", "compact_hit_state",
        }
    ):
        return None
    if receipt["contract"] != "packaged-agent-browser-probe.v1":
        return None
    if any(type(receipt[key]) is not bool for key in _BROWSER_BOOLEANS):
        return None
    if any(type(receipt[key]) is not int or not 0 <= receipt[key] <= 1000 for key in _BROWSER_COUNTS):
        return None
    error = receipt["error_code"]
    if error is not None and (not isinstance(error, str) or error not in _BROWSER_ERRORS):
        return None
    kind = receipt["exception_kind"]
    if kind is not None and (
        not isinstance(kind, str)
        or kind not in {"target_closed", "timeout", "playwright_error", "unknown"}
    ):
        return None
    check = receipt["compact_check"]
    if check is not None and (
        error != "model_dialog_compact_failed"
        or not isinstance(check, str) or check not in _COMPACT_CHECKS
    ):
        return None
    occluder = receipt["compact_occluder"]
    if occluder is not None and (
        not isinstance(occluder, str) or occluder not in {
            "header", "actions", "panel", "topbar", "sidebar", "agent_header", "body", "other_outside",
        }
        or check is None or not check.endswith("_hit")
    ):
        return None
    bounds = receipt["compact_dialog_bounds"]
    if bounds is not None:
        if (
            error != "model_dialog_compact_failed"
            or check is None or not check.endswith(("_bounds", "_hit"))
            or not isinstance(bounds, dict)
            or set(bounds) != {"x", "y", "width", "height", "viewport_width", "viewport_height"}
            or any(
                type(value) not in {int, float}
                or abs(value) > 100000
                or not math.isfinite(value)
                for value in bounds.values()
            )
        ):
            return None
    hit_classes = receipt["compact_hit_classes"]
    hit_tag = receipt["compact_hit_tag"]
    hit_state = receipt["compact_hit_state"]
    hit_diagnostic_present = any(value is not None for value in (hit_classes, hit_tag, hit_state))
    if hit_diagnostic_present:
        if (
            error != "model_dialog_compact_failed"
            or check is None or not check.endswith("_hit")
            or occluder is None
            or not isinstance(hit_classes, list)
            or len(hit_classes) > 8
            or any(not isinstance(value, str) or value not in _COMPACT_HIT_CLASSES for value in hit_classes)
            or len(hit_classes) != len(set(hit_classes))
            or not isinstance(hit_tag, str) or hit_tag not in _COMPACT_HIT_TAGS
            or not isinstance(hit_state, dict)
            or set(hit_state) != {
                "target_pointer_events", "control_pointer_events", "panel_pointer_events",
                "target_visibility", "control_visibility", "panel_visibility",
                "target_position", "hit_ancestor_z_index", "panel_z_index",
            }
            or any(not isinstance(hit_state[key], str) or hit_state[key] not in _POINTER_EVENTS for key in (
                "target_pointer_events", "control_pointer_events", "panel_pointer_events",
            ))
            or any(not isinstance(hit_state[key], str) or hit_state[key] not in _VISIBILITIES for key in (
                "target_visibility", "control_visibility", "panel_visibility",
            ))
            or not isinstance(hit_state["target_position"], str)
            or hit_state["target_position"] not in _POSITIONS
            or any(
                value is not None and (
                    type(value) not in {int, float}
                    or abs(value) > 10_000
                    or not math.isfinite(value)
                )
                for value in (hit_state["hit_ancestor_z_index"], hit_state["panel_z_index"])
            )
        ):
            return None
    if hit_diagnostic_present != all(value is not None for value in (hit_classes, hit_tag, hit_state)):
        return None
    if occluder is not None and not hit_diagnostic_present:
        return None
    return receipt


def _receipt_passed(receipt: dict[str, object]) -> bool:
    return (
        receipt["error_code"] is None
        and receipt["exception_kind"] is None
        and receipt["compact_dialog_bounds"] is None
        and receipt["compact_check"] is None
        and receipt["compact_occluder"] is None
        and receipt["compact_hit_classes"] is None
        and receipt["compact_hit_tag"] is None
        and receipt["compact_hit_state"] is None
        and all(receipt[key] is True for key in _BROWSER_BOOLEANS - {"draft_persistence_claimed"})
        and receipt["draft_persistence_claimed"] is False
        and all(receipt[key] == 0 for key in (
            "draft_send_requests", "model_start_requests", "external_requests",
            "page_errors", "server_failures",
        ))
        and receipt["projects_created"] == 1
        and receipt["chats_created"] == 1
        and receipt["model_dialog_viewports_verified"] == 3
        and all(receipt[key] >= 1 for key in (
            "composer_drafts_typed", "reloads", "catalog_reopens",
        ))
    )


def probe(runtime: Path, node: Path, script: Path, browser_executable: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "contract": "packaged-browser-runner.v1",
        "health_ok": False,
        "browser_exit_ok": False,
        "browser_receipt_ok": False,
        "server_tree_stopped": False,
        "browser_tree_stopped": False,
        "server_handles_closed": False,
        "browser_handles_closed": False,
        "port_released": False,
        "shutdown_kind": "owned_process_termination",
        "browser_process_limit": 8,
        "browser_peak_observed_processes": None,
        "browser_process_inventory_available": False,
        "error_code": None,
    }
    executable = runtime / "python.exe"
    if sys.platform != "win32" or not all(
        path.is_absolute() and path.is_file()
        for path in (executable, node, script, browser_executable)
    ):
        report["error_code"] = "probe_inputs_unavailable"
        return report
    port = _ephemeral_loopback_port()
    # Never touch the normal personal service, even if allocation behavior changes.
    if port == 8765 or not 1024 <= port <= 65535:
        report["error_code"] = "unsafe_probe_port"
        return report
    results = Path(__file__).resolve().parents[2] / "test-results"
    results.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="packaged-browser-", dir=results))
    server = browser = None
    browser_capture = None
    captures = []
    try:
        for name in ("temp", "empty-profile", "example-workspace"):
            (root / name).mkdir()
        environment = _environment(runtime, root, port)
        server = start_owned_process(
            (os.fspath(executable), "-I", "-B", "-m", "prompt_enhancer", "serve"),
            cwd=root, env=environment, capture_stdout=True, capture_stderr=True,
            maximum_active_processes=4,
        )
        server_capture = _capture_threads(server)
        captures.append(server_capture)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if any(event.is_set() for event in server_capture[2]):
                report["error_code"] = "server_output_limit"
                break
            if process_tree_exited(server):
                report["error_code"] = "server_exited_before_ready"
                break
            try:
                status, _, payload = _get(port, "/health", "application/json")
                if status == 200 and json.loads(payload) == {
                    "status": "ok", "cost_mode": "offline_only", "data_tier": "metadata",
                }:
                    report["health_ok"] = True
                    break
            except (OSError, http.client.HTTPException, ValueError):
                pass
            time.sleep(0.1)
        if not report["health_ok"]:
            report["error_code"] = report["error_code"] or "health_timeout"
        else:
            browser_environment = dict(environment)
            browser_environment.update({
                "PE_PACKAGED_BASE_URL": f"http://127.0.0.1:{port}",
                "PE_PACKAGED_WORKSPACE": os.fspath(root / "example-workspace"),
                "PE_PACKAGED_BROWSER_EXECUTABLE": os.fspath(browser_executable),
            })
            browser = start_owned_process(
                (os.fspath(node), os.fspath(script)),
                cwd=root, env=browser_environment, capture_stdout=True, capture_stderr=True,
                maximum_active_processes=8,
            )
            browser_capture = _capture_threads(browser)
            captures.append(browser_capture)
            deadline = time.monotonic() + 90.0
            while time.monotonic() < deadline:
                # Count only this exact owned Job Object; never enumerate the
                # machine or emit PIDs. Sampling cannot prove limit exhaustion.
                try:
                    count = len(browser.active_process_ids())
                    previous = report["browser_peak_observed_processes"]
                    report["browser_peak_observed_processes"] = max(
                        count, previous if isinstance(previous, int) else 0,
                    )
                    report["browser_process_inventory_available"] = True
                except (AttributeError, OSError):
                    pass
                if any(event.is_set() for capture in captures for event in capture[2]):
                    report["error_code"] = "child_output_limit"
                    break
                if process_tree_exited(server):
                    report["error_code"] = "server_exited_during_browser"
                    break
                if browser.poll() is not None:
                    report["browser_exit_ok"] = browser.returncode == 0
                    if not report["browser_exit_ok"]:
                        report["error_code"] = "browser_probe_failed"
                    break
                time.sleep(0.1)
            else:
                report["error_code"] = "browser_timeout"
    except Exception:
        report["error_code"] = "packaged_browser_probe_failed"
    finally:
        for label, process in (("browser", browser), ("server", server)):
            if process is None:
                continue
            try:
                report[f"{label}_tree_stopped"] = terminate_owned_process(
                    process, graceful_timeout=0.1, forced_timeout=3.0,
                )
            except Exception:
                report[f"{label}_tree_stopped"] = False
            finally:
                try:
                    report[f"{label}_handles_closed"] = bool(process.close(close_streams=True))
                except Exception:
                    report[f"{label}_handles_closed"] = False
        for threads, _, _ in captures:
            for thread in threads:
                thread.join(timeout=1.0)
        if any(event.is_set() for capture in captures for event in capture[2]):
            report["error_code"] = report["error_code"] or "child_output_limit"
        if browser_capture is not None:
            receipt = _browser_receipt(browser_capture[1][0])
            if receipt is not None:
                report["browser_receipt"] = receipt
                report["browser_receipt_ok"] = _receipt_passed(receipt)
            if not report["browser_receipt_ok"]:
                report["error_code"] = report["error_code"] or "browser_receipt_invalid"
        for _, buffers, _ in captures:
            for buffer in buffers:
                buffer.clear()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if _port_is_released(port):
                report["port_released"] = True
                break
            time.sleep(0.05)
        if report["error_code"] is None and not all(
            value is True for key, value in report.items()
            if key not in {
                "contract", "error_code", "shutdown_kind", "browser_receipt",
                "browser_process_limit", "browser_peak_observed_processes",
                "browser_process_inventory_available",
            }
        ):
            report["error_code"] = "probe_completion_unconfirmed"
    return report


def main(argv: list[str] | None = None) -> int:
    class ContentFreeParser(argparse.ArgumentParser):
        def error(self, message: str) -> None:
            raise ValueError("invalid_arguments")

    parser = ContentFreeParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--node", required=True, type=Path)
    parser.add_argument("--script", required=True, type=Path)
    parser.add_argument("--browser-executable", required=True, type=Path)
    try:
        arguments = parser.parse_args(argv)
    except ValueError:
        print('PACKAGED_BROWSER_RUNNER={"error_code":"invalid_arguments"}', flush=True)
        return 2
    report = probe(arguments.runtime, arguments.node, arguments.script, arguments.browser_executable)
    print("PACKAGED_BROWSER_RUNNER=" + json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if report["error_code"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
