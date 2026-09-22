"""Process-free validation for the packaged calibration closed receipt."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def helper(monkeypatch):
    support = Path(__file__).parent / "support"
    monkeypatch.syspath_prepend(str(support))
    spec = importlib.util.spec_from_file_location(
        "synthetic_packaged_calibration_runner", support / "packaged_calibration_runner.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _success():
    return {
        "contract": "packaged-calibration-browser-probe.v1", "passed": True,
        "browser_started": True, "browser_closed": True,
        "calibration_page_loaded": True, "case_reviewed": True,
        "evidence_container_visible": True, "expected_evidence_visible": True,
        "reloaded_evidence_container_visible": True,
        "reloaded_expected_evidence_visible": True,
        "review_acknowledged": True, "ratings_saved": True,
        "reload_verified": True, "rater_persisted": True,
        "review_expiry_claimed": False, "review_requests": 2,
        "initial_review_status": 200, "reload_review_status": 200,
        "rating_mutations": 1, "ratings_verified": 3,
        "cannot_judge_verified": 1, "reloads": 1,
        "model_mutation_requests": 0, "forbidden_mutations": 0, "external_requests": 0,
        "page_errors": 0, "server_failures": 0,
        "error_code": None, "exception_kind": None,
    }


def _encode(value) -> bytearray:
    return bytearray(("PACKAGED_CALIBRATION_BROWSER_PROBE="
        + json.dumps(value, separators=(",", ":")) + "\n").encode())


def test_exact_success_receipt_is_accepted(helper):
    assert helper._browser_receipt(_encode(_success())) == _success()
    assert helper._browser_passed(_success()) is True


@pytest.mark.parametrize(("key", "value"), [
    ("passed", 1), ("review_expiry_claimed", True), ("review_requests", True),
    ("initial_review_status", True), ("initial_review_status", 99),
    ("reload_review_status", 600),
    ("review_requests", 1), ("ratings_verified", 4),
    ("cannot_judge_verified", 0), ("model_mutation_requests", 1),
    ("forbidden_mutations", 1),
    ("error_code", "synthetic_private_error"), ("exception_kind", "private_kind"),
    ("contract", "other.v1"),
])
def test_wrong_types_counts_claims_and_enums_do_not_pass(helper, key, value):
    candidate = {**_success(), key: value}
    parsed = helper._browser_receipt(_encode(candidate))
    assert parsed is None or helper._browser_passed(parsed) is False


def test_unknown_duplicate_and_multiline_output_is_rejected(helper):
    assert helper._browser_receipt(_encode({**_success(), "extra": 1})) is None
    raw = bytes(_encode(_success()))
    duplicate = raw.replace(b'"passed":true', b'"passed":true,"passed":true', 1)
    assert helper._browser_receipt(bytearray(duplicate)) is None
    assert helper._browser_receipt(bytearray(b"noise\n" + raw)) is None
    assert helper._browser_receipt(bytearray(raw + raw)) is None


def test_failure_keeps_only_closed_diagnostics(helper):
    failure = {**_success(), "passed": False, "ratings_saved": False,
               "error_code": "rating_save_failed", "exception_kind": None}
    assert helper._browser_receipt(_encode(failure)) == failure
    assert helper._browser_passed(failure) is False


def test_review_status_and_render_phase_are_preserved_without_content(helper):
    refused = {
        **_success(), "passed": False, "case_reviewed": False,
        "evidence_container_visible": False, "expected_evidence_visible": False,
        "reloaded_evidence_container_visible": False,
        "reloaded_expected_evidence_visible": False,
        "ratings_saved": False, "reload_verified": False, "rater_persisted": False,
        "review_requests": 1, "initial_review_status": 409,
        "reload_review_status": None, "rating_mutations": 0,
        "ratings_verified": 0, "cannot_judge_verified": 0, "reloads": 0,
        "error_code": "initial_review_response_failed",
    }
    assert helper._browser_receipt(_encode(refused)) == refused


def test_runner_success_requires_all_cleanup_and_exact_aggregates(helper):
    report = {
        "error_code": None,
        **dict.fromkeys(helper._RUNNER_FLAGS, True),
        "sessions_indexed": 1, "ratings_exported": 3,
        "cannot_judge_exported": 1, "model_mutations": 0,
        "review_expiry_claimed": False,
    }
    assert helper._complete(report) is True
    for key in helper._RUNNER_FLAGS:
        assert helper._complete({**report, key: False}) is False


def test_export_requires_exact_mapping_and_bound_provenance(helper, monkeypatch):
    fingerprint = "a" * 64
    rows = [{
        "rater_id": "b" * 64, "session_id": "c" * 64,
        "provider": "claude_code", "metric_key": metric, "label": label,
        "revision": 1, "rating_version": "calibration-rating-v2-reviewed-case",
        "case_fingerprint": fingerprint, "case_version": "calibration-case.v1",
        "window_fingerprint": "d" * 64,
    } for metric, label in helper._EXPECTED_RATINGS.items()]
    body = {"contract_version": "calibration-ratings.v1", "rows": rows}
    monkeypatch.setattr(helper, "_fresh_browser_auth", lambda _port: object())
    monkeypatch.setattr(helper, "_json_request", lambda *_args, **_kwargs: (200, body, None))
    helper._verify_export(1234)
    for changed in (
        [{**rows[0], "label": "low"}, *rows[1:]],
        [{**rows[0], "rater_id": "e" * 64}, *rows[1:]],
        [{**rows[0], "case_fingerprint": None}, *rows[1:]],
        [{**rows[0], "window_fingerprint": "e" * 64}, *rows[1:]],
        [{**rows[0], "rating_version": "calibration-rating-v1"}, *rows[1:]],
    ):
        monkeypatch.setattr(helper, "_json_request", lambda *_args, _rows=changed, **_kwargs:
                            (200, {"contract_version": "calibration-ratings.v1", "rows": _rows}, None))
        with pytest.raises(Exception, match="export_failed"):
            helper._verify_export(1234)


def test_fixture_verification_is_identity_tree_and_content_bound(helper, tmp_path):
    transcript = helper._write_fixture(tmp_path)
    identity = helper._fixture_identity(transcript)
    assert helper._fixture_matches(tmp_path, transcript, identity) is True
    transcript.write_bytes(helper._TRANSCRIPT + b"extra")
    assert helper._fixture_matches(tmp_path, transcript, identity) is False

    fresh_root = tmp_path / "second"
    fresh_root.mkdir()
    fresh = helper._write_fixture(fresh_root)
    fresh_identity = helper._fixture_identity(fresh)
    (fresh.parent / "unexpected.txt").write_text("synthetic", encoding="utf-8")
    assert helper._fixture_matches(fresh_root, fresh, fresh_identity) is False


def test_nonzero_browser_preserves_closed_receipt_and_cleanup(helper, monkeypatch, tmp_path):
    from types import SimpleNamespace
    failed = {**_success(), "passed": False, "ratings_saved": False,
              "error_code": "rating_save_failed"}
    monkeypatch.setattr(helper, "run_owned_process", lambda *_args, **_kwargs:
                        SimpleNamespace(returncode=1, stdout=bytes(_encode(failed)), stderr=b""))
    report = {"browser_receipt": None, "browser_cleanup_confirmed": False,
              "browser_process_exit_zero": False, "browser_stderr_empty": False,
              "browser_owned_failure_code": None}
    with pytest.raises(Exception, match="browser_failed"):
        helper._run_browser(tmp_path / "node", tmp_path / "script", tmp_path / "browser", {}, tmp_path, 1234, report)
    assert report["browser_receipt"] == failed
    assert report["browser_cleanup_confirmed"] is True
    assert report["browser_process_exit_zero"] is False
    assert report["browser_stderr_empty"] is True


def test_browser_source_has_exact_mutation_allowlist_and_no_expiry_override():
    source = (Path(__file__).parents[1] / "frontend" / "e2e" /
              "packaged-calibration-probe.mjs").read_text(encoding="utf-8")
    assert 'method === "POST" && path === "/v1/calibration/review"' in source
    assert 'method === "PUT" && path === "/v1/calibration/ratings"' in source
    assert "forbidden_mutations" in source
    assert "REVIEW_LIFETIME" not in source
