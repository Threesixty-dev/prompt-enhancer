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
SPEC = importlib.util.spec_from_file_location(
    "packaged_analytics_runner", SUPPORT / "packaged_analytics_runner.py"
)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def _browser_value() -> dict[str, object]:
    value = {
        "contract": "packaged-analytics-browser-probe.v1",
        **dict.fromkeys(runner._BROWSER_FLAGS, True),
        "session_rows": 1,
        "metric_response_events": 2,
        "verified_category_responses": 2,
        "forbidden_mutations": 0,
        "external_requests": 0,
        "page_errors": 0,
        "server_failures": 0,
        "model_mutation_requests": 0,
        "model_usage_status": 200,
        "outcome_status": 200,
        "error_code": None,
        "exception_kind": None,
    }
    return value


def _encoded(value: dict[str, object]) -> bytes:
    return runner._BROWSER_PREFIX + json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode() + b"\n"


def test_browser_receipt_accepts_exact_read_only_success() -> None:
    value = _browser_value()
    assert runner._browser_receipt(_encoded(value)) == value
    assert runner._browser_passed(value)


@pytest.mark.parametrize(
    ("key", "replacement"),
    [
        ("unknown_token_displayed", False),
        ("assistant_claim_not_verified", False),
        ("session_rows", 0),
        ("verified_category_responses", 1),
        ("forbidden_mutations", 1),
        ("model_usage_status", 204),
        ("outcome_status", None),
    ],
)
def test_browser_receipt_rejects_false_success_claims(key: str, replacement: object) -> None:
    value = _browser_value()
    value[key] = replacement
    assert runner._browser_receipt(_encoded(value)) is None


def test_browser_receipt_rejects_unknown_field_duplicate_and_raw_text() -> None:
    value = _browser_value()
    value["raw_body"] = "fictional transcript"
    assert runner._browser_receipt(_encoded(value)) is None
    raw = _encoded(_browser_value()).replace(
        b'"contract":"packaged-analytics-browser-probe.v1"',
        b'"contract":"packaged-analytics-browser-probe.v1","contract":"forged"',
    )
    assert runner._browser_receipt(raw) is None
    assert runner._browser_receipt(b"diagnostic text\n") is None


@pytest.mark.parametrize("field", ["session_rows", "metric_response_events", "verified_category_responses", "external_requests"])
def test_browser_receipt_rejects_boolean_or_unbounded_count(field: str) -> None:
    value = _browser_value()
    value[field] = True
    assert runner._browser_receipt(_encoded(value)) is None
    value[field] = 101
    assert runner._browser_receipt(_encoded(value)) is None


def test_metric_lookup_preserves_unknown_distinct_from_zero() -> None:
    unknown = {
        "key": "usage.total_tokens", "numeric_value": None,
        "observed_count": 0, "eligible_count": 1, "coverage": 0,
    }
    zero = {**unknown, "numeric_value": 0, "observed_count": 1, "coverage": 1}
    assert runner._metric([unknown], "usage.total_tokens") is unknown
    assert runner._metric([zero], "usage.total_tokens") is zero
    assert unknown["numeric_value"] is None
    assert zero["numeric_value"] == 0
    assert runner._metric([unknown, zero], "usage.total_tokens") is None


def test_fixture_is_fictional_missing_usage_and_contains_untrusted_claim(tmp_path: Path) -> None:
    transcript, identity = runner._write_fixture(tmp_path)
    assert runner._fixture_matches(tmp_path, transcript, identity)
    rows = [json.loads(line) for line in runner._TRANSCRIPT.decode().splitlines()]
    assert len(rows) == 2
    assert all("usage" not in row["message"] for row in rows)
    assert "complete" in rows[1]["message"]["content"][0]["text"].lower()
    assert "C:\\example\\analytics" == rows[0]["cwd"]


def test_fixture_verifier_rejects_changed_content(tmp_path: Path) -> None:
    transcript, identity = runner._write_fixture(tmp_path)
    transcript.write_bytes(runner._TRANSCRIPT + b" ")
    assert not runner._fixture_matches(tmp_path, transcript, identity)


def test_browser_source_has_closed_read_only_route_boundary() -> None:
    source = (ROOT / "frontend" / "e2e" / "packaged-analytics-probe.mjs").read_text(
        encoding="utf-8"
    )
    assert '!["GET", "HEAD", "OPTIONS"].includes(request.method())' in source
    assert 'await route.abort("blockedbyclient")' in source
    assert 'page.goto(`${origin}/sessions`' in source
    assert 'page.locator("button.session-row")' in source
    assert "metrics\\/readiness" in source
    assert 'categoryUrl(page.url(), "model-usage")' in source
    assert 'categoryUrl(page.url(), "outcome")' in source
    assert "usage.total_tokens" in source
    assert "verification.verification_count" in source
    assert "verification.pass_rate" in source
    assert "page.screenshot" not in source
    assert "response.json()" not in source
    assert '["identity", "gzip"].includes(encoding)' in source
    assert "decodedLength >= 2 && decodedLength <= 65_536" in source
    assert "Provider Reported" in source
    assert "Eligible evidence exists, but no usable observations" in source
    assert "verificationCount.observed_count === 1" in source
    assert "passRate.observed_count === 0" in source


def test_runner_wires_sterile_fixture_and_owned_bounds() -> None:
    source = (SUPPORT / "packaged_analytics_runner.py").read_text(encoding="utf-8")
    assert 'environment["PROMPT_ENHANCER_CLAUDE_HOME"]' in source
    assert '"-I", "-B", "-m", "prompt_enhancer", "serve"' in source
    assert "maximum_active_processes=4" in source
    assert "maximum_active_processes=8" in source
    assert "timeout=90" in source
    assert "_verify_candidate(runtime, candidate, canonical)" in source
    assert source.count("_verify_candidate(runtime, candidate, canonical)") == 2
    assert "8765, 8766" in source


def test_candidate_ui_binding_requires_canonical_installed_resource_prefix() -> None:
    canonical = SimpleNamespace(files=(
        SimpleNamespace(relative_path="prompt_enhancer/_resources/dashboard/index.html"),
        SimpleNamespace(relative_path="prompt_enhancer/_resources/dashboard/assets/example.js"),
    ))
    root_only = SimpleNamespace(files=(
        SimpleNamespace(relative_path="index.html"),
        SimpleNamespace(relative_path="assets/example.js"),
    ))
    wrong_nested = SimpleNamespace(files=(
        SimpleNamespace(relative_path="example/_resources/dashboard/index.html"),
        SimpleNamespace(relative_path="example/_resources/dashboard/assets/example.js"),
    ))
    assert runner._candidate_ui_bound(canonical)
    assert not runner._candidate_ui_bound(root_only)
    assert not runner._candidate_ui_bound(wrong_nested)


def test_main_returns_closed_invalid_argument_receipt(capsys: pytest.CaptureFixture[str]) -> None:
    assert runner.main(["--unknown", "private-canary"]) == 1
    output = capsys.readouterr()
    assert output.err == ""
    assert "private-canary" not in output.out
    value = json.loads(output.out.removeprefix("PACKAGED_ANALYTICS_RUNNER="))
    assert value == {
        "contract": "packaged-analytics-runner.v1",
        "passed": False,
        "error_code": "invalid_arguments",
    }
