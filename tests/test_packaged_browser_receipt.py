"""Pure synthetic checks for the packaged browser's closed receipt boundary."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re

import pytest

from prompt_enhancer.application import owned_process


@pytest.fixture
def runner(monkeypatch):
    def forbidden_launch(*_args, **_kwargs):
        pytest.fail("receipt parsing must not launch a process")

    monkeypatch.setattr(owned_process, "start_owned_process", forbidden_launch)
    support = Path(__file__).parent / "support"
    monkeypatch.syspath_prepend(str(support))
    spec = importlib.util.spec_from_file_location(
        "synthetic_packaged_browser_receipt_runner",
        support / "packaged_browser_runner.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _success():
    return {
        "contract": "packaged-agent-browser-probe.v1",
        "passed": True,
        "browser_started": True,
        "agent_page_loaded": True,
        "projects_created": 1,
        "chats_created": 1,
        "retained_chat_verified": True,
        "composer_drafts_typed": 1,
        "draft_send_requests": 0,
        "draft_cleared_before_reload": True,
        "draft_persistence_claimed": False,
        "model_dialog_viewports_verified": 3,
        "model_start_requests": 0,
        "reloads": 1,
        "catalog_reopens": 1,
        "external_requests": 0,
        "page_errors": 0,
        "server_failures": 0,
        "browser_closed": True,
        "error_code": None,
        "exception_kind": None,
        "compact_dialog_bounds": None,
        "compact_check": None,
        "compact_occluder": None,
        "compact_hit_classes": None,
        "compact_hit_tag": None,
        "compact_hit_state": None,
    }


def _compact_failure():
    return {
        **_success(),
        "passed": False,
        "error_code": "model_dialog_compact_failed",
        "exception_kind": "unknown",
        "model_dialog_viewports_verified": 1,
        "compact_check": "panel_720_bounds",
        "compact_dialog_bounds": {
            "x": 12, "y": 412.25, "width": 696, "height": 468,
            "viewport_width": 720, "viewport_height": 720,
        },
    }


def _encode(receipt):
    return bytearray(
        ("PACKAGED_AGENT_BROWSER_PROBE=" + json.dumps(receipt, separators=(",", ":")) + "\n").encode()
    )


def _javascript_string_set(source: str, declaration: str) -> set[str]:
    start = source.index(declaration) + len(declaration)
    end = source.index(");", start)
    values = re.findall(r'"([a-zA-Z0-9_-]+)"', source[start:end])
    assert len(values) == len(set(values))
    return set(values)


def _compact_hit_failure():
    return {
        **_compact_failure(),
        "compact_check": "close_720_hit",
        "compact_occluder": "other_outside",
        "compact_hit_classes": ["mobile-shell-header", "app-shell", "app-shell--agent-focus"],
        "compact_hit_tag": "header",
        "compact_hit_state": {
            "target_pointer_events": "auto",
            "control_pointer_events": "auto",
            "panel_pointer_events": "auto",
            "target_visibility": "visible",
            "control_visibility": "visible",
            "panel_visibility": "visible",
            "target_position": "sticky",
            "hit_ancestor_z_index": 40,
            "panel_z_index": 30,
        },
    }


def test_compact_diagnostic_allowlists_match_browser_probe(runner):
    probe = (Path(__file__).parents[1] / "frontend" / "e2e" / "packaged-agent-probe.mjs").read_text(
        encoding="utf-8"
    )
    assert _javascript_string_set(probe, "const allowedClasses = new Set(") == runner._COMPACT_HIT_CLASSES
    assert _javascript_string_set(probe, "const allowedTags = new Set(") | {"none", "other"} == runner._COMPACT_HIT_TAGS


def test_success_receipt_import_and_parse_are_process_free(runner):
    receipt = runner._browser_receipt(_encode(_success()))
    assert receipt == _success()
    assert runner._receipt_passed(receipt) is True


def test_compact_failure_keeps_only_numeric_geometry(runner):
    receipt = runner._browser_receipt(_encode(_compact_failure()))
    assert receipt == _compact_failure()
    assert runner._receipt_passed(receipt) is False


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, 100001, -100001, 10**400, "12"])
def test_geometry_rejects_nonfinite_bool_oversize_and_text(runner, value):
    receipt = _compact_failure()
    receipt["compact_dialog_bounds"]["x"] = value
    assert runner._browser_receipt(_encode(receipt)) is None


@pytest.mark.parametrize("nested", [False, True])
def test_unknown_keys_are_rejected_at_both_levels(runner, nested):
    receipt = _compact_failure()
    target = receipt["compact_dialog_bounds"] if nested else receipt
    target["synthetic_extra"] = 1
    assert runner._browser_receipt(_encode(receipt)) is None


@pytest.mark.parametrize("nested", [False, True])
def test_duplicate_keys_are_rejected_at_both_levels(runner, nested):
    raw = _encode(_compact_failure())
    needle = b'"x":12' if nested else b'"passed":false'
    replacement = b'"x":12,"x":12' if nested else b'"passed":false,"passed":false'
    assert needle in raw
    assert runner._browser_receipt(raw.replace(needle, replacement, 1)) is None


@pytest.mark.parametrize("transform", [
    lambda raw: b"synthetic output\n" + raw,
    lambda raw: raw + b"synthetic output\n",
    lambda raw: raw.replace(b',"passed"', b',\n"passed"', 1),
    lambda raw: raw + raw,
    lambda raw: raw.replace(b"PACKAGED_AGENT_BROWSER_PROBE=", b"OTHER=", 1),
])
def test_raw_multiline_or_nonreceipt_output_is_rejected(runner, transform):
    assert runner._browser_receipt(bytearray(transform(_encode(_success())))) is None


@pytest.mark.parametrize(("key", "value"), [
    ("projects_created", True), ("chats_created", 1.5),
    ("page_errors", -1), ("page_errors", 1001),
    ("passed", 1), ("contract", "synthetic-unknown.v1"),
    ("error_code", "unreviewed_error"), ("exception_kind", "unreviewed_exception"),
])
def test_closed_types_ranges_and_enums(runner, key, value):
    receipt = {**_success(), key: value}
    assert runner._browser_receipt(_encode(receipt)) is None


@pytest.mark.parametrize(("key", "value"), [
    ("passed", False), ("browser_started", False), ("browser_closed", False),
    ("retained_chat_verified", False), ("draft_cleared_before_reload", False),
    ("draft_persistence_claimed", True), ("draft_send_requests", 1),
    ("model_start_requests", 1), ("external_requests", 1),
    ("page_errors", 1), ("server_failures", 1),
    ("projects_created", 2), ("chats_created", 2),
    ("model_dialog_viewports_verified", 2), ("model_dialog_viewports_verified", 4),
    ("composer_drafts_typed", 0), ("reloads", 0), ("catalog_reopens", 0),
    ("error_code", "browser_probe_failed"), ("exception_kind", "unknown"),
])
def test_inconsistent_success_never_passes(runner, key, value):
    receipt = runner._browser_receipt(_encode({**_success(), key: value}))
    assert receipt is not None
    assert runner._receipt_passed(receipt) is False


def test_geometry_cannot_be_attached_to_success(runner):
    receipt = _success()
    receipt["compact_dialog_bounds"] = _compact_failure()["compact_dialog_bounds"]
    assert runner._browser_receipt(_encode(receipt)) is None


@pytest.mark.parametrize("check", [
    "panel_720_bounds", "model_720_bounds", "start_720_bounds", "close_720_bounds",
    "model_720_hit", "close_720_hit", "panel_scrolled_bounds", "close_scrolled_bounds",
    "close_scrolled_hit", "panel_480_bounds", "model_480_bounds", "start_480_bounds",
    "close_480_bounds", "model_480_hit", "close_480_hit",
])
def test_compact_substep_is_closed_and_content_free(runner, check):
    receipt = {**_compact_failure(), "compact_check": check, "compact_dialog_bounds": None}
    parsed = runner._browser_receipt(_encode(receipt))
    assert parsed == receipt and runner._receipt_passed(parsed) is False


@pytest.mark.parametrize("check", ["unreviewed_check", 1, True, {}])
def test_unknown_compact_substeps_rejected(runner, check):
    assert runner._browser_receipt(_encode({**_compact_failure(), "compact_check": check})) is None


def test_compact_substep_requires_matching_failure_and_geometry_substep(runner):
    assert runner._browser_receipt(_encode({**_success(), "compact_check": "model_720_hit"})) is None
    hit_receipt = {**_compact_failure(), "compact_check": "model_720_hit"}
    assert runner._browser_receipt(_encode(hit_receipt)) == hit_receipt


@pytest.mark.parametrize("occluder", ["header", "actions", "panel", "topbar", "sidebar", "agent_header", "body", "other_outside"])
def test_compact_occluder_requires_hit_failure(runner, occluder):
    receipt = {**_compact_hit_failure(), "compact_dialog_bounds": None, "compact_check": "model_720_hit", "compact_occluder": occluder}
    assert runner._browser_receipt(_encode(receipt)) == receipt
    assert runner._browser_receipt(_encode({**receipt, "compact_check": "model_720_bounds"})) is None


@pytest.mark.parametrize("occluder", ["unreviewed", "outside", 1, True, {}])
def test_compact_occluder_rejects_unknown_values(runner, occluder):
    receipt = {**_compact_hit_failure(), "compact_dialog_bounds": None, "compact_check": "model_720_hit", "compact_occluder": occluder}
    assert runner._browser_receipt(_encode(receipt)) is None


def test_failed_control_bounds_are_accepted(runner):
    receipt = {**_compact_failure(), "compact_check": "start_720_bounds"}
    assert runner._browser_receipt(_encode(receipt)) == receipt


def test_compact_hit_diagnostic_accepts_only_closed_content_free_schema(runner):
    receipt = _compact_hit_failure()
    assert runner._browser_receipt(_encode(receipt)) == receipt
    assert runner._receipt_passed(receipt) is False


@pytest.mark.parametrize("classes", [
    ["synthetic-forged-class"],
    ["mobile-shell-header", "mobile-shell-header"],
    ["mobile-shell-header"] * 9,
    [1],
    [{}],
    "mobile-shell-header",
])
def test_compact_hit_classes_reject_forged_duplicate_oversize_and_wrong_types(runner, classes):
    receipt = {**_compact_hit_failure(), "compact_hit_classes": classes}
    assert runner._browser_receipt(_encode(receipt)) is None


@pytest.mark.parametrize(("key", "value"), [
    ("compact_hit_tag", "script"),
    ("compact_hit_tag", 1),
    ("compact_hit_state", []),
])
def test_compact_hit_diagnostic_rejects_unknown_tags_and_wrong_container_types(runner, key, value):
    receipt = {**_compact_hit_failure(), key: value}
    assert runner._browser_receipt(_encode(receipt)) is None


@pytest.mark.parametrize(("key", "value"), [
    ("target_pointer_events", "inherit"),
    ("target_visibility", "opaque"),
    ("target_position", "anchor"),
    ("hit_ancestor_z_index", float("nan")),
    ("hit_ancestor_z_index", float("inf")),
    ("hit_ancestor_z_index", 10**400),
    ("panel_z_index", True),
    ("panel_z_index", 10001),
    ("panel_z_index", 10**400),
])
def test_compact_hit_state_rejects_unknown_enums_and_unsafe_numbers(runner, key, value):
    receipt = _compact_hit_failure()
    receipt["compact_hit_state"] = {**receipt["compact_hit_state"], key: value}
    assert runner._browser_receipt(_encode(receipt)) is None


def test_compact_hit_state_rejects_unknown_nested_field(runner):
    receipt = _compact_hit_failure()
    receipt["compact_hit_state"] = {**receipt["compact_hit_state"], "synthetic_extra": False}
    assert runner._browser_receipt(_encode(receipt)) is None


@pytest.mark.parametrize("field", ["compact_hit_classes", "compact_hit_tag", "compact_hit_state"])
def test_compact_hit_diagnostic_fields_are_bound_together_and_to_hit_failures(runner, field):
    hit_receipt = _compact_hit_failure()
    assert runner._browser_receipt(_encode({**hit_receipt, field: None})) is None
    assert runner._browser_receipt(_encode({**hit_receipt, "compact_check": "close_720_bounds"})) is None
    assert runner._browser_receipt(_encode({**_success(), field: hit_receipt[field]})) is None
