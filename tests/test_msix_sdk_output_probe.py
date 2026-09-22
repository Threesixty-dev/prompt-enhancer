from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from prompt_enhancer.application.owned_process import OwnedProcessResult


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests" / "support" / "msix_sdk_output_probe.py"
SPEC = importlib.util.spec_from_file_location("msix_sdk_output_probe", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PROBE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROBE
SPEC.loader.exec_module(PROBE)


def test_stdout_classifier_emits_counts_only() -> None:
    payload = (
        "Microsoft (R) MakeAppx Tool\r\n"
        "C:/synthetic/candidate/Synthetic01.txt\r\n"
        "unrecognized fixed-free line\r\n"
        "error 0x80000001\r\n"
    ).encode("utf-8")
    assert PROBE.classify_stdout(payload, ("C:/synthetic/candidate", "Synthetic01.txt")) == {
        "bytes": len(payload), "lines": 4, "fixed": 1,
        "known_path": 1, "error": 1, "unknown": 1,
    }


def test_error_with_known_filename_is_classified_as_error() -> None:
    payload = b"Error 0x80000001: Synthetic01.txt rejected\n"
    counts = PROBE.classify_stdout(payload, ("Synthetic01.txt",))
    assert counts["error"] == 1
    assert counts["known_path"] == 0


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"x" * (16 * 1024 + 1), "stdout_bounds_invalid"),
        (b"\xff", "stdout_encoding_invalid"),
        (("x" * 1025).encode(), "stdout_line_bounds_invalid"),
        (("x\n" * 513).encode(), "stdout_line_bounds_invalid"),
    ],
)
def test_stdout_classifier_refuses_bounds_and_binary_data(payload: bytes, code: str) -> None:
    with pytest.raises(PROBE.ProbeError, match=code):
        PROBE.classify_stdout(payload, ())


def test_classifier_budget_is_not_the_sdk_process_budget() -> None:
    assert PROBE.CLASSIFIER_LIMIT_BYTES == 16 * 1024
    receipt = PROBE._receipt((2,), passed=False, error_code="sdk_probe_failed")
    receipt.update({
        "observed_fixture_file_additions": [2], "sdk_exit_codes": [None],
        "owned_cleanup_confirmed": [None], "pack_error_codes": ["sdk_run_failed"],
        "owned_failure_codes": [None], "classifier_error_codes": [None],
        "packer_passed": [False], "sdk_stdout_limit_bytes": [64 * 1024],
    })
    PROBE._validate_receipt(receipt)


def test_two_tiny_candidates_keep_owned_limits_and_return_closed_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    main = tmp_path / "main.exe"
    metrics = tmp_path / "metrics.exe"
    main.write_bytes(b"synthetic-main")
    metrics.write_bytes(b"synthetic-metrics")
    monkeypatch.setattr(PROBE, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(PROBE, "HOME_ROOT", tmp_path / "reserved-home")
    monkeypatch.setattr(PROBE.PACK, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(PROBE.PACK, "HOME_ROOT", tmp_path / "reserved-home")
    observed_counts: list[int] = []
    derived_limits = {2: 8 * 1024, 6: 64 * 1024}

    def owned(command: list[str], **kwargs: object) -> OwnedProcessResult:
        assert kwargs["timeout"] == 120
        assert kwargs["maximum_active_processes"] == 1
        assert kwargs["stdout_limit"] in derived_limits.values()
        assert kwargs["stderr_limit"] == 16 * 1024
        return OwnedProcessResult(returncode=0, stdout=b"Microsoft (R) MakeAppx Tool\nunknown\n", stderr=b"")

    def packer(**kwargs: object) -> dict[str, object]:
        candidate = Path(kwargs["candidate_root"])
        observed_counts.append(len(tuple((candidate / "Diagnostic").glob("*.txt"))))
        limit = derived_limits[observed_counts[-1]]
        kwargs["runner"](["synthetic-sdk"], cwd=Path(kwargs["output_root"]), env={}, timeout=120,
                         maximum_active_processes=1, stdout_limit=limit, stderr_limit=16 * 1024)
        return {"passed": True}

    receipt = PROBE.run_probe(
        artifact_root=str(external.resolve()),
        main_launcher=str(main.resolve()), main_sha256=hashlib.sha256(main.read_bytes()).hexdigest(),
        main_size=main.stat().st_size, metrics_launcher=str(metrics.resolve()),
        metrics_sha256=hashlib.sha256(metrics.read_bytes()).hexdigest(), metrics_size=metrics.stat().st_size,
        packer=packer, owned_runner=owned,
    )
    assert observed_counts == [2, 6]
    assert receipt["passed"] is True
    assert receipt["classifier_limit_bytes"] == 16 * 1024
    assert receipt["sdk_stdout_limit_bytes"] == [8 * 1024, 64 * 1024]
    assert receipt["stdout_lines"] == [2, 2]
    assert receipt["fixed_lines"] == [1, 1]
    assert receipt["unknown_lines"] == [1, 1]
    assert receipt["sdk_exit_codes"] == [0, 0]
    assert receipt["observed_fixture_file_additions"] == [2, 6]
    assert receipt["pack_error_codes"] == [None, None]
    assert receipt["owned_failure_codes"] == [None, None]
    assert receipt["classifier_error_codes"] == [None, None]
    assert receipt["packer_passed"] == [True, True]
    assert receipt["diagnostic_only"] is True
    assert receipt["signed"] is False and receipt["installed"] is False
    persisted = list(external.glob(f"msix-sdk-output-*/{PROBE.RECEIPT_FILENAME}"))
    assert len(persisted) == 1
    assert json.loads(persisted[0].read_text(encoding="ascii")) == receipt


def test_single_fixture_selection_runs_only_requested_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    launcher = tmp_path / "launcher.exe"
    launcher.write_bytes(b"synthetic")
    monkeypatch.setattr(PROBE, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(PROBE, "HOME_ROOT", tmp_path / "reserved-home")
    observed: list[int] = []

    def packer(**kwargs: object) -> dict[str, object]:
        candidate = Path(kwargs["candidate_root"])
        observed.append(len(tuple((candidate / "Diagnostic").glob("*.txt"))))
        kwargs["runner"](["synthetic-sdk"], cwd=Path(kwargs["output_root"]), env={}, timeout=120,
                         maximum_active_processes=1, stdout_limit=16 * 1024, stderr_limit=16 * 1024)
        return {"passed": True}

    receipt = PROBE.run_probe(
        artifact_root=str(external.resolve()),
        main_launcher=str(launcher.resolve()),
        main_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
        main_size=launcher.stat().st_size,
        metrics_launcher=str(launcher.resolve()),
        metrics_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
        metrics_size=launcher.stat().st_size,
        fixture_counts=(6,), packer=packer,
        owned_runner=lambda *args, **kwargs: OwnedProcessResult(
            returncode=0, stdout=b"Microsoft (R) MakeAppx Tool\n", stderr=b""
        ),
    )
    assert observed == [6]
    assert receipt["fixture_file_additions"] == [6]
    assert receipt["observed_fixture_file_additions"] == [6]
    assert receipt["sdk_exit_codes"] == [0]
    assert receipt["sdk_stdout_limit_bytes"] == [16 * 1024]


@pytest.mark.parametrize("selection", [(), (2, 2), (6, 2), (4,), (2, 6, 2)])
def test_invalid_fixture_selection_is_refused(selection: tuple[int, ...]) -> None:
    with pytest.raises(PROBE.ProbeError, match="invalid_fixture_selection"):
        PROBE.run_probe(
            artifact_root="unused", main_launcher="unused", main_sha256="0" * 64,
            main_size=1, metrics_launcher="unused", metrics_sha256="0" * 64,
            metrics_size=1, fixture_counts=selection,
            packer=lambda **kwargs: pytest.fail("packer must not run"),
        )


def test_launcher_hash_mismatch_prevents_packer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    external = tmp_path / "external"
    external.mkdir()
    launcher = tmp_path / "launcher.exe"
    launcher.write_bytes(b"synthetic")
    monkeypatch.setattr(PROBE, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(PROBE, "HOME_ROOT", tmp_path / "reserved-home")
    with pytest.raises(PROBE.ProbeError, match="launcher_identity_mismatch"):
        PROBE.run_probe(
            artifact_root=str(external.resolve()),
            main_launcher=str(launcher.resolve()), main_sha256="0" * 64,
            main_size=launcher.stat().st_size, metrics_launcher=str(launcher.resolve()),
            metrics_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
            metrics_size=launcher.stat().st_size,
            packer=lambda **kwargs: pytest.fail("packer must not run"),
        )


def test_sdk_nonzero_preserves_only_closed_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    launcher = tmp_path / "launcher.exe"
    launcher.write_bytes(b"synthetic")
    monkeypatch.setattr(PROBE, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(PROBE, "HOME_ROOT", tmp_path / "reserved-home")

    def packer(**kwargs: object) -> dict[str, object]:
        kwargs["runner"](["synthetic-sdk"], cwd=Path(kwargs["output_root"]), env={}, timeout=120,
                         maximum_active_processes=1, stdout_limit=16 * 1024, stderr_limit=16 * 1024)
        raise PROBE.PACK.PackError(
            "sdk_pack_failed", stage="sdk", owned_cleanup_confirmed=True,
            sdk_exit_code=5,
        )

    def owned(*args: object, **kwargs: object) -> OwnedProcessResult:
        return OwnedProcessResult(returncode=5, stdout=b"error 0x80000001\n", stderr=b"")

    with pytest.raises(PROBE.ProbeError, match="sdk_nonzero") as raised:
        PROBE.run_probe(
            artifact_root=str(external.resolve()),
            main_launcher=str(launcher.resolve()),
            main_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
            main_size=launcher.stat().st_size,
            metrics_launcher=str(launcher.resolve()),
            metrics_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
            metrics_size=launcher.stat().st_size,
            packer=packer, owned_runner=owned,
        )
    assert raised.value.details == {
        "stdout_bytes": [17], "stdout_lines": [1], "fixed_lines": [0],
        "known_path_lines": [0], "error_lines": [1], "unknown_lines": [0],
        "sdk_exit_codes": [5], "owned_cleanup_confirmed": [True],
        "observed_fixture_file_additions": [2],
        "pack_error_codes": ["sdk_pack_failed"],
        "owned_failure_codes": [None], "classifier_error_codes": [None],
        "packer_passed": [False], "sdk_stdout_limit_bytes": [16 * 1024],
    }


def test_post_pack_failure_preserves_sdk_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    launcher = tmp_path / "launcher.exe"
    launcher.write_bytes(b"synthetic")
    monkeypatch.setattr(PROBE, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(PROBE, "HOME_ROOT", tmp_path / "reserved-home")

    def packer(**kwargs: object) -> dict[str, object]:
        kwargs["runner"](["synthetic-sdk"], cwd=Path(kwargs["output_root"]), env={}, timeout=120,
                         maximum_active_processes=1, stdout_limit=16 * 1024, stderr_limit=16 * 1024)
        raise PROBE.PACK.PackError(
            "package_coverage_mismatch", stage="post_pack",
            owned_cleanup_confirmed=True, sdk_exit_code=0,
        )

    with pytest.raises(PROBE.ProbeError, match="sdk_probe_failed") as raised:
        PROBE.run_probe(
            artifact_root=str(external.resolve()),
            main_launcher=str(launcher.resolve()),
            main_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
            main_size=launcher.stat().st_size,
            metrics_launcher=str(launcher.resolve()),
            metrics_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
            metrics_size=launcher.stat().st_size,
            packer=packer,
            owned_runner=lambda *args, **kwargs: OwnedProcessResult(
                returncode=0, stdout=b"Successfully created package\n", stderr=b""
            ),
        )
    assert raised.value.details["stdout_lines"] == [1]
    assert raised.value.details["sdk_exit_codes"] == [0]
    assert raised.value.details["owned_cleanup_confirmed"] == [True]
    assert raised.value.details["pack_error_codes"] == ["package_coverage_mismatch"]
    assert raised.value.details["packer_passed"] == [False]
    assert raised.value.details["sdk_stdout_limit_bytes"] == [16 * 1024]
    persisted = list(external.glob(f"msix-sdk-output-*/{PROBE.RECEIPT_FILENAME}"))
    assert len(persisted) == 1
    stored = json.loads(persisted[0].read_text(encoding="ascii"))
    assert stored["passed"] is False
    assert stored["error_code"] == "sdk_probe_failed"
    assert stored["stdout_lines"] == [1]
    assert stored["pack_error_codes"] == ["package_coverage_mismatch"]


def test_pre_execution_failure_records_unknown_sdk_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external = tmp_path / "external"; external.mkdir()
    launcher = tmp_path / "launcher.exe"; launcher.write_bytes(b"synthetic")
    monkeypatch.setattr(PROBE, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(PROBE, "HOME_ROOT", tmp_path / "reserved-home")

    def packer(**_kwargs: object) -> dict[str, object]:
        raise PROBE.PACK.PackError("candidate_verification_failed", stage="preflight")

    with pytest.raises(PROBE.ProbeError) as raised:
        PROBE.run_probe(
            artifact_root=str(external.resolve()), main_launcher=str(launcher.resolve()),
            main_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
            main_size=launcher.stat().st_size, metrics_launcher=str(launcher.resolve()),
            metrics_sha256=hashlib.sha256(launcher.read_bytes()).hexdigest(),
            metrics_size=launcher.stat().st_size, fixture_counts=(2,), packer=packer,
        )
    assert raised.value.details["sdk_stdout_limit_bytes"] == [None]
    assert raised.value.details["sdk_exit_codes"] == [None]


@pytest.mark.parametrize("code", (
    "sdk_stdout_bounds_invalid", "sdk_stdout_encoding_invalid", "sdk_stdout_truncated",
    "sdk_stdout_unknown", "sdk_stdout_duplicate", "sdk_stdout_incomplete",
))
def test_closed_packer_stdout_failures_are_schema_allowed(code: str) -> None:
    receipt = PROBE._receipt((2,), passed=False, error_code="sdk_probe_failed")
    receipt.update({
        "observed_fixture_file_additions": [2], "sdk_exit_codes": [0],
        "owned_cleanup_confirmed": [True], "pack_error_codes": [code],
        "owned_failure_codes": [None], "classifier_error_codes": [None],
        "packer_passed": [False], "sdk_stdout_limit_bytes": [32 * 1024],
    })
    PROBE._validate_receipt(receipt)


def test_persisted_receipt_is_exclusive_and_rejects_non_schema_content(
    tmp_path: Path
) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    receipt = PROBE._receipt((6,), passed=False, error_code="sdk_probe_failed")
    PROBE._persist_receipt(fixture, receipt)
    with pytest.raises(PROBE.ProbeError, match="receipt_persist_failed"):
        PROBE._persist_receipt(fixture, receipt)
    forged = dict(receipt)
    forged["private_path"] = "C:/private/example"
    with pytest.raises(PROBE.ProbeError, match="receipt_schema_invalid"):
        PROBE._persist_receipt(tmp_path / "unused", forged)


def test_cli_argument_failure_is_content_free(capsys: pytest.CaptureFixture[str]) -> None:
    private = "PRIVATE_ARGUMENT_CANARY"
    assert PROBE.main(["--unknown", private]) == 1
    captured = capsys.readouterr()
    assert private not in captured.out and captured.err == ""
    receipt = json.loads(captured.out.removeprefix("MSIX_SDK_OUTPUT_PROBE="))
    assert receipt["passed"] is False
    assert receipt["error_code"] == "invalid_arguments"
